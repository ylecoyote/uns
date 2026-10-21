"""Exact, self-contained reproductions for F-01 through F-08 against commit 3f6005f."""

from __future__ import annotations

import asyncio
import smtplib
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import event, select, update

from agsignal.responses import SendNotificationRequest
from agsignal_mcp import tools as mcp_tools
from agsignal_mcp.runtime import RuntimeState
from notification.adapters.base import (
    AdapterStatus,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
    guard_provider_attempt,
)
from notification.adapters.email import EmailAdapter, EmailConfig
from notification.models import Channel
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.rate_limiting import RateLimitConfig, configure_rate_limiter
from notification.service import SimpleAdapterRegistry
from uns.maintenance import maintain
from uns.runtime import Conflict, Runtime, events as events_table, work


class RecordingAdapter(BaseAdapter):
    def __init__(self, channel: Channel = Channel.SLACK, success: bool = True, effect=None):
        self._channel = channel
        self.success = success
        self.effect = effect
        self.calls: list[str] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification):
        if self.effect is not None:
            await self.effect(notification)
        self.calls.append(str(notification.notification_id))
        return DeliveryResult(success=self.success, channel=self.channel)

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(AdapterStatus.HEALTHY, "recording adapter")


def make_request(key: str = "one", dedup_key: str = "same-alarm", **changes) -> SendNotificationRequest:
    payload = {
        "notification_type": "test.remediation",
        "intent": "SAFETY",
        "title": "Alarm",
        "message": "Alarm",
        "source": "reproduction",
        "autonomy_context": {
            "agent_id": "00000000-0000-0000-0000-000000000001",
            "autonomy_mode": "LIVE",
        },
        "idempotency_key": key,
        "dedup_key": dedup_key,
    }
    payload.update(changes)
    return SendNotificationRequest(**payload)


@pytest.fixture
def env(tmp_path: Path):
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    now = [1000.0]
    adapter = RecordingAdapter(Channel.SLACK, success=True)
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    url = f"sqlite:///{tmp_path}/repro.db"
    runtime = Runtime(
        url,
        create_tables=True,
        adapters=registry,
        clock=lambda: now[0],
        max_attempts=1,
    )
    return runtime, adapter, registry, now, url


# ---------------------------------------------------------------------------
# F-01: Dedup window expiry + stale owner failure promotes superseded follower
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f01_stale_window_owner_failure_promotes_follower_after_new_owner_delivered(env):
    runtime, adapter, _, now, _ = env
    owner1 = runtime.accept(make_request("k1"), principal="producer")
    now[0] = 1010.0
    follower1 = runtime.accept(make_request("k2"), principal="producer")

    # Default dedup window (1300.0) expires while owner1 is still pending; owner2 arrives and delivers
    now[0] = 1301.0
    owner2 = runtime.accept(make_request("k3"), principal="producer")
    adapter.success = True
    assert await runtime.dispatch(owner2.notification_id) is True
    assert runtime.get(owner2.notification_id)["status"] == "DELIVERED"

    # Now owner1 fails; _settle_followers overwrites uns_dedup and promotes follower1
    adapter.success = False
    await runtime.dispatch(owner1.notification_id)
    assert runtime.get(owner1.notification_id)["status"] == "FAILED"
    adapter.success = True
    await runtime.dispatch(follower1.notification_id)

    # Contract assertion: follower1 should not deliver after owner2 already delivered in the new window
    assert runtime.get(follower1.notification_id)["status"] == "DEDUPLICATED"
    assert adapter.calls == [str(owner2.notification_id), str(owner1.notification_id)]


# ---------------------------------------------------------------------------
# F-02: Manual replay() ignores promoted follower that already delivered
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f02_replay_after_follower_promoted_and_delivered_causes_duplicate_send(env):
    runtime, adapter, _, _, _ = env
    n_a = runtime.accept(make_request("ra", dedup_key="replay-key"), principal="producer")
    n_b = runtime.accept(make_request("rb", dedup_key="replay-key"), principal="producer")

    # Initial owner n_a fails -> follower n_b is promoted and delivers
    adapter.success = False
    await runtime.dispatch(n_a.notification_id)
    assert runtime.get(n_a.notification_id)["status"] == "FAILED"
    adapter.success = True
    await runtime.dispatch(n_b.notification_id)
    assert runtime.get(n_b.notification_id)["status"] == "DELIVERED"

    # Replaying dead-lettered n_a succeeds and dispatches a duplicate provider send
    runtime.replay(n_a.notification_id, actor="operator")
    await runtime.dispatch(n_a.notification_id)

    assert len(adapter.calls) == 2  # Expected: 1 failed (n_a) + 1 delivered (n_b), no 2nd delivered send


# ---------------------------------------------------------------------------
# F-03: Multi-channel DeliveryLeaseLostError discards completed channel outcome
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f03_best_effort_lease_loss_discards_completed_channel_outcome(env):
    runtime, _, _, _, _ = env
    slack = RecordingAdapter(Channel.SLACK, success=True)

    class LateGuardEmail(BaseAdapter):
        guards_provider_attempts = True

        @property
        def channel(self) -> Channel:
            return Channel.EMAIL

        async def deliver(self, notification):
            await asyncio.sleep(0.02)
            with runtime.engine.begin() as conn:
                conn.execute(
                    update(work)
                    .where(work.c.id == str(notification.notification_id))
                    .values(lease_token="other-worker-token")
                )
            guard_provider_attempt(self.channel)
            return DeliveryResult(success=True, channel=self.channel)

        async def health_check(self) -> HealthCheckResult:
            return HealthCheckResult(AdapterStatus.HEALTHY, "ok")

    runtime.adapters.register(slack)
    runtime.adapters.register(LateGuardEmail())
    accepted = runtime.accept(make_request("be1", dedup_key="be-key"), principal="producer")
    notif = runtime.get(accepted.notification_id)["notification"]
    notif.update(channels=["SLACK", "EMAIL"], delivery_mode="BEST_EFFORT")
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(accepted.notification_id))
            .values(notification=notif)
        )

    await runtime.dispatch(accepted.notification_id)
    row = runtime.get(accepted.notification_id)
    assert len(slack.calls) == 1
    assert "SLACK" in row["outcome"]["channels_succeeded"]


# ---------------------------------------------------------------------------
# F-04a: EmailAdapter._send_email_sync emits duplicate CHANNEL_ATTEMPT_STARTED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f04a_email_adapter_single_send_emits_duplicate_channel_attempt_started(env, monkeypatch):
    runtime, _, _, _, _ = env

    class DummySMTP:
        def __init__(self, *args, **kwargs):
            pass

        def sendmail(self, *args, **kwargs):
            return {}

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", DummySMTP)
    runtime.adapters.register(
        EmailAdapter(
            EmailConfig(
                "test.invalid",
                25,
                "",
                "",
                "from@example.invalid",
                ["to@example.invalid"],
                use_tls=False,
            )
        )
    )
    accepted = runtime.accept(make_request("em1", dedup_key="em-key"), principal="producer")
    notif = runtime.get(accepted.notification_id)["notification"]
    notif.update(channels=["EMAIL"])
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(accepted.notification_id))
            .values(notification=notif)
        )

    assert await runtime.dispatch(accepted.notification_id) is True
    kinds = [e["kind"] for e in runtime.events(accepted.notification_id)]
    assert kinds.count("CHANNEL_ATTEMPT_STARTED") == 1


# ---------------------------------------------------------------------------
# F-04b: Slow SMTP thread completes sendmail after adapter_timeout_seconds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f04b_slow_smtp_executor_thread_completes_sendmail_after_adapter_timeout(env, monkeypatch):
    runtime, slack_adapter, _, _, _ = env
    runtime.delivery.adapter_timeout_seconds = 0.05  # Fast reproduction of the 10s wait_for vs 30s SMTP timeout
    sendmail_completed_at: list[float] = []
    done_event = threading.Event()

    class SlowSendmailSMTP:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        def sendmail(self, *args, **kwargs):
            # Passes guard_provider_attempt before adapter_timeout_seconds (0.05s),
            # then blocks inside sendmail for 0.12s (within EmailConfig.timeout_seconds=30.0s).
            time.sleep(0.12)
            sendmail_completed_at.append(time.monotonic())
            done_event.set()
            return {}

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", SlowSendmailSMTP)
    runtime.adapters.register(
        EmailAdapter(
            EmailConfig(
                "test.invalid",
                25,
                "",
                "",
                "from@example.invalid",
                ["to@example.invalid"],
                use_tls=False,
                retry_attempts=1,
            )
        )
    )
    pagerduty = RecordingAdapter(Channel.PAGERDUTY, success=True)
    runtime.adapters.register(pagerduty)

    accepted = runtime.accept(make_request("em-slow", dedup_key="em-slow-key"), principal="producer")
    notif = runtime.get(accepted.notification_id)["notification"]
    # GUARANTEED fallback order: EMAIL -> PAGERDUTY
    notif.update(channels=["EMAIL", "PAGERDUTY"], delivery_mode="GUARANTEED")
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(accepted.notification_id))
            .values(notification=notif)
        )

    assert await runtime.dispatch(accepted.notification_id) is True
    assert done_event.wait(timeout=1.0) is True

    row = runtime.get(accepted.notification_id)
    # PAGERDUTY fallback delivered because EMAIL timed out at 0.05s,
    # YET the background SMTP thread still completed sendmail at ~0.12s!
    assert row["outcome"]["channels_succeeded"] == ["PAGERDUTY"]
    assert "EMAIL" in row["outcome"]["channels_failed"]
    assert sendmail_completed_at == []  # Fails: sendmail completed after dispatch finished!


# ---------------------------------------------------------------------------
# F-05: Read-only PolicyStore.load_snapshot() executes SQL UPDATE write lock
# ---------------------------------------------------------------------------
def test_f05_read_only_policy_registry_executes_unconditional_sql_update(tmp_path: Path):
    runtime = Runtime(f"sqlite:///{tmp_path}/policy_lock.db", create_tables=True)
    statements: list[str] = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip())

    event.listen(runtime.engine, "before_cursor_execute", capture_sql)
    runtime.policy_runtime.registry()  # Read-only lookup used by /ready and simulate_signal
    update_statements = [s for s in statements if s.upper().startswith("UPDATE")]
    assert update_statements == []


# ---------------------------------------------------------------------------
# F-06a: Queue ordering failure in deliver_callbacks() (new callback_until=0.0
# preempts overdue retried callback with callback_until=1002.0, while SQLite
# index scans incidentally order expire() and run_once() despite no ORDER BY)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f06a_deliver_callbacks_orders_new_zero_until_ahead_of_overdue_retry(tmp_path: Path):
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({Channel.SLACK: RateLimitConfig(tokens_per_second=10_000.0, bucket_size=10_000)})
    now = [1000.0]
    delivered_event_ids: list[str] = []
    fail_first = [True]

    async def callback_handler(event_row: dict):
        if fail_first[0]:
            fail_first[0] = False
            raise RuntimeError("transient callback error")
        delivered_event_ids.append(event_row["id"])

    registry = SimpleAdapterRegistry()
    registry.register(RecordingAdapter(Channel.WEBSOCKET, success=True))
    registry.register(RecordingAdapter(Channel.SLACK, success=True))
    runtime = Runtime(
        f"sqlite:///{tmp_path}/cb_order.db",
        create_tables=True,
        adapters=registry,
        clock=lambda: now[0],
        callback=callback_handler,
        max_attempts=1,
    )

    # 1. Create an early notification at t=1000.0, ACK it, and fail its first callback attempt
    #    so its callback_until becomes 1002.0 (due at t=1002.0).
    early = runtime.accept(make_request("early-0", dedup_key="early-d-0", require_ack=True), principal="producer")
    await runtime.dispatch(early.notification_id)
    runtime.acknowledge(early.notification_id, actor="operator")
    early_event_id = [e["id"] for e in runtime.events(early.notification_id) if e["kind"] == "ACKED"][0]
    await runtime.deliver_callbacks()  # Fails attempt 1 -> sets callback_until = 1002.0

    # 2. At t=2000.0 (998s after early_event_id's retry became due at 1002.0),
    #    100 brand-new notifications are ACKed. Because _event() leaves callback_until=0.0,
    #    all 100 brand-new events have callback_until=0.0 < 1002.0!
    now[0] = 2000.0
    for i in range(100):
        res = runtime.accept(make_request(f"new-{i}", dedup_key=f"new-d-{i}", require_ack=True), principal="producer")
        await runtime.dispatch(res.notification_id)
        runtime.acknowledge(res.notification_id, actor="operator")

    await runtime.deliver_callbacks()
    # The overdue callback from t=1000.0 (due at 1002.0) should be delivered before brand-new t=2000.0 callbacks
    assert early_event_id in delivered_event_ids


# ---------------------------------------------------------------------------
# F-06b: Demonstrated multi-tick starvation of overdue retry callback when
# 100 fresh callbacks arrive per tick (callback_until=0.0 < 1002.0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f06b_deliver_callbacks_starves_overdue_retry_across_ticks_under_fresh_arrivals(tmp_path: Path):
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({Channel.SLACK: RateLimitConfig(tokens_per_second=10_000.0, bucket_size=10_000)})
    now = [1000.0]
    delivered_event_ids: list[str] = []
    fail_first = [True]

    async def callback_handler(event_row: dict):
        if fail_first[0]:
            fail_first[0] = False
            raise RuntimeError("transient callback error")
        delivered_event_ids.append(event_row["id"])

    registry = SimpleAdapterRegistry()
    registry.register(RecordingAdapter(Channel.SLACK, success=True))
    runtime = Runtime(
        f"sqlite:///{tmp_path}/cb_starve.db",
        create_tables=True,
        adapters=registry,
        clock=lambda: now[0],
        callback=callback_handler,
        max_attempts=1,
    )

    early = runtime.accept(make_request("early-s", dedup_key="early-ds", require_ack=True), principal="producer")
    await runtime.dispatch(early.notification_id)
    runtime.acknowledge(early.notification_id, actor="operator")
    early_event_id = [e["id"] for e in runtime.events(early.notification_id) if e["kind"] == "ACKED"][0]
    await runtime.deliver_callbacks()  # Fails attempt 1 -> callback_until = 1002.0

    # Across 3 consecutive ticks at t=2000, 2001, 2002, 100 fresh callbacks arrive each tick.
    # Because fresh callbacks have callback_until=0.0, early_event_id (callback_until=1002.0)
    # is starved across all 3 ticks (300 callbacks delivered, 0 for early_event_id).
    for tick in range(3):
        now[0] = 2000.0 + tick
        for i in range(100):
            idx = f"{tick}-{i}"
            res = runtime.accept(make_request(f"wave-{idx}", dedup_key=f"wave-d-{idx}", require_ack=True), principal="producer")
            await runtime.dispatch(res.notification_id)
            runtime.acknowledge(res.notification_id, actor="operator")
        await runtime.deliver_callbacks()

    assert len(delivered_event_ids) == 300
    assert early_event_id in delivered_event_ids


# ---------------------------------------------------------------------------
# F-07: Direct agsignal_mcp.tools functions and RuntimeState(runtime=...) ignore Runtime
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f07_direct_mcp_tools_and_runtime_state_ignore_durable_runtime(env):
    runtime, adapter, _, _, _ = env
    adapter.success = False
    accepted = runtime.accept(make_request("mcp-1", dedup_key="mcp-key"), principal="producer")
    await runtime.dispatch(accepted.notification_id)

    state = RuntimeState(runtime=runtime)
    delivery_status = mcp_tools.get_delivery_status(str(accepted.notification_id), runtime_state=state)
    dlq = mcp_tools.list_dlq(runtime_state=state)
    notif_status = await mcp_tools.get_notification_status(str(accepted.notification_id))

    assert runtime.get(accepted.notification_id)["status"] == "FAILED"
    assert len(runtime.dead_letters()) == 1
    assert delivery_status["found"] is True
    assert dlq["depth"] == 1
    assert notif_status["ack_status"] is not None


# ---------------------------------------------------------------------------
# F-08a: Non-archive maintain(archive=None) embeds full deleted rows into uns_events
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f08a_non_archive_retention_embeds_full_deleted_rows_in_unprunable_event(tmp_path: Path):
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    t0 = time.time()
    registry = SimpleAdapterRegistry()
    registry.register(RecordingAdapter(Channel.WEBSOCKET, success=True))
    runtime = Runtime(
        f"sqlite:///{tmp_path}/ret_bloat.db",
        create_tables=True,
        adapters=registry,
        clock=lambda: t0,
        max_attempts=1,
    )
    accepted = runtime.accept(
        make_request("ret-bloat-1", dedup_key="ret-bloat-key", intent="INFORMATIONAL"),
        principal="producer",
    )
    await runtime.dispatch(accepted.notification_id)

    report = maintain(
        runtime.engine,
        cutoff=t0 + 500.0,
        idempotency_seconds=60.0,
        apply=True,
        operator="ops",
        archive=None,
        now=t0 + 1000.0,
    )
    assert report["deleted_rows"] == 2  # 1 uns_notifications + 1 uns_dedup

    with runtime.engine.begin() as conn:
        receipt = (
            conn.execute(select(events_table).where(events_table.c.kind == "RETENTION_APPLIED"))
            .mappings()
            .one()
        )
    # The full deleted uns_notifications row (including request payload) is copied into uns_events.payload["removed"]
    assert "removed" not in receipt["payload"]


# ---------------------------------------------------------------------------
# F-08b: Runtime._audit stamps wall-clock created_at instead of Runtime.clock()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f08b_retention_blocks_pruning_under_synthetic_runtime_clock(env):
    runtime, _, _, now, _ = env
    runtime.adapters.register(RecordingAdapter(Channel.WEBSOCKET, success=True))
    accepted = runtime.accept(
        make_request("ret-clock-1", dedup_key="ret-clock-key", intent="INFORMATIONAL"),
        principal="producer",
    )
    await runtime.dispatch(accepted.notification_id)

    # Synthetic clock is at 1000.0; advance synthetic clock to 10000.0 with cutoff=5000.0
    now[0] = 10000.0
    report = maintain(
        runtime.engine,
        cutoff=5000.0,
        idempotency_seconds=60.0,
        apply=True,
        operator="ops",
        archive=None,
        now=10000.0,
    )
    assert report["deleted_rows"] >= 1

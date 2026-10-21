"""State-machine regression schedules, including a real provider-effect crash."""

import asyncio
import contextlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select, update

from agsignal.responses import SendNotificationRequest
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel, DeliveryStatus
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.rate_limiting import configure_rate_limiter
from notification.service import SimpleAdapterRegistry
from uns.runtime import Conflict, Runtime, dedup, work


class Adapter(BaseAdapter):
    def __init__(self, channel=Channel.SLACK, success=True, effect=None):
        self._channel, self.success, self.effect = channel, success, effect
        self.calls = []

    @property
    def channel(self):
        return self._channel

    async def deliver(self, notification):
        self.calls.append(str(notification.notification_id))
        if self.effect:
            await self.effect(notification)
        return DeliveryResult(success=self.success, channel=self.channel)

    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY, "recording adapter")


def request(key="one", **changes):
    payload = {
        "notification_type": "test.remediation",
        "intent": "SAFETY",
        "title": "Alarm",
        "message": "Alarm",
        "source": "regression",
        "autonomy_context": {
            "agent_id": "00000000-0000-0000-0000-000000000001",
            "autonomy_mode": "LIVE",
        },
        "idempotency_key": key,
        "dedup_key": "same-alarm",
    }
    payload.update(changes)
    return SendNotificationRequest(**payload)


@pytest.fixture
def state(tmp_path):
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    now = [1000.0]
    adapter = Adapter()
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    url = f"sqlite:///{tmp_path}/delivery.db"
    runtime = Runtime(
        url, create_tables=True, adapters=registry, clock=lambda: now[0], max_attempts=1
    )
    return runtime, adapter, registry, now, url


@pytest.mark.asyncio
async def test_failed_owner_does_not_suppress_new_alarm(state):
    runtime, adapter, _, _, _ = state
    adapter.success = False
    first = await runtime.send(request(), principal="producer")
    assert first.status == DeliveryStatus.FAILED
    adapter.success = True
    second = await runtime.send(request("two"), principal="producer")
    assert second.status == DeliveryStatus.DELIVERED
    assert len(adapter.calls) == 2


@pytest.mark.asyncio
async def test_pending_followers_elect_one_successor_after_owner_failure(state):
    runtime, adapter, _, _, _ = state
    first = runtime.accept(request(), principal="producer")
    followers = [runtime.accept(request(str(i)), principal="producer") for i in range(2, 5)]
    assert all(f.status == DeliveryStatus.PENDING for f in followers)
    for follower in followers:
        row = runtime.get(follower.notification_id)
        assert row["dedup_owner_id"] == str(first.notification_id)
        assert not await runtime.dispatch(follower.notification_id)
    adapter.success = False
    await runtime.dispatch(first.notification_id)
    rows = [runtime.get(f.notification_id) for f in followers]
    successors = [row for row in rows if row["dedup_owner_id"] is None]
    assert len(successors) == 1
    successor = successors[0]
    assert all(row["dedup_owner_id"] == successor["id"] for row in rows if row != successor)
    adapter.success = True
    await runtime.run_once()
    assert len(adapter.calls) == 2
    assert runtime.get(successor["id"])["status"] == "DELIVERED"
    assert all(
        runtime.get(row["id"])["status"] == "DEDUPLICATED" for row in rows if row != successor
    )
    assert any(e["kind"] == "DEDUP_OWNER_PROMOTED" for e in runtime.events(successor["id"]))


@pytest.mark.asyncio
async def test_old_owner_failure_cannot_replace_new_window_owner(state):
    runtime, adapter, _, now, _ = state
    first = runtime.accept(request(), principal="producer")
    follower = runtime.accept(request("two"), principal="producer")
    now[0] += 100000
    newer = runtime.accept(request("three"), principal="producer")
    adapter.success = False
    await runtime.dispatch(first.notification_id)
    with runtime.sessions() as session:
        claim = session.execute(select(dedup)).mappings().one()
    assert claim["owner_id"] == str(newer.notification_id)
    assert runtime.get(follower.notification_id)["dedup_owner_id"] is None


@pytest.mark.asyncio
async def test_replay_has_fresh_budget_with_immutable_cumulative_history(state):
    runtime, adapter, _, _, _ = state
    adapter.success = False
    first = await runtime.send(request(), principal="producer")
    before = runtime.events(first.notification_id)
    runtime.replay(first.notification_id, actor="operator")
    adapter.success = True
    await runtime.dispatch(first.notification_id)
    row = runtime.get(first.notification_id)
    assert row["status"] == "DELIVERED"
    assert row["attempts"] == 2 and row["cycle"] == 2 and row["cycle_attempts"] == 1
    assert runtime.events(first.notification_id)[: len(before)] == before
    assert len(adapter.calls) == 2
    results = [
        e["payload"]
        for e in runtime.events(first.notification_id)
        if e["kind"] == "DELIVERY_RESULT"
    ]
    assert [(r["cycle"], r["cycle_attempt"]) for r in results] == [(1, 1), (2, 1)]


@pytest.mark.asyncio
async def test_cross_actor_terminal_replay_conflicts_but_same_actor_is_idempotent(state):
    runtime, _, _, _, _ = state
    first = await runtime.send(request(), principal="producer")
    acknowledged = runtime.acknowledge(first.notification_id, actor="alice")
    assert runtime.acknowledge(first.notification_id, actor="alice") == acknowledged
    with pytest.raises(Conflict, match="actor|another"):
        runtime.acknowledge(first.notification_id, actor="bob")
    assert len(runtime.audit_store.get_ack_audits_for_notification(first.notification_id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("takeover", [False, True])
async def test_expired_worker_never_calls_external_fallback(state, takeover):
    runtime, slack, _, now, url = state
    email = Adapter(Channel.EMAIL)
    runtime.adapters.register(email)
    first = runtime.accept(request(), principal="producer")
    notification = runtime.get(first.notification_id)["notification"]
    notification["channels"] = ["SLACK", "EMAIL"]
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(first.notification_id))
            .values(notification=notification)
        )
    second_registry = SimpleAdapterRegistry()
    second_email = Adapter(Channel.EMAIL)
    second_registry.register(second_email)
    second = Runtime(url, adapters=second_registry, clock=lambda: now[0], max_attempts=3)

    async def lose_lease(notification):
        now[0] += runtime.lease_seconds + 1
        if takeover:
            await second.dispatch(notification.notification_id)

    slack.success, slack.effect = False, lose_lease
    assert not await runtime.dispatch(first.notification_id)
    assert not email.calls
    assert len(second_email.calls) == int(takeover)
    if not takeover:
        assert runtime.get(first.notification_id)["status"] == "PENDING"
    assert any(e["kind"] == "LEASE_LOST" for e in runtime.events(first.notification_id))


@pytest.mark.asyncio
async def test_blocked_callback_does_not_delay_timeout_worker(state):
    runtime, _, _, now, _ = state
    entered, release = asyncio.Event(), asyncio.Event()

    async def callback(event):
        entered.set()
        await release.wait()

    runtime.callback = callback
    first = await runtime.send(request(), principal="producer")
    runtime.acknowledge(first.notification_id, actor="alice")
    blocked = await runtime.send(request("two", dedup_key="callback-two"), principal="producer")
    runtime.acknowledge(blocked.notification_id, actor="alice")
    second = await runtime.send(request("three", dedup_key="different"), principal="producer")
    worker = asyncio.create_task(runtime.worker())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        await asyncio.sleep(0.1)  # Let both legacy loops enter the blocked callback queue.
        now[0] = runtime.get(second.notification_id)["deadline"] + 1
        await asyncio.sleep(1.2)
        assert runtime.get(second.notification_id)["ack_status"] == "TIMED_OUT"
    finally:
        release.set()
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker


@pytest.mark.asyncio
async def test_follower_election_and_failure_audit_commit_atomically(state, monkeypatch):
    runtime, adapter, _, _, _ = state
    first = runtime.accept(request(), principal="producer")
    follower = runtime.accept(request("two"), principal="producer")
    adapter.success = False
    original = runtime._event

    def fail_election(session, identifier, kind, payload):
        if kind == "DEDUP_OWNER_PROMOTED":
            raise RuntimeError("election audit unavailable")
        return original(session, identifier, kind, payload)

    monkeypatch.setattr(runtime, "_event", fail_election)
    with pytest.raises(RuntimeError, match="election audit"):
        await runtime.dispatch(first.notification_id)
    assert runtime.get(first.notification_id)["status"] == "PENDING"
    assert runtime.get(follower.notification_id)["dedup_owner_id"] == str(first.notification_id)


@pytest.mark.asyncio
async def test_process_death_after_provider_effect_recovers_with_duplicate_warning(state, tmp_path):
    runtime, adapter, _, now, url = state
    first = runtime.accept(request(), principal="producer")
    marker = tmp_path / "provider-receipt"
    script = r"""
import asyncio, os, sys
from notification.adapters.base import BaseAdapter
from notification.models import Channel
from notification.service import SimpleAdapterRegistry
from uns.runtime import Runtime
class Provider(BaseAdapter):
    channel = Channel.SLACK
    async def health_check(self): pass
    async def deliver(self, notification):
        with open(sys.argv[3], "w") as receipt:
            receipt.write(str(notification.notification_id))
            receipt.flush()
            os.fsync(receipt.fileno())
        os._exit(73)
registry = SimpleAdapterRegistry()
registry.register(Provider())
runtime = Runtime(sys.argv[1], adapters=registry, clock=lambda: 1000.0, max_attempts=3)
asyncio.run(runtime.dispatch(sys.argv[2]))
"""
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    process = subprocess.run(
        [sys.executable, "-c", script, url, str(first.notification_id), str(marker)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert process.returncode == 73, process.stderr
    assert marker.read_text() == str(first.notification_id)
    claimed = runtime.get(first.notification_id)
    assert claimed["status"] == "PENDING" and claimed["attempts"] == 1
    now[0] += 61
    runtime.max_attempts = 3
    await runtime.run_once()
    assert adapter.calls == [str(first.notification_id)]
    assert runtime.get(first.notification_id)["status"] == "DELIVERED"
    attempts = [e for e in runtime.events(first.notification_id) if e["kind"] == "ATTEMPT_STARTED"]
    assert attempts[-1]["payload"]["recovery_may_repeat_provider_effect"] is True
    assert runtime.get(first.notification_id)["cycle_attempts"] == 2


@pytest.mark.asyncio
async def test_provider_success_after_lease_expiry_is_recorded_as_ambiguous(state):
    runtime, adapter, _, now, _ = state
    first = runtime.accept(request(), principal="producer")

    async def pause_after_effect(notification):
        now[0] += runtime.lease_seconds + 1

    adapter.effect = pause_after_effect
    assert not await runtime.dispatch(first.notification_id)
    row = runtime.get(first.notification_id)
    assert row["status"] == "PENDING" and row["delivered_at"] is None
    event = runtime.events(first.notification_id)[-1]
    assert event["kind"] == "LEASE_LOST"
    assert event["payload"]["provider_effect_may_have_occurred"]


@pytest.mark.asyncio
async def test_successful_owner_suppresses_only_equivalent_obligation(state):
    runtime, adapter, _, _, _ = state
    first = await runtime.send(request(), principal="producer")
    second = await runtime.send(request("two"), principal="producer")
    assert second.status == DeliveryStatus.DEDUPLICATED
    assert runtime.get(second.notification_id)["dedup_owner_id"] == str(first.notification_id)
    assert str(first.notification_id) in second.message
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_followers_stay_linked_while_owner_has_retry_budget(state):
    runtime, adapter, _, now, _ = state
    runtime.max_attempts = 2
    first = runtime.accept(request(), principal="producer")
    follower = runtime.accept(request("two"), principal="producer")
    adapter.success = False
    await runtime.dispatch(first.notification_id)
    assert runtime.get(first.notification_id)["status"] == "PENDING"
    assert runtime.get(follower.notification_id)["dedup_owner_id"] == str(first.notification_id)
    now[0] += 2
    adapter.success = True
    await runtime.run_once()
    assert runtime.get(follower.notification_id)["status"] == "DEDUPLICATED"
    assert len(adapter.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["GUARANTEED", "BEST_EFFORT"])
async def test_websocket_lease_loss_blocks_every_persistent_channel(state, mode):
    runtime, slack, _, now, _ = state

    async def pause_after_websocket(notification):
        now[0] += runtime.lease_seconds + 1

    websocket = Adapter(Channel.WEBSOCKET, effect=pause_after_websocket)
    email = Adapter(Channel.EMAIL)
    runtime.adapters.register(websocket)
    runtime.adapters.register(email)
    first = runtime.accept(request(), principal="producer")
    notification = runtime.get(first.notification_id)["notification"]
    notification.update(channels=["WEBSOCKET", "SLACK", "EMAIL"], delivery_mode=mode)
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(first.notification_id))
            .values(notification=notification)
        )
    assert not await runtime.dispatch(first.notification_id)
    assert len(websocket.calls) == 1
    assert not slack.calls and not email.calls
    assert runtime.get(first.notification_id)["status"] == "PENDING"

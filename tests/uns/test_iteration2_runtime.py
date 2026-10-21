"""Cross-window ownership, replay lineage, fairness and clock contracts."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC

import pytest
from sqlalchemy import select, update
from tests.uns import test_delivery_remediation as delivery_fixtures
from tests.uns.test_delivery_remediation import request

from notification.models import Channel
from uns.maintenance import maintain
from uns.runtime import Conflict, Runtime, dedup, events, work


@pytest.fixture
def state(tmp_path):
    return delivery_fixtures.state.__wrapped__(tmp_path)


async def fail(runtime, adapter, identifier):
    adapter.success = False
    await runtime.dispatch(identifier)
    adapter.success = True


@pytest.mark.asyncio
async def test_pending_owner_survives_window_expiry(state):
    runtime, adapter, _, now, _ = state
    owner = runtime.accept(request("owner"), principal="p")
    now[0] += 301
    follower = runtime.accept(request("later"), principal="p")
    assert runtime.get(follower.notification_id)["dedup_owner_id"] == str(owner.notification_id)
    assert not await runtime.dispatch(follower.notification_id)
    await runtime.dispatch(owner.notification_id)
    assert runtime.get(follower.notification_id)["status"] == "DEDUPLICATED"
    assert len(adapter.calls) == 1
    # TTL is acceptance based; completed owner no longer suppresses after expiry.
    fresh = runtime.accept(request("fresh"), principal="p")
    assert runtime.get(fresh.notification_id)["dedup_owner_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("newer_delivered", [False, True])
async def test_legacy_overlapping_owner_relinks_without_stealing(state, newer_delivered):
    runtime, adapter, _, now, _ = state
    old = runtime.accept(request("old"), principal="p")
    follower = runtime.accept(request("follower"), principal="p")
    # Construct the overlap allowed by the previous implementation.
    with runtime.sessions.begin() as s:
        s.execute(update(work).where(work.c.id == str(old.notification_id)).values(status="FAILED"))
    now[0] += 301
    newer = runtime.accept(request("newer"), principal="p")
    with runtime.sessions.begin() as s:
        s.execute(
            update(work).where(work.c.id == str(old.notification_id)).values(status="PENDING")
        )
    if newer_delivered:
        await runtime.dispatch(newer.notification_id)
    await fail(runtime, adapter, old.notification_id)
    with runtime.sessions() as s:
        claim = s.execute(select(dedup)).mappings().one()
    row = runtime.get(follower.notification_id)
    assert claim["owner_id"] == str(newer.notification_id)
    assert row["dedup_owner_id"] == str(newer.notification_id)
    assert row["dedup_generation"] == claim["generation"]
    assert row["status"] == ("DEDUPLICATED" if newer_delivered else "PENDING")
    assert not await runtime.dispatch(follower.notification_id)
    if not newer_delivered:
        await fail(runtime, adapter, newer.notification_id)
        await runtime.dispatch(follower.notification_id)
        assert runtime.get(follower.notification_id)["status"] == "DELIVERED"


@pytest.mark.asyncio
async def test_replay_blocks_pending_and_delivered_successor_after_restart_and_expiry(state):
    runtime, adapter, registry, now, url = state
    owner = runtime.accept(request("owner"), principal="p")
    successor = runtime.accept(request("successor"), principal="p")
    await fail(runtime, adapter, owner.notification_id)
    with pytest.raises(Conflict, match="pending|Pending"):
        runtime.replay(owner.notification_id, actor="ops")
    await runtime.dispatch(successor.notification_id)
    now[0] += 10000
    reopened = Runtime(url, adapters=registry, clock=lambda: now[0])
    unrelated = reopened.accept(request("new-window"), principal="p")
    await reopened.dispatch(unrelated.notification_id)
    with pytest.raises(Conflict, match="satisfied|delivered"):
        reopened.replay(owner.notification_id, actor="ops")
    dead = next(
        r for r in reopened.dead_letters() if r["notification_id"] == str(owner.notification_id)
    )
    assert dead["replay_blocked_by"] == str(successor.notification_id)
    assert dead["replay_block_reason"] == "DELIVERED"
    assert reopened.resolve_failure(owner.notification_id, actor="ops")
    assert reopened.get(owner.notification_id)["status"] == "FAILED"


@pytest.mark.asyncio
async def test_replay_claims_key_and_prevents_parallel_predecessor_replays(state):
    runtime, adapter, _, _, _ = state
    a = runtime.accept(request("a"), principal="p")
    b = runtime.accept(request("b"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    await fail(runtime, adapter, b.notification_id)

    def replay(identifier):
        try:
            runtime.replay(identifier, actor="ops")
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(replay, [a.notification_id, b.notification_id]))
    assert sum(results) == 1
    await runtime.run_once()
    assert len(adapter.calls) == 3


@pytest.mark.asyncio
async def test_retention_keeps_replay_successor_evidence(state):
    runtime, adapter, _, now, _ = state
    a = runtime.accept(request("a"), principal="p")
    b = runtime.accept(request("b"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    await runtime.dispatch(b.notification_id)
    runtime.acknowledge(b.notification_id, actor="ops")
    now[0] = 10000
    report = maintain(
        runtime.engine, cutoff=5000, idempotency_seconds=60, now=10000, apply=True, operator="ops"
    )
    assert str(b.notification_id) not in report["notification_ids"]
    with pytest.raises(Conflict):
        runtime.replay(a.notification_id, actor="ops")


@pytest.mark.asyncio
async def test_runtime_clock_applies_to_delivery_and_ack_audits(state):
    runtime, _, _, now, _ = state
    accepted = await runtime.send(request("clock"), principal="p")
    runtime.acknowledge(accepted.notification_id, actor="ops")
    for audit in runtime.audit_store.get_delivery_audits_for_notification(accepted.notification_id):
        assert audit.audit_created_at.replace(tzinfo=UTC).timestamp() == now[0]
    for audit in runtime.audit_store.get_ack_audits_for_notification(accepted.notification_id):
        assert audit.audit_created_at.replace(tzinfo=UTC).timestamp() == now[0]
    now[0] = 10000
    report = maintain(
        runtime.engine, cutoff=5000, idempotency_seconds=60, now=10000, apply=True, operator="ops"
    )
    assert report["deleted_rows"] == 2


@pytest.mark.asyncio
async def test_callback_overdue_retry_gets_capacity_before_fresh_arrivals(state):
    runtime, _, _, now, _ = state
    delivered = []
    first = [True]

    async def callback(row):
        if first[0]:
            first[0] = False
            raise RuntimeError("retry")
        delivered.append(row["id"])

    runtime.callback = callback
    with runtime.sessions.begin() as s:
        runtime._event(s, "early", "ACKED", {})
    await runtime.deliver_callbacks()
    early = runtime.events("early")[0]["id"]
    now[0] = 2000
    with runtime.sessions.begin() as s:
        for i in range(100):
            runtime._event(s, f"fresh-{i}", "ACKED", {})
    await runtime.deliver_callbacks()
    assert delivered[0] == early
    assert len(delivered) == 100


@pytest.mark.asyncio
async def test_replaying_failed_root_keeps_descendant_satisfaction_after_expiry(state):
    runtime, adapter, _, now, _ = state
    a = runtime.accept(request("root"), principal="p")
    b = runtime.accept(request("child"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    await fail(runtime, adapter, b.notification_id)
    runtime.replay(a.notification_id, actor="ops")
    await runtime.dispatch(a.notification_id)
    now[0] += 10000
    with pytest.raises(Conflict, match="satisfied"):
        runtime.replay(b.notification_id, actor="ops")


@pytest.mark.asyncio
async def test_migration_backfills_recorded_successor_and_callback_due_time(state):
    runtime, adapter, registry, now, url = state
    a = runtime.accept(request("a"), principal="p")
    b = runtime.accept(request("b"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    await runtime.dispatch(b.notification_id)
    with runtime.engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX ix_uns_dedup_successor")
        conn.exec_driver_sql("ALTER TABLE uns_notifications DROP COLUMN dedup_successor_id")
        conn.execute(
            events.insert().values(
                id="old-callback",
                notification_id="legacy",
                kind="ACKED",
                at=1000,
                payload={},
                callback_pending=True,
                callback_until=0,
            )
        )
    reopened = Runtime(url, adapters=registry, clock=lambda: now[0])
    reopened = Runtime(url, adapters=registry, clock=lambda: now[0])
    assert reopened.get(a.notification_id)["dedup_successor_id"] == str(b.notification_id)
    assert reopened.events("legacy")[0]["callback_until"] == 1000
    now[0] += 10000
    with pytest.raises(Conflict, match="satisfied"):
        reopened.replay(a.notification_id, actor="ops")


@pytest.mark.asyncio
async def test_completed_channel_evidence_survives_lease_takeover(state):
    from notification.adapters.base import BaseAdapter, DeliveryResult, guard_provider_attempt

    runtime, adapter, _, _, _ = state

    class LostEmail(BaseAdapter):
        guards_provider_attempts = True
        channel = Channel.EMAIL

        async def deliver(self, notification):
            await asyncio.sleep(0.02)
            with runtime.sessions.begin() as s:
                s.execute(
                    update(work)
                    .where(work.c.id == str(notification.notification_id))
                    .values(lease_token="replacement")
                )
            guard_provider_attempt(self.channel)
            return DeliveryResult(success=True, channel=self.channel)

        async def health_check(self):
            pass

    runtime.adapters.register(LostEmail())
    accepted = runtime.accept(request("partial"), principal="p")
    notification = runtime.get(accepted.notification_id)["notification"]
    notification.update(channels=["SLACK", "EMAIL"], delivery_mode="BEST_EFFORT")
    with runtime.sessions.begin() as s:
        s.execute(
            update(work)
            .where(work.c.id == str(accepted.notification_id))
            .values(notification=notification)
        )
    assert not await runtime.dispatch(accepted.notification_id)
    row = runtime.get(accepted.notification_id)
    assert row["lease_token"] == "replacement"
    assert row["outcome"]["channels_succeeded"] == []
    evidence = [
        e["payload"]
        for e in runtime.events(accepted.notification_id)
        if e["kind"] == "CHANNEL_ATTEMPT_RESULT"
    ]
    assert any(e["channel"] == "SLACK" and e["success"] for e in evidence)
    assert all(e["lease_token"] != "replacement" for e in evidence)
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_promotion_does_not_restart_expired_suppression_window(state):
    runtime, adapter, _, now, _ = state
    a = runtime.accept(request("a"), principal="p")
    b = runtime.accept(request("b"), principal="p")
    now[0] = 1301
    await fail(runtime, adapter, a.notification_id)
    await runtime.dispatch(b.notification_id)
    c = runtime.accept(request("c"), principal="p")
    assert c.status.value == "PENDING"
    assert runtime.get(c.notification_id)["dedup_owner_id"] is None


@pytest.mark.asyncio
async def test_upgrade_keeps_missing_successor_as_unresolved_evidence(state):
    runtime, adapter, registry, now, url = state
    a = runtime.accept(request("old-a"), principal="p")
    b = runtime.accept(request("old-b"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    await runtime.dispatch(b.notification_id)
    with runtime.engine.begin() as conn:
        # Previous non-archive retention could remove B, leaving promotion evidence.
        conn.execute(work.delete().where(work.c.id == str(b.notification_id)))
        conn.execute(dedup.delete())
        conn.exec_driver_sql("DROP INDEX ix_uns_dedup_successor")
        conn.exec_driver_sql("ALTER TABLE uns_notifications DROP COLUMN dedup_successor_id")
    reopened = Runtime(url, adapters=registry, clock=lambda: now[0])
    assert reopened.get(a.notification_id)["dedup_successor_id"] == str(b.notification_id)
    with pytest.raises(Conflict, match="unresolved"):
        reopened.replay(a.notification_id, actor="ops")


@pytest.mark.asyncio
async def test_channel_evidence_failure_does_not_turn_success_into_fallback(state, monkeypatch):
    runtime, slack, _, _, _ = state
    email = delivery_fixtures.Adapter(Channel.EMAIL)
    runtime.adapters.register(email)
    accepted = runtime.accept(request("evidence-store"), principal="p")
    notification = runtime.get(accepted.notification_id)["notification"]
    notification.update(channels=["SLACK", "EMAIL"])
    with runtime.sessions.begin() as s:
        s.execute(
            update(work)
            .where(work.c.id == str(accepted.notification_id))
            .values(notification=notification)
        )
    original = runtime._event

    def reject_result(session, identifier, kind, payload):
        if kind == "CHANNEL_ATTEMPT_RESULT":
            raise OSError("evidence store unavailable")
        return original(session, identifier, kind, payload)

    monkeypatch.setattr(runtime, "_event", reject_result)
    assert not await runtime.dispatch(accepted.notification_id)
    assert len(slack.calls) == 1
    assert email.calls == []
    row = runtime.get(accepted.notification_id)
    assert row["status"] == "PENDING"
    assert row["lease_token"] is not None


@pytest.mark.asyncio
async def test_upgrade_retains_promotion_when_replay_and_promotion_clocks_tie(state):
    runtime, adapter, registry, now, url = state
    a = runtime.accept(request("a"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    now[0] = 1001
    runtime.replay(a.notification_id, actor="ops")
    b = runtime.accept(request("b"), principal="p")
    await fail(runtime, adapter, a.notification_id)
    await runtime.dispatch(b.notification_id)
    with runtime.engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX ix_uns_dedup_successor")
        conn.exec_driver_sql("ALTER TABLE uns_notifications DROP COLUMN dedup_successor_id")
    now[0] = 10000
    reopened = Runtime(url, adapters=registry, clock=lambda: now[0])
    assert reopened.get(a.notification_id)["dedup_successor_id"] == str(b.notification_id)
    with pytest.raises(Conflict, match="satisfied"):
        reopened.replay(a.notification_id, actor="ops")


@pytest.mark.asyncio
async def test_upgrade_reconstructs_successful_legacy_root_replay_transitively(state):
    runtime, adapter, registry, now, url = state
    a = runtime.accept(request("a"), principal="p")
    runtime.accept(request("b"), principal="p")
    runtime.accept(request("c"), principal="p")
    adapter.success = False
    for _ in range(3):
        await runtime.run_once()
    ids = [r["notification_id"] for r in runtime.dead_letters()]
    assert len(ids) == 3
    runtime.replay(a.notification_id, actor="ops")
    adapter.success = True
    await runtime.dispatch(a.notification_id)
    with runtime.engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX ix_uns_dedup_successor")
        conn.exec_driver_sql("ALTER TABLE uns_notifications DROP COLUMN dedup_successor_id")
    now[0] = 10000
    reopened = Runtime(url, adapters=registry, clock=lambda: now[0])
    for identifier in ids:
        if identifier != str(a.notification_id):
            assert reopened.get(identifier)["dedup_successor_id"] == str(a.notification_id)
            with pytest.raises(Conflict, match="satisfied"):
                reopened.replay(identifier, actor="ops")

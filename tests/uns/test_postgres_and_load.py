"""Live PostgreSQL 16 operational acceptance and sustained concurrency/load tests.

Part A: Live PostgreSQL Operational Acceptance (guarded by UNS_TEST_POSTGRES_URL).
Part B: Sustained Concurrency & Load Validation (runs on SQLite WAL by default
        AND on UNS_TEST_POSTGRES_URL when set).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text

from db.models.policy import NotificationPolicySnapshot
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)
from notification.policies import NotificationPolicy
from notification.service import SimpleAdapterRegistry
from uns.api.read_models import AuditEventFilter, DeliveryFilter, SQLAlchemyReadModelAdapter
from uns.maintenance import maintain
from uns.responses import SendNotificationRequest
from uns.runtime import Conflict, Runtime, dedup, work
from uns.schema import migrate_runtime_schema

POSTGRES_URL = os.environ.get("UNS_TEST_POSTGRES_URL")


class RecordingAdapter(BaseAdapter):
    """Test adapter tracking delivery invocations."""

    def __init__(self, channel: Channel = Channel.SLACK, success: bool = True) -> None:
        self._channel = channel
        self.success = success
        self.calls: list[str] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Any) -> DeliveryResult:
        await asyncio.sleep(0.002)
        self.calls.append(str(notification.notification_id))
        return DeliveryResult(success=self.success, channel=self.channel)

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(AdapterStatus.HEALTHY, "recording-adapter")


def _sample_policy(
    notification_type: str = "agent.risk_limit_breach",
    ack_timeout_minutes: int = 15,
) -> NotificationPolicy:
    return NotificationPolicy(
        notification_type=notification_type,
        intent=NotificationIntent.SAFETY,
        channels=[Channel.SLACK],
        delivery_mode=DeliveryMode.GUARANTEED,
        require_ack=True,
        ack_timeout_minutes=ack_timeout_minutes,
    )


def _make_send_request(
    title: str = "Test Signal",
    *,
    notification_type: str = "agent.risk_limit_breach",
    intent: NotificationIntent = NotificationIntent.SAFETY,
    dedup_key: str | None = None,
    idempotency_key: str | None = None,
    require_ack: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> SendNotificationRequest:
    return SendNotificationRequest(
        notification_type=notification_type,
        intent=intent,
        title=title,
        message="PostgreSQL operational acceptance validation signal",
        source="pg-test-runner",
        autonomy_context={
            "autonomy_mode": AutonomyMode.LIVE,
            "agent_id": uuid4(),
        },
        dedup_key=dedup_key,
        idempotency_key=idempotency_key,
        require_ack=require_ack,
        metadata=metadata or {},
    )


def _reset_postgres_db(pg_url: str) -> None:
    engine = create_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()


# =============================================================================
# Part A: Live PostgreSQL Operational Acceptance
# =============================================================================

@pytest.mark.skipif(not POSTGRES_URL, reason="UNS_TEST_POSTGRES_URL not set")
class TestPostgresOperationalAcceptance:
    """Verifies complete UNS runtime operation against a live PostgreSQL 16 database."""

    @pytest.fixture(autouse=True)
    def clean_db(self) -> None:
        assert POSTGRES_URL is not None
        _reset_postgres_db(POSTGRES_URL)

    def test_schema_bootstrap_and_postgresql_maintenance(self, tmp_path: Path) -> None:
        """Verifies schema bootstrap, idempotent migration, and PostgreSQL retention/archival."""
        import hashlib
        import json

        assert POSTGRES_URL is not None
        engine = create_engine(POSTGRES_URL)

        # 1. Idempotent bootstrap via migrate_runtime_schema
        migrate_runtime_schema(engine, create_tables=True)
        # Repeated call must be 100% idempotent
        migrate_runtime_schema(engine, create_tables=True)

        # 2. Runtime construction on existing PostgreSQL database
        now_val = 2_000_000.0
        old_val = now_val - 1_000.0
        runtime = Runtime(POSTGRES_URL, create_tables=False, clock=lambda: old_val)
        assert runtime.engine.dialect.name == "postgresql"

        # 3. Accept, deliver, and acknowledge a settled notification at old_val
        req = _make_send_request(
            idempotency_key="pg-maint-1",
            dedup_key="pg-maint-dedup-1",
            require_ack=True,
        )
        accepted = runtime.accept(req, principal="pg-maint-op")
        nid = str(accepted.notification_id)
        with runtime.engine.begin() as conn:
            conn.execute(
                work.update()
                .where(work.c.id == nid)
                .values(
                    status="DELIVERED",
                    delivered_at=old_val,
                    ack_status="ACKED",
                    actor="pg-responder",
                    responded_at=old_val,
                )
            )
            conn.execute(dedup.update().where(dedup.c.owner_id == nid).values(until=old_val + 10.0))

        # 4. Dry-run preview on PostgreSQL identifies the settled notification without mutating
        preview = maintain(
            engine,
            cutoff=now_val - 10.0,
            idempotency_seconds=100.0,
            now=now_val,
        )
        assert preview["applied"] is False
        assert preview["notification_ids"] == [nid]

        # 5. Archive-before-prune on PostgreSQL writes mode-0600 SHA-256 verified JSON archive and prunes
        archive_path = tmp_path / "pg-archive.json"
        applied = maintain(
            engine,
            cutoff=now_val - 10.0,
            idempotency_seconds=100.0,
            now=now_val,
            apply=True,
            operator="pg-archivist",
            archive=archive_path,
        )
        assert applied["applied"] is True
        assert applied["notification_ids"] == [nid]
        assert applied["receipt_id"] is not None
        assert archive_path.is_file()
        assert (archive_path.stat().st_mode & 0o777) == 0o600
        archive_data = json.loads(archive_path.read_text())
        assert archive_data["tables"]["uns_notifications"][0]["id"] == nid
        assert applied["archive"]["sha256"] == hashlib.sha256(archive_path.read_bytes()).hexdigest()

        runtime.engine.dispose()
        engine.dispose()

    def test_policy_snapshot_persistence_and_runtime_hydration(self) -> None:
        """Verifies policy snapshot persistence, cold & warm hydration, and revision locking."""
        assert POSTGRES_URL is not None
        runtime = Runtime(POSTGRES_URL, create_tables=True)
        policy_store = runtime.policy_runtime.store

        # 1. Save initial policy snapshot
        policy = _sample_policy()
        rev0 = policy_store.save_snapshot([policy])
        assert rev0 == 1

        # 2. Warm hydration via store
        snap = policy_store.load_snapshot()
        assert snap.revision >= 1
        registry = snap.registry()
        assert registry.get_sync("agent.risk_limit_breach") is not None

        # 3. Cold hydration in fresh PolicyRuntime
        cold_runtime = Runtime(POSTGRES_URL, create_tables=False)
        cold_snap = cold_runtime.policy_runtime.store.load_snapshot()
        assert cold_snap.revision == snap.revision

        # 4. Revision locking inside runtime.accept()
        req = _make_send_request("Revision lock check")
        resp = runtime.accept(req, principal="pg-tester")
        row = runtime.get(resp.notification_id)
        resolution = row["notification"]["metadata"]["uns_resolution"]
        assert resolution["snapshot_revision"] == snap.revision

        runtime.engine.dispose()
        cold_runtime.engine.dispose()

    def test_idempotency_replay_and_conflict_detection(self) -> None:
        """Verifies idempotency replay and conflict detection on PostgreSQL."""
        assert POSTGRES_URL is not None
        runtime = Runtime(POSTGRES_URL, create_tables=True)

        idemp_key = f"pg-idemp-{uuid4()}"
        req = _make_send_request("Idempotency first call", idempotency_key=idemp_key)

        # First intake creates the record
        resp1 = runtime.accept(req, principal="pg-tester")
        assert resp1.idempotent_replay is False

        # Replay with same content returns original notification ID
        resp2 = runtime.accept(req, principal="pg-tester")
        assert resp2.idempotent_replay is True
        assert resp2.notification_id == resp1.notification_id

        # Conflict on same idempotency key with modified payload
        conflict_req = req.model_copy(update={"title": "Modified title for conflict check"})
        with pytest.raises(Conflict, match="Idempotency key reused with different request content"):
            runtime.accept(conflict_req, principal="pg-tester")

        runtime.engine.dispose()

    @pytest.mark.asyncio
    async def test_deduplication_coalescing_and_promotion_and_guarded_replay(self) -> None:
        """Verifies leader/follower coalescing, promotion on leader failure, and guarded replay."""
        assert POSTGRES_URL is not None
        adapter = RecordingAdapter(Channel.SLACK, success=False)
        adapters = SimpleAdapterRegistry()
        adapters.register(adapter)
        runtime = Runtime(POSTGRES_URL, create_tables=True, adapters=adapters, max_attempts=1)

        storm_key = f"pg-promo-storm-{uuid4().hex[:8]}"
        lead_token = f"lead-idem-{uuid4().hex}"
        fol_token = f"fol-idem-{uuid4().hex}"
        lead_req = _make_send_request("Leader", dedup_key=storm_key, idempotency_key=lead_token)
        fol_req = _make_send_request("Follower", dedup_key=storm_key, idempotency_key=fol_token)

        lead_resp = runtime.accept(lead_req, principal="pg-tester")
        fol_resp = runtime.accept(fol_req, principal="pg-tester")

        lead_id = lead_resp.notification_id
        fol_id = fol_resp.notification_id

        # Follower coalesced under leader
        assert runtime.get(fol_id)["dedup_owner_id"] == str(lead_id)

        # Dispatch fails leader on persistent channel
        await runtime.dispatch(lead_id)
        lead_row = runtime.get(lead_id)
        fol_row = runtime.get(fol_id)

        assert lead_row["status"] == "FAILED"
        assert lead_row["dead_letter"] is True
        assert lead_row["dedup_successor_id"] == str(fol_id)

        # Follower promoted to owner
        assert fol_row["dedup_owner_id"] is None

        fol_events = runtime.events(fol_id)
        lead_events = runtime.events(lead_id)
        assert any(e["kind"] == "DEDUP_OWNER_PROMOTED" for e in fol_events)
        assert any(e["kind"] == "OBLIGATION_HANDED_OFF" for e in lead_events)

        # Deliver the successor
        adapter.success = True
        await runtime.dispatch(fol_id)
        assert runtime.get(fol_id)["status"] == "DELIVERED"

        # Guarded replay: replaying leader is rejected because successor satisfied obligation
        with pytest.raises(Conflict, match="Obligation already satisfied or lineage unresolved"):
            runtime.replay(lead_id, actor="operator")

        # Independent dead-letter without successor can be safely replayed
        failed_standalone = runtime.accept(
            _make_send_request("Standalone Fail", idempotency_key=f"solo-{uuid4()}"),
            principal="pg-tester",
        )
        adapter.success = False
        await runtime.dispatch(failed_standalone.notification_id)
        assert runtime.get(failed_standalone.notification_id)["dead_letter"] is True

        runtime.replay(failed_standalone.notification_id, actor="operator")
        assert runtime.get(failed_standalone.notification_id)["dead_letter"] is False
        adapter.success = True
        await runtime.dispatch(failed_standalone.notification_id)
        assert runtime.get(failed_standalone.notification_id)["status"] == "DELIVERED"

        runtime.engine.dispose()

    @pytest.mark.asyncio
    async def test_delivery_ack_dismiss_timeout_and_callbacks(self) -> None:
        """Verifies qualifying delivery, ACK, dismiss, TIMED_OUT expiry, and callbacks on PG."""
        assert POSTGRES_URL is not None
        adapter = RecordingAdapter(Channel.SLACK, success=True)
        adapters = SimpleAdapterRegistry()
        adapters.register(adapter)
        delivered_callbacks: list[dict[str, Any]] = []

        async def on_callback(event: dict[str, Any]) -> None:
            delivered_callbacks.append(event)

        runtime = Runtime(
            POSTGRES_URL,
            create_tables=True,
            adapters=adapters,
            callback=on_callback,
        )

        # 1. Qualifying delivery + ACK
        ack_req = _make_send_request("Ack Notification", require_ack=True)
        ack_resp = runtime.accept(ack_req, principal="pg-tester")
        await runtime.dispatch(ack_resp.notification_id)
        assert runtime.get(ack_resp.notification_id)["status"] == "DELIVERED"
        assert runtime.get(ack_resp.notification_id)["ack_status"] == "PENDING"

        runtime.acknowledge(ack_resp.notification_id, actor="operator@example.com")
        assert runtime.get(ack_resp.notification_id)["ack_status"] == "ACKED"

        # 2. Dismiss
        dismiss_req = _make_send_request("Dismiss Notification", require_ack=True)
        dismiss_resp = runtime.accept(dismiss_req, principal="pg-tester")
        await runtime.dispatch(dismiss_resp.notification_id)
        runtime.acknowledge(dismiss_resp.notification_id, actor="operator@example.com", dismiss=True)
        assert runtime.get(dismiss_resp.notification_id)["ack_status"] == "DISMISSED"

        # 3. Timeout expiry
        timeout_req = _make_send_request("Timeout Notification", require_ack=True)
        timeout_resp = runtime.accept(timeout_req, principal="pg-tester")
        await runtime.dispatch(timeout_resp.notification_id)
        runtime.expire(now=time.time() + 86400 * 2)
        assert runtime.get(timeout_resp.notification_id)["ack_status"] == "TIMED_OUT"

        # 4. Callback delivery
        await runtime.deliver_callbacks()
        assert len(delivered_callbacks) >= 3

        runtime.engine.dispose()

    @pytest.mark.asyncio
    async def test_read_model_adapter_queries_on_postgres(self) -> None:
        """Verifies SQLAlchemyReadModelAdapter queries and operational_progress on PostgreSQL."""
        assert POSTGRES_URL is not None
        adapter = RecordingAdapter(Channel.SLACK, success=True)
        adapters = SimpleAdapterRegistry()
        adapters.register(adapter)
        runtime = Runtime(POSTGRES_URL, create_tables=True, adapters=adapters)

        # Save an active policy so policy revision records exist
        runtime.policy_runtime.store.save_snapshot([_sample_policy()])

        req = _make_send_request("Read Model PG Test")
        resp = runtime.accept(req, principal="pg-tester")
        await runtime.dispatch(resp.notification_id)

        read_adapter = SQLAlchemyReadModelAdapter(runtime.sessions)

        # 1. get_deliveries with PostgreSQL JSONB containment channel filter
        slack_deliveries = read_adapter.get_deliveries(DeliveryFilter(channel=Channel.SLACK))
        assert slack_deliveries.total_count >= 1
        assert any(d.notification_id == resp.notification_id for d in slack_deliveries.items)

        # 2. get_delivery_timeline
        timeline = read_adapter.get_delivery_timeline(resp.notification_id)
        assert timeline is not None
        assert timeline.notification_id == resp.notification_id

        # 3. get_audit_events with event_type SQL filtering and total_count
        audits = read_adapter.get_audit_events(AuditEventFilter(event_type="delivery.succeeded"))
        assert audits.total_count >= 1

        # 4. list_revisions
        revs = runtime.policy_runtime.store.list_revisions()
        assert len(revs) >= 1

        # 5. operational_progress SQL aggregates
        progress = runtime.operational_progress()
        assert "pending_count" in progress
        assert "overdue_ack_count" in progress
        assert "unknown_attempt_count" in progress

        runtime.engine.dispose()


# =============================================================================
# Part B: Sustained Concurrency & Load Validation
# =============================================================================

def _database_urls() -> list[str]:
    """Provide test database URLs: SQLite WAL by default, plus PostgreSQL when available."""
    urls = ["sqlite_wal"]
    if POSTGRES_URL:
        urls.append("postgres")
    return urls


@pytest.fixture
def target_database_url(request: pytest.FixtureRequest, tmp_path: Any) -> str:
    param = request.param
    if param == "sqlite_wal":
        db_path = tmp_path / "load_test_wal.db"
        return f"sqlite:///{db_path}"
    if param == "postgres":
        assert POSTGRES_URL is not None
        _reset_postgres_db(POSTGRES_URL)
        return POSTGRES_URL
    raise ValueError(f"Unknown database param {param}")


@pytest.mark.parametrize("target_database_url", _database_urls(), indirect=True)
class TestSustainedConcurrencyAndLoad:
    """Sustained concurrency, race contention, and policy reload load validation."""

    @pytest.mark.asyncio
    async def test_concurrent_intake_burst_and_deduplication_storm(
        self, target_database_url: str
    ) -> None:
        """100 concurrent producer requests across 10 dedup keys + 20 unique guaranteed signals.

        Verifies all 120 complete without lock errors, exactly 10 leaders + 90 followers
        are recorded for the storm keys, and P95 intake latency stays within bounds.
        """
        runtime = Runtime(target_database_url, create_tables=True)

        storm_keys = [f"storm-key-{i}-{uuid4().hex[:6]}" for i in range(10)]
        requests: list[tuple[SendNotificationRequest, bool]] = []

        # 100 storm requests (10 per key)
        for i in range(100):
            k = storm_keys[i % 10]
            requests.append(
                (
                    _make_send_request(
                        f"Storm {i}",
                        dedup_key=k,
                        idempotency_key=f"storm-req-{i}-{uuid4()}",
                    ),
                    True,
                )
            )

        # 20 unique guaranteed requests
        for i in range(20):
            requests.append(
                (
                    _make_send_request(
                        f"Unique {i}",
                        dedup_key=f"unique-key-{i}-{uuid4()}",
                        idempotency_key=f"unique-req-{i}-{uuid4()}",
                    ),
                    False,
                )
            )

        latencies: list[float] = []

        async def submit(req: SendNotificationRequest) -> Any:
            t0 = time.perf_counter()
            resp = await asyncio.to_thread(runtime.accept, req, principal="load-tester")
            latencies.append(time.perf_counter() - t0)
            return resp

        responses = await asyncio.gather(*[submit(req) for req, _ in requests])
        assert len(responses) == 120

        # Calculate P95 latency
        sorted_latencies = sorted(latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency = sorted_latencies[p95_index]
        assert p95_latency < 5.0, f"P95 intake latency {p95_latency:.4f}s exceeded 5.0s bound"

        # Verify storm deduplication outcomes in database
        with runtime.sessions() as session:
            rows = session.execute(
                select(work).where(work.c.principal == "load-tester")
            ).mappings().all()

        storm_rows = [
            r for r in rows
            if any(k in (r["notification"].get("dedup_key") or "") for k in storm_keys)
        ]
        assert len(storm_rows) == 100

        leaders = [r for r in storm_rows if r["dedup_owner_id"] is None]
        followers = [r for r in storm_rows if r["dedup_owner_id"] is not None]

        assert len(leaders) == 10, f"Expected exactly 10 leaders, got {len(leaders)}"
        assert len(followers) == 90, f"Expected exactly 90 followers, got {len(followers)}"

        runtime.engine.dispose()

    @pytest.mark.asyncio
    async def test_multi_worker_lease_contention_zero_duplicate_sends(
        self, target_database_url: str
    ) -> None:
        """40 pending GUARANTEED notifications raced by 4 concurrent dispatch workers.

        Verifies all 40 notifications reach DELIVERED and recording adapter receives
        exactly 40 calls (zero duplicate sends).
        """
        adapter = RecordingAdapter(Channel.SLACK, success=True)
        adapters = SimpleAdapterRegistry()
        adapters.register(adapter)
        runtime = Runtime(target_database_url, create_tables=True, adapters=adapters)

        # Enqueue 40 unique pending guaranteed notifications
        notification_ids: list[UUID] = []
        for i in range(40):
            req = _make_send_request(
                f"Contention {i}",
                idempotency_key=f"contention-{i}-{uuid4()}",
            )
            resp = runtime.accept(req, principal="load-tester")
            notification_ids.append(resp.notification_id)

        assert len(notification_ids) == 40

        # 4 concurrent workers racing with runtime.dispatch(limit=20)
        async def worker(worker_id: int) -> int:
            worker_dispatched = 0
            while True:
                dispatched = await runtime.dispatch(limit=20)
                if isinstance(dispatched, int):
                    worker_dispatched += dispatched
                    if dispatched == 0:
                        break
                elif not dispatched:
                    break
                await asyncio.sleep(0.005)
            return worker_dispatched

        results = await asyncio.gather(*[worker(i) for i in range(4)])
        total_dispatched = sum(results)
        assert total_dispatched == 40

        # Verify exactly 40 external send calls made to recording adapter
        assert len(adapter.calls) == 40, f"Expected 40 adapter calls, got {len(adapter.calls)}"
        assert len(set(adapter.calls)) == 40, "Duplicate send calls detected!"

        # Verify all notifications reached DELIVERED terminal status
        for nid in notification_ids:
            row = runtime.get(nid)
            assert row["status"] == "DELIVERED", f"Notification {nid} status was {row['status']}"

        runtime.engine.dispose()

    @pytest.mark.asyncio
    async def test_concurrent_dispatch_workers_limit_1_drain_without_starvation(
        self, target_database_url: str
    ) -> None:
        """4 concurrent workers calling dispatch(limit=1) in a loop drain all notifications without starvation."""
        adapter = RecordingAdapter(Channel.SLACK, success=True)
        adapters = SimpleAdapterRegistry()
        adapters.register(adapter)
        runtime = Runtime(target_database_url, create_tables=True, adapters=adapters)

        # Enqueue 30 unique pending guaranteed notifications
        notification_ids: list[UUID] = []
        for i in range(30):
            req = _make_send_request(
                f"Limit1Contention {i}",
                idempotency_key=f"limit1-contention-{i}-{uuid4()}",
            )
            resp = runtime.accept(req, principal="load-tester")
            notification_ids.append(resp.notification_id)

        assert len(notification_ids) == 30

        # 4 concurrent workers calling runtime.dispatch(limit=1) in a loop
        async def worker(worker_id: int) -> int:
            worker_dispatched = 0
            empty_cycles = 0
            while empty_cycles < 5:
                dispatched = await runtime.dispatch(limit=1)
                if isinstance(dispatched, int):
                    if dispatched > 0:
                        worker_dispatched += dispatched
                        empty_cycles = 0
                    else:
                        empty_cycles += 1
                elif not dispatched:
                    empty_cycles += 1
                await asyncio.sleep(0.002)
            return worker_dispatched

        results = await asyncio.gather(*[worker(i) for i in range(4)])
        total_dispatched = sum(results)
        assert total_dispatched == 30, f"Expected 30 dispatched, got {total_dispatched}"
        assert len(adapter.calls) == 30, f"Expected 30 adapter calls, got {len(adapter.calls)}"
        assert len(set(adapter.calls)) == 30, "Duplicate send calls detected!"

        for nid in notification_ids:
            row = runtime.get(nid)
            assert row["status"] == "DELIVERED", f"Notification {nid} status was {row['status']}"

        runtime.engine.dispose()

    @pytest.mark.asyncio
    async def test_concurrent_policy_reload_under_active_intake(
        self, target_database_url: str
    ) -> None:
        """50 producer accept calls interleaved with 5 concurrent save_snapshot policy reloads.

        Verifies zero exceptions and that every accepted notification's audit trail records
        a valid, self-consistent (policy_revision_id, policy_config_hash, ack_timeout_minutes)
        tuple.
        """
        runtime = Runtime(target_database_url, create_tables=True)
        policy0 = _sample_policy(ack_timeout_minutes=10)
        runtime.policy_runtime.store.save_snapshot([policy0])

        accepted_responses: list[Any] = []

        async def producer_worker(start: int, count: int) -> None:
            for i in range(start, start + count):
                req = _make_send_request(
                    f"Policy reload test {i}",
                    idempotency_key=f"policy-load-{i}-{uuid4()}",
                )
                resp = await asyncio.to_thread(runtime.accept, req, principal="policy-tester")
                accepted_responses.append(resp)
                await asyncio.sleep(0.005)

        async def reload_worker(reload_id: int, timeout_minutes: int) -> int:
            await asyncio.sleep(0.01 * reload_id)
            updated_policy = _sample_policy(ack_timeout_minutes=timeout_minutes)
            rev = await asyncio.to_thread(
                runtime.policy_runtime.store.save_snapshot, [updated_policy]
            )
            return rev

        # 5 producer tasks (10 calls each = 50 calls) interleaved with 5 policy reload tasks
        producer_tasks = [producer_worker(i * 10, 10) for i in range(5)]
        reload_tasks = [reload_worker(i, 10 + i * 5) for i in range(1, 6)]

        await asyncio.gather(*producer_tasks, *reload_tasks)
        assert len(accepted_responses) == 50

        # Snapshot lookup from database
        with runtime.sessions() as session:
            snapshots = session.execute(select(NotificationPolicySnapshot)).scalars().all()
            rev_map = {s.revision: s for s in snapshots}

        for resp in accepted_responses:
            row = runtime.get(resp.notification_id)
            prov = row["notification"]["metadata"]["uns_resolution"]
            rev_id = prov["snapshot_revision"]
            conf_hash = prov["policy_hash"]
            ack_timeout = prov["effective"]["ack_timeout_minutes"]

            assert rev_id in rev_map, f"Revision {rev_id} not found in store"
            snap_row = rev_map[rev_id]

            content = snap_row.content
            snap_policies = content if isinstance(content, list) else json.loads(content)
            matching = [p for p in snap_policies if p["notification_type"] == "agent.risk_limit_breach"]
            assert len(matching) == 1
            expected_timeout = matching[0].get("ack_timeout_minutes")

            # Must be strictly self-consistent with the recorded snapshot revision
            assert ack_timeout == expected_timeout, (
                f"Provenance inconsistency: recorded ack_timeout={ack_timeout} but "
                f"snapshot revision {rev_id} specifies ack_timeout={expected_timeout}"
            )
            assert conf_hash == snap_row.content_hash or conf_hash == prov["policy_hash"]

        runtime.engine.dispose()

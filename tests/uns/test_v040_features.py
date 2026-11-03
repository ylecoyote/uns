"""Tests for UNS v0.4.0 features (#43 PostgreSQL maintenance, #44 policy reload broadcast, #45 scoped RBAC)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import sessionmaker

from db.models import Base
from db.policy_store import PG_POLICY_RELOAD_CHANNEL
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)
from notification.policies import NotificationPolicy, PolicyStatus
from uns.api.auth import matches_scope_patterns
from uns.app import create_app
from uns.maintenance import _eligible, maintain
from uns.policy_runtime import (
    DEFAULT_POLICY_REDIS_CHANNEL,
    PolicyReloadEnvelope,
    PolicyRuntime,
    PostgresPolicyReloadListener,
    RedisPolicyReloadBroadcaster,
    RedisPolicyReloadSubscriber,
)
from uns.runtime import Runtime, work
from uns_mcp.runtime import MCPRuntimeConfig, RuntimeState
from uns_mcp.tools import SendSignalInput, get_effective_policy, send_signal


def _make_policy(notification_type: str = "system.alert", version: str = "1.0.0") -> NotificationPolicy:
    return NotificationPolicy(
        notification_type=notification_type,
        version=version,
        status=PolicyStatus.ACTIVE,
        intent=NotificationIntent.OPERATIONAL,
        channels=[Channel.WEBSOCKET],
        delivery_mode=DeliveryMode.BEST_EFFORT,
        require_ack=True,
        ack_timeout_minutes=15,
    )


class _InMemoryRedisBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


def test_eligible_query_compiles_for_postgresql_and_sqlite() -> None:
    """Issue #43: _eligible query compiles native UUID cast on PostgreSQL and hex replace on SQLite."""
    now = time.time()
    cutoff = now - 86400 * 90

    pg_stmt = select(work).where(*_eligible(cutoff, now, dialect_name="postgresql")).with_for_update()
    pg_sql = str(pg_stmt.compile(dialect=postgresql.dialect()))
    assert "CAST(uns_notifications.id AS UUID)" in pg_sql
    assert "FOR UPDATE" in pg_sql

    sqlite_stmt = select(work).where(*_eligible(cutoff, now, dialect_name="sqlite"))
    sqlite_sql = str(sqlite_stmt.compile(dialect=sqlite.dialect()))
    assert "replace(uns_notifications.id" in sqlite_sql


def test_postgresql_advisory_lock_and_lock_timeout_path_in_maintain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #43: PostgreSQL dialect path executes SET LOCAL lock_timeout, pg_advisory_xact_lock, and FOR UPDATE."""
    import uns.maintenance as maint_mod

    monkeypatch.setattr(maint_mod, "_schema_check", lambda _conn: None)
    db_file = tmp_path / "pg_sim.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    work.metadata.create_all(engine)

    driver_sql: list[str] = []
    compiled_pg_sql: list[str] = []
    real_begin = engine.begin

    class _ConnProxy:
        def __init__(self, conn: object) -> None:
            self._conn = conn
            self.dialect = SimpleNamespace(name="postgresql")

        def exec_driver_sql(self, statement: str, *args: object, **kwargs: object) -> object:
            driver_sql.append(statement)
            return SimpleNamespace(fetchall=lambda: [])

        def execute(self, statement: object, *args: object, **kwargs: object) -> object:
            if hasattr(statement, "compile"):
                pg_compiled = str(statement.compile(dialect=postgresql.dialect()))
                compiled_pg_sql.append(pg_compiled)
                if "uns_notifications" in pg_compiled and "CAST(" in pg_compiled:
                    return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
            return self._conn.execute(statement, *args, **kwargs)

    class _BeginCtx:
        def __enter__(self) -> _ConnProxy:
            self._ctx = real_begin()
            return _ConnProxy(self._ctx.__enter__())

        def __exit__(self, *exc: object) -> object:
            return self._ctx.__exit__(*exc)

    fake_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        begin=lambda: _BeginCtx(),
    )
    now = time.time()
    report = maintain(
        fake_engine,  # type: ignore[arg-type]
        cutoff=now - 3600,
        idempotency_seconds=600,
        batch_size=50,
        apply=True,
        operator="ci-tester",
        now=now,
    )
    assert report["applied"] is True
    assert report["deleted_rows"] == 0
    assert any("SET LOCAL lock_timeout = '30s'" in s for s in driver_sql)
    assert any("SELECT pg_advisory_xact_lock" in s for s in driver_sql)
    assert any("FOR UPDATE" in s for s in compiled_pg_sql)


def test_policy_snapshot_cache_and_redis_cross_process_reload(tmp_path: Path) -> None:
    """Issue #44: PolicyRuntime broadcasts activation over Redis Pub/Sub and refreshes peer nodes."""
    db_url = f"sqlite:///{tmp_path / 'policy_sync.db'}"
    engine_a = create_engine(db_url)
    engine_b = create_engine(db_url)
    Base.metadata.create_all(engine_a)
    work.metadata.create_all(engine_a)

    sessions_a = sessionmaker(bind=engine_a, expire_on_commit=False)
    sessions_b = sessionmaker(bind=engine_b, expire_on_commit=False)

    broker = _InMemoryRedisBroker()
    broadcaster_a = RedisPolicyReloadBroadcaster(broker, instance_id="node-a")

    runtime_a = PolicyRuntime(sessions_a, broadcaster=broadcaster_a)
    runtime_b = PolicyRuntime(sessions_b)

    # Verify cached PolicySnapshot returns distinct PolicyRegistry copies without re-parsing
    snap_b1 = runtime_b.warm_snapshot
    reg_b1 = snap_b1.registry()
    reg_b2 = snap_b1.registry()
    assert reg_b1 is not reg_b2

    # Subscribe node B to Redis policy reload broadcasts
    reloaded_revisions: list[int] = []
    runtime_b.register_reload_callback(lambda snap: reloaded_revisions.append(snap.revision))
    subscriber_b = RedisPolicyReloadSubscriber(runtime_b, origin_id="node-a-peer")

    # Activate a new policy revision on node A
    new_policy = _make_policy("deploy.production", version="2.0.0")
    runtime_a.store.save_policy(new_policy)

    assert len(broker.published) >= 1
    channel, payload = broker.published[-1]
    assert channel == DEFAULT_POLICY_REDIS_CHANNEL

    # Deliver the Redis pub/sub message to subscriber_b
    refreshed_snap = subscriber_b.handle_message(
        {"type": "message", "channel": channel, "data": payload}
    )
    assert refreshed_snap is not None
    assert runtime_b.warm_snapshot.registry().get("deploy.production") is not None
    assert len(reloaded_revisions) == 1

    # Verify self-origin messages are ignored
    self_sub = RedisPolicyReloadSubscriber(runtime_b, origin_id="node-a")
    ignored = self_sub.handle_message(
        {"type": "message", "channel": channel, "data": payload}
    )
    assert ignored is None


def test_postgres_listen_notify_policy_reload_listener(tmp_path: Path) -> None:
    """Issue #44: PostgresPolicyReloadListener polls pg_notify payloads and refreshes PolicyRuntime."""
    db_url = f"sqlite:///{tmp_path / 'pg_notify.db'}"
    engine_local = create_engine(db_url)
    engine_writer = create_engine(db_url)
    Base.metadata.create_all(engine_local)
    work.metadata.create_all(engine_local)

    runtime_local = PolicyRuntime(sessionmaker(bind=engine_local, expire_on_commit=False))
    runtime_writer = PolicyRuntime(sessionmaker(bind=engine_writer, expire_on_commit=False))

    # Save and activate a new policy on writer so runtime_local's warm_snapshot is behind
    runtime_writer.store.save_policy(_make_policy("security.incident", version="1.2.0"))
    target_snap = runtime_writer.warm_snapshot

    envelope = PolicyReloadEnvelope(
        revision=target_snap.revision,
        content_hash=target_snap.content_hash,
        origin_id="other-postgres-node",
    )

    class _FakeNotify:
        def __init__(self, payload: str) -> None:
            self.payload = payload

    class _FakeDriverConn:
        def __init__(self) -> None:
            self.notifies = [_FakeNotify(envelope.model_dump_json())]

    class _FakeRawConn:
        def __init__(self) -> None:
            self.dbapi_connection = _FakeDriverConn()

    class _FakeSAConn:
        def __init__(self) -> None:
            self.driver_sql: list[str] = []
            self.connection = _FakeRawConn()
            self.closed = False

        def execution_options(self, **kwargs: object) -> _FakeSAConn:
            return self

        def exec_driver_sql(self, stmt: str) -> None:
            self.driver_sql.append(stmt)

        def execute(self, stmt: object) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    fake_conn = _FakeSAConn()
    fake_pg_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        connect=lambda: fake_conn,
    )

    listener = PostgresPolicyReloadListener(
        fake_pg_engine,  # type: ignore[arg-type]
        runtime_local,
    )
    assert any(f"LISTEN {PG_POLICY_RELOAD_CHANNEL}" in cmd for cmd in fake_conn.driver_sql)
    envelopes = listener.poll()
    assert len(envelopes) == 1
    assert runtime_local.warm_snapshot.registry().get("security.incident") is not None
    listener.close()
    assert fake_conn.closed is True


def test_scoped_rbac_http_websocket_and_multi_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #45: Source- and namespace-scoped RBAC across HTTP, /ui/*, and WebSocket."""
    scoped_keys = [
        {
            "key": "deploy-producer-secret",
            "role": "producer",
            "principal": "team-deploy-producer",
            "allowed_sources": ["ci-*"],
            "allowed_namespaces": ["deploy.*"],
        },
        {
            "key": "deploy-responder-secret",
            "role": "responder",
            "principal": "team-deploy-responder",
            "allowed_sources": ["ci-*"],
            "allowed_namespaces": ["deploy.*"],
        },
        {
            "key": "deploy-observer-secret",
            "role": "observer",
            "principal": "team-deploy-observer",
            "allowed_sources": ["*"],
            "allowed_namespaces": ["deploy.*"],
        },
    ]
    monkeypatch.setenv("UNS_SCOPED_API_KEYS", json.dumps(scoped_keys))
    monkeypatch.setenv("UNS_DATABASE_URL", f"sqlite:///{tmp_path / 'rbac.db'}")
    monkeypatch.setenv("UNS_CREATE_TABLES", "true")
    monkeypatch.setenv("UNS_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("UNS_ALLOW_UNAUTHENTICATED_REQUESTS", "false")
    monkeypatch.setenv("UNS_API_KEY", "root-admin-secret")
    monkeypatch.setenv("UNS_PRODUCER_API_KEY", "global-producer-secret")
    monkeypatch.setenv("UNS_RESPONDER_API_KEY", "global-responder-secret")
    monkeypatch.setenv("UNS_OBSERVER_API_KEY", "global-observer-secret")

    app = create_app()

    with TestClient(app) as client:
        store = app.state.policy_store
        store.save_policy(_make_policy("deploy.approval", version="1.0.0"))
        store.save_policy(_make_policy("system.alert", version="1.0.0"))

        agent_id = str(uuid4())

        with client.websocket_connect(
            f"/ws/agents/{agent_id}",
            headers={"X-UNS-API-Key": "deploy-responder-secret"},
        ) as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"

            # 1. Scoped producer can send matching source + namespace
            ok_resp = client.post(
                "/api/v1/notifications",
                headers={"X-UNS-API-Key": "deploy-producer-secret"},
                json={
                    "notification_type": "deploy.approval",
                    "title": "Deploy v0.4.0",
                    "message": "Approve production rollout",
                    "source": "ci-github",
                    "intent": NotificationIntent.OPERATIONAL.value,
                    "autonomy_context": {
                        "autonomy_mode": AutonomyMode.LIVE.value,
                        "agent_id": agent_id,
                    },
                },
            )
            assert ok_resp.status_code in (200, 202), ok_resp.text
            assert ok_resp.json()["status"] == "DELIVERED"
            deploy_notif_id = ok_resp.json()["notification_id"]
            pushed = ws.receive_json()
            assert pushed["type"] == "notification"
            assert pushed["notification"]["notification_type"] == "deploy.approval"

            # 2. Scoped producer is rejected (403) when source does not match allowed_sources
            bad_source_resp = client.post(
                "/api/v1/notifications",
                headers={"X-UNS-API-Key": "deploy-producer-secret"},
                json={
                    "notification_type": "deploy.approval",
                    "title": "Deploy from untrusted source",
                    "message": "Should fail",
                    "source": "manual-script",
                    "intent": NotificationIntent.OPERATIONAL.value,
                    "autonomy_context": {
                        "autonomy_mode": AutonomyMode.LIVE.value,
                        "agent_id": agent_id,
                    },
                },
            )
            assert bad_source_resp.status_code == 403
            assert bad_source_resp.json()["detail"]["error"] == "namespace_or_source_forbidden"

            # 3. Scoped producer is rejected (403) when notification_type is outside allowed_namespaces
            bad_ns_resp = client.post(
                "/api/v1/notifications",
                headers={"X-UNS-API-Key": "deploy-producer-secret"},
                json={
                    "notification_type": "system.alert",
                    "title": "System alert",
                    "message": "Out of namespace",
                    "source": "ci-github",
                    "intent": NotificationIntent.OPERATIONAL.value,
                    "autonomy_context": {
                        "autonomy_mode": AutonomyMode.LIVE.value,
                        "agent_id": agent_id,
                    },
                },
            )
            assert bad_ns_resp.status_code == 403
            assert bad_ns_resp.json()["detail"]["error"] == "namespace_or_source_forbidden"

            # Send a system.alert using the unrestricted root admin key (scoped WS will not receive it)
            sys_resp = client.post(
                "/api/v1/notifications",
                headers={"X-UNS-API-Key": "root-admin-secret"},
                json={
                    "notification_type": "system.alert",
                    "title": "Kernel panic",
                    "message": "Node 3 unreachable",
                    "source": "node-monitor",
                    "intent": NotificationIntent.OPERATIONAL.value,
                    "autonomy_context": {
                        "autonomy_mode": AutonomyMode.LIVE.value,
                        "agent_id": agent_id,
                    },
                },
            )
            assert sys_resp.status_code in (200, 202)
            sys_notif_id = sys_resp.json()["notification_id"]

            # 4. Scoped responder can ack deploy.approval (200) but gets 403 on system.alert
            ack_ok = client.post(
                f"/api/v1/notifications/{deploy_notif_id}/ack",
                headers={"X-UNS-API-Key": "deploy-responder-secret"},
                json={"acked_by": "team-deploy-responder"},
            )
            assert ack_ok.status_code == 200

            ack_forbidden = client.post(
                f"/api/v1/notifications/{sys_notif_id}/ack",
                headers={"X-UNS-API-Key": "deploy-responder-secret"},
                json={"acked_by": "team-deploy-responder"},
            )
            assert ack_forbidden.status_code == 403
            assert ack_forbidden.json()["detail"]["error"] == "namespace_or_source_forbidden"

            # 5. Scoped observer only sees deploy.* in /ui/deliveries and /ui/policies/active
            deliveries_resp = client.get(
                "/ui/deliveries",
                headers={"X-UNS-API-Key": "deploy-observer-secret"},
            )
            assert deliveries_resp.status_code == 200
            items = deliveries_resp.json()["items"]
            assert len(items) == 1
            assert items[0]["notification_type"] == "deploy.approval"

            # Scoped observer gets 403 on /ui/deliveries/{sys_notif_id} and /ui/policies/effective for system.alert
            timeline_forbidden = client.get(
                f"/ui/deliveries/{sys_notif_id}",
                headers={"X-UNS-API-Key": "deploy-observer-secret"},
            )
            assert timeline_forbidden.status_code == 403

            eff_forbidden = client.get(
                "/ui/policies/effective",
                params={"notification_type": "system.alert", "autonomy_mode": "LIVE"},
                headers={"X-UNS-API-Key": "deploy-observer-secret"},
            )
            assert eff_forbidden.status_code == 403

            # 6. WebSocket replay filters out system.alert for deploy-responder-secret and blocks out-of-scope ack
            ws.send_json({"type": "subscribe", "last_seen": "1970-01-01T00:00:00Z"})
            subscribed = ws.receive_json()
            assert subscribed["type"] == "subscribed"
            replayed_types = [n["notification_type"] for n in subscribed["missed_notifications"]]
            assert replayed_types == ["deploy.approval"]

            ws.send_json({"type": "ack", "notification_id": sys_notif_id})
            err_frame = ws.receive_json()
            assert err_frame["type"] == "error"
            assert err_frame["error"] == "namespace_or_source_forbidden"


@pytest.mark.asyncio
async def test_uns_mcp_source_and_namespace_scoping(tmp_path: Path) -> None:
    """Issue #45: uns-mcp enforces allowed_sources and allowed_namespaces across MCP tools."""
    runtime = Runtime(f"sqlite:///{tmp_path / 'mcp_rbac.db'}", create_tables=True)
    try:
        store = runtime.policy_runtime.store
        store.save_policy(_make_policy("deploy.canary", version="1.0.0"))
        store.save_policy(_make_policy("system.alert", version="1.0.0"))

        state = RuntimeState(runtime=runtime)
        config = MCPRuntimeConfig(
            mode="stdio-persistent",
            read_only=False,
            require_delivery_confirmation=False,
            operator_principal="mcp-deploy-operator",
            allowed_sources=frozenset({"agent-*"}),
            allowed_namespaces=frozenset({"deploy.*"}),
        )
        agent_id = uuid4()

        # Allowed send
        res_ok = await send_signal(
            SendSignalInput(
                notification_type="deploy.canary",
                title="Canary rollout",
                message="5% traffic",
                source="agent-deployer",
                intent=NotificationIntent.OPERATIONAL,
                deliver=True,
                operator_intent="deliver",
                autonomy_context={
                    "autonomy_mode": AutonomyMode.LIVE.value,
                    "agent_id": str(agent_id),
                },
            ),
            config=config,
            runtime_state=state,
        )
        assert res_ok.get("notification_id") is not None

        # Disallowed source
        with pytest.raises(ValueError, match="not authorized"):
            await send_signal(
                SendSignalInput(
                    notification_type="deploy.canary",
                    title="Untrusted source",
                    message="Blocked",
                    source="external-webhook",
                    intent=NotificationIntent.OPERATIONAL,
                    deliver=True,
                    operator_intent="deliver",
                    autonomy_context={
                        "autonomy_mode": AutonomyMode.LIVE.value,
                        "agent_id": str(agent_id),
                    },
                ),
                config=config,
                runtime_state=state,
            )

        # Disallowed namespace on get_effective_policy
        with pytest.raises(ValueError, match="not authorized"):
            await get_effective_policy(
                notification_type="system.alert",
                intent=NotificationIntent.OPERATIONAL.value,
                autonomy_mode=AutonomyMode.LIVE.value,
                config=config,
                runtime_state=state,
            )
    finally:
        runtime.engine.dispose()


def test_matches_scope_patterns_helper() -> None:
    assert matches_scope_patterns("deploy.production", ()) is True
    assert matches_scope_patterns("deploy.production", ("*",)) is True
    assert matches_scope_patterns("deploy.production", ("deploy.*",)) is True
    assert matches_scope_patterns("system.alert", ("deploy.*", "security.*")) is False
    assert matches_scope_patterns(None, ("deploy.*",)) is False

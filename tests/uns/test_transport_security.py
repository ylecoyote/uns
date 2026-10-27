"""Authentication and durable response boundaries shared across transports."""
from __future__ import annotations

import asyncio
import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel
from notification.service import SimpleAdapterRegistry
from uns.app import create_app
from uns.responses import SendNotificationRequest
from uns.runtime import Runtime


class RecordingAdapter(BaseAdapter):
    channel = Channel.SLACK

    def __init__(self):
        self.calls = 0
        self.success = True

    async def deliver(self, notification):
        self.calls += 1
        return DeliveryResult(success=self.success, channel=self.channel)

    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY)


def signal(**overrides):
    payload = {
        "notification_type": "security.test",
        "intent": "SAFETY",
        "title": "test",
        "message": "test",
        "source": "test",
        "autonomy_context": {"agent_id": str(uuid4()), "autonomy_mode": "LIVE"},
    }
    payload.update(overrides)
    return SendNotificationRequest(**payload)


@pytest.fixture
def configured(tmp_path, monkeypatch):
    from notification.policies import PolicyRegistry, configure_policy_registry
    from notification.rate_limiting import configure_rate_limiter
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    for name in ("UNS_API_KEY", "UNS_API_KEY", "UNS_ALLOW_UNAUTHENTICATED_READS",
                 "UNS_ALLOW_UNAUTHENTICATED_READS", "UNS_POLICY_DIR", "UNS_POLICY_DIR"):
        monkeypatch.delenv(name, raising=False)
    adapter = RecordingAdapter()
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    runtime = Runtime(f"sqlite:///{tmp_path}/security.db", adapters=registry, create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_api_key = "test-key"
    app.state.uns_api_principal = "verified-operator"
    yield app, runtime, adapter
    runtime.engine.dispose()


@pytest.mark.parametrize("path", [
    "/ui/audit", "/ui/deliveries", "/ui/invariants", "/api/v1/dlq",
    "/ready", "/readyz", "/metrics",
    "/api/v1/channels/health", f"/api/v1/notifications/{uuid4()}",
    f"/api/v1/notifications/{uuid4()}/ack-status", f"/api/v1/notifications/{uuid4()}/delivery",
])
def test_reads_default_deny(configured, path):
    app, _, _ = configured
    client = TestClient(app)
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_legacy_read_mode_does_not_allow_any_mutation(configured):
    app, _, _ = configured
    app.state.uns_allow_unauthenticated_reads = True
    client = TestClient(app)
    assert client.get("/ui/audit").status_code == 200
    assert client.get("/health").status_code == 200
    for protected in ("/metrics", "/ready", "/readyz", "/api/v1/runtime/dead-letters"):
        assert client.get(protected).status_code == 401
    for path, method, payload in [
        ("/api/v1/notifications", "post", signal().model_dump(mode="json")),
        ("/api/v1/notifications/simulate", "post", signal().model_dump(mode="json")),
        (f"/api/v1/notifications/{uuid4()}/ack", "post", {}),
        (f"/api/v1/notifications/{uuid4()}/dismiss", "post", {}),
        ("/api/v1/policies/reload", "post", {"policy_dir": "/tmp"}),
        (f"/api/v1/dlq/{uuid4()}", "delete", None),
        (f"/api/v1/runtime/notifications/{uuid4()}/replay", "post", None),
    ]:
        assert client.request(method, path, json=payload).status_code == 401, path
    with pytest.raises(WebSocketDisconnect) as rejected, client.websocket_connect(f"/ws/agents/{uuid4()}"):
        pass
    assert rejected.value.code == 1008


def test_fixture_only_http_composition_still_requires_write_auth():
    app = create_app(skip_persistence_config=True)
    app.state.uns_api_key = "test-key"
    client = TestClient(app)
    assert client.post("/api/v1/notifications", json=signal().model_dump(mode="json")).status_code == 401
    assert client.delete(f"/api/v1/dlq/{uuid4()}").status_code == 401
    assert client.post("/api/v1/policies/reload", json={"policy_dir": "/tmp"}).status_code == 401


def test_unconfigured_read_auth_fails_closed(configured):
    app, _, _ = configured
    app.state.uns_api_key = None
    assert TestClient(app).get("/ui/audit").status_code == 503


def test_websocket_uses_verified_actor_and_durable_ack(configured):
    app, runtime, _ = configured
    payload = signal()
    accepted = asyncio.run(runtime.send(payload, principal="verified-operator"))
    # Old compatibility flag cannot allow caller attribution spoofing.
    app.state.uns_allow_principal_override = True
    denied = TestClient(app).post(
        f"/api/v1/notifications/{accepted.notification_id}/ack",
        json={"acked_by": "imposter"}, headers={"Authorization": "Bearer test-key"},
    )
    assert denied.status_code == 403
    token = base64.urlsafe_b64encode(b"test-key").decode().rstrip("=")
    with TestClient(app).websocket_connect(
        f"/ws/agents/{payload.autonomy_context.agent_id}",
        subprotocols=["uns.v1", f"bearer.{token}"],
        headers={"Origin": "http://localhost:5173"},
    ) as ws:
        assert ws.accepted_subprotocol == "uns.v1"
        assert ws.receive_json()["type"] == "connected"
        ws.send_json({"type": "ack", "notification_id": str(accepted.notification_id), "acked_by": "imposter"})
        assert ws.receive_json()["error"] == "principal_override_forbidden"
        assert runtime.get(accepted.notification_id)["ack_status"] == "PENDING"
        ws.send_json({"type": "ack", "notification_id": "malformed"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "ack", "notification_id": str(accepted.notification_id)})
        response = ws.receive_json()
        assert response["ack_status"] == "ACKED"
        assert response["acked_by"] == "verified-operator"
    assert runtime.get(accepted.notification_id)["ack_status"] == "ACKED"
    assert len(runtime.audit_store.get_ack_audits_for_notification(accepted.notification_id)) == 1


def test_websocket_rejects_untrusted_origin_and_query_credentials(configured):
    app, _, _ = configured
    client = TestClient(app)
    for suffix, headers in [
        ("?token=test-key", {}),
        ("", {"Authorization": "Bearer test-key", "Origin": "https://untrusted.example"}),
    ]:
        with pytest.raises(WebSocketDisconnect) as rejected, client.websocket_connect(f"/ws/agents/{uuid4()}{suffix}", headers=headers):
            pass
        assert rejected.value.code == 1008


@pytest.mark.asyncio
async def test_http_and_mcp_previews_use_durable_policy_authority(configured):
    from mcp.shared.memory import create_connected_server_and_client_session

    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policies import NotificationPolicy
    from uns_mcp.factory import create_mcp_server

    app, runtime, _ = configured
    policy = NotificationPolicy.from_dict({
        "notification_type": "security.test", "version": "1", "status": "ACTIVE",
        "delivery_mode": "GUARANTEED", "channels": {"LIVE": ["EMAIL"]},
        "require_ack": {"LIVE": True},
    })
    SQLAlchemyPolicyStore(runtime.sessions).save_snapshot([policy])
    client = TestClient(app, headers={"Authorization": "Bearer test-key"})
    payload = signal().model_dump(mode="json")
    preview = client.post("/api/v1/notifications/simulate", json=payload)
    assert preview.status_code == 200
    assert preview.json()["channels_attempted"] == ["EMAIL"]
    effective = client.get("/ui/policies/effective", params={
        "notification_type": "security.test", "intent": "SAFETY", "autonomy_mode": "LIVE",
    })
    assert effective.json()["effective"]["channels"] == ["EMAIL"]
    payload["require_ack"] = False
    assert client.post("/api/v1/notifications/simulate", json=payload).status_code == 422
    assert client.post("/api/v1/notifications", json=payload).status_code == 422
    async with create_connected_server_and_client_session(create_mcp_server(runtime=runtime)) as session:
        result = await session.call_tool("simulate_signal", {"payload": payload})
        assert result.isError


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    from notification.rate_limiting import configure_rate_limiter

    configure_rate_limiter({})
    for name in ("UNS_POLICY_DIR", "UNS_POLICY_DIR"):
        monkeypatch.delenv(name, raising=False)
    runtimes = [Runtime(f"sqlite:///{tmp_path}/{label}.db", create_tables=True) for label in ("a", "b")]
    identifiers = []
    for label, runtime in zip(("a", "b"), runtimes):
        payload = signal().model_copy(update={"notification_type": f"private.{label}", "title": label})
        accepted = runtime.accept(payload, principal=label)
        identifiers.append(str(accepted.notification_id))
    yield runtimes, identifiers
    for runtime in runtimes:
        runtime.engine.dispose()


def isolated_app(runtime, label):
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_api_key = f"key-{label}"
    app.state.uns_api_principal = f"principal-{label}"
    return app


@pytest.mark.parametrize("later_transport", ["http", "mcp"])
@pytest.mark.parametrize("path", ["/ui/deliveries", "/ui/audit"])
def test_http_reads_stay_bound_to_authenticated_app(isolated_stores, path, later_transport):
    from uns_mcp.factory import create_mcp_server

    runtimes, identifiers = isolated_stores
    app = isolated_app(runtimes[0], "a")
    if later_transport == "http":
        isolated_app(runtimes[1], "b")
    else:
        create_mcp_server(runtime=runtimes[1])
    response = TestClient(app).get(path, headers={"Authorization": "Bearer key-a"})
    assert response.status_code == 200
    assert {item["notification_id"] for item in response.json()["items"]} == {identifiers[0]}


@pytest.mark.parametrize("later_transport", ["http", "mcp"])
def test_http_timeline_cannot_read_another_runtime(isolated_stores, later_transport):
    from uns_mcp.factory import create_mcp_server

    runtimes, identifiers = isolated_stores
    app = isolated_app(runtimes[0], "a")
    if later_transport == "http":
        isolated_app(runtimes[1], "b")
    else:
        create_mcp_server(runtime=runtimes[1])
    client = TestClient(app, headers={"Authorization": "Bearer key-a"})
    assert client.get(f"/ui/deliveries/{identifiers[1]}").status_code == 404
    own = client.get(f"/ui/deliveries/{identifiers[0]}")
    assert own.status_code == 200
    assert own.json()["notification_id"] == identifiers[0]
    assert own.json()["runtime_state"]["delivery_status"] == "PENDING"


@pytest.mark.asyncio
@pytest.mark.parametrize("later_transport", ["http", "mcp"])
@pytest.mark.parametrize("tool", ["list_deliveries", "list_audit_events"])
async def test_mcp_reads_stay_bound_to_server_runtime(isolated_stores, tool, later_transport):
    import json

    from mcp.shared.memory import create_connected_server_and_client_session

    from uns_mcp.factory import create_mcp_server

    runtimes, identifiers = isolated_stores
    server = create_mcp_server(runtime=runtimes[0])
    if later_transport == "http":
        isolated_app(runtimes[1], "b")
    else:
        create_mcp_server(runtime=runtimes[1])
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(tool, {"limit": 25})
        assert not result.isError
        body = json.loads(result.content[0].text)
        assert {item["notification_id"] for item in body["items"]} == {identifiers[0]}


def test_scoped_credentials_enforce_least_privilege(configured):
    app, _, _ = configured
    app.state.uns_producer_api_key = "producer-key"
    app.state.uns_producer_api_principal = "wyredeck-producer"
    app.state.uns_responder_api_key = "responder-key"
    app.state.uns_responder_api_principal = "oncall-responder"
    app.state.uns_observer_api_key = "observer-key"
    app.state.uns_observer_api_principal = "console-observer"

    client = TestClient(app)
    producer_headers = {"Authorization": "Bearer producer-key"}
    responder_headers = {"Authorization": "Bearer responder-key"}
    observer_headers = {"Authorization": "Bearer observer-key"}
    admin_headers = {"Authorization": "Bearer test-key"}

    # Producer can submit and simulate, and read status, but cannot ack or invoke admin routes
    sent = client.post(
        "/api/v1/notifications",
        json=signal(require_ack=True).model_dump(mode="json"),
        headers=producer_headers,
    )
    assert sent.status_code == 202
    nid = sent.json()["notification_id"]

    sim = client.post(
        "/api/v1/notifications/simulate",
        json=signal().model_dump(mode="json"),
        headers=producer_headers,
    )
    assert sim.status_code == 200
    assert client.get(f"/api/v1/notifications/{nid}", headers=producer_headers).status_code == 200
    assert (
        client.post(f"/api/v1/notifications/{nid}/ack", json={}, headers=producer_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/policies/reload", json={"policy_dir": "config/notification_policies"}, headers=producer_headers
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/dlq/{nid}", headers=producer_headers).status_code == 403
    assert (
        client.post(f"/api/v1/runtime/notifications/{nid}/replay", headers=producer_headers).status_code
        == 403
    )

    # Observer can read status, Console, and /readyz, but cannot send, ack, or administer
    assert client.get("/readyz", headers=observer_headers).status_code == 200
    assert client.get("/ui/audit", headers=observer_headers).status_code == 200
    assert (
        client.post(
            "/api/v1/notifications",
            json=signal().model_dump(mode="json"),
            headers=observer_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/notifications/{nid}/ack", json={}, headers=observer_headers).status_code
        == 403
    )

    # Responder can acknowledge and read, but cannot submit or administer
    assert (
        client.post(
            "/api/v1/notifications",
            json=signal().model_dump(mode="json"),
            headers=responder_headers,
        ).status_code
        == 403
    )
    acked = client.post(
        f"/api/v1/notifications/{nid}/ack",
        json={"acked_by": "oncall-responder"},
        headers=responder_headers,
    )
    assert acked.status_code == 200
    assert acked.json()["acked_by"] == "oncall-responder"

    # Admin key still has full access
    assert client.get("/readyz", headers=admin_headers).status_code == 200


def test_deduplicated_follower_exposes_structured_obligation_owner_and_inherited_ack(configured):
    app, _, _ = configured
    client = TestClient(app, headers={"Authorization": "Bearer test-key"})

    owner_resp = client.post(
        "/api/v1/notifications",
        json=signal(require_ack=True, dedup_key="wyredeck-provider-degraded").model_dump(mode="json"),
    )
    assert owner_resp.status_code == 202
    owner_body = owner_resp.json()
    owner_id = owner_body["notification_id"]
    assert owner_body["obligation_owner_id"] == owner_id
    assert owner_body["effective_ack_status"] == "PENDING"
    assert owner_body["ack_inherited"] is False

    follower_resp = client.post(
        "/api/v1/notifications",
        json=signal(require_ack=True, dedup_key="wyredeck-provider-degraded").model_dump(mode="json"),
    )
    assert follower_resp.status_code == 202
    follower_body = follower_resp.json()
    follower_id = follower_body["notification_id"]
    assert follower_body["status"] == "DEDUPLICATED"
    assert follower_body["ack_status"] is None
    assert follower_body["obligation_owner_id"] == owner_id
    assert follower_body["effective_ack_status"] == "PENDING"
    assert follower_body["ack_inherited"] is True

    # Acknowledge the canonical owner and verify follower status reflects inherited ACKED state
    ack_resp = client.post(
        f"/api/v1/notifications/{owner_id}/ack",
        json={"acked_by": "verified-operator"},
    )
    assert ack_resp.status_code == 200

    follower_status = client.get(f"/api/v1/notifications/{follower_id}").json()
    assert follower_status["ack_status"] is None
    assert follower_status["obligation_owner_id"] == owner_id
    assert follower_status["effective_ack_status"] == "ACKED"
    assert follower_status["ack_inherited"] is True

    follower_ack_status = client.get(f"/api/v1/notifications/{follower_id}/ack-status").json()
    assert follower_ack_status["ack_status"] is None
    assert follower_ack_status["obligation_owner_id"] == owner_id
    assert follower_ack_status["effective_ack_status"] == "ACKED"
    assert follower_ack_status["ack_inherited"] is True


def test_daemon_startup_requires_explicit_persistence_or_in_memory_flag(monkeypatch, tmp_path):
    from uns.config import ensure_daemon_persistence_configured

    monkeypatch.delenv("UNS_DATABASE_URL", raising=False)
    monkeypatch.delenv("UNS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("UNS_ALLOW_IN_MEMORY", raising=False)
    monkeypatch.delenv("UNS_ALLOW_IN_MEMORY", raising=False)

    with pytest.raises(RuntimeError, match="Refusing to start the UNS daemon with volatile in-memory storage"):
        ensure_daemon_persistence_configured()

    assert ensure_daemon_persistence_configured(allow_in_memory=True) == "sqlite://"

    db_url = f"sqlite:///{tmp_path / 'uns.db'}"
    monkeypatch.setenv("UNS_DATABASE_URL", db_url)
    assert ensure_daemon_persistence_configured() == db_url


def test_readyz_reports_persistence_mode_and_operational_progress(configured):
    app, _, _ = configured
    client = TestClient(app, headers={"Authorization": "Bearer test-key"})
    ready = client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["persistence_mode"] == "persistent"
    progress = body["operational_progress"]
    assert set(progress) >= {
        "pending_count",
        "oldest_pending_age_seconds",
        "overdue_ack_count",
        "pending_callback_count",
        "oldest_callback_retry_age_seconds",
        "unresolved_failure_count",
    }


def test_ui_session_introspects_principal_scopes_and_persistence_mode(configured):
    app, _, _ = configured
    app.state.uns_producer_api_key = "producer-key"
    app.state.uns_producer_api_principal = "wyredeck-producer"
    app.state.uns_responder_api_key = "responder-key"
    app.state.uns_responder_api_principal = "oncall-responder"
    app.state.uns_observer_api_key = "observer-key"
    app.state.uns_observer_api_principal = "console-observer"

    client = TestClient(app)

    assert client.get("/ui/session").status_code == 401
    assert client.get("/ui/session", headers={"Authorization": "Bearer invalid-key"}).status_code == 401

    obs = client.get("/ui/session", headers={"Authorization": "Bearer observer-key"})
    assert obs.status_code == 200
    assert obs.json() == {
        "subject": "console-observer",
        "scopes": ["observer"],
        "persistence_mode": "persistent",
    }

    prod = client.get("/ui/session", headers={"Authorization": "Bearer producer-key"})
    assert prod.status_code == 200
    assert prod.json() == {
        "subject": "wyredeck-producer",
        "scopes": ["observer", "producer"],
        "persistence_mode": "persistent",
    }

    resp = client.get("/ui/session", headers={"Authorization": "Bearer responder-key"})
    assert resp.status_code == 200
    assert resp.json() == {
        "subject": "oncall-responder",
        "scopes": ["observer", "responder"],
        "persistence_mode": "persistent",
    }

    adm = client.get("/ui/session", headers={"Authorization": "Bearer test-key"})
    assert adm.status_code == 200
    assert adm.json() == {
        "subject": "verified-operator",
        "scopes": ["admin", "observer", "producer", "responder"],
        "persistence_mode": "persistent",
    }


def test_ui_delivery_timeline_projects_obligation_lineage_and_bounds_events(configured):
    app, runtime, _ = configured
    client = TestClient(app, headers={"Authorization": "Bearer test-key"})

    owner_resp = client.post(
        "/api/v1/notifications",
        json=signal(require_ack=True, dedup_key="ui-lineage-key").model_dump(mode="json"),
    )
    assert owner_resp.status_code == 202
    owner_id = owner_resp.json()["notification_id"]

    follower_resp = client.post(
        "/api/v1/notifications",
        json=signal(require_ack=True, dedup_key="ui-lineage-key").model_dump(mode="json"),
    )
    assert follower_resp.status_code == 202
    follower_id = follower_resp.json()["notification_id"]

    # Append > 100 synthetic runtime events to verify the 100-event bound
    with runtime.sessions.begin() as session:
        for idx in range(110):
            runtime._event(session, str(owner_id), "SYNTHETIC_CHECK", {"seq": idx})

    owner_timeline = client.get(f"/ui/deliveries/{owner_id}")
    assert owner_timeline.status_code == 200
    owner_rt = owner_timeline.json()["runtime_state"]
    assert owner_rt["obligation_owner_id"] == owner_id
    assert owner_rt["ack_inherited"] is False
    assert owner_rt["obligation_resolution_status"] == "RESOLVED"
    assert owner_rt["events_truncated"] is True
    assert owner_rt["events_total_count"] >= 111
    assert len(owner_rt["events"]) == 100
    assert owner_rt["events"][-1]["payload"]["seq"] == 109

    follower_timeline = client.get(f"/ui/deliveries/{follower_id}")
    assert follower_timeline.status_code == 200
    follower_rt = follower_timeline.json()["runtime_state"]
    assert follower_rt["obligation_owner_id"] == owner_id
    assert follower_rt["effective_ack_status"] == "PENDING"
    assert follower_rt["ack_inherited"] is True
    assert follower_rt["obligation_resolution_status"] == "RESOLVED"
    assert follower_rt["events_truncated"] is False


def test_ui_active_policies_catalog_and_default_policy_reload(configured, tmp_path, monkeypatch):
    import yaml

    app, _, _ = configured
    client = TestClient(app, headers={"Authorization": "Bearer test-key"})

    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    (policy_dir / "ops.yaml").write_text(
        yaml.safe_dump(
            {
                "notification_type": "ops.console_test",
                "version": "1.2.0",
                "status": "ACTIVE",
                "intent": "OPERATIONAL",
                "delivery_mode": "GUARANTEED",
                "channels": {"LIVE": ["SLACK", "WEBSOCKET"]},
                "require_ack": {"LIVE": True},
                "ack_timeout_minutes": 10,
                "dedup_window_seconds": 180,
            }
        )
    )
    monkeypatch.setenv("UNS_POLICY_DIR", str(policy_dir))

    # Reload with empty body {} -> defaults to UNS_POLICY_DIR
    reload_resp = client.post("/api/v1/policies/reload", json={})
    assert reload_resp.status_code == 200, reload_resp.text
    assert reload_resp.json()["policy_count"] == 1
    assert reload_resp.json()["notification_types"] == ["ops.console_test"]

    active_resp = client.get("/ui/policies/active")
    assert active_resp.status_code == 200
    payload = active_resp.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["notification_type"] == "ops.console_test"
    assert payload["items"][0]["channels"] == ["SLACK", "WEBSOCKET"]
    assert payload["items"][0]["delivery_mode"] == "GUARANTEED"
    assert payload["items"][0]["require_ack"] is True
    assert payload["items"][0]["ack_timeout_seconds"] == 600
    assert payload["items"][0]["dedup_window_seconds"] == 180


def test_ui_policy_revisions_returns_lineage_across_statuses_and_filters(configured):
    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policies import NotificationPolicy

    app, runtime, _ = configured
    app.state.uns_observer_api_key = "observer-key"
    app.state.uns_observer_api_principal = "console-observer"

    store = SQLAlchemyPolicyStore(runtime.sessions)
    # Persist v1.0.0 ACTIVE, then supersede with v2.0.0 ACTIVE (retiring v1.0.0)
    store.save_policy(
        NotificationPolicy.from_dict(
            {
                "notification_type": "trading.order_placed",
                "version": "1.0.0",
                "status": "ACTIVE",
                "intent": "GOVERNANCE",
                "delivery_mode": "GUARANTEED",
                "channels": {"LIVE": ["SLACK"]},
                "require_ack": {"LIVE": True},
                "dedup_window_seconds": 300,
            }
        )
    )
    store.save_policy(
        NotificationPolicy.from_dict(
            {
                "notification_type": "trading.order_placed",
                "version": "2.0.0",
                "status": "ACTIVE",
                "intent": "GOVERNANCE",
                "delivery_mode": "GUARANTEED",
                "channels": {"LIVE": ["SLACK", "EMAIL"]},
                "require_ack": {"LIVE": True},
                "dedup_window_seconds": 120,
            }
        )
    )
    # Persist PREVIEW and DRAFT policies
    store.save_policy(
        NotificationPolicy.from_dict(
            {
                "notification_type": "trading.order_placed",
                "version": "2.1.0",
                "status": "PREVIEW",
                "intent": "GOVERNANCE",
                "delivery_mode": "BEST_EFFORT",
                "channels": {"LIVE": ["WEBSOCKET"]},
                "require_ack": {"LIVE": False},
                "dedup_window_seconds": 60,
            }
        )
    )
    store.save_policy(
        NotificationPolicy.from_dict(
            {
                "notification_type": "ops.canary_check",
                "version": "0.1.0",
                "status": "DRAFT",
                "intent": "OPERATIONAL",
                "delivery_mode": "BEST_EFFORT",
                "channels": {"LIVE": ["WEBSOCKET"]},
                "require_ack": {"LIVE": False},
                "dedup_window_seconds": 90,
            }
        )
    )

    unauth_client = TestClient(app)
    assert unauth_client.get("/ui/policies/revisions").status_code == 401

    observer_client = TestClient(app, headers={"Authorization": "Bearer observer-key"})
    resp = observer_client.get("/ui/policies/revisions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 4
    # Deterministic ordering: notification_type ASC, version DESC
    assert [
        (item["notification_type"], item["version"], item["status"])
        for item in body["items"]
    ] == [
        ("ops.canary_check", "0.1.0", "DRAFT"),
        ("trading.order_placed", "2.1.0", "PREVIEW"),
        ("trading.order_placed", "2.0.0", "ACTIVE"),
        ("trading.order_placed", "1.0.0", "RETIRED"),
    ]
    for item in body["items"]:
        assert item["config_hash"]
        assert item["created_at"]
        assert item["updated_at"]

    # Filter by notification_type and status
    retired_only = observer_client.get(
        "/ui/policies/revisions",
        params={"notification_type": "trading.order_placed", "status": "RETIRED"},
    )
    assert retired_only.status_code == 200
    retired_payload = retired_only.json()
    assert retired_payload["total_count"] == 1
    assert retired_payload["items"][0]["version"] == "1.0.0"
    assert retired_payload["items"][0]["status"] == "RETIRED"
    assert retired_payload["items"][0]["channels"] == ["SLACK"]


def test_f01_deliveries_deduplicates_retry_rows_and_timeline_reflects_runtime_replay(configured):
    """F-01: GET /ui/deliveries deduplicates by notification_id before filtering/counting; timeline reflects runtime_state."""
    from datetime import UTC, datetime, timedelta

    from db.models import NotificationAuditRecord

    app, runtime, adapter = configured
    client = TestClient(app, headers={"Authorization": "Bearer test-key"})

    nid = uuid4()
    agent_id = uuid4()
    t0 = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
    with runtime.sessions() as session:
        # Earlier FAILED attempt followed by later DELIVERED attempt for the same notification_id
        session.add(
            NotificationAuditRecord(
                id=uuid4(),
                notification_id=nid,
                notification_type="security.test",
                status="FAILED",
                channels_attempted=["SLACK"],
                channels_succeeded=[],
                channels_failed=["SLACK"],
                delivery_mode="GUARANTEED",
                autonomy_mode="LIVE",
                intent="SAFETY",
                agent_id=agent_id,
                title="Retry test",
                source="test",
                notification_created_at=t0,
                delivered_at=t0,
                created_at=t0,
                error_message="Initial timeout",
            )
        )
        session.add(
            NotificationAuditRecord(
                id=uuid4(),
                notification_id=nid,
                notification_type="security.test",
                status="DELIVERED",
                channels_attempted=["SLACK"],
                channels_succeeded=["SLACK"],
                channels_failed=[],
                delivery_mode="GUARANTEED",
                autonomy_mode="LIVE",
                intent="SAFETY",
                agent_id=agent_id,
                title="Retry test",
                source="test",
                notification_created_at=t0,
                delivered_at=t0 + timedelta(seconds=5),
                created_at=t0 + timedelta(seconds=5),
            )
        )
        session.commit()

    all_resp = client.get("/ui/deliveries")
    assert all_resp.status_code == 200
    all_body = all_resp.json()
    assert all_body["pagination"]["total_count"] == 1
    assert len(all_body["items"]) == 1
    assert all_body["items"][0]["notification_id"] == str(nid)
    assert all_body["items"][0]["status"] == "DELIVERED"

    # Filtering by status=FAILED must NOT return a notification whose current state is DELIVERED
    failed_resp = client.get("/ui/deliveries", params={"status": "FAILED"})
    assert failed_resp.status_code == 200
    assert failed_resp.json()["pagination"]["total_count"] == 0
    assert failed_resp.json()["items"] == []

    # When a failed notification is replayed and runtime_state is PENDING, timeline status reflects PENDING
    adapter.success = False
    runtime.max_attempts = 1
    send_resp = client.post(
        "/api/v1/notifications",
        json=signal(title="Replay target").model_dump(mode="json"),
    )
    assert send_resp.status_code in (200, 201, 202)
    failed_nid = send_resp.json()["notification_id"]

    replay_resp = client.post(f"/api/v1/runtime/notifications/{failed_nid}/replay")
    assert replay_resp.status_code == 200

    timeline_resp = client.get(f"/ui/deliveries/{failed_nid}")
    assert timeline_resp.status_code == 200
    timeline_body = timeline_resp.json()
    assert timeline_body["runtime_state"]["delivery_status"] == "PENDING"
    assert timeline_body["status"] == "PENDING"


def test_f02_policy_revisions_single_query_no_ddl_and_chronological_ordering(configured):
    """F-02: GET /ui/policies/revisions executes a single read-only SELECT, orders chronologically, and emits UTC timestamps."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import event

    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policies import NotificationPolicy

    app, runtime, _ = configured
    store = SQLAlchemyPolicyStore(runtime.sessions)
    t0 = datetime(2026, 4, 20, 10, 0, 0, tzinfo=UTC)

    store.save_policy(
        NotificationPolicy.from_dict(
            {
                "notification_type": "risk.limit",
                "version": "9.0.0",
                "status": "RETIRED",
                "intent": "OPERATIONAL",
                "delivery_mode": "GUARANTEED",
                "channels": {"LIVE": ["SLACK"]},
                "require_ack": {"LIVE": False},
                "created_at": t0.isoformat(),
                "updated_at": t0.isoformat(),
            }
        )
    )
    store.save_policy(
        NotificationPolicy.from_dict(
            {
                "notification_type": "risk.limit",
                "version": "10.0.0",
                "status": "ACTIVE",
                "intent": "OPERATIONAL",
                "delivery_mode": "GUARANTEED",
                "channels": {"LIVE": ["SLACK", "PAGERDUTY"]},
                "require_ack": {"LIVE": True},
                "created_at": (t0 + timedelta(minutes=5)).isoformat(),
                "updated_at": (t0 + timedelta(minutes=5)).isoformat(),
            }
        )
    )

    statements: list[str] = []

    def record_sql(_conn, _cursor, statement, *_args):
        verb = statement.strip().split(None, 1)[0].upper() if statement.strip() else ""
        statements.append(verb)

    event.listen(runtime.engine, "before_cursor_execute", record_sql)
    try:
        client = TestClient(app, headers={"Authorization": "Bearer test-key"})
        resp = client.get("/ui/policies/revisions", params={"notification_type": "risk.limit"})
    finally:
        event.remove(runtime.engine, "before_cursor_execute", record_sql)

    assert resp.status_code == 200
    assert statements == ["SELECT"]
    items = resp.json()["items"]
    assert [item["version"] for item in items] == ["10.0.0", "9.0.0"]
    for item in items:
        assert item["created_at"].endswith("Z") or item["created_at"].endswith("+00:00")
        assert item["updated_at"].endswith("Z") or item["updated_at"].endswith("+00:00")


def test_f03_effective_policy_resolves_registered_policy_intent_when_omitted(configured):
    """F-03: GET /ui/policies/effective resolves policy.intent when intent param is omitted for registered policy."""
    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policies import NotificationPolicy

    app, runtime, _ = configured
    store = SQLAlchemyPolicyStore(runtime.sessions)
    store.save_snapshot(
        [
            NotificationPolicy.from_dict(
                {
                    "notification_type": "governance.approval_required",
                    "version": "1.0.0",
                    "status": "ACTIVE",
                    "intent": "GOVERNANCE",
                    "delivery_mode": "GUARANTEED",
                    "channels": {"LIVE": ["SLACK"]},
                    "require_ack": {"LIVE": True},
                    "ack_timeout_minutes": 15,
                }
            )
        ]
    )

    client = TestClient(app, headers={"Authorization": "Bearer test-key"})
    resp = client.get(
        "/ui/policies/effective",
        params={"notification_type": "governance.approval_required", "autonomy_mode": "LIVE"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["notification_type"] == "governance.approval_required"
    assert body["resolution_context"]["intent"] == "GOVERNANCE"
    assert body["effective"]["require_ack"] is True


def test_f04_audit_events_preserve_ack_metadata_and_stage_order(configured):
    """F-04: GET /ui/audit preserves responder ack_metadata in SQL mode and orders equal-timestamp stages deterministically."""
    from datetime import UTC, datetime

    from db.models import AckAuditRecord, NotificationAuditRecord

    app, runtime, _ = configured
    nid = uuid4()
    agent_id = uuid4()
    t_same = datetime(2026, 4, 20, 15, 30, 0, tzinfo=UTC)

    with runtime.sessions() as session:
        session.add(
            NotificationAuditRecord(
                id=uuid4(),
                notification_id=nid,
                notification_type="security.test",
                status="DELIVERED",
                channels_attempted=["SLACK"],
                channels_succeeded=["SLACK"],
                channels_failed=[],
                delivery_mode="GUARANTEED",
                autonomy_mode="LIVE",
                intent="SAFETY",
                agent_id=agent_id,
                title="Audit test",
                source="test",
                notification_created_at=t_same,
                delivered_at=t_same,
                created_at=t_same,
            )
        )
        session.add(
            AckAuditRecord(
                id=uuid4(),
                notification_id=nid,
                old_status=None,
                new_status="PENDING",
                acked_by=None,
                acked_at=t_same,
                created_at=t_same,
                ack_metadata={},
            )
        )
        session.add(
            AckAuditRecord(
                id=uuid4(),
                notification_id=nid,
                old_status="PENDING",
                new_status="ACKED",
                acked_by="risk-lead",
                acked_at=t_same,
                created_at=t_same,
                ack_metadata={"note": "Verified on desk"},
            )
        )
        session.commit()

    client = TestClient(app, headers={"Authorization": "Bearer test-key"})
    resp = client.get("/ui/audit", params={"notification_id": str(nid)})
    assert resp.status_code == 200
    events = resp.json()["items"]
    event_types = [e["event_type"] for e in events]
    assert event_types.index("ack.received") < event_types.index("ack.pending")
    assert event_types.index("ack.pending") < event_types.index("delivery.succeeded")

    ack_event = next(e for e in events if e["event_type"] == "ack.received")
    assert ack_event["payload"]["note"] == "Verified on desk"
    assert ack_event["payload"]["acked_by"] == "risk-lead"


def test_f05_policy_hash_consistency_and_reload_path_containment(configured, tmp_path):
    """F-05: compute_policy_content_hash matches across YAML/dict/store, and reload rejects arbitrary paths when UNS_POLICY_DIR is unset."""
    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policy_loader import compute_policy_content_hash, load_policy_from_yaml

    app, runtime, _ = configured
    yaml_path = tmp_path / "sample_policy.yaml"
    yaml_path.write_text(
        """
notification_type: execution.slippage
version: "1.0.0"
status: ACTIVE
description: "Initial description"
intent: OPERATIONAL
delivery_mode: GUARANTEED
channels:
  LIVE: [SLACK]
require_ack:
  LIVE: true
ack_timeout_minutes: 10
""".strip()
    )
    loaded = load_policy_from_yaml(yaml_path)
    store = SQLAlchemyPolicyStore(runtime.sessions)
    persisted = store.save_policy(loaded)
    assert loaded.config_hash == persisted.content_hash
    # Changing only description or config_id does not alter canonical content hash
    dumped = loaded.model_dump(mode="json")
    dumped["description"] = "Updated description only"
    assert compute_policy_content_hash(dumped) == loaded.config_hash

    client = TestClient(app, headers={"Authorization": "Bearer test-key"})
    bad_reload = client.post("/api/v1/policies/reload", json={"policy_dir": "/etc"})
    assert bad_reload.status_code == 422


def test_f07_sqlite_engine_configures_wal_and_busy_timeout(configured):
    """F-07: File-backed SQLite engine enables WAL journal mode and 30000ms busy_timeout."""
    from sqlalchemy import text

    _, runtime, _ = configured
    with runtime.engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert str(journal_mode).lower() == "wal"
    assert int(busy_timeout) == 30000


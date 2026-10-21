"""Authentication and durable response boundaries shared across transports."""
from __future__ import annotations

import asyncio
import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agsignal.app import create_app
from agsignal.responses import SendNotificationRequest
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel
from notification.service import SimpleAdapterRegistry
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


def signal():
    return SendNotificationRequest(
        notification_type="security.test", intent="SAFETY", title="test", message="test",
        source="test", autonomy_context={"agent_id": str(uuid4()), "autonomy_mode": "LIVE"},
    )


@pytest.fixture
def configured(tmp_path, monkeypatch):
    from notification.policies import PolicyRegistry, configure_policy_registry
    from notification.rate_limiting import configure_rate_limiter
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    for name in ("UNS_API_KEY", "AGSIGNAL_API_KEY", "UNS_ALLOW_UNAUTHENTICATED_READS",
                 "AGSIGNAL_ALLOW_UNAUTHENTICATED_READS", "UNS_POLICY_DIR", "AGSIGNAL_POLICY_DIR"):
        monkeypatch.delenv(name, raising=False)
    adapter = RecordingAdapter()
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    runtime = Runtime(f"sqlite:///{tmp_path}/security.db", adapters=registry, create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.agsignal_api_key = "test-key"
    app.state.agsignal_api_principal = "verified-operator"
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
    app.state.agsignal_api_key = "test-key"
    client = TestClient(app)
    assert client.post("/api/v1/notifications", json=signal().model_dump(mode="json")).status_code == 401
    assert client.delete(f"/api/v1/dlq/{uuid4()}").status_code == 401
    assert client.post("/api/v1/policies/reload", json={"policy_dir": "/tmp"}).status_code == 401


def test_unconfigured_read_auth_fails_closed(configured):
    app, _, _ = configured
    app.state.agsignal_api_key = None
    assert TestClient(app).get("/ui/audit").status_code == 503


def test_websocket_uses_verified_actor_and_durable_ack(configured):
    app, runtime, _ = configured
    payload = signal()
    accepted = asyncio.run(runtime.send(payload, principal="verified-operator"))
    # Old compatibility flag cannot allow caller attribution spoofing.
    app.state.agsignal_allow_principal_override = True
    denied = TestClient(app).post(
        f"/api/v1/notifications/{accepted.notification_id}/ack",
        json={"acked_by": "imposter"}, headers={"Authorization": "Bearer test-key"},
    )
    assert denied.status_code == 403
    token = base64.urlsafe_b64encode(b"test-key").decode().rstrip("=")
    with TestClient(app).websocket_connect(
        f"/ws/agents/{payload.autonomy_context.agent_id}",
        subprotocols=["agsignal.v1", f"bearer.{token}"],
        headers={"Origin": "http://localhost:5173"},
    ) as ws:
        assert ws.accepted_subprotocol == "agsignal.v1"
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

    from agsignal_mcp.factory import create_mcp_server
    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policies import NotificationPolicy

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

"""Capability checks must apply to WebSocket commands as well as HTTP routes."""

from __future__ import annotations

import asyncio
import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agsignal.app import create_app
from agsignal.responses import SendNotificationRequest
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.rate_limiting import configure_rate_limiter
from notification.service import SimpleAdapterRegistry
from uns.runtime import Runtime


class RecordingAdapter(BaseAdapter):
    channel = Channel.SLACK

    def __init__(self):
        self.calls = 0

    async def deliver(self, notification):
        self.calls += 1
        return DeliveryResult(success=True, channel=self.channel)

    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY)


@pytest.fixture
def scoped_app(tmp_path, monkeypatch):
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    for prefix in ("UNS_", "AGSIGNAL_"):
        for suffix in (
            "API_KEY", "API_PRINCIPAL", "PRODUCER_API_KEY", "PRODUCER_API_PRINCIPAL",
            "RESPONDER_API_KEY", "RESPONDER_API_PRINCIPAL", "OBSERVER_API_KEY",
            "OBSERVER_API_PRINCIPAL", "ALLOW_UNAUTHENTICATED_READS", "POLICY_DIR",
            "ALLOWED_ORIGINS",
        ):
            monkeypatch.delenv(prefix + suffix, raising=False)

    adapters = SimpleAdapterRegistry()
    adapters.register(RecordingAdapter())
    runtime = Runtime(f"sqlite:///{tmp_path}/scoped-websocket.db", adapters=adapters, create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.agsignal_api_key = "operator-test-key"
    app.state.agsignal_api_principal = "operator-principal"
    for role in ("producer", "responder", "observer"):
        setattr(app.state, f"uns_{role}_api_key", f"{role}-test-key")
        setattr(app.state, f"uns_{role}_api_principal", f"{role}-principal")

    yield app, runtime
    runtime.engine.dispose()


@pytest.mark.parametrize("role", ["producer", "observer", "responder", "operator"])
@pytest.mark.parametrize("response_status", ["ACKED", "DISMISSED"])
@pytest.mark.parametrize("auth_mode", ["bearer", "browser_subprotocol"])
def test_websocket_response_requires_responder_scope(
    scoped_app, role, response_status, auth_mode,
):
    app, runtime = scoped_app
    agent_id = uuid4()
    request = SendNotificationRequest(
        notification_type="security.websocket",
        intent="SAFETY",
        title="Operator response required",
        message="A recorded notification awaiting a response.",
        source="websocket-scope-test",
        require_ack=True,
        autonomy_context={"agent_id": str(agent_id), "autonomy_mode": "LIVE"},
    )
    accepted = asyncio.run(runtime.send(request, principal="producer-principal"))
    identifier = str(accepted.notification_id)
    assert accepted.status.value == "DELIVERED"
    assert accepted.ack_status.value == "PENDING"

    before = runtime.get(identifier)
    before_events = runtime.events(identifier)
    before_ack_audits = runtime.audit_store.get_ack_audits_for_notification(accepted.notification_id)

    client = TestClient(app)
    key = f"{role}-test-key"
    permitted = role in {"responder", "operator"}
    if not permitted:
        action = "ack" if response_status == "ACKED" else "dismiss"
        denied_http = client.post(
            f"/api/v1/notifications/{identifier}/{action}",
            json={},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert denied_http.status_code == 403

    headers = {"Authorization": f"Bearer {key}"}
    subprotocols = None
    if auth_mode == "browser_subprotocol":
        encoded = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
        headers = {"Origin": "http://localhost:5173"}
        subprotocols = ["agsignal.v1", f"bearer.{encoded}"]

    with client.websocket_connect(
        f"/ws/agents/{agent_id}", headers=headers, subprotocols=subprotocols,
    ) as websocket:
        if auth_mode == "browser_subprotocol":
            assert websocket.accepted_subprotocol == "agsignal.v1"
        assert websocket.receive_json()["type"] == "connected"
        websocket.send_json({
            "type": "ack", "notification_id": identifier, "status": response_status,
        })
        response = websocket.receive_json()

        if permitted:
            assert response["type"] == "ack_result"
            assert response["ack_status"] == response_status
            assert response["acked_by"] == f"{role}-principal"
            assert runtime.get(identifier)["ack_status"] == response_status
            assert len(runtime.audit_store.get_ack_audits_for_notification(accepted.notification_id)) == 1
        else:
            assert response["type"] == "error"
            assert response["error"] == "insufficient_scope"
            assert runtime.get(identifier) == before
            assert runtime.events(identifier) == before_events
            assert runtime.audit_store.get_ack_audits_for_notification(accepted.notification_id) == before_ack_audits

        # The delivered notification's real replay entry remains readable after a denial.
        websocket.send_json({"type": "subscribe", "last_seen": "2000-01-01T00:00:00+00:00"})
        replay = websocket.receive_json()
        assert replay["type"] == "subscribed"
        assert replay["replay_available"] is True
        assert [item["notification_id"] for item in replay["missed_notifications"]] == [identifier]

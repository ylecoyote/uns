"""Integration tests for the unified uns.app factory.

Exercises both the write surface (/api/v1/notifications/*) and the read
surface (/ui/*) through one TestClient to confirm both lobes are
reachable in the unified app.
"""

import pytest
from fastapi.testclient import TestClient

from uns.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app(skip_persistence_config=True)  # tests configure their own stores
    app.state.uns_api_key = "test-key"
    return TestClient(app, headers={"Authorization": "Bearer test-key"})


def test_health_responds(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "uns"


def test_ready_responds_with_unified_payload(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    # Core-side fields
    assert "channels_configured" in body
    assert "dlq_depth" in body
    assert "policy_count" in body
    # Console-side fields
    assert "read_model_adapter" in body
    assert "audit_logger" in body


def test_metrics_endpoint_responds(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    # Prometheus format check - contains at least one HELP/TYPE line
    assert "# HELP" in response.text or "# TYPE" in response.text


def test_write_surface_is_mounted(client: TestClient) -> None:
    """POST to /api/v1/notifications/send (preview-only) reaches the write router."""
    payload = {
        "notification_type": "test.signal",
        "intent": "info",
        "title": "test",
        "message": "test",
        "source": "test-suite",
        "autonomy_context": {"agent_id": "a", "autonomy_mode": "L0"},
    }
    response = client.post(
        "/api/v1/notifications/simulate",
        json=payload,
        headers={"X-Agent-ID": "a"},
    )
    # Either succeeds (200) or returns auth error (401/403) - what matters
    # is the route is NOT 404 (which would mean the router isn't mounted).
    assert response.status_code != 404, (
        f"Write surface unreachable: {response.status_code}"
    )


def test_read_surface_is_mounted(client: TestClient) -> None:
    """GET /ui/invariants reaches the read router."""
    response = client.get("/ui/invariants/summary")
    assert response.status_code != 404, (
        f"Read surface unreachable: {response.status_code}"
    )


def test_ack_surface_is_mounted(client: TestClient) -> None:
    """POST to /api/v1/notifications/{id}/ack reaches the ack router."""
    response = client.post(
        "/api/v1/notifications/00000000-0000-0000-0000-000000000000/ack",
        json={},
        headers={"X-Agent-ID": "a"},
    )
    # 404 here would mean the ack router isn't mounted under /api.
    # We expect 401/403/422/404-not-found-notification but NOT 404-route-missing.
    # Distinguish by checking the response body - the route exists if we get
    # a JSON error envelope rather than the FastAPI default "Not Found" string.
    assert response.status_code != 404 or response.json().get("detail") != "Not Found"


def test_websocket_endpoint_is_mounted(client: TestClient) -> None:
    """WebSocket connect to /ws/agents/{agent_id} succeeds the handshake.

    CORRECTED FROM PLAN V1: the route signature is
    `websocket_endpoint(websocket: WebSocket, agent_id: UUID)` - FastAPI
    will reject a non-UUID path param at handshake. Use a real UUID.
    """
    from uuid import uuid4
    agent_id = uuid4()
    with client.websocket_connect(f"/ws/agents/{agent_id}") as ws:
        # If the route weren't mounted, websocket_connect would raise.
        # We just need to confirm the handshake path is reachable.
        ws.close()

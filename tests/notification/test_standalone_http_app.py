"""Tests for the standalone AGSignal HTTP application."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine


def _payload() -> dict[str, object]:
    return {
        "notification_type": "agent.risk_limit_breach",
        "intent": "SAFETY",
        "title": "Risk limit breached",
        "message": "Agent entered a position outside configured limits.",
        "source": "agent-runtime",
        "autonomy_context": {
            "autonomy_mode": "LIVE",
            "agent_id": str(uuid4()),
        },
    }


def _client() -> TestClient:
    configure_ack_engine(storage=InMemoryAckStorage())

    from notification.main import create_app

    return TestClient(create_app())


def test_standalone_app_metadata_and_routes_are_agsignal_native() -> None:
    client = _client()

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    assert openapi["info"]["title"] == "AGSignal Core"
    assert "/health" in openapi["paths"]
    assert "/ready" in openapi["paths"]
    assert "/api/v1/notifications" in openapi["paths"]
    assert "/api/v1/notifications/{notification_id}/ack-status" in openapi["paths"]


def test_ready_does_not_require_market_insights_dependencies() -> None:
    client = _client()

    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "agsignal-core"
    assert "market" not in str(data).lower()
    assert "atp" not in str(data).lower()


def test_send_signal_registers_live_safety_ack_state() -> None:
    client = _client()

    response = client.post("/api/v1/notifications", json=_payload())

    assert response.status_code == 202
    data = response.json()
    assert data["notification_id"]
    assert data["status"] == "SUCCESS"
    assert data["require_ack"] is True
    assert data["ack_status"] == "PENDING"
    assert "channels_attempted" in data

    status_response = client.get(
        f"/api/v1/notifications/{data['notification_id']}/ack-status"
    )

    assert status_response.status_code == 200
    assert status_response.json()["ack_status"] == "PENDING"


def test_send_signal_rejects_producer_selected_channels() -> None:
    client = _client()
    payload = _payload()
    payload["channels"] = ["SLACK"]

    response = client.post("/api/v1/notifications", json=payload)

    assert response.status_code == 422

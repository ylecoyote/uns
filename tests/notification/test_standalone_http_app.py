"""Tests for the standalone AGSignal HTTP application."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import yaml
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from db.policy_store import SQLAlchemyPolicyStore
from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine
from notification.channel_health import ChannelHealthTracker
from notification.dlq import DLQService
from notification.models import (
    AutonomyContext,
    AutonomyMode,
    Channel,
    Notification,
    NotificationIntent,
)
from notification.websocket_runtime import WebSocketFanoutEnvelope


class FakeRedisList:
    def __init__(self) -> None:
        self.values: list[str] = []

    def lpush(self, key: str, value: str) -> int:
        self.values.insert(0, value)
        return len(self.values)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        stop = None if end == -1 else end + 1
        return self.values[start:stop]

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        next_values = []
        for item in self.values:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            next_values.append(item)
        self.values = next_values
        return removed

    def llen(self, key: str) -> int:
        return len(self.values)

    def publish(self, channel: str, payload: str) -> int:
        self.values.append(payload)
        return 1

    def pubsub(self) -> FakePubSub:
        return FakePubSub()


class FakePubSub:
    def subscribe(self, *channels: str) -> int:
        return len(channels)

    def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 0.5,
    ) -> None:
        return None

    def close(self) -> None:
        return None


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


def _client(
    dlq_service: DLQService | None = None,
    policy_store: SQLAlchemyPolicyStore | None = None,
    channel_health_tracker: ChannelHealthTracker | None = None,
) -> TestClient:
    configure_ack_engine(storage=InMemoryAckStorage())

    from notification.main import create_app

    return TestClient(
        create_app(
            dlq_service=dlq_service,
            policy_store=policy_store,
            channel_health_tracker=channel_health_tracker,
        )
    )


class ExplodingRedisFactory:
    def __call__(self, url: str) -> FakeRedisList:
        raise AssertionError("Redis should not be created unless fanout is enabled")


class CapturingFanout:
    def __init__(self) -> None:
        self.envelopes: list[WebSocketFanoutEnvelope] = []

    def publish(self, envelope: WebSocketFanoutEnvelope) -> bool:
        self.envelopes.append(envelope)
        return True


def _notification() -> Notification:
    return Notification(
        notification_type="safety.kill_switch",
        intent=NotificationIntent.SAFETY,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
        title="Kill switch",
        message="Kill switch engaged",
        source="agent_governor",
    )


def test_standalone_app_metadata_and_routes_are_agsignal_native() -> None:
    client = _client()
    from notification.main import create_app

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    assert openapi["info"]["title"] == "AGSignal Core"
    assert "/health" in openapi["paths"]
    assert "/ready" in openapi["paths"]
    assert "/api/v1/notifications" in openapi["paths"]
    assert "/api/v1/notifications/{notification_id}/ack-status" in openapi["paths"]
    assert "/ws/agents/{agent_id}" in [
        getattr(route, "path", None) for route in create_app().routes
    ]


def test_ready_does_not_require_market_insights_dependencies() -> None:
    client = _client()

    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "agsignal-core"
    assert "market" not in str(data).lower()
    assert "atp" not in str(data).lower()


def test_channel_health_summary_is_separate_from_ready_status() -> None:
    tracker = ChannelHealthTracker(failure_threshold=1)
    tracker.record_failure(Channel.SLACK, reason="timeout")
    client = _client(channel_health_tracker=tracker)

    health_response = client.get("/api/v1/channels/health")
    ready_response = client.get("/ready")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "DEGRADED"
    assert health_response.json()["degraded_channels"] == ["SLACK"]
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"


def test_app_does_not_create_redis_fanout_by_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("UNS_WEBSOCKET_REDIS_ENABLED", raising=False)

    from notification.main import create_app

    app = create_app(redis_client_factory=ExplodingRedisFactory())

    assert app.state.websocket_fanout is None


def test_app_creates_redis_fanout_when_enabled(monkeypatch: MonkeyPatch) -> None:
    class RedisFactory:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, url: str) -> FakeRedisList:
            self.urls.append(url)
            return FakeRedisList()

    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_ENABLED", "true")
    monkeypatch.setenv("UNS_REDIS_URL", "redis://example/0")
    factory = RedisFactory()

    from notification.main import create_app

    app = create_app(redis_client_factory=factory)

    assert factory.urls == ["redis://example/0"]
    assert app.state.websocket_fanout is not None
    assert app.state.websocket_subscriber is not None


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


def test_send_signal_delivers_to_connected_websocket_agent() -> None:
    client = _client()
    payload = _payload()
    agent_id = uuid4()
    autonomy_context = payload["autonomy_context"]
    assert isinstance(autonomy_context, dict)
    autonomy_context["agent_id"] = str(agent_id)

    with client.websocket_connect(f"/ws/agents/{agent_id}") as websocket:
        websocket.receive_json()

        response = client.post("/api/v1/notifications", json=payload)
        event = websocket.receive_json()

    assert response.status_code == 202
    assert event["type"] == "notification"
    assert event["notification"]["notification_id"] == response.json()["notification_id"]
    assert event["notification"]["ack_status"] == "PENDING"
    assert event["notification"]["require_ack"] is True


def test_send_signal_publishes_optional_websocket_fanout() -> None:
    configure_ack_engine(storage=InMemoryAckStorage())

    from notification.main import create_app

    app = create_app()
    fanout = CapturingFanout()
    app.state.websocket_fanout = fanout
    client = TestClient(app)
    payload = _payload()
    agent_id = uuid4()
    autonomy_context = payload["autonomy_context"]
    assert isinstance(autonomy_context, dict)
    autonomy_context["agent_id"] = str(agent_id)

    response = client.post("/api/v1/notifications", json=payload)

    assert response.status_code == 202
    assert len(fanout.envelopes) == 1
    envelope = fanout.envelopes[0]
    assert envelope.type == "notification"
    assert envelope.agent_id == agent_id
    assert envelope.notification["notification_id"] == response.json()["notification_id"]


def test_send_signal_rejects_producer_selected_channels() -> None:
    client = _client()
    payload = _payload()
    payload["channels"] = ["SLACK"]

    response = client.post("/api/v1/notifications", json=payload)

    assert response.status_code == 422


def test_simulate_signal_returns_routing_preview_without_registering_ack() -> None:
    client = _client()

    response = client.post("/api/v1/notifications/simulate", json=_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["simulated"] is True
    assert data["notification_id"]
    assert data["require_ack"] is True
    assert data["ack_status"] is None
    assert data["channels_attempted"]

    status_response = client.get(
        f"/api/v1/notifications/{data['notification_id']}/ack-status"
    )

    assert status_response.status_code == 200
    assert status_response.json()["ack_status"] is None


def test_dlq_list_returns_seeded_entries() -> None:
    redis = FakeRedisList()
    dlq_service = DLQService(redis_client=redis, key="uns:test:dlq")
    entry = dlq_service.enqueue(_notification(), reason="all persistent channels failed")
    client = _client(dlq_service=dlq_service)

    response = client.get("/api/v1/dlq")

    assert response.status_code == 200
    data = response.json()
    assert data["depth"] == 1
    assert data["items"][0]["entry_id"] == str(entry.entry_id)
    assert data["items"][0]["reason"] == "all persistent channels failed"


def test_policy_reload_loads_yaml_directory(tmp_path: Path) -> None:
    policy_file = tmp_path / "safety.yaml"
    policy_file.write_text(
        yaml.safe_dump(
            {
                "notification_type": "safety.kill_switch",
                "version": "1.0.0",
                "status": "ACTIVE",
                "delivery_mode": "GUARANTEED",
                "channels": {
                    "LIVE": ["SLACK", "WEBSOCKET"],
                },
                "require_ack": {
                    "LIVE": True,
                },
            }
        )
    )
    client = _client()

    response = client.post("/api/v1/policies/reload", json={"policy_dir": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()
    assert data["loaded_count"] == 1
    assert data["policy_count"] == 1
    assert data["notification_types"] == ["safety.kill_switch"]


def test_policy_reload_persists_loaded_yaml_when_policy_store_is_configured(
    tmp_path: Path,
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base

    policy_file = tmp_path / "safety.yaml"
    policy_file.write_text(
        yaml.safe_dump(
            {
                "notification_type": "safety.kill_switch",
                "version": "1.0.0",
                "status": "ACTIVE",
                "delivery_mode": "GUARANTEED",
                "channels": {"LIVE": ["SLACK", "WEBSOCKET"]},
                "require_ack": {"LIVE": True},
            }
        )
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'policies.db'}")
    Base.metadata.create_all(engine)
    policy_store = SQLAlchemyPolicyStore(sessionmaker(bind=engine))
    client = _client(policy_store=policy_store)

    response = client.post("/api/v1/policies/reload", json={"policy_dir": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["persisted_count"] == 1
    assert policy_store.count_rows() == 1


def test_policy_reload_rejects_missing_directory(tmp_path: Path) -> None:
    client = _client()

    response = client.post(
        "/api/v1/policies/reload",
        json={"policy_dir": str(tmp_path / "missing")},
    )

    assert response.status_code == 404

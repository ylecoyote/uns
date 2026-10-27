"""Tests for standalone UNS WebSocket runtime."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine
from notification.channel_health import ChannelHealthStatus, ChannelHealthTracker
from notification.models import AckStatus, AutonomyContext, AutonomyMode, NotificationIntent
from notification.websocket_runtime import (
    InMemoryWebSocketReplayStore,
    RedisWebSocketFanout,
    RedisWebSocketSubscriber,
    WebSocketConnectionManager,
    WebSocketFanoutEnvelope,
    WebSocketReplayStore,
    get_missed_notifications,
    websocket_endpoint,
)


def _app(
    manager: WebSocketConnectionManager | None = None,
    replay_store: WebSocketReplayStore | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.uns_api_key = "test-key"
    app.state.uns_api_principal = "operator"
    app.state.websocket_manager = manager or WebSocketConnectionManager()
    app.state.websocket_replay_store = replay_store or InMemoryWebSocketReplayStore()
    app.websocket("/ws/agents/{agent_id}")(websocket_endpoint)
    return app


def test_connection_manager_tracks_agent_connections() -> None:
    manager = WebSocketConnectionManager()
    agent_id = uuid4()

    manager.register(agent_id, connection_id="conn-1")
    manager.register(agent_id, connection_id="conn-2")

    assert manager.connection_count == 2
    assert manager.agent_connection_count(agent_id) == 2

    manager.unregister(agent_id, connection_id="conn-1")

    assert manager.connection_count == 1
    assert manager.agent_connection_count(agent_id) == 1


def test_missed_notification_replay_is_explicitly_empty() -> None:
    assert get_missed_notifications(agent_id=uuid4(), last_seen="cursor") == []


def test_replay_store_returns_notifications_after_cursor() -> None:
    store = InMemoryWebSocketReplayStore()
    agent_id = uuid4()
    first_cursor = store.record(
        agent_id,
        {"notification_id": str(uuid4()), "title": "old"},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    second_payload = {"notification_id": str(uuid4()), "title": "new"}
    second_cursor = store.record(
        agent_id,
        second_payload,
        created_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )

    assert store.missed(agent_id, first_cursor) == [
        {**second_payload, "replay_cursor": second_cursor}
    ]


def test_websocket_subscribe_reports_missed_notifications_from_replay_store() -> None:
    store = InMemoryWebSocketReplayStore()
    agent_id = uuid4()
    first_cursor = store.record(
        agent_id,
        {"notification_id": str(uuid4()), "title": "old"},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    missed_payload = {"notification_id": str(uuid4()), "title": "new"}
    missed_cursor = store.record(
        agent_id,
        missed_payload,
        created_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )
    client = TestClient(_app(replay_store=store))

    with client.websocket_connect(f"/ws/agents/{agent_id}", headers={"Authorization": "Bearer test-key"}) as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        assert connected["agent_id"] == str(agent_id)

        websocket.send_json({"type": "subscribe", "last_seen": first_cursor})
        response = websocket.receive_json()

        assert response["type"] == "subscribed"
        assert response["missed_notifications"] == [
            {**missed_payload, "replay_cursor": missed_cursor}
        ]
        assert response["replay_available"] is True


def test_websocket_ack_without_durable_runtime_does_not_update_legacy_engine() -> None:
    configure_ack_engine(storage=InMemoryAckStorage())
    engine = configure_ack_engine(storage=InMemoryAckStorage())
    notification_id = uuid4()
    agent_id = uuid4()
    engine.register_notification(
        notification_id=notification_id,
        intent=NotificationIntent.SAFETY,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        ),
    )
    client = TestClient(_app())

    with client.websocket_connect(f"/ws/agents/{agent_id}", headers={"Authorization": "Bearer test-key"}) as websocket:
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "ack",
                "notification_id": str(notification_id),
                "status": "ACKED",
                "acked_by": "operator",
            }
        )
        response = websocket.receive_json()

        assert response["type"] == "error"
        assert response["error"] == "runtime_unavailable"
        assert engine.get_status(notification_id) == AckStatus.PENDING


def test_websocket_ping_returns_pong() -> None:
    client = TestClient(_app())

    with client.websocket_connect(f"/ws/agents/{uuid4()}", headers={"Authorization": "Bearer test-key"}) as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "ping"})

        assert websocket.receive_json()["type"] == "pong"


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, payload: str) -> int:
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.published.append((channel, payload))
        return 1


class CapturingWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


def test_redis_fanout_publishes_stable_envelope() -> None:
    redis = FakeRedis()
    fanout = RedisWebSocketFanout(
        redis_client=redis,
        channel_prefix="uns:test",
        instance_id="instance-a",
    )
    agent_id = uuid4()

    delivered = fanout.publish(
        WebSocketFanoutEnvelope(
            type="notification",
            agent_id=agent_id,
            notification={"notification_id": str(uuid4())},
        )
    )

    assert delivered is True
    channel, payload = redis.published[0]
    assert channel == f"uns:test:agent:{agent_id}"
    assert '"type":"notification"' in payload
    assert str(agent_id) in payload
    assert '"origin_id":"instance-a"' in payload


def test_redis_fanout_failure_degrades_websocket_health_without_raising() -> None:
    tracker = ChannelHealthTracker(failure_threshold=1)
    fanout = RedisWebSocketFanout(
        redis_client=FakeRedis(fail=True),
        channel_prefix="uns:test",
        channel_health_tracker=tracker,
    )

    delivered = fanout.publish(
        WebSocketFanoutEnvelope(
            type="notification",
            agent_id=uuid4(),
            notification={"notification_id": str(uuid4())},
        )
    )

    assert delivered is False
    assert tracker.get_summary().status == ChannelHealthStatus.DEGRADED


def test_redis_subscriber_forwards_other_instance_message_to_local_agent() -> None:
    async def run() -> None:
        manager = WebSocketConnectionManager()
        agent_id = uuid4()
        websocket = CapturingWebSocket()
        manager.register(agent_id, "conn-1", websocket)  # type: ignore[arg-type]
        subscriber = RedisWebSocketSubscriber(
            redis_client=FakeRedis(),  # type: ignore[arg-type]
            channel_prefix="uns:test",
            manager=manager,
            origin_id="instance-a",
        )
        envelope = WebSocketFanoutEnvelope(
            type="notification",
            agent_id=agent_id,
            notification={"notification_id": str(uuid4())},
            origin_id="instance-b",
        )

        handled = await subscriber.handle_message(
            {"type": "message", "data": envelope.model_dump_json()}
        )

        assert handled is True
        assert websocket.sent == [
            {"type": "notification", "notification": envelope.notification}
        ]

    asyncio.run(run())


def test_redis_subscriber_ignores_same_origin_message() -> None:
    async def run() -> None:
        manager = WebSocketConnectionManager()
        agent_id = uuid4()
        websocket = CapturingWebSocket()
        manager.register(agent_id, "conn-1", websocket)  # type: ignore[arg-type]
        subscriber = RedisWebSocketSubscriber(
            redis_client=FakeRedis(),  # type: ignore[arg-type]
            channel_prefix="uns:test",
            manager=manager,
            origin_id="instance-a",
        )
        envelope = WebSocketFanoutEnvelope(
            type="notification",
            agent_id=agent_id,
            notification={"notification_id": str(uuid4())},
            origin_id="instance-a",
        )

        handled = await subscriber.handle_message(
            {"type": "message", "data": envelope.model_dump_json()}
        )

        assert handled is False
        assert websocket.sent == []

    asyncio.run(run())


class FailingThenBlockingRedis:
    def __init__(self) -> None:
        self.pubsub_attempts = 0
        self.second_subscription_started = threading.Event()

    def pubsub(self) -> object:
        self.pubsub_attempts += 1
        if self.pubsub_attempts == 1:
            return FailingSubscribePubSub()
        return BlockingPubSub(self.second_subscription_started)


class FailingSubscribePubSub:
    def subscribe(self, *channels: str) -> None:
        raise RuntimeError("redis subscribe failed")

    def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 0.5,
    ) -> None:
        return None

    def close(self) -> None:
        return None


class BlockingPubSub:
    def __init__(self, started: threading.Event) -> None:
        self._started = started

    def subscribe(self, *channels: str) -> None:
        self._started.set()

    def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 0.5,
    ) -> None:
        time.sleep(0.01)
        return None

    def close(self) -> None:
        return None


def test_redis_subscriber_reconnects_after_transient_subscription_failure() -> None:
    async def run() -> None:
        manager = WebSocketConnectionManager()
        redis = FailingThenBlockingRedis()
        subscriber = RedisWebSocketSubscriber(
            redis_client=redis,  # type: ignore[arg-type]
            channel_prefix="uns:test",
            manager=manager,
            origin_id="instance-a",
            reconnect_initial_delay_seconds=0.0,
            reconnect_max_delay_seconds=0.0,
        )
        agent_id = uuid4()

        await subscriber.ensure_agent_subscription(agent_id)
        await asyncio.wait_for(
            asyncio.to_thread(redis.second_subscription_started.wait),
            timeout=1.0,
        )

        assert redis.pubsub_attempts >= 2
        assert subscriber.active_subscription_count == 1

        await subscriber.stop_agent_subscription(agent_id)
        assert subscriber.active_subscription_count == 0

    asyncio.run(run())

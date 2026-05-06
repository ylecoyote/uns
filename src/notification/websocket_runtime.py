"""Standalone FastAPI WebSocket runtime for AGSignal clients."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from notification.acknowledgment import get_ack_engine
from notification.channel_health import ChannelHealthTracker
from notification.models import AckStatus, Channel

logger = logging.getLogger(__name__)


class WebSocketSubscriber(Protocol):
    """Optional cross-process subscription lifecycle for WebSocket fanout."""

    async def ensure_agent_subscription(self, agent_id: UUID) -> None: ...

    async def stop_agent_subscription(self, agent_id: UUID) -> None: ...


class WebSocketConnectionManager:
    """In-memory connection tracker for standalone WebSocket sessions."""

    def __init__(self, subscriber: WebSocketSubscriber | None = None) -> None:
        self._connections_by_agent: dict[UUID, dict[str, WebSocket | None]] = {}
        self._subscriber = subscriber

    def set_subscriber(self, subscriber: WebSocketSubscriber | None) -> None:
        self._subscriber = subscriber

    @property
    def connection_count(self) -> int:
        return sum(len(connections) for connections in self._connections_by_agent.values())

    def agent_connection_count(self, agent_id: UUID) -> int:
        return len(self._connections_by_agent.get(agent_id, {}))

    def register(
        self,
        agent_id: UUID,
        connection_id: str,
        websocket: WebSocket | None = None,
    ) -> None:
        self._connections_by_agent.setdefault(agent_id, {})[connection_id] = websocket

    def unregister(self, agent_id: UUID, connection_id: str) -> None:
        connections = self._connections_by_agent.get(agent_id)
        if connections is None:
            return
        connections.pop(connection_id, None)
        if not connections:
            del self._connections_by_agent[agent_id]

    async def send_to_agent(self, agent_id: UUID, payload: dict[str, object]) -> int:
        """Send a JSON payload to all local WebSocket sessions for an agent."""
        connections = self._connections_by_agent.get(agent_id, {}).copy()
        delivered = 0
        for connection_id, websocket in connections.items():
            if websocket is None:
                continue
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning("WebSocket send failed: %s", exc)
                self.unregister(agent_id, connection_id)
                continue
            delivered += 1
        return delivered

    async def ensure_agent_subscription(self, agent_id: UUID) -> None:
        if self._subscriber is not None:
            await self._subscriber.ensure_agent_subscription(agent_id)

    async def stop_agent_subscription_if_idle(self, agent_id: UUID) -> None:
        if self._subscriber is not None and self.agent_connection_count(agent_id) == 0:
            await self._subscriber.stop_agent_subscription(agent_id)


class WebSocketFanoutEnvelope(BaseModel):
    """Stable envelope for optional cross-process WebSocket fanout."""

    type: str = Field(description="Fanout message type")
    agent_id: UUID = Field(description="Target agent identifier")
    notification: dict[str, object] = Field(default_factory=dict)
    origin_id: str | None = Field(
        default=None,
        description="AGSignal process identifier that created the fanout event",
    )


class RedisPublisher(Protocol):
    """Redis-compatible publishing surface used by WebSocket fanout."""

    def publish(self, channel: str, message: str) -> object: ...


class RedisPubSub(Protocol):
    """Redis-compatible pub/sub surface used by WebSocket fanout."""

    def subscribe(self, *channels: str) -> object: ...

    def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 0.5,
    ) -> object: ...

    def close(self) -> object: ...


class RedisWebSocketClient(RedisPublisher, Protocol):
    """Redis surface required for AGSignal WebSocket fanout."""

    def pubsub(self) -> RedisPubSub: ...


class RedisWebSocketFanout:
    """Optional Redis-backed WebSocket fanout publisher."""

    def __init__(
        self,
        redis_client: RedisPublisher,
        channel_prefix: str,
        instance_id: str | None = None,
        channel_health_tracker: ChannelHealthTracker | None = None,
    ) -> None:
        self._redis = redis_client
        self._channel_prefix = channel_prefix
        self._instance_id = instance_id or str(uuid4())
        self._channel_health_tracker = channel_health_tracker

    @property
    def channel_prefix(self) -> str:
        return self._channel_prefix

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def channel_for_agent(self, agent_id: UUID) -> str:
        return f"{self._channel_prefix}:agent:{agent_id}"

    def publish(self, envelope: WebSocketFanoutEnvelope) -> bool:
        """Publish a fanout envelope.

        Redis failures are observable via channel health but are not raised to
        callers. Live fanout should not block the notification execution path.
        """
        outbound = envelope
        if outbound.origin_id is None:
            outbound = outbound.model_copy(update={"origin_id": self._instance_id})
        payload = outbound.model_dump_json()
        try:
            publish = self._redis.publish
            publish(self.channel_for_agent(outbound.agent_id), payload)
        except Exception as exc:
            logger.warning("Redis WebSocket fanout failed: %s", exc)
            if self._channel_health_tracker is not None:
                self._channel_health_tracker.record_failure(Channel.WEBSOCKET, reason=str(exc))
            return False

        if self._channel_health_tracker is not None:
            self._channel_health_tracker.record_success(Channel.WEBSOCKET)
        return True


class RedisWebSocketSubscriber:
    """Optional Redis-backed subscriber for cross-process WebSocket fanout."""

    def __init__(
        self,
        redis_client: RedisWebSocketClient,
        channel_prefix: str,
        manager: WebSocketConnectionManager,
        origin_id: str,
        channel_health_tracker: ChannelHealthTracker | None = None,
    ) -> None:
        self._redis = redis_client
        self._channel_prefix = channel_prefix
        self._manager = manager
        self._origin_id = origin_id
        self._channel_health_tracker = channel_health_tracker
        self._tasks_by_agent: dict[UUID, asyncio.Task[None]] = {}

    @property
    def active_subscription_count(self) -> int:
        return len(self._tasks_by_agent)

    def channel_for_agent(self, agent_id: UUID) -> str:
        return f"{self._channel_prefix}:agent:{agent_id}"

    async def ensure_agent_subscription(self, agent_id: UUID) -> None:
        existing = self._tasks_by_agent.get(agent_id)
        if existing is not None and not existing.done():
            return
        self._tasks_by_agent[agent_id] = asyncio.create_task(self._run_agent_subscription(agent_id))

    async def stop_agent_subscription(self, agent_id: UUID) -> None:
        task = self._tasks_by_agent.pop(agent_id, None)
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def handle_message(self, message: object) -> bool:
        """Validate and forward one Redis pub/sub message."""
        if not isinstance(message, dict) or message.get("type") != "message":
            return False

        raw_data = message.get("data")
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        if not isinstance(raw_data, str):
            logger.warning("Redis WebSocket fanout message had non-string payload")
            return False

        try:
            envelope = WebSocketFanoutEnvelope.model_validate_json(raw_data)
        except ValueError:
            logger.warning("Redis WebSocket fanout message had invalid JSON")
            return False

        if envelope.origin_id == self._origin_id:
            return False

        await self._manager.send_to_agent(
            envelope.agent_id,
            {"type": envelope.type, "notification": envelope.notification},
        )
        if self._channel_health_tracker is not None:
            self._channel_health_tracker.record_success(Channel.WEBSOCKET)
        return True

    async def _run_agent_subscription(self, agent_id: UUID) -> None:
        pubsub: RedisPubSub | None = None
        try:
            pubsub = self._redis.pubsub()
            await asyncio.to_thread(pubsub.subscribe, self.channel_for_agent(agent_id))
            while True:
                message = await asyncio.to_thread(pubsub.get_message, True, 0.5)
                await self.handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Redis WebSocket subscription failed: %s", exc)
            if self._channel_health_tracker is not None:
                self._channel_health_tracker.record_failure(Channel.WEBSOCKET, reason=str(exc))
        finally:
            if pubsub is not None:
                await asyncio.to_thread(pubsub.close)
            self._tasks_by_agent.pop(agent_id, None)


def get_missed_notifications(agent_id: UUID, last_seen: str | None = None) -> list[dict[str, str]]:
    """Return missed notifications for a reconnecting agent.

    Replay persistence is intentionally not implemented in this slice. Returning
    an explicit empty list keeps the runtime contract honest until a durable
    notification read model owns replay assembly.
    """
    return []


async def websocket_endpoint(websocket: WebSocket, agent_id: UUID) -> None:
    """Handle a standalone AGSignal agent WebSocket session."""
    manager: WebSocketConnectionManager = websocket.app.state.websocket_manager
    connection_id = str(uuid4())
    await websocket.accept()
    manager.register(agent_id, connection_id, websocket)
    await manager.ensure_agent_subscription(agent_id)
    await websocket.send_json(
        {
            "type": "connected",
            "agent_id": str(agent_id),
            "connection_id": connection_id,
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif message_type == "subscribe":
                missed = get_missed_notifications(agent_id, message.get("last_seen"))
                await websocket.send_json(
                    {
                        "type": "subscribed",
                        "agent_id": str(agent_id),
                        "missed_notifications": missed,
                        "replay_available": bool(missed),
                    }
                )
            elif message_type == "ack":
                await _handle_ack_message(websocket, message)
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unsupported message type: {message_type}",
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(agent_id, connection_id)
        await manager.stop_agent_subscription_if_idle(agent_id)


async def _handle_ack_message(websocket: WebSocket, message: dict[str, object]) -> None:
    notification_id = UUID(str(message["notification_id"]))
    requested_status = AckStatus(str(message.get("status", AckStatus.ACKED.value)))
    if requested_status not in (AckStatus.ACKED, AckStatus.DISMISSED):
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Unsupported ack status: {requested_status.value}",
            }
        )
        return

    event = get_ack_engine().ack(
        notification_id=notification_id,
        ack_status=requested_status,
        acked_by=str(message["acked_by"]) if message.get("acked_by") is not None else None,
        metadata={"transport": "websocket"},
    )
    ack_status = event.ack_status or event.status
    if ack_status is None:
        raise RuntimeError("ack engine returned event without status")

    await websocket.send_json(
        {
            "type": "ack_result",
            "notification_id": str(event.notification_id),
            "ack_status": ack_status.value,
            "acked_by": event.acked_by,
        }
    )

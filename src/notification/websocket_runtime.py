"""Standalone FastAPI WebSocket runtime for AGSignal clients."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from agsignal.api.auth import (
    WritePrincipal,
    require_principal_scope,
    require_websocket_principal,
    resolve_requested_actor,
)
from notification.channel_health import ChannelHealthTracker
from notification.models import AckStatus, Channel

logger = logging.getLogger(__name__)


@runtime_checkable
class WebSocketReplayStore(Protocol):
    """Read model for replaying WebSocket notifications after reconnect."""

    def record(
        self,
        agent_id: UUID,
        notification: Mapping[str, object],
        created_at: datetime | None = None,
    ) -> str: ...

    def missed(
        self,
        agent_id: UUID,
        last_seen: str | None,
        limit: int = 100,
    ) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class _ReplayEntry:
    agent_id: UUID
    created_at: datetime
    payload: dict[str, object]


class InMemoryWebSocketReplayStore:
    """Process-local WebSocket replay read model.

    The store keeps a bounded payload log per agent and exposes cursor-based
    replay. Durable deployments can provide another WebSocketReplayStore
    implementation without changing the WebSocket protocol.
    """

    def __init__(self, max_entries_per_agent: int = 1000) -> None:
        self._max_entries_per_agent = max_entries_per_agent
        self._entries_by_agent: dict[UUID, list[_ReplayEntry]] = {}

    def record(
        self,
        agent_id: UUID,
        notification: Mapping[str, object],
        created_at: datetime | None = None,
    ) -> str:
        created_at = _normalize_cursor_time(created_at or datetime.now(UTC))
        replay_cursor = _format_replay_cursor(created_at)
        payload = dict(notification)
        payload["replay_cursor"] = replay_cursor
        entries = self._entries_by_agent.setdefault(agent_id, [])
        entries.append(_ReplayEntry(agent_id=agent_id, created_at=created_at, payload=payload))
        if len(entries) > self._max_entries_per_agent:
            del entries[: len(entries) - self._max_entries_per_agent]
        return replay_cursor

    def missed(
        self,
        agent_id: UUID,
        last_seen: str | None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        since = _parse_replay_cursor(last_seen)
        if since is None:
            return []

        entries = [
            entry
            for entry in self._entries_by_agent.get(agent_id, [])
            if entry.created_at > since
        ]
        return [dict(entry.payload) for entry in entries[-limit:]]


def _normalize_cursor_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_replay_cursor(value: datetime) -> str:
    return _normalize_cursor_time(value).isoformat()


def _parse_replay_cursor(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _normalize_cursor_time(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


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
        reconnect_initial_delay_seconds: float = 0.25,
        reconnect_max_delay_seconds: float = 5.0,
    ) -> None:
        self._redis = redis_client
        self._channel_prefix = channel_prefix
        self._manager = manager
        self._origin_id = origin_id
        self._channel_health_tracker = channel_health_tracker
        self._reconnect_initial_delay_seconds = reconnect_initial_delay_seconds
        self._reconnect_max_delay_seconds = reconnect_max_delay_seconds
        self._tasks_by_agent: dict[UUID, asyncio.Task[None]] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=16,
            thread_name_prefix="uns-ws-redis",
        )

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
        reconnect_delay = self._reconnect_initial_delay_seconds
        try:
            while True:
                pubsub: RedisPubSub | None = None
                try:
                    loop = asyncio.get_running_loop()
                    pubsub = self._redis.pubsub()
                    await loop.run_in_executor(
                        self._executor,
                        pubsub.subscribe,
                        self.channel_for_agent(agent_id),
                    )
                    reconnect_delay = self._reconnect_initial_delay_seconds
                    while True:
                        message = await loop.run_in_executor(
                            self._executor,
                            pubsub.get_message,
                            True,
                            0.5,
                        )
                        await self.handle_message(message)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("Redis WebSocket subscription failed: %s", exc)
                    if self._channel_health_tracker is not None:
                        self._channel_health_tracker.record_failure(
                            Channel.WEBSOCKET,
                            reason=str(exc),
                        )
                    if reconnect_delay > 0:
                        await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(
                        self._reconnect_max_delay_seconds,
                        reconnect_delay * 2
                        if reconnect_delay > 0
                        else self._reconnect_initial_delay_seconds,
                    )
                finally:
                    if pubsub is not None:
                        with suppress(Exception):
                            await asyncio.get_running_loop().run_in_executor(
                                self._executor,
                                pubsub.close,
                            )
        except asyncio.CancelledError:
            raise
        finally:
            self._tasks_by_agent.pop(agent_id, None)


def get_missed_notifications(
    agent_id: UUID,
    last_seen: str | None = None,
    replay_store: WebSocketReplayStore | None = None,
) -> list[dict[str, object]]:
    """Return missed notifications for a reconnecting agent.

    Missing or invalid cursors return an empty list so reconnecting clients do
    not accidentally request the entire retained history.
    """
    if replay_store is None:
        return []
    return replay_store.missed(agent_id=agent_id, last_seen=last_seen)


async def websocket_endpoint(websocket: WebSocket, agent_id: UUID) -> None:
    """Handle a standalone AGSignal agent WebSocket session."""
    principal, subprotocol = require_websocket_principal(websocket)
    manager: WebSocketConnectionManager = websocket.app.state.websocket_manager
    connection_id = str(uuid4())
    await websocket.accept(subprotocol=subprotocol)
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
            try:
                message = await websocket.receive_json()
            except (json.JSONDecodeError, UnicodeError):
                await websocket.send_json({"type": "error", "error": "invalid_message", "message": "Expected JSON"})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "error": "invalid_message", "message": "Expected an object"})
                continue
            message_type = message.get("type")
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif message_type == "subscribe":
                replay_store = getattr(websocket.app.state, "websocket_replay_store", None)
                missed = get_missed_notifications(
                    agent_id,
                    str(message["last_seen"]) if message.get("last_seen") is not None else None,
                    replay_store=replay_store,
                )
                await websocket.send_json(
                    {
                        "type": "subscribed",
                        "agent_id": str(agent_id),
                        "missed_notifications": missed,
                        "replay_available": bool(missed),
                    }
                )
            elif message_type == "ack":
                await _handle_ack_message(websocket, message, principal)
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


async def _handle_ack_message(
    websocket: WebSocket, message: dict[str, object], principal: WritePrincipal,
) -> None:
    """Commit the same durable response as HTTP; never mutate the legacy engine."""
    from uns.runtime import Conflict

    try:
        require_principal_scope(principal, "responder")
        notification_id = UUID(str(message.get("notification_id", "")))
        requested_status = AckStatus(str(message.get("status", AckStatus.ACKED.value)))
        if requested_status not in (AckStatus.ACKED, AckStatus.DISMISSED):
            raise ValueError("Only ACKED or DISMISSED responses are supported")
        actor = resolve_requested_actor(
            principal, str(message["acked_by"]) if message.get("acked_by") is not None else None,
        )
        runtime = getattr(websocket.app.state, "runtime", None)
        if runtime is None:
            await websocket.send_json({"type": "error", "error": "runtime_unavailable", "message": "Durable ACK runtime is not configured"})
            return
        event = runtime.acknowledge(
            notification_id, actor=actor, dismiss=requested_status == AckStatus.DISMISSED,
            metadata={"transport": "websocket"},
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": "forbidden", "message": str(exc.detail)}
        await websocket.send_json({"type": "error", **detail})
        return
    except KeyError:
        await websocket.send_json({"type": "error", "error": "not_found", "message": "Notification not found"})
        return
    except Conflict as exc:
        await websocket.send_json({"type": "error", "error": "invalid_transition", "message": str(exc)})
        return
    except (ValueError, TypeError) as exc:
        await websocket.send_json({"type": "error", "error": "invalid_message", "message": str(exc)})
        return
    await websocket.send_json({"type": "ack_result", **event.model_dump(mode="json")})

"""WebSocket adapter for notification delivery.

This module implements the WebSocket channel adapter for real-time
push notifications to connected clients. Designed for fire-and-forget
delivery as specified in the PRD.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from notification.adapters.base import (
    AdapterStatus,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)
from notification.models import Channel

if TYPE_CHECKING:
    from notification.models import Notification

logger = logging.getLogger(__name__)


class WebSocketConnection(Protocol):
    """Protocol for WebSocket connections.

    Allows plugging in different WebSocket implementations
    (websockets, aiohttp, FastAPI, etc.)
    """

    async def send(self, message: str) -> None:
        """Send a message through the connection."""
        ...

    async def close(self) -> None:
        """Close the connection."""
        ...

    @property
    def is_connected(self) -> bool:
        """Check if the connection is still active."""
        ...


class WebSocketConnectionManager(Protocol):
    """Protocol for managing WebSocket connections.

    Allows different implementations for connection tracking
    and message broadcasting.
    """

    async def broadcast(self, message: str) -> int:
        """Broadcast message to all connected clients.

        Returns:
            Number of clients that received the message
        """
        ...

    async def send_to_user(self, user_id: str, message: str) -> bool:
        """Send message to a specific user.

        Returns:
            True if message was sent, False if user not connected
        """
        ...

    async def send_to_agent(self, agent_id: UUID, message: str) -> bool:
        """Send message to connections subscribed to an agent.

        Returns:
            True if message was sent, False if no subscriptions
        """
        ...

    def get_connection_count(self) -> int:
        """Get the current number of active connections."""
        ...


@dataclass
class InMemoryConnectionManager:
    """Simple in-memory connection manager for WebSocket clients.

    This is a basic implementation suitable for single-process deployments.
    For distributed deployments, use Redis-backed pub/sub.
    """

    _connections: dict[str, WebSocketConnection] = field(default_factory=dict)
    _user_connections: dict[str, set[str]] = field(default_factory=dict)
    _agent_subscriptions: dict[UUID, set[str]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def register(
        self,
        connection_id: str,
        connection: WebSocketConnection,
        user_id: str | None = None,
        agent_ids: list[UUID] | None = None,
    ) -> None:
        """Register a new WebSocket connection."""
        async with self._lock:
            self._connections[connection_id] = connection

            if user_id:
                if user_id not in self._user_connections:
                    self._user_connections[user_id] = set()
                self._user_connections[user_id].add(connection_id)

            if agent_ids:
                for agent_id in agent_ids:
                    if agent_id not in self._agent_subscriptions:
                        self._agent_subscriptions[agent_id] = set()
                    self._agent_subscriptions[agent_id].add(connection_id)

    async def unregister(self, connection_id: str) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            self._connections.pop(connection_id, None)

            # Clean up user mappings
            for user_id, conn_ids in list(self._user_connections.items()):
                conn_ids.discard(connection_id)
                if not conn_ids:
                    del self._user_connections[user_id]

            # Clean up agent subscriptions
            for agent_id, conn_ids in list(self._agent_subscriptions.items()):
                conn_ids.discard(connection_id)
                if not conn_ids:
                    del self._agent_subscriptions[agent_id]

    async def broadcast(self, message: str) -> int:
        """Broadcast message to all connected clients."""
        sent_count = 0
        disconnected = []

        async with self._lock:
            connections = list(self._connections.items())

        for conn_id, conn in connections:
            try:
                if conn.is_connected:
                    await conn.send(message)
                    sent_count += 1
                else:
                    disconnected.append(conn_id)
            except Exception as e:
                logger.warning("Failed to send to connection %s: %s", conn_id, e)
                disconnected.append(conn_id)

        # Clean up disconnected
        for conn_id in disconnected:
            await self.unregister(conn_id)

        return sent_count

    async def send_to_user(self, user_id: str, message: str) -> bool:
        """Send message to a specific user."""
        async with self._lock:
            conn_ids = self._user_connections.get(user_id, set()).copy()

        if not conn_ids:
            return False

        sent = False
        for conn_id in conn_ids:
            async with self._lock:
                conn = self._connections.get(conn_id)

            if conn and conn.is_connected:
                try:
                    await conn.send(message)
                    sent = True
                except Exception as e:
                    logger.warning("Failed to send to user %s: %s", user_id, e)

        return sent

    async def send_to_agent(self, agent_id: UUID, message: str) -> bool:
        """Send message to connections subscribed to an agent."""
        async with self._lock:
            conn_ids = self._agent_subscriptions.get(agent_id, set()).copy()

        if not conn_ids:
            return False

        sent = False
        for conn_id in conn_ids:
            async with self._lock:
                conn = self._connections.get(conn_id)

            if conn and conn.is_connected:
                try:
                    await conn.send(message)
                    sent = True
                except Exception as e:
                    logger.warning("Failed to send to agent %s subscriber: %s", agent_id, e)

        return sent

    def get_connection_count(self) -> int:
        """Get the current number of active connections."""
        return len(self._connections)


@dataclass
class WebSocketConfig:
    """Configuration for the WebSocket adapter.

    Attributes:
        broadcast_mode: Whether to broadcast to all clients (default)
        target_user_metadata_key: Metadata key for targeted user delivery
        include_metadata: Include notification metadata in the payload
        json_encoder: Optional custom JSON encoder
    """

    broadcast_mode: bool = True
    target_user_metadata_key: str = "websocket_user_id"
    include_metadata: bool = True
    json_encoder: Callable[[Any], str] | None = None


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder that handles UUIDs."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


@dataclass
class WebSocketAdapter(BaseAdapter):
    """WebSocket adapter for real-time notification delivery.

    Designed for fire-and-forget delivery. Failures are logged
    but do not raise exceptions (BEST_EFFORT semantics).

    Supports:
    - Broadcasting to all connected clients
    - Targeted delivery to specific users
    - Agent-based subscriptions
    - Structured JSON payloads
    """

    config: WebSocketConfig
    connection_manager: WebSocketConnectionManager
    _json_encoder: json.JSONEncoder = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._json_encoder = UUIDEncoder()

    @property
    def channel(self) -> Channel:
        return Channel.WEBSOCKET

    async def deliver(self, notification: Notification) -> DeliveryResult:
        """Deliver a notification via WebSocket.

        This is a fire-and-forget operation. Failures are logged but
        the method returns success=False rather than raising exceptions.

        Args:
            notification: The notification to deliver

        Returns:
            DeliveryResult with delivery status
        """
        try:
            payload = self._build_payload(notification)
            message = self._encode_json(payload)

            delivered_to = 0

            # Try targeted delivery first if specified
            target_user = notification.metadata.get(self.config.target_user_metadata_key)
            if target_user:
                sent = await self.connection_manager.send_to_user(str(target_user), message)
                if sent:
                    delivered_to += 1
                    logger.debug(
                        "WebSocket notification sent to user: notification_id=%s, user=%s",
                        notification.notification_id,
                        target_user,
                    )

            # Try agent-based delivery
            agent_id = notification.autonomy_context.agent_id
            sent = await self.connection_manager.send_to_agent(agent_id, message)
            if sent:
                delivered_to += 1
                logger.debug(
                    "WebSocket notification sent to agent subscribers: notification_id=%s, agent=%s",
                    notification.notification_id,
                    agent_id,
                )

            # Broadcast if configured and no targeted delivery succeeded
            if self.config.broadcast_mode and delivered_to == 0:
                count = await self.connection_manager.broadcast(message)
                delivered_to = count
                logger.debug(
                    "WebSocket notification broadcast: notification_id=%s, recipients=%d",
                    notification.notification_id,
                    count,
                )

            if delivered_to > 0:
                logger.info(
                    "WebSocket notification delivered: notification_id=%s, recipients=%d",
                    notification.notification_id,
                    delivered_to,
                )

                return DeliveryResult(
                    success=True,
                    channel=Channel.WEBSOCKET,
                    metadata={
                        "recipients_count": delivered_to,
                        "broadcast": self.config.broadcast_mode,
                    },
                    delivered_at=datetime.now(UTC),
                )
            else:
                # No connected clients - this is expected in some scenarios
                logger.info(
                    "WebSocket notification: no connected clients: notification_id=%s",
                    notification.notification_id,
                )

                return DeliveryResult(
                    success=True,  # Fire-and-forget, no clients is not a failure
                    channel=Channel.WEBSOCKET,
                    metadata={
                        "recipients_count": 0,
                        "no_clients": True,
                    },
                    delivered_at=datetime.now(UTC),
                )

        except Exception as e:
            # WebSocket is fire-and-forget, log but don't propagate
            logger.error(
                "WebSocket delivery error: notification_id=%s, error=%s",
                notification.notification_id,
                str(e),
            )

            return DeliveryResult(
                success=False,
                channel=Channel.WEBSOCKET,
                error=str(e),
                delivered_at=datetime.now(UTC),
            )

    async def health_check(self) -> HealthCheckResult:
        """Check WebSocket connection manager health."""
        try:
            connection_count = self.connection_manager.get_connection_count()

            # Connection manager is always "healthy" as it's in-process
            # The health check mainly reports on current state
            if connection_count > 0:
                return HealthCheckResult(
                    status=AdapterStatus.HEALTHY,
                    message=f"WebSocket adapter active with {connection_count} connections",
                    metadata={"connection_count": connection_count},
                )
            else:
                return HealthCheckResult(
                    status=AdapterStatus.HEALTHY,
                    message="WebSocket adapter active, no current connections",
                    metadata={"connection_count": 0},
                )

        except Exception as e:
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message=f"WebSocket health check failed: {e}",
                metadata={"error": str(e)},
            )

    def format_message(self, notification: Notification) -> str:
        """Format notification as JSON string."""
        payload = self._build_payload(notification)
        return self._encode_json(payload)

    def _build_payload(self, notification: Notification) -> dict[str, Any]:
        """Build WebSocket message payload."""
        payload: dict[str, Any] = {
            "type": "notification",
            "notification_id": str(notification.notification_id),
            "notification_type": notification.notification_type,
            "intent": notification.intent.value,
            "title": notification.title,
            "message": notification.message,
            "priority": (notification.priority.value if notification.priority else None),
            "require_ack": notification.require_ack,
            "created_at": notification.created_at.isoformat(),
            "autonomy_context": {
                "autonomy_mode": notification.autonomy_context.autonomy_mode.value,
                "agent_id": str(notification.autonomy_context.agent_id),
            },
        }

        if self.config.include_metadata and notification.metadata:
            # Filter out internal metadata keys
            external_metadata = {
                k: v
                for k, v in notification.metadata.items()
                if not k.startswith("_") and k != self.config.target_user_metadata_key
            }
            if external_metadata:
                payload["metadata"] = external_metadata

        if notification.require_ack and notification.ack_timeout_minutes:
            payload["ack_timeout_minutes"] = notification.ack_timeout_minutes

        return payload

    def _encode_json(self, payload: dict[str, Any]) -> str:
        """Encode payload as JSON string."""
        if self.config.json_encoder:
            return self.config.json_encoder(payload)
        return json.dumps(payload, cls=UUIDEncoder)

"""Runtime configuration and state for AGSignal MCP tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agsignal._in_memory import InMemoryRedisList
from agsignal.responses import SendNotificationResponse
from notification.audit import AuditStore, InMemoryAuditStore
from notification.channel_health import ChannelHealthTracker
from notification.dlq import DLQService

RuntimeMode = Literal["stdio-local", "stdio-persistent", "read-only"]


@dataclass(frozen=True)
class MCPRuntimeConfig:
    """Safe local runtime defaults for the AGSignal MCP server."""

    mode: RuntimeMode = "stdio-local"
    read_only: bool = True
    require_delivery_confirmation: bool = True
    operator_principal: str | None = None
    delivery_confirmation_token: str | None = None


@dataclass
class RuntimeState:
    """Process-scoped runtime services shared by MCP tools.

    Holds the in-memory audit store, DLQ service, channel-health tracker, and
    idempotency cache. The MCP write tools (``send_signal``, ``ack_notification``,
    ``dismiss_notification``) delegate to ``agsignal.signaling.*`` and pass the
    relevant fields as keyword arguments. Phase 5 of the v0.2 refactor may
    consolidate this with a Redis-backed idempotency service.
    """

    audit_store: AuditStore = field(default_factory=InMemoryAuditStore)
    dlq_service: DLQService = field(
        default_factory=lambda: DLQService(redis_client=InMemoryRedisList())
    )
    channel_health_tracker: ChannelHealthTracker = field(default_factory=ChannelHealthTracker)
    idempotency_records: dict[str, SendNotificationResponse] = field(default_factory=dict)

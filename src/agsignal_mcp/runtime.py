"""Runtime configuration and state for AGSignal MCP tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from uns.runtime import Runtime

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
    """Services shared by one MCP server lifespan.

    Public factory tools always use ``runtime``. The in-memory fields support
    explicit low-level legacy fixtures only; they cannot silently receive
    production mutations when a durable runtime is absent.
    """

    runtime: Runtime | None = None
    legacy_fixture_mode: bool = False
    audit_store: AuditStore = field(default_factory=InMemoryAuditStore)
    dlq_service: DLQService = field(
        default_factory=lambda: DLQService(redis_client=InMemoryRedisList())
    )
    channel_health_tracker: ChannelHealthTracker = field(default_factory=ChannelHealthTracker)
    idempotency_records: dict[str, SendNotificationResponse] = field(default_factory=dict)

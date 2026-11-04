"""Runtime configuration and state for UNS MCP tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from uns.api.read_models import ReadModelAdapter
    from uns.runtime import Runtime

from notification.audit import AuditStore, InMemoryAuditStore
from notification.channel_health import ChannelHealthTracker
from notification.dlq import DLQService
from uns._in_memory import InMemoryRedisList
from uns.responses import SendNotificationResponse

RuntimeMode = Literal["stdio-local", "stdio-persistent", "read-only"]


@dataclass(frozen=True)
class MCPRuntimeConfig:
    """Safe local runtime defaults for the UNS MCP server."""

    mode: RuntimeMode = "stdio-local"
    read_only: bool = True
    require_delivery_confirmation: bool = True
    operator_principal: str | None = None
    delivery_confirmation_token: str | None = None
    allowed_sources: frozenset[str] = frozenset()
    allowed_namespaces: frozenset[str] = frozenset()


@dataclass
class RuntimeState:
    """Services shared by one MCP server lifespan.

    Public factory tools always use ``runtime``. Omitted audit and read-model
    dependencies bind to that runtime; explicitly supplied dependencies remain
    available to embedded hosts and fixtures. The in-memory fields cannot
    silently receive production mutations when a durable runtime is absent.
    """

    runtime: Runtime | None = None
    legacy_fixture_mode: bool = False
    read_model_adapter: ReadModelAdapter | None = field(default=None, kw_only=True)
    audit_store: AuditStore | None = None
    dlq_service: DLQService = field(
        default_factory=lambda: DLQService(redis_client=InMemoryRedisList())
    )
    channel_health_tracker: ChannelHealthTracker = field(default_factory=ChannelHealthTracker)
    idempotency_records: dict[str, SendNotificationResponse] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.runtime is not None:
            existing_tracker = getattr(self.runtime, "channel_health", None) or getattr(
                self.runtime, "channel_health_tracker", None
            )
            if (
                isinstance(existing_tracker, ChannelHealthTracker)
                and not self.channel_health_tracker._health
            ):
                self.channel_health_tracker = existing_tracker
            self.runtime.channel_health = self.channel_health_tracker
        self.channel_health = self.channel_health_tracker
        if self.audit_store is None:
            self.audit_store = (
                self.runtime.audit_store if self.runtime is not None else InMemoryAuditStore()
            )
        if self.runtime is not None and self.read_model_adapter is None:
            from uns.api.read_models import SQLAlchemyReadModelAdapter

            self.read_model_adapter = SQLAlchemyReadModelAdapter(
                self.runtime.sessions,
                runtime=self.runtime,
            )


def create_runtime_state(
    uns_runtime: Runtime | None = None,
    *,
    channel_health: ChannelHealthTracker | None = None,
) -> RuntimeState:
    """Create a RuntimeState bound to a shared ChannelHealthTracker instance."""
    resolved_health = (
        channel_health
        or (getattr(uns_runtime, "channel_health", None) if uns_runtime is not None else None)
        or ChannelHealthTracker()
    )
    if uns_runtime is not None:
        uns_runtime.channel_health = resolved_health
    return RuntimeState(runtime=uns_runtime, channel_health_tracker=resolved_health)

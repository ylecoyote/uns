"""Factory for AGSignal MCP servers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import anyio
from mcp.server.fastmcp import FastMCP

from agsignal_mcp.runtime import MCPRuntimeConfig, RuntimeState
from agsignal_mcp.tools import AckNotificationInput, SendSignalInput
from agsignal_mcp.tools import ack_notification as ack_notification_impl
from agsignal_mcp.tools import dismiss_notification as dismiss_notification_impl
from agsignal_mcp.tools import get_channel_health as get_channel_health_impl
from agsignal_mcp.tools import get_delivery_status as get_delivery_status_impl
from agsignal_mcp.tools import get_effective_policy as get_effective_policy_impl
from agsignal_mcp.tools import get_invariants_summary as get_invariants_summary_impl
from agsignal_mcp.tools import health as health_impl
from agsignal_mcp.tools import list_audit_events as list_audit_events_impl
from agsignal_mcp.tools import list_deliveries as list_deliveries_impl
from agsignal_mcp.tools import list_invariants as list_invariants_impl
from agsignal_mcp.tools import ready as ready_impl
from agsignal_mcp.tools import send_signal as send_signal_impl
from agsignal_mcp.tools import simulate_signal as simulate_signal_impl
from uns.runtime import Runtime

AGSIGNAL_MCP_TOOL_NAMES = (
    "simulate_signal",
    "send_signal",
    "get_delivery_status",
    "ack_notification",
    "dismiss_notification",
    "get_notification_status",
    "get_ack_status",
    "list_deliveries",
    "list_audit_events",
    "get_effective_policy",
    "list_invariants",
    "get_invariants_summary",
    "list_dlq",
    "get_channel_health",
    "health",
    "ready",
)


def create_mcp_server(
    runtime_config: MCPRuntimeConfig | None = None, *, runtime: Runtime | None = None,
) -> FastMCP:
    """Create the trusted local stdio server and own its recovery lifecycle.

    Write authority comes from process-launch configuration, never tool input.
    Network MCP hosting requires a separate authenticated transport boundary.
    """
    config = runtime_config or MCPRuntimeConfig()
    if not config.read_only:
        if config.mode == "read-only":
            raise ValueError("read-only mode cannot enable mutations")
        if not config.operator_principal:
            raise ValueError("Writable MCP requires an operator principal")
        if config.require_delivery_confirmation and not config.delivery_confirmation_token:
            raise ValueError("Writable MCP requires a delivery confirmation token")
    from uns.config import build_runtime
    owns_runtime = runtime is None
    runtime = runtime or build_runtime()
    state = RuntimeState(runtime=runtime, audit_store=runtime.audit_store)
    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[RuntimeState]:
        worker = None
        try:
            if not config.read_only:
                worker = asyncio.create_task(runtime.worker(), name="uns-mcp-worker")
            yield state
        finally:
            # MCP server shutdown cancels its AnyIO scope. Shield the join so
            # every Runtime child task has stopped before releasing owned DB resources.
            with anyio.CancelScope(shield=True):
                if worker is not None:
                    worker.cancel()
                    with suppress(asyncio.CancelledError):
                        await worker
                if owns_runtime:
                    runtime.engine.dispose()

    mcp = FastMCP("UNS", lifespan=lifespan)

    @mcp.tool(name="simulate_signal")
    async def simulate_signal_tool(payload: SendSignalInput) -> dict[str, object]:
        """Preview AGSignal routing and policy behavior without side effects."""
        return await simulate_signal_impl(payload, runtime_state=state)

    @mcp.tool(name="send_signal")
    async def send_signal_tool(payload: SendSignalInput) -> dict[str, object]:
        """Preview or send an AGSignal signal."""
        return await send_signal_impl(payload, config=config, runtime_state=state)

    @mcp.tool(name="get_delivery_status")
    def get_delivery_status_tool(notification_id: str) -> dict[str, object]:
        """Return persisted delivery audit status for a notification."""
        return get_delivery_status_impl(notification_id, runtime_state=state)

    @mcp.tool(name="ack_notification")
    async def ack_notification_tool(payload: AckNotificationInput) -> dict[str, object]:
        """Acknowledge a tracked AGSignal notification."""
        return await ack_notification_impl(payload, config=config, runtime_state=state)

    @mcp.tool(name="dismiss_notification")
    async def dismiss_notification_tool(payload: AckNotificationInput) -> dict[str, object]:
        """Dismiss a tracked AGSignal notification."""
        return await dismiss_notification_impl(payload, config=config, runtime_state=state)

    @mcp.tool(name="get_notification_status")
    async def get_notification_status_tool(notification_id: str) -> dict[str, object]:
        """Return notification status from the ACK runtime."""
        try:
            row = runtime.get(notification_id)
            return {"notification_id":notification_id, "found":True, "ack_status":row["ack_status"], "status":row["status"]}
        except KeyError:
            return {"notification_id":notification_id,"found":False}

    @mcp.tool(name="get_ack_status")
    async def get_ack_status_tool(notification_id: str) -> dict[str, object]:
        """Return ACK status for a notification."""
        try:
            return {"notification_id":notification_id,"ack_status":runtime.get(notification_id)["ack_status"]}
        except KeyError:
            return {"notification_id":notification_id,"ack_status":None}

    @mcp.tool(name="list_deliveries")
    async def list_deliveries_tool(limit: int = 25) -> dict[str, object]:
        """Return delivery read-model entries."""
        return await list_deliveries_impl(limit=limit, runtime_state=state)

    @mcp.tool(name="list_audit_events")
    async def list_audit_events_tool(limit: int = 25) -> dict[str, object]:
        """Return audit read-model entries."""
        return await list_audit_events_impl(limit=limit, runtime_state=state)

    @mcp.tool(name="get_effective_policy")
    async def get_effective_policy_tool(
        notification_type: str,
        intent: str,
        autonomy_mode: str,
        irreversible: bool = False,
    ) -> dict[str, object]:
        """Return effective policy resolution for a signal shape."""
        return await get_effective_policy_impl(
            notification_type=notification_type,
            intent=intent,
            autonomy_mode=autonomy_mode,
            irreversible=irreversible,
            runtime_state=state,
        )

    @mcp.tool(name="list_invariants")
    async def list_invariants_tool(limit: int = 25) -> dict[str, object]:
        """Return registered AGSignal invariants."""
        return await list_invariants_impl(limit=limit)

    @mcp.tool(name="get_invariants_summary")
    async def get_invariants_summary_tool() -> dict[str, object]:
        """Return invariant summary counts."""
        return await get_invariants_summary_impl()

    @mcp.tool(name="list_dlq")
    def list_dlq_tool() -> dict[str, object]:
        """List visible dead-lettered delivery failures."""
        return {"depth":len(runtime.dead_letters()), "items":runtime.dead_letters()}

    @mcp.tool(name="get_channel_health")
    def get_channel_health_tool() -> dict[str, object]:
        """Return runtime channel health."""
        return get_channel_health_impl(runtime_state=state)

    @mcp.tool(name="health")
    def health_tool() -> dict[str, object]:
        """Return MCP process liveness."""
        return {**health_impl()}

    @mcp.tool(name="ready")
    def ready_tool() -> dict[str, object]:
        """Return MCP runtime readiness."""
        return ready_impl(config)

    return mcp

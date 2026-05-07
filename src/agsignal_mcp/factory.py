"""Factory for AGSignal MCP servers."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agsignal_mcp.runtime import MCPRuntimeConfig
from agsignal_mcp.tools import SendSignalInput
from agsignal_mcp.tools import send_signal as send_signal_impl
from agsignal_mcp.tools import simulate_signal as simulate_signal_impl

AGSIGNAL_MCP_TOOL_NAMES = (
    "simulate_signal",
    "send_signal",
)


def create_mcp_server(runtime_config: MCPRuntimeConfig | None = None) -> FastMCP:
    """Create an AGSignal MCP server with the v1 tool registry."""
    config = runtime_config or MCPRuntimeConfig()
    mcp = FastMCP("AGSignal")

    @mcp.tool(name="simulate_signal")
    def simulate_signal_tool(payload: SendSignalInput) -> dict[str, object]:
        """Preview AGSignal routing and policy behavior without side effects."""
        return simulate_signal_impl(payload)

    @mcp.tool(name="send_signal")
    def send_signal_tool(payload: SendSignalInput) -> dict[str, object]:
        """Preview or send an AGSignal signal."""
        if config.read_only:
            raise ValueError("send_signal is disabled in read-only mode")
        return send_signal_impl(payload)

    return mcp

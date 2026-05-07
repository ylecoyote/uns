"""Stdio transport entrypoint for the AGSignal MCP server."""

from __future__ import annotations

from agsignal_mcp.factory import create_mcp_server
from agsignal_mcp.runtime import MCPRuntimeConfig


def main() -> None:
    """Run the AGSignal MCP server over stdio."""
    mcp = create_mcp_server(MCPRuntimeConfig())
    mcp.run()


if __name__ == "__main__":
    main()

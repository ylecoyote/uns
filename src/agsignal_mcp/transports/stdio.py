"""Trusted-local stdio entrypoint, read-only unless explicitly enabled."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP
from sqlalchemy.engine import make_url

from agsignal_mcp.factory import create_mcp_server
from agsignal_mcp.runtime import MCPRuntimeConfig
from uns.config import value


def runtime_config(*, enable_writes: bool = False) -> MCPRuntimeConfig:
    """Read host configuration without placing secrets in arguments or URLs."""
    if not enable_writes:
        return MCPRuntimeConfig()
    database_url = value("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    if not database_url:
        raise ValueError("Set UNS_DATABASE_URL before enabling MCP writes")
    parsed = make_url(database_url)
    sqlite_path = unquote(parsed.database or "").removeprefix("file:")
    if parsed.get_backend_name() == "sqlite" and (
        not sqlite_path or sqlite_path == ":memory:" or parsed.query.get("mode") == "memory"
    ):
        raise ValueError("Write-enabled MCP requires a persistent database")
    principal = value("API_PRINCIPAL")
    if not principal:
        raise ValueError("Set UNS_API_PRINCIPAL before enabling MCP writes")
    confirmation = value("MCP_DELIVERY_CONFIRMATION_TOKEN")
    if not confirmation:
        raise ValueError("Set UNS_MCP_DELIVERY_CONFIRMATION_TOKEN before enabling MCP writes")
    return MCPRuntimeConfig(
        mode="stdio-persistent", read_only=False, operator_principal=principal,
        delivery_confirmation_token=confirmation,
    )


async def _serve(mcp: FastMCP) -> None:
    """Cancel stdio on SIGTERM so the MCP lifespan joins its recovery worker."""
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await mcp.run_stdio_async()
    except asyncio.CancelledError:
        pass  # SIGINT (asyncio.run) and SIGTERM both execute lifespan cleanup.
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def main(argv: list[str] | None = None) -> None:
    """Run stdio; secrets and database configuration come from the environment."""
    parser = argparse.ArgumentParser(description="UNS local MCP server (read-only by default)")
    parser.add_argument("--enable-writes", action="store_true", help="Enable durable writes using required host environment configuration")
    args = parser.parse_args(argv)
    try:
        config = runtime_config(enable_writes=args.enable_writes)
    except ValueError as exc:
        parser.error(str(exc))
    mcp = create_mcp_server(config)
    asyncio.run(_serve(mcp))


if __name__ == "__main__":
    main()

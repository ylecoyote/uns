"""Trusted local MCP entry point using the same recording profile and database."""

import argparse
import asyncio

from recording_runtime import make_runtime

from uns_mcp.factory import create_mcp_server
from uns_mcp.transports.stdio import _serve, runtime_config


def main() -> None:
    parser = argparse.ArgumentParser(description="UNS local recording MCP")
    parser.add_argument("--enable-writes", action="store_true")
    arguments = parser.parse_args()
    runtime = make_runtime()
    try:
        asyncio.run(
            _serve(
                create_mcp_server(
                    runtime_config(enable_writes=arguments.enable_writes), runtime=runtime
                )
            )
        )
    finally:
        runtime.engine.dispose()


if __name__ == "__main__":
    main()

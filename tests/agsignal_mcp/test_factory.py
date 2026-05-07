from __future__ import annotations

from agsignal_mcp import MCPRuntimeConfig


def test_runtime_config_defaults_to_safe_local_stdio() -> None:
    config = MCPRuntimeConfig()

    assert config.mode == "stdio-local"
    assert config.read_only is False
    assert config.require_delivery_confirmation is True

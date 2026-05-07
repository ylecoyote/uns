from __future__ import annotations

from agsignal_mcp import MCPRuntimeConfig
from agsignal_mcp.factory import AGSIGNAL_MCP_TOOL_NAMES, create_mcp_server


def test_runtime_config_defaults_to_safe_local_stdio() -> None:
    config = MCPRuntimeConfig()

    assert config.mode == "stdio-local"
    assert config.read_only is True
    assert config.require_delivery_confirmation is True
    assert config.operator_principal is None


def test_factory_declares_v1_signal_tool_names() -> None:
    create_mcp_server(MCPRuntimeConfig())

    assert "simulate_signal" in AGSIGNAL_MCP_TOOL_NAMES
    assert "send_signal" in AGSIGNAL_MCP_TOOL_NAMES
    assert "reload_policies" not in AGSIGNAL_MCP_TOOL_NAMES
    assert "remove_dlq_entry" not in AGSIGNAL_MCP_TOOL_NAMES

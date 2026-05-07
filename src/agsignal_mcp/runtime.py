"""Runtime configuration for AGSignal MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RuntimeMode = Literal["stdio-local", "stdio-persistent", "read-only"]


@dataclass(frozen=True)
class MCPRuntimeConfig:
    """Safe local runtime defaults for the AGSignal MCP server."""

    mode: RuntimeMode = "stdio-local"
    read_only: bool = True
    require_delivery_confirmation: bool = True
    operator_principal: str | None = None
    delivery_confirmation_token: str | None = None

"""AGSignal Model Context Protocol integration.

``MCPRuntimeConfig`` is a pure-Python dataclass and is always importable.

``create_mcp_server`` requires the optional ``[mcp]`` extra::

    pip install 'agsignal[mcp]'

It is loaded lazily via PEP 562 module ``__getattr__`` so that
``import agsignal_mcp`` succeeds even when the ``mcp`` runtime dependency
is not installed. Only attribute access for ``create_mcp_server`` triggers
the import; failure surfaces a clear instruction to install the extra.
"""

from __future__ import annotations

from typing import Any

from agsignal_mcp.runtime import MCPRuntimeConfig

__all__ = ["MCPRuntimeConfig", "create_mcp_server"]


def __getattr__(name: str) -> Any:
    if name == "create_mcp_server":
        try:
            from agsignal_mcp.factory import create_mcp_server
        except ModuleNotFoundError as exc:
            if exc.name == "mcp":
                raise ModuleNotFoundError(
                    "agsignal_mcp.create_mcp_server requires the optional 'mcp' "
                    "dependency. Install with: pip install 'agsignal[mcp]'"
                ) from exc
            raise
        return create_mcp_server
    raise AttributeError(f"module 'agsignal_mcp' has no attribute {name!r}")

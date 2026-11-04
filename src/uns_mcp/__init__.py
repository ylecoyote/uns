"""UNS Model Context Protocol integration.

``MCPRuntimeConfig`` is a pure-Python dataclass and is always importable.

``create_mcp_server`` requires the optional ``[mcp]`` extra::

    pip install 'uns[mcp]'

It is loaded lazily via PEP 562 module ``__getattr__`` so that
``import uns_mcp`` succeeds even when the ``mcp`` runtime dependency
is not installed. Only attribute access for ``create_mcp_server`` triggers
the import; failure surfaces a clear instruction to install the extra.
"""

from __future__ import annotations

from typing import Any

from uns_mcp.runtime import MCPRuntimeConfig

__version__ = "0.6.1"

__all__ = ["MCPRuntimeConfig", "__version__", "create_mcp_server"]


def __getattr__(name: str) -> Any:
    if name == "create_mcp_server":
        try:
            from uns_mcp.factory import create_mcp_server
        except ModuleNotFoundError as exc:
            if exc.name == "mcp":
                raise ModuleNotFoundError(
                    "uns_mcp.create_mcp_server requires the optional 'mcp' "
                    "dependency. Install with: pip install 'uns[mcp]'"
                ) from exc
            raise
        return create_mcp_server
    raise AttributeError(f"module 'uns_mcp' has no attribute {name!r}")

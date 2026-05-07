from __future__ import annotations

from agsignal_mcp.transports.stdio import main


def test_stdio_main_is_importable() -> None:
    assert callable(main)

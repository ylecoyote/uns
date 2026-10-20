"""UNS public API with lazy optional runtime dependencies."""

from typing import Any

import agsignal as _legacy

__all__ = [*_legacy.__all__, "Client", "Runtime"]


def __getattr__(name: str) -> Any:
    if name == "Client":
        from uns.client import Client

        return Client
    if name == "Runtime":
        from uns.runtime import Runtime

        return Runtime
    return getattr(_legacy, name)

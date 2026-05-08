"""Typed domain errors raised by the AGSignal service layer.

Service-layer functions (``agsignal.queries``, ``agsignal.signaling``)
raise these exceptions instead of HTTP-shaped errors. Route adapters
translate them to HTTP status codes; non-HTTP transports (MCP tools,
Python SDK) handle them as Python exceptions.
"""

from __future__ import annotations


class AGSignalError(Exception):
    """Base class for AGSignal service-layer domain errors."""


class NotFoundError(AGSignalError):
    """A requested resource does not exist.

    The route adapter translates this to HTTP 404. Non-HTTP transports
    propagate as a Python exception.
    """

    def __init__(self, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} not found: {identifier}")


__all__ = [
    "AGSignalError",
    "NotFoundError",
]

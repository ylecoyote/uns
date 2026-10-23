"""Canonical UNS HTTP entrypoint, sharing the legacy app instance."""

from typing import TYPE_CHECKING, Any

from agsignal.app import create_app, main

if TYPE_CHECKING:
    from fastapi import FastAPI

    app: FastAPI


def __getattr__(name: str) -> Any:
    if name == "app":
        import agsignal.app as _agsignal_app

        return _agsignal_app.app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app", "create_app", "main"]

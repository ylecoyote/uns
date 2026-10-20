"""Canonical UNS HTTP entrypoint, sharing the legacy app instance."""

from agsignal.app import app, create_app, main

__all__ = ["app", "create_app", "main"]

"""AGSignal HTTP rate limiter.

Wraps :mod:`slowapi` to apply a process-wide default limit to all HTTP routes
on AGSignal Core and Console. Limits are keyed by API principal when a Bearer
token (or ``X-AGSignal-API-Key`` / legacy ``X-UNS-API-Key``) is present, and
fall back to the remote IP otherwise.

Probe traffic — Kubernetes ``/healthz`` / ``/readyz`` (~6 req/min) and
Prometheus ``/metrics`` scrapes (~4 req/min) — runs well below the default
limit (``1000/minute``), so probes are unaffected without explicit exemption.
Operators who want stricter behavior should tighten the limit; operators who
want different limits per route should layer reverse-proxy limits in front
(see ``docs/DEPLOYMENT.md``).

Configuration:
    - ``AGSIGNAL_RATE_LIMIT_DEFAULT``: limit string in slowapi format
      (default ``"1000/minute"``). Set to an empty string to disable.
    - ``AGSIGNAL_RATE_LIMIT_STORAGE_URI``: storage backend URI
      (default ``"memory://"``). For multi-process deployments use Redis,
      e.g. ``"redis://redis.internal:6379/0"``.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def _rate_limit_key(request: Request) -> str:
    """Compose a rate-limit key from the verified principal or remote IP.

    Authenticated callers are keyed by their bearer token / API key. Anonymous
    callers fall back to remote IP. The key string is a slowapi storage key,
    not a credential — but we still avoid logging full keys elsewhere.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return f"key:{auth[7:]}"
    api_key = request.headers.get("x-agsignal-api-key") or request.headers.get(
        "x-uns-api-key"
    )
    if api_key:
        return f"key:{api_key}"
    return f"ip:{get_remote_address(request)}"


def _default_limit() -> str | None:
    """Resolve the default limit string. Empty string disables rate limiting."""
    raw = os.environ.get("AGSIGNAL_RATE_LIMIT_DEFAULT", "1000/minute").strip()
    return raw or None


def _build_limiter() -> Limiter:
    storage_uri = os.environ.get("AGSIGNAL_RATE_LIMIT_STORAGE_URI", "memory://")
    default_limit = _default_limit()
    return Limiter(
        key_func=_rate_limit_key,
        storage_uri=storage_uri,
        default_limits=[default_limit] if default_limit else [],
        headers_enabled=True,
    )


def install_rate_limiter(app: FastAPI) -> None:
    """Install slowapi-based rate limiting on a FastAPI app.

    Idempotent — repeated calls on the same app are no-ops. Reads environment
    on each fresh installation, so each ``create_app()`` call gets a Limiter
    matched to the current env (important for tests that mutate env via
    monkeypatch).
    """
    if getattr(app.state, "agsignal_rate_limiter_installed", False):
        return
    if _default_limit() is None:
        # Operator explicitly disabled rate limiting via empty env var.
        app.state.agsignal_rate_limiter_installed = True
        return

    limiter = _build_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.state.agsignal_rate_limiter_installed = True

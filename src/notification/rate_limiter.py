"""UNS HTTP rate limiter.

Wraps :mod:`slowapi` to apply a process-wide default limit to all HTTP routes
on UNS Core and Console. Limits are keyed by API principal when a Bearer
token (or ``X-UNS-API-Key`` / legacy ``X-UNS-API-Key``) is present, and
fall back to the remote IP otherwise.

Probe traffic - Kubernetes ``/healthz`` / ``/readyz`` (~6 req/min) and
Prometheus ``/metrics`` scrapes (~4 req/min) - runs well below the default
limit (``1000/minute``), so probes are unaffected without explicit exemption.
Operators who want stricter behavior should tighten the limit; operators who
want different limits per route should layer reverse-proxy limits in front
(see ``docs/DEPLOYMENT.md``).

Configuration:
    - ``UNS_RATE_LIMIT_DEFAULT``: limit string in slowapi format
      (default ``"1000/minute"``). Set to an empty string to disable.
    - ``UNS_RATE_LIMIT_STORAGE_URI``: storage backend URI
      (default ``"memory://"``). For multi-process deployments use Redis,
      e.g. ``"redis://redis.internal:6379/0"``.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from uns.api.auth import _configured_credentials, _header_key


def _rate_limit_key(request: Request) -> str:
    """Compose a rate-limit key from the verified principal or remote IP.

    Authenticated callers whose bearer token / API key matches a configured
    credential are keyed by a SHA-256 digest of that key. Unauthenticated or
    invalid callers fall back to remote IP so rotating spoofed headers cannot
    bypass rate limits or grow limiter state unboundedly.
    """
    provided_key = _header_key(request)
    if provided_key:
        provided_key = provided_key.strip()
    if provided_key:
        provided_bytes = provided_key.encode()
        for configured_key, _, _ in _configured_credentials(request):
            if hmac.compare_digest(provided_bytes, configured_key.encode()):
                return f"key:{hashlib.sha256(provided_bytes).hexdigest()[:16]}"
    return f"ip:{get_remote_address(request)}"


def _default_limit() -> str | None:
    """Resolve the default limit string. Empty string disables rate limiting."""
    raw = os.environ.get("UNS_RATE_LIMIT_DEFAULT", "1000/minute").strip()
    return raw or None


def _build_limiter() -> Limiter:
    storage_uri = os.environ.get("UNS_RATE_LIMIT_STORAGE_URI", "memory://")
    default_limit = _default_limit()
    return Limiter(
        key_func=_rate_limit_key,
        storage_uri=storage_uri,
        default_limits=[default_limit] if default_limit else [],
        headers_enabled=True,
    )


def install_rate_limiter(app: FastAPI) -> None:
    """Install slowapi-based rate limiting on a FastAPI app.

    Idempotent - repeated calls on the same app are no-ops. Reads environment
    on each fresh installation, so each ``create_app()`` call gets a Limiter
    matched to the current env (important for tests that mutate env via
    monkeypatch).
    """
    if getattr(app.state, "uns_rate_limiter_installed", False):
        return
    if _default_limit() is None:
        # Operator explicitly disabled rate limiting via empty env var.
        app.state.uns_rate_limiter_installed = True
        return

    limiter = _build_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]  # slowapi narrows its handler exception type
    app.add_middleware(SlowAPIMiddleware)
    app.state.uns_rate_limiter_installed = True

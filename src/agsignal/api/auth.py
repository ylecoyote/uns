"""Shared authentication for HTTP and WebSocket application surfaces.

One configured key represents one configured principal. This is not a role or
multi-tenant authorization system. Caller-supplied identities never confer authority.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketException, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import HTTPConnection


@dataclass(frozen=True)
class WritePrincipal:
    """Verified actor for API calls; name retained for source compatibility."""

    subject: str


def _state_or_env(connection: HTTPConnection, state_name: str, env_name: str, legacy_env: str) -> str | None:
    value = getattr(connection.app.state, state_name, None)
    if value is not None:
        return str(value)
    return os.environ.get(legacy_env, os.environ.get(env_name))


def _bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _authenticate(connection: HTTPConnection, supplied_key: str | None) -> WritePrincipal:
    configured_key = _state_or_env(connection, "agsignal_api_key", "AGSIGNAL_API_KEY", "UNS_API_KEY")
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "write_auth_not_configured", "message": "Set UNS_API_KEY before enabling API access."},
        )
    if not supplied_key or not hmac.compare_digest(supplied_key.encode(), configured_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "A valid UNS API key is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = _state_or_env(connection, "agsignal_api_principal", "AGSIGNAL_API_PRINCIPAL", "UNS_API_PRINCIPAL")
    return WritePrincipal(subject=subject or "agsignal-api-key")


def _header_key(connection: HTTPConnection) -> str | None:
    return (
        _bearer_token(connection.headers.get("authorization"))
        or connection.headers.get("x-agsignal-api-key")
        or connection.headers.get("x-uns-api-key")
    )


def require_write_principal(request: Request) -> WritePrincipal:
    """Require a configured API key and derive the audit actor from it."""
    return _authenticate(request, _header_key(request))


def require_read_principal(request: Request) -> WritePrincipal | None:
    """Protect reads unless an operator explicitly enables legacy HTTP reads.

    The compatibility flag applies only to GET/HEAD. It never permits writes or
    WebSocket establishment, even when a read dependency is reused accidentally.
    """
    legacy = _state_or_env(request, "uns_allow_unauthenticated_reads", "AGSIGNAL_ALLOW_UNAUTHENTICATED_READS", "UNS_ALLOW_UNAUTHENTICATED_READS")
    if request.method in {"GET", "HEAD"} and str(legacy).lower() in {"1", "true", "yes", "on"}:
        return None
    return require_write_principal(request)


def allowed_origins() -> list[str]:
    raw = os.environ.get("UNS_ALLOWED_ORIGINS", os.environ.get("AGSIGNAL_ALLOWED_ORIGINS", ""))
    return [origin.strip() for origin in raw.split(",") if origin.strip()] or [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


def require_websocket_principal(websocket: WebSocket) -> tuple[WritePrincipal, str | None]:
    """Authenticate before accept; browser tokens use a non-echoed subprotocol.

    Browser clients offer ``agsignal.v1`` and ``bearer.<base64url(UTF8(key))>``.
    Credentials are never accepted in URLs and only ``agsignal.v1`` is echoed.
    Non-browser clients can use the same Authorization header as HTTP.
    """
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in allowed_origins():
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Origin is not allowed")
    protocols = websocket.scope.get("subprotocols", [])
    token = _header_key(websocket)
    if token is None and "agsignal.v1" in protocols:
        credentials = [part.removeprefix("bearer.") for part in protocols if part.startswith("bearer.")]
        if len(credentials) == 1:
            try:
                encoded = credentials[0]
                token = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode("utf-8")
            except (ValueError, UnicodeError, binascii.Error):
                token = None
    try:
        principal = _authenticate(websocket, token)
    except HTTPException as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required") from exc
    return principal, "agsignal.v1" if "agsignal.v1" in protocols else None


def resolve_requested_actor(principal: WritePrincipal, requested_actor: str | None) -> str:
    """Only the authenticated principal may be named as the response actor."""
    if requested_actor is None or requested_actor == principal.subject:
        return principal.subject
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "principal_override_forbidden", "message": "acked_by/dismissed_by must match the authenticated principal."},
    )


def configure_cors(app: FastAPI) -> None:
    """Install closed-list CORS for browser-based console deployments."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-AGSignal-API-Key", "X-UNS-API-Key", "X-Request-ID"],
    )

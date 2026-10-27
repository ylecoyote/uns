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

ALL_SCOPES: frozenset[str] = frozenset({"admin", "producer", "responder", "observer"})


@dataclass(frozen=True)
class WritePrincipal:
    """Verified actor and capability scopes for API calls."""

    subject: str
    scopes: frozenset[str] = ALL_SCOPES


def _state_or_env(connection: HTTPConnection, state_name: str, env_name: str) -> str | None:
    value = getattr(connection.app.state, state_name, None)
    if value is not None:
        return str(value)
    return os.environ.get(env_name)


def _bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _configured_credentials(connection: HTTPConnection) -> list[tuple[str, str, frozenset[str]]]:
    """Return configured (key, subject, scopes) tuples in priority order."""
    specs = (
        (
            _state_or_env(connection, "uns_api_key", "UNS_API_KEY"),
            _state_or_env(connection, "uns_api_principal", "UNS_API_PRINCIPAL")
            or "uns-api-key",
            ALL_SCOPES,
        ),
        (
            _state_or_env(connection, "uns_producer_api_key", "UNS_PRODUCER_API_KEY"),
            _state_or_env(
                connection,
                "uns_producer_api_principal",
                "UNS_PRODUCER_API_PRINCIPAL",
            )
            or "uns-producer",
            frozenset({"producer", "observer"}),
        ),
        (
            _state_or_env(connection, "uns_responder_api_key", "UNS_RESPONDER_API_KEY"),
            _state_or_env(
                connection,
                "uns_responder_api_principal",
                "UNS_RESPONDER_API_PRINCIPAL",
            )
            or "uns-responder",
            frozenset({"responder", "observer"}),
        ),
        (
            _state_or_env(connection, "uns_observer_api_key", "UNS_OBSERVER_API_KEY"),
            _state_or_env(
                connection,
                "uns_observer_api_principal",
                "UNS_OBSERVER_API_PRINCIPAL",
            )
            or "uns-observer",
            frozenset({"observer"}),
        ),
    )
    return [(key, subject, scopes) for key, subject, scopes in specs if key]


def require_principal_scope(principal: WritePrincipal, required_scope: str) -> WritePrincipal:
    """Authorize one command for an authenticated principal on any transport."""
    if required_scope not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "message": f"Credential principal '{principal.subject}' lacks required '{required_scope}' authority.",
            },
        )
    return principal


def _authenticate(
    connection: HTTPConnection,
    supplied_key: str | None,
    *,
    required_scope: str = "admin",
) -> WritePrincipal:
    credentials = _configured_credentials(connection)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "write_auth_not_configured", "message": "Set UNS_API_KEY before enabling API access."},
        )
    if not supplied_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "A valid UNS API key is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    matched_subject: str | None = None
    matched_scopes: set[str] = set()
    supplied_bytes = supplied_key.encode()
    for configured_key, subject, scopes in credentials:
        if hmac.compare_digest(supplied_bytes, configured_key.encode()):
            if matched_subject is None:
                matched_subject = subject
            matched_scopes.update(scopes)
    if matched_subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "A valid UNS API key is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = WritePrincipal(subject=matched_subject, scopes=frozenset(matched_scopes))
    return require_principal_scope(principal, required_scope)


def _header_key(connection: HTTPConnection) -> str | None:
    return (
        _bearer_token(connection.headers.get("authorization"))
        or connection.headers.get("x-uns-api-key")
    )


def require_write_principal(request: Request) -> WritePrincipal:
    """Require an operator/admin API key and derive the audit actor from it."""
    return _authenticate(request, _header_key(request), required_scope="admin")


def require_admin_principal(request: Request) -> WritePrincipal:
    """Require operator/admin authority (policy reload, DLQ resolution/replay)."""
    return _authenticate(request, _header_key(request), required_scope="admin")


def require_producer_principal(request: Request) -> WritePrincipal:
    """Require producer or operator authority (send/simulate notifications)."""
    return _authenticate(request, _header_key(request), required_scope="producer")


def require_responder_principal(request: Request) -> WritePrincipal:
    """Require responder or operator authority (acknowledge/dismiss notifications)."""
    return _authenticate(request, _header_key(request), required_scope="responder")


def require_authenticated_observer(request: Request) -> WritePrincipal:
    """Require an authenticated credential with observer authority; never bypassed by legacy read mode."""
    return _authenticate(request, _header_key(request), required_scope="observer")


def require_read_principal(request: Request) -> WritePrincipal | None:
    """Protect reads unless an operator explicitly enables unauthenticated HTTP reads.

    The compatibility flag applies only to GET/HEAD. It never permits writes or
    WebSocket establishment, even when a read dependency is reused accidentally.
    """
    legacy = _state_or_env(request, "uns_allow_unauthenticated_reads", "UNS_ALLOW_UNAUTHENTICATED_READS")
    if request.method in {"GET", "HEAD"} and str(legacy).lower() in {"1", "true", "yes", "on"}:
        return None
    principal = _authenticate(request, _header_key(request), required_scope="observer")
    if request.method not in {"GET", "HEAD"} and not (
        principal.scopes & {"admin", "producer", "responder"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "message": f"Credential principal '{principal.subject}' lacks write authority.",
            },
        )
    return principal


def allowed_origins() -> list[str]:
    raw = os.environ.get("UNS_ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()] or [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


def require_websocket_principal(websocket: WebSocket) -> tuple[WritePrincipal, str | None]:
    """Authenticate before accept; browser tokens use a non-echoed subprotocol.

    Browser clients offer ``uns.v1`` and ``bearer.<base64url(UTF8(key))>``.
    Credentials are never accepted in URLs and only ``uns.v1`` is echoed.
    Non-browser clients can use the same Authorization header as HTTP.
    """
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in allowed_origins():
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Origin is not allowed")
    protocols = websocket.scope.get("subprotocols", [])
    token = _header_key(websocket)
    if token is None and "uns.v1" in protocols:
        credentials = [part.removeprefix("bearer.") for part in protocols if part.startswith("bearer.")]
        if len(credentials) == 1:
            try:
                encoded = credentials[0]
                token = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode("utf-8")
            except (ValueError, UnicodeError, binascii.Error):
                token = None
    try:
        principal = _authenticate(websocket, token, required_scope="observer")
    except HTTPException as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required") from exc
    return principal, "uns.v1" if "uns.v1" in protocols else None


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
        allow_headers=["Authorization", "Content-Type", "X-UNS-API-Key", "X-Request-ID"],
    )

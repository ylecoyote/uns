"""Shared authentication for HTTP and WebSocket application surfaces.

One configured key represents one configured principal. This is not a role or
multi-tenant authorization system. Caller-supplied identities never confer authority.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketException, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import HTTPConnection

ALL_SCOPES: frozenset[str] = frozenset({"admin", "producer", "responder", "observer"})


def matches_scope_patterns(value: str | None, patterns: frozenset[str]) -> bool:
    """Return True if ``value`` matches any configured source/namespace pattern.

    An empty ``patterns`` set (or a pattern of ``"*"``) permits all values.
    Each pattern may be an exact identifier (``"mip.risk"``), a segment prefix
    (``"mip"`` or ``"mip.*"`` or ``"mip."`` matching ``"mip"`` and ``"mip.*"``),
    or a wildcard prefix (``"mip*"``).
    """
    if not patterns or "*" in patterns:
        return True
    if not value:
        return False
    target = value.strip()
    if not target:
        return False
    for raw_pat in patterns:
        pat = raw_pat.strip()
        if not pat:
            continue
        if pat == "*":
            return True
        if pat.endswith(".*"):
            prefix = pat[:-2]
            if target == prefix or target.startswith(f"{prefix}."):
                return True
        elif pat.endswith("*"):
            prefix = pat[:-1]
            if target.startswith(prefix):
                return True
        elif pat.endswith("."):
            prefix = pat[:-1]
            if target == prefix or target.startswith(pat):
                return True
        else:
            if target == pat or target.startswith(f"{pat}."):
                return True
    return False


def _parse_pattern_csv(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in str(raw).split(",") if part.strip())


@dataclass(frozen=True)
class WritePrincipal:
    """Verified actor, capability scopes, and optional source/namespace bounds."""

    subject: str
    scopes: frozenset[str] = ALL_SCOPES
    allowed_sources: frozenset[str] = frozenset()
    allowed_namespaces: frozenset[str] = frozenset()

    def allows_source(self, source: str | None) -> bool:
        """Check whether this principal is authorized for ``source``."""
        if "admin" in self.scopes and not self.allowed_sources:
            return True
        return matches_scope_patterns(source, self.allowed_sources)

    def allows_namespace(self, notification_type: str | None) -> bool:
        """Check whether this principal is authorized for ``notification_type``."""
        if "admin" in self.scopes and not self.allowed_namespaces:
            return True
        return matches_scope_patterns(notification_type, self.allowed_namespaces)


@dataclass(frozen=True)
class _CredentialSpec:
    key: str
    subject: str
    scopes: frozenset[str]
    allowed_sources: frozenset[str] = frozenset()
    allowed_namespaces: frozenset[str] = frozenset()


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


def _configured_credential_specs(connection: HTTPConnection) -> list[_CredentialSpec]:
    """Return configured credential specs in priority order."""
    raw_specs = (
        _CredentialSpec(
            key=_state_or_env(connection, "uns_api_key", "UNS_API_KEY") or "",
            subject=_state_or_env(connection, "uns_api_principal", "UNS_API_PRINCIPAL")
            or "uns-api-key",
            scopes=ALL_SCOPES,
        ),
        _CredentialSpec(
            key=_state_or_env(connection, "uns_producer_api_key", "UNS_PRODUCER_API_KEY") or "",
            subject=_state_or_env(
                connection,
                "uns_producer_api_principal",
                "UNS_PRODUCER_API_PRINCIPAL",
            )
            or "uns-producer",
            scopes=frozenset({"producer", "observer"}),
            allowed_sources=_parse_pattern_csv(
                _state_or_env(
                    connection,
                    "uns_producer_allowed_sources",
                    "UNS_PRODUCER_ALLOWED_SOURCES",
                )
            ),
            allowed_namespaces=_parse_pattern_csv(
                _state_or_env(
                    connection,
                    "uns_producer_allowed_namespaces",
                    "UNS_PRODUCER_ALLOWED_NAMESPACES",
                )
            ),
        ),
        _CredentialSpec(
            key=_state_or_env(connection, "uns_responder_api_key", "UNS_RESPONDER_API_KEY") or "",
            subject=_state_or_env(
                connection,
                "uns_responder_api_principal",
                "UNS_RESPONDER_API_PRINCIPAL",
            )
            or "uns-responder",
            scopes=frozenset({"responder", "observer"}),
            allowed_sources=_parse_pattern_csv(
                _state_or_env(
                    connection,
                    "uns_responder_allowed_sources",
                    "UNS_RESPONDER_ALLOWED_SOURCES",
                )
            ),
            allowed_namespaces=_parse_pattern_csv(
                _state_or_env(
                    connection,
                    "uns_responder_allowed_namespaces",
                    "UNS_RESPONDER_ALLOWED_NAMESPACES",
                )
            ),
        ),
        _CredentialSpec(
            key=_state_or_env(connection, "uns_observer_api_key", "UNS_OBSERVER_API_KEY") or "",
            subject=_state_or_env(
                connection,
                "uns_observer_api_principal",
                "UNS_OBSERVER_API_PRINCIPAL",
            )
            or "uns-observer",
            scopes=frozenset({"observer"}),
            allowed_sources=_parse_pattern_csv(
                _state_or_env(
                    connection,
                    "uns_observer_allowed_sources",
                    "UNS_OBSERVER_ALLOWED_SOURCES",
                )
            ),
            allowed_namespaces=_parse_pattern_csv(
                _state_or_env(
                    connection,
                    "uns_observer_allowed_namespaces",
                    "UNS_OBSERVER_ALLOWED_NAMESPACES",
                )
            ),
        ),
    )
    specs = [spec for spec in raw_specs if spec.key]
    extra_json = _state_or_env(connection, "uns_scoped_api_keys", "UNS_SCOPED_API_KEYS")
    if extra_json:
        try:
            parsed = json.loads(extra_json)
            if isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key", "")).strip()
                    subject = str(item.get("principal") or item.get("subject") or "").strip()
                    raw_scopes = item.get("scopes")
                    if raw_scopes is None:
                        role = str(item.get("role", "observer")).strip().lower()
                        if role == "admin":
                            raw_scopes = list(ALL_SCOPES)
                        elif role in ("producer", "responder"):
                            raw_scopes = [role, "observer"]
                        else:
                            raw_scopes = [role]
                    scopes = frozenset(
                        str(s).strip() for s in raw_scopes if str(s).strip() in ALL_SCOPES
                    )
                    if not key or not subject or not scopes:
                        continue
                    raw_sources = item.get("allowed_sources", [])
                    raw_namespaces = item.get("allowed_namespaces", [])
                    sources = (
                        _parse_pattern_csv(raw_sources)
                        if isinstance(raw_sources, str)
                        else frozenset(str(s).strip() for s in raw_sources if str(s).strip())
                    )
                    namespaces = (
                        _parse_pattern_csv(raw_namespaces)
                        if isinstance(raw_namespaces, str)
                        else frozenset(str(n).strip() for n in raw_namespaces if str(n).strip())
                    )
                    specs.append(
                        _CredentialSpec(
                            key=key,
                            subject=subject,
                            scopes=scopes,
                            allowed_sources=sources,
                            allowed_namespaces=namespaces,
                        )
                    )
        except ValueError:
            pass
    return specs


def _configured_credentials(connection: HTTPConnection) -> list[tuple[str, str, frozenset[str]]]:
    """Return configured (key, subject, scopes) tuples in priority order."""
    return [(s.key, s.subject, s.scopes) for s in _configured_credential_specs(connection)]


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


def require_source_and_namespace(
    principal: WritePrincipal | None,
    *,
    source: str | None = None,
    notification_type: str | None = None,
) -> None:
    """Enforce source and notification_type namespace restrictions for a scoped principal."""
    if principal is None:
        return
    if source is not None and not principal.allows_source(source):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "namespace_or_source_forbidden",
                "message": f"Credential principal '{principal.subject}' is not authorized for source '{source}'.",
            },
        )
    if notification_type is not None and not principal.allows_namespace(notification_type):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "namespace_or_source_forbidden",
                "message": f"Credential principal '{principal.subject}' is not authorized for notification_type '{notification_type}'.",
            },
        )


def _authenticate(
    connection: HTTPConnection,
    supplied_key: str | None,
    *,
    required_scope: str = "admin",
) -> WritePrincipal:
    credentials = _configured_credential_specs(connection)
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
    matched_sources: set[str] = set()
    matched_namespaces: set[str] = set()
    unrestricted_sources = False
    unrestricted_namespaces = False
    supplied_bytes = supplied_key.encode()
    for spec in credentials:
        if hmac.compare_digest(supplied_bytes, spec.key.encode()):
            if matched_subject is None:
                matched_subject = spec.subject
            matched_scopes.update(spec.scopes)
            if not spec.allowed_sources:
                unrestricted_sources = True
            else:
                matched_sources.update(spec.allowed_sources)
            if not spec.allowed_namespaces:
                unrestricted_namespaces = True
            else:
                matched_namespaces.update(spec.allowed_namespaces)
    if matched_subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "A valid UNS API key is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = WritePrincipal(
        subject=matched_subject,
        scopes=frozenset(matched_scopes),
        allowed_sources=frozenset() if unrestricted_sources else frozenset(matched_sources),
        allowed_namespaces=frozenset() if unrestricted_namespaces else frozenset(matched_namespaces),
    )
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

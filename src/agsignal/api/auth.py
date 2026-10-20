"""Authentication helpers for AGSignal HTTP write endpoints."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware


@dataclass(frozen=True)
class WritePrincipal:
    """Verified actor for mutating API calls."""

    subject: str
    allow_subject_override: bool = False


def _state_or_env(request: Request, state_name: str, env_name: str, legacy_env: str) -> str | None:
    value = getattr(request.app.state, state_name, None)
    if value:
        return str(value)
    primary = os.environ.get(legacy_env)
    if primary is not None:
        return primary
    return os.environ.get(env_name)


def _state_or_env_bool(request: Request, state_name: str, env_name: str) -> bool:
    value = getattr(request.app.state, state_name, None)
    if value is None:
        value = os.environ.get(env_name)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_write_principal(request: Request) -> WritePrincipal:
    """Require a configured API key and derive the audit actor from it."""
    configured_key = _state_or_env(
        request,
        "agsignal_api_key",
        "AGSIGNAL_API_KEY",
        "UNS_API_KEY",
    )
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "write_auth_not_configured",
                "message": "Set UNS_API_KEY before enabling write endpoints.",
            },
        )

    supplied_key = (
        _bearer_token(request.headers.get("authorization"))
        or request.headers.get("x-agsignal-api-key")
        or request.headers.get("x-uns-api-key")
    )
    if not supplied_key or not hmac.compare_digest(str(supplied_key), configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "message": "A valid UNS API key is required.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = _state_or_env(
        request,
        "agsignal_api_principal",
        "AGSIGNAL_API_PRINCIPAL",
        "UNS_API_PRINCIPAL",
    )
    return WritePrincipal(
        subject=subject or "agsignal-api-key",
        allow_subject_override=_state_or_env_bool(
            request,
            "agsignal_allow_principal_override",
            "AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE",
        ),
    )


def resolve_requested_actor(
    principal: WritePrincipal,
    requested_actor: str | None,
) -> str:
    """Resolve caller-requested actor fields against the verified principal."""
    if requested_actor is None or requested_actor == principal.subject:
        return principal.subject
    if principal.allow_subject_override:
        return requested_actor
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "principal_override_forbidden",
            "message": "acked_by/dismissed_by must match the authenticated principal.",
        },
    )


def configure_cors(app: FastAPI) -> None:
    """Install closed-list CORS for browser-based console deployments."""
    origins_env = os.environ.get("AGSIGNAL_ALLOWED_ORIGINS", "")
    origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    if not origins:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-AGSignal-API-Key",
            "X-UNS-API-Key",
            "X-Request-ID",
        ],
    )

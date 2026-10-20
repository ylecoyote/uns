"""API routes for notification acknowledgment and status.

This module provides HTTP endpoints for:
- POST /v1/notifications/{id}/ack - Acknowledge a notification
- POST /v1/notifications/{id}/dismiss - Dismiss a notification
- GET /v1/notifications/{id} - Get notification status
- GET /v1/notifications/{id}/ack-status - Get acknowledgment status

Per Phase 2 Task 7, the write routes (ack/dismiss) are thin HTTP adapters
that delegate to ``agsignal.signaling.*``. The route handlers contain only
parameter parsing + auth + observability + delegation + error translation.

Per Phase 3 Task 1, the Pydantic Request/Response DTOs that previously
lived in this module have been relocated to :mod:`agsignal.responses`.
``ErrorResponse`` is re-aliased to ``NotificationErrorResponse`` (the
canonical name in ``agsignal.responses``); the alias preserves the local
name for handler signatures and for any external caller importing
``ErrorResponse`` from this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from uns.runtime import Runtime

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from agsignal.api.auth import WritePrincipal, require_write_principal, resolve_requested_actor
from agsignal.queries import get_ack_status as _query_ack_status
from agsignal.queries import get_engine
from agsignal.queries import get_notification_status as _query_notification_status
from agsignal.responses import (
    AckRequest,
    AckResponse,
    AckStatusResponse,
    DismissRequest,
    NotificationStatusResponse,
)
from agsignal.responses import (
    NotificationErrorResponse as ErrorResponse,
)
from agsignal.signaling import acknowledge, dismiss
from notification.acknowledgment import InvalidAckTransitionError
from notification.audit import AuditPersistenceError, AuditStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


# Routes


@router.post(
    "/{notification_id}/ack",
    response_model=AckResponse,
    responses={
        200: {"description": "Notification acknowledged successfully"},
        404: {"model": ErrorResponse, "description": "Notification not found"},
        409: {"model": ErrorResponse, "description": "Invalid status transition"},
    },
)
async def acknowledge_notification(
    notification_id: UUID,
    http_request: Request,
    principal: WritePrincipal = Depends(require_write_principal),
    request: AckRequest | None = None,
) -> AckResponse:
    """HTTP adapter — delegates to agsignal.signaling.acknowledge.

    Translates typed signaling errors to HTTP responses:
    - ``KeyError`` -> 404 not_found
    - :class:`InvalidAckTransitionError` -> 409 invalid_transition
    - :class:`AuditPersistenceError` -> 503 ack_audit_persistence_failed
    """
    # Ensure the ack engine is initialized before delegation; the route
    # historically auto-configured it via :func:`get_engine` for convenience.
    get_engine()

    request = request or AckRequest()
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    if runtime is not None:
        from uns.runtime import Conflict
        actor = resolve_requested_actor(principal, request.acked_by)
        try:
            return runtime.acknowledge(notification_id, actor=actor, dismiss=False, metadata=request.metadata)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Notification not found") from exc
        except Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    acked_by = resolve_requested_actor(principal, request.acked_by)
    audit_store = getattr(http_request.app.state, "audit_store", None)

    try:
        return await acknowledge(
            notification_id=notification_id,
            acked_by=acked_by,
            metadata=request.metadata,
            audit_store=cast(AuditStore, audit_store),
        )
    except KeyError as exc:
        logger.warning("Ack failed - notification not found: %s", notification_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Notification not found: {notification_id}",
                "notification_id": str(notification_id),
            },
        ) from exc
    except InvalidAckTransitionError as exc:
        logger.warning(
            "Ack failed - invalid transition: notification_id=%s %s -> %s",
            notification_id,
            exc.current_status.value,
            exc.requested_status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
                "notification_id": str(notification_id),
                "current_status": exc.current_status.value,
                "requested_status": exc.requested_status.value,
            },
        ) from exc
    except AuditPersistenceError as exc:
        logger.error(
            "Failed to persist ack audit: notification_id=%s error=%s",
            notification_id,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "ack_audit_persistence_failed",
                "message": "ack state was not committed because audit could not be persisted",
                "notification_id": str(notification_id),
            },
        ) from exc


@router.post(
    "/{notification_id}/dismiss",
    response_model=AckResponse,
    responses={
        200: {"description": "Notification dismissed successfully"},
        404: {"model": ErrorResponse, "description": "Notification not found"},
        409: {"model": ErrorResponse, "description": "Invalid status transition"},
    },
)
async def dismiss_notification(
    notification_id: UUID,
    http_request: Request,
    principal: WritePrincipal = Depends(require_write_principal),
    request: DismissRequest | None = None,
) -> AckResponse:
    """HTTP adapter — delegates to agsignal.signaling.dismiss.

    Translates typed signaling errors to HTTP responses:
    - ``KeyError`` -> 404 not_found
    - :class:`InvalidAckTransitionError` -> 409 invalid_transition
    - :class:`AuditPersistenceError` -> 503 ack_audit_persistence_failed
    """
    # Ensure the ack engine is initialized before delegation; the route
    # historically auto-configured it via :func:`get_engine` for convenience.
    get_engine()

    request = request or DismissRequest()
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    if runtime is not None:
        from uns.runtime import Conflict
        actor = resolve_requested_actor(principal, request.dismissed_by)
        try:
            return runtime.acknowledge(notification_id, actor=actor, dismiss=True, metadata=request.metadata)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Notification not found") from exc
        except Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    dismissed_by = resolve_requested_actor(principal, request.dismissed_by)
    audit_store = getattr(http_request.app.state, "audit_store", None)

    try:
        return await dismiss(
            notification_id=notification_id,
            dismissed_by=dismissed_by,
            metadata=request.metadata,
            audit_store=cast(AuditStore, audit_store),
        )
    except KeyError as exc:
        logger.warning("Dismiss failed - notification not found: %s", notification_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Notification not found: {notification_id}",
                "notification_id": str(notification_id),
            },
        ) from exc
    except InvalidAckTransitionError as exc:
        logger.warning(
            "Dismiss failed - invalid transition: notification_id=%s %s -> %s",
            notification_id,
            exc.current_status.value,
            exc.requested_status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
                "notification_id": str(notification_id),
                "current_status": exc.current_status.value,
                "requested_status": exc.requested_status.value,
            },
        ) from exc
    except AuditPersistenceError as exc:
        logger.error(
            "Failed to persist ack audit: notification_id=%s error=%s",
            notification_id,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "ack_audit_persistence_failed",
                "message": "ack state was not committed because audit could not be persisted",
                "notification_id": str(notification_id),
            },
        ) from exc


@router.get(
    "/{notification_id}",
    response_model=NotificationStatusResponse,
    responses={
        200: {"description": "Notification status retrieved"},
    },
)
async def get_notification_status(
    notification_id: UUID,
    http_request: Request,
) -> NotificationStatusResponse:
    """HTTP adapter — delegates to agsignal.queries.get_notification_status."""
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    if runtime is not None:
        try:
            row = runtime.get(notification_id)
        except KeyError:
            return NotificationStatusResponse(notification_id=notification_id, found=False)
        n = row["notification"]
        return NotificationStatusResponse(notification_id=notification_id, found=True,
            notification_type=n["notification_type"], intent=n["intent"], title=n["title"],
            message=n["message"], require_ack=n["require_ack"], created_at=n["created_at"], ack_status=row["ack_status"])
    return await _query_notification_status(notification_id=notification_id)


@router.get(
    "/{notification_id}/ack-status",
    response_model=AckStatusResponse,
    responses={
        200: {"description": "Ack status retrieved"},
    },
)
async def get_ack_status(
    notification_id: UUID,
    http_request: Request,
) -> AckStatusResponse:
    """HTTP adapter — delegates to agsignal.queries.get_ack_status."""
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    if runtime is not None:
        try:
            return AckStatusResponse(notification_id=notification_id, ack_status=runtime.get(notification_id)["ack_status"])
        except KeyError:
            return AckStatusResponse(notification_id=notification_id, ack_status=None)
    return await _query_ack_status(notification_id=notification_id)


def create_notification_router() -> APIRouter:
    """Factory function to create the notification router.

    Returns:
        Configured APIRouter with notification endpoints
    """
    return router


# Re-export for backward compatibility. External callers that did
# ``from agsignal.api.routes_notification import AckRequest`` (etc.) continue
# to work; the canonical home is now ``agsignal.responses``.
__all__ = [
    "AckRequest",
    "AckResponse",
    "AckStatusResponse",
    "DismissRequest",
    "ErrorResponse",  # alias for NotificationErrorResponse
    "NotificationStatusResponse",
    "get_engine",
    "router",
]

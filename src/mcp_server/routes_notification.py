"""API routes for notification acknowledgment and status.

This module provides HTTP endpoints for:
- POST /v1/notifications/{id}/ack - Acknowledge a notification
- POST /v1/notifications/{id}/dismiss - Dismiss a notification
- GET /v1/notifications/{id} - Get notification status
- GET /v1/notifications/{id}/ack-status - Get acknowledgment status

Per PRD Task 10:
- Ack endpoint writes audit and triggers callback
- Status endpoint returns notification details and ack state
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from mcp_server.auth import WritePrincipal, require_write_principal, resolve_requested_actor
from notification.acknowledgment import (
    AcknowledgmentEngine,
    InvalidAckTransitionError,
    configure_ack_engine,
    get_ack_engine,
)
from notification.audit import AuditPersistenceError, AuditStore, create_ack_audit_record
from notification.models import AckStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


# Request/Response Models


class AckRequest(BaseModel):
    """Request body for acknowledging a notification."""

    acked_by: str | None = Field(default=None, description="User or system identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional acknowledgment metadata"
    )


class DismissRequest(BaseModel):
    """Request body for dismissing a notification."""

    dismissed_by: str | None = Field(default=None, description="User or system identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional dismissal metadata"
    )


class AckResponse(BaseModel):
    """Response for ack/dismiss operations."""

    notification_id: UUID = Field(description="ID of the notification")
    ack_status: AckStatus = Field(description="Current acknowledgment status")
    acked_by: str | None = Field(default=None, description="Who acknowledged/dismissed")
    acked_at: datetime = Field(description="Timestamp of the action")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AckStatusResponse(BaseModel):
    """Response for ack status queries."""

    notification_id: UUID = Field(description="ID of the notification")
    ack_status: AckStatus | None = Field(
        default=None, description="Current ack status (null if not tracked)"
    )


class NotificationStatusResponse(BaseModel):
    """Response for notification status queries."""

    notification_id: UUID = Field(description="ID of the notification")
    notification_type: str | None = Field(default=None, description="Type of notification")
    intent: str | None = Field(default=None, description="Notification intent")
    title: str | None = Field(default=None, description="Notification title")
    message: str | None = Field(default=None, description="Notification message")
    ack_status: AckStatus | None = Field(default=None, description="Current ack status")
    require_ack: bool | None = Field(default=None, description="Whether ack is required")
    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    found: bool = Field(description="Whether the notification was found")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    notification_id: UUID | None = Field(default=None, description="Related notification ID")


# Dependency for getting the ack engine


def get_engine() -> AcknowledgmentEngine:
    """Get the acknowledgment engine, initializing if needed."""
    try:
        return get_ack_engine()
    except RuntimeError:
        # Auto-configure with defaults for convenience
        return configure_ack_engine()


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
    """Acknowledge a notification.

    This endpoint allows users to acknowledge receipt of a notification.
    The operation is idempotent - acknowledging an already-acked notification
    returns success without error.

    Args:
        notification_id: UUID of the notification to acknowledge
        request: Optional ack request body with acked_by and metadata

    Returns:
        AckResponse with the acknowledgment details

    Raises:
        HTTPException 404: If notification is not found
        HTTPException 409: If the status transition is invalid
    """
    engine = get_engine()
    request = request or AckRequest()
    acked_by = resolve_requested_actor(principal, request.acked_by)

    try:
        event = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by=acked_by,
            metadata=request.metadata,
            before_commit=lambda old_status, ack_event: _persist_ack_audit(
                http_request=http_request,
                notification_id=notification_id,
                old_status=old_status,
                new_status=ack_event.ack_status,
                acked_by=ack_event.acked_by,
                acked_at=ack_event.acked_at,
                metadata=ack_event.metadata,
            ),
        )

        logger.info(
            "Notification acknowledged via API: notification_id=%s acked_by=%s",
            notification_id,
            acked_by,
        )
        return AckResponse(
            notification_id=event.notification_id,
            ack_status=event.ack_status,
            acked_by=event.acked_by,
            acked_at=event.acked_at,
            metadata=event.metadata,
        )

    except KeyError as e:
        logger.warning("Ack failed - notification not found: %s", notification_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Notification not found: {notification_id}",
                "notification_id": str(notification_id),
            },
        ) from e

    except InvalidAckTransitionError as e:
        logger.warning(
            "Ack failed - invalid transition: notification_id=%s %s -> %s",
            notification_id,
            e.current_status.value,
            e.requested_status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_transition",
                "message": str(e),
                "notification_id": str(notification_id),
                "current_status": e.current_status.value,
                "requested_status": e.requested_status.value,
            },
        ) from e


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
    """Dismiss a notification.

    Dismissal indicates the operator saw the notification but chose not to
    formally acknowledge it. This is a terminal state.

    Args:
        notification_id: UUID of the notification to dismiss
        request: Optional dismiss request body with dismissed_by and metadata

    Returns:
        AckResponse with the dismissal details

    Raises:
        HTTPException 404: If notification is not found
        HTTPException 409: If the status transition is invalid
    """
    engine = get_engine()
    request = request or DismissRequest()
    dismissed_by = resolve_requested_actor(principal, request.dismissed_by)

    try:
        event = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.DISMISSED,
            acked_by=dismissed_by,
            metadata=request.metadata,
            before_commit=lambda old_status, ack_event: _persist_ack_audit(
                http_request=http_request,
                notification_id=notification_id,
                old_status=old_status,
                new_status=ack_event.ack_status,
                acked_by=ack_event.acked_by,
                acked_at=ack_event.acked_at,
                metadata=ack_event.metadata,
            ),
        )

        logger.info(
            "Notification dismissed via API: notification_id=%s dismissed_by=%s",
            notification_id,
            dismissed_by,
        )
        return AckResponse(
            notification_id=event.notification_id,
            ack_status=event.ack_status,
            acked_by=event.acked_by,
            acked_at=event.acked_at,
            metadata=event.metadata,
        )

    except KeyError as e:
        logger.warning("Dismiss failed - notification not found: %s", notification_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Notification not found: {notification_id}",
                "notification_id": str(notification_id),
            },
        ) from e

    except InvalidAckTransitionError as e:
        logger.warning(
            "Dismiss failed - invalid transition: notification_id=%s %s -> %s",
            notification_id,
            e.current_status.value,
            e.requested_status.value,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_transition",
                "message": str(e),
                "notification_id": str(notification_id),
                "current_status": e.current_status.value,
                "requested_status": e.requested_status.value,
            },
        ) from e


@router.get(
    "/{notification_id}",
    response_model=NotificationStatusResponse,
    responses={
        200: {"description": "Notification status retrieved"},
    },
)
async def get_notification_status(
    notification_id: UUID,
) -> NotificationStatusResponse:
    """HTTP adapter — delegates to agsignal.queries.get_notification_status."""
    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import get_notification_status as _query

    return await _query(notification_id=notification_id)


@router.get(
    "/{notification_id}/ack-status",
    response_model=AckStatusResponse,
    responses={
        200: {"description": "Ack status retrieved"},
    },
)
async def get_ack_status(
    notification_id: UUID,
) -> AckStatusResponse:
    """HTTP adapter — delegates to agsignal.queries.get_ack_status."""
    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import get_ack_status as _query

    return await _query(notification_id=notification_id)


def _persist_ack_audit(
    *,
    http_request: Request,
    notification_id: UUID,
    old_status: AckStatus | None,
    new_status: AckStatus,
    acked_by: str | None,
    acked_at: datetime,
    metadata: dict[str, Any],
) -> None:
    if old_status == new_status:
        return
    audit_store = getattr(http_request.app.state, "audit_store", None)
    if not isinstance(audit_store, AuditStore):
        return
    try:
        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notification_id,
                old_status=old_status,
                new_status=new_status,
                acked_by=acked_by,
                acked_at=acked_at,
                metadata=metadata,
            )
        )
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


def create_notification_router() -> APIRouter:
    """Factory function to create the notification router.

    Returns:
        Configured APIRouter with notification endpoints
    """
    return router

"""Read-only UI HTTP route adapters for AGSignal Console.

This module provides the HTTP endpoints for the UI dashboard per
``docs/ui/ui-data-contracts.md``:

- GET /ui/deliveries — List delivery timelines with filtering
- GET /ui/deliveries/{id} — Get single delivery timeline
- GET /ui/policies/effective — Get effective policy resolution
- GET /ui/invariants — List system invariants
- GET /ui/invariants/summary — Aggregate invariant summary
- GET /ui/audit — List audit events with filtering

All endpoints are READ-ONLY. No mutating actions are permitted.

Architecture (post-Phase-2 Task 3, post-Phase-3 Task 1):
- Each route handler is a thin adapter: parameter parsing (Query/Depends)
  + log_endpoint_call observability + ``await agsignal.queries.X(...)``.
- The canonical implementation of each read operation lives in
  :mod:`agsignal.queries`. Routes do not contain business logic.
- Pydantic response models live in :mod:`agsignal.responses`; this
  module re-exports them at the bottom for backward compatibility.

Authentication/Authorization:
- All endpoints require read-only permissions (stub: no auth enforcement yet)
- Future: integrate with auth middleware for proper RBAC

Observability:
- All endpoints emit request metrics via ObservabilityMiddleware
- Structured logs include request IDs for correlation
- Error metrics are recorded for 4xx/5xx responses
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from agsignal.api.auth import require_read_principal
from agsignal.api.observability import (
    create_error_response_with_request_id,
    get_structured_logger,
    log_endpoint_call,
    record_endpoint_error,
)
from agsignal.errors import NotFoundError
from agsignal.queries import (
    get_delivery_timeline as _query_delivery_timeline,
)
from agsignal.queries import (
    get_effective_policy as _query_effective_policy,
)
from agsignal.queries import (
    get_invariants_summary as _query_invariants_summary,
)
from agsignal.queries import (
    list_audit_events as _query_list_audit_events,
)
from agsignal.queries import (
    list_deliveries as _query_list_deliveries,
)
from agsignal.queries import (
    list_invariants as _query_list_invariants,
)
from agsignal.responses import (
    AuditEvent,
    AuditEventListResponse,
    AuditEventType,
    AutonomyContextResponse,
    DeliveryAttempt,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    EnforcementType,
    ErrorDetail,
    EvidenceLink,
    InvariantEnforcement,
    InvariantEntry,
    InvariantListResponse,
    InvariantSeverity,
    InvariantStatus,
    InvariantSummaryResponse,
    PaginationInfo,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)
from agsignal.responses import (
    UIErrorResponse as ErrorResponse,
)
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/ui", tags=["ui"], dependencies=[Depends(require_read_principal)])


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/deliveries",
    response_model=DeliveryTimelineListResponse,
    responses={
        200: {"description": "List of delivery timelines"},
        400: {"description": "Invalid parameters"},
    },
    summary="List delivery timelines",
    description="Query delivery timelines with optional filtering. Read-only endpoint.",
)
async def list_deliveries(
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    start_time: datetime | None = Query(default=None, description="Filter by created_at >="),
    end_time: datetime | None = Query(default=None, description="Filter by created_at <"),
    status: DeliveryStatus | None = Query(default=None, description="Filter by delivery status"),
    intent: NotificationIntent | None = Query(default=None, description="Filter by intent"),
    delivery_mode: DeliveryMode | None = Query(default=None, description="Filter by delivery mode"),
    agent_id: UUID | None = Query(default=None, description="Filter by agent UUID"),
    autonomy_mode: AutonomyMode | None = Query(default=None, description="Filter by autonomy mode"),
    notification_type: str | None = Query(default=None, description="Filter by notification type"),
    channel: Channel | None = Query(default=None, description="Filter by channel attempted"),
) -> DeliveryTimelineListResponse:
    """HTTP adapter — delegates to agsignal.queries.list_deliveries."""
    log_endpoint_call(
        logger,
        "list_deliveries",
        cursor=cursor,
        limit=limit,
        status=status.value if status else None,
        intent=intent.value if intent else None,
        delivery_mode=delivery_mode.value if delivery_mode else None,
        autonomy_mode=autonomy_mode.value if autonomy_mode else None,
    )

    return await _query_list_deliveries(
        cursor=cursor,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        status=status,
        intent=intent,
        delivery_mode=delivery_mode,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        notification_type=notification_type,
        channel=channel,
    )


@router.get(
    "/deliveries/{notification_id}",
    response_model=DeliveryTimelineResponse,
    responses={
        200: {"description": "Delivery timeline details"},
        404: {"description": "Notification not found"},
    },
    summary="Get delivery timeline",
    description="Get full delivery timeline for a specific notification. Read-only endpoint.",
)
async def get_delivery_timeline(
    notification_id: UUID,
) -> DeliveryTimelineResponse:
    """HTTP adapter — delegates to agsignal.queries.get_delivery_timeline.

    Translates the typed :class:`agsignal.errors.NotFoundError` raised by
    the service layer to an HTTP 404 response with the standard error
    envelope. Observability metric emission for the 404 path lives here
    in the route adapter (not in the service layer).
    """
    log_endpoint_call(
        logger,
        "get_delivery_timeline",
        notification_id=str(notification_id),
    )

    try:
        return await _query_delivery_timeline(notification_id=notification_id)
    except NotFoundError as exc:
        message = f"Delivery timeline not found for notification {notification_id}"
        error_response = create_error_response_with_request_id(
            code="not_found",
            message=message,
        )
        record_endpoint_error(
            endpoint="/ui/deliveries/{id}",
            error_code="not_found",
            error_message=message,
            status_code=404,
        )
        # Preserve traceback chain (matches routes_notification.py convention
        # for typed-domain-error → HTTP-status translation).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response,
        ) from exc


@router.get(
    "/policies/effective",
    response_model=EffectivePolicyResponse,
    responses={
        200: {"description": "Effective policy resolution"},
        400: {"description": "Invalid parameters"},
    },
    summary="Get effective policy",
    description="Get effective policy resolution for a notification type. Read-only endpoint.",
)
async def get_effective_policy(
    http_request: Request,
    notification_type: str = Query(..., description="The notification type to resolve"),
    intent: NotificationIntent = Query(..., description="The notification intent"),
    autonomy_mode: AutonomyMode = Query(..., description="The autonomy mode"),
    irreversible: bool = Query(default=False, description="Whether the action is irreversible"),
) -> EffectivePolicyResponse:
    """HTTP adapter — delegates to agsignal.queries.get_effective_policy."""
    log_endpoint_call(
        logger,
        "get_effective_policy",
        notification_type=notification_type,
        intent=intent.value,
        autonomy_mode=autonomy_mode.value,
        irreversible=irreversible,
    )

    try:
        return await _query_effective_policy(
            notification_type=notification_type,
            intent=intent,
            autonomy_mode=autonomy_mode,
            irreversible=irreversible,
            policy_registry=(http_request.app.state.runtime.policy_runtime.registry()
                             if getattr(http_request.app.state, "runtime", None) is not None else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/invariants",
    response_model=InvariantListResponse,
    responses={
        200: {"description": "List of invariants"},
        400: {"description": "Invalid parameters"},
    },
    summary="List system invariants",
    description="Get the system invariant registry. Read-only endpoint.",
)
async def list_invariants(
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    severity: InvariantSeverity | None = Query(default=None, description="Filter by severity"),
    enforcement_type: EnforcementType | None = Query(
        default=None, description="Filter by enforcement type"
    ),
    invariant_status: InvariantStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    search: str | None = Query(default=None, description="Full-text search on statement"),
) -> InvariantListResponse:
    """HTTP adapter — delegates to agsignal.queries.list_invariants."""
    log_endpoint_call(
        logger,
        "list_invariants",
        cursor=cursor,
        limit=limit,
        severity=severity.value if severity else None,
        enforcement_type=enforcement_type.value if enforcement_type else None,
        status=invariant_status.value if invariant_status else None,
        search=search,
    )

    return await _query_list_invariants(
        cursor=cursor,
        limit=limit,
        severity=severity,
        enforcement_type=enforcement_type,
        invariant_status=invariant_status,
        search=search,
    )


@router.get(
    "/invariants/summary",
    response_model=InvariantSummaryResponse,
    responses={
        200: {"description": "Invariant summary statistics"},
    },
    summary="Get invariant summary",
    description="Get summary statistics for system invariants. Read-only endpoint.",
)
async def get_invariants_summary() -> InvariantSummaryResponse:
    """HTTP adapter — delegates to agsignal.queries.get_invariants_summary."""
    log_endpoint_call(logger, "get_invariants_summary")

    return await _query_invariants_summary()


@router.get(
    "/audit",
    response_model=AuditEventListResponse,
    responses={
        200: {"description": "List of audit events"},
        400: {"description": "Invalid parameters"},
    },
    summary="List audit events",
    description="Query audit event stream with filtering. Read-only endpoint.",
)
async def list_audit_events(
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    start_time: datetime | None = Query(default=None, description="Filter by event_time >="),
    end_time: datetime | None = Query(default=None, description="Filter by event_time <"),
    event_type: AuditEventType | None = Query(default=None, description="Filter by event type"),
    notification_id: UUID | None = Query(default=None, description="Filter by notification UUID"),
    agent_id: UUID | None = Query(default=None, description="Filter by agent UUID"),
    autonomy_mode: AutonomyMode | None = Query(default=None, description="Filter by autonomy mode"),
    correlation_id: str | None = Query(default=None, description="Filter by correlation ID"),
) -> AuditEventListResponse:
    """HTTP adapter — delegates to agsignal.queries.list_audit_events."""
    log_endpoint_call(
        logger,
        "list_audit_events",
        cursor=cursor,
        limit=limit,
        event_type=event_type.value if event_type else None,
        notification_id=str(notification_id) if notification_id else None,
        agent_id=str(agent_id) if agent_id else None,
        autonomy_mode=autonomy_mode.value if autonomy_mode else None,
        correlation_id=correlation_id,
    )

    return await _query_list_audit_events(
        cursor=cursor,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
        notification_id=notification_id,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        correlation_id=correlation_id,
    )


def create_ui_router() -> APIRouter:
    """Factory function to create the UI router.

    Returns:
        Configured APIRouter with UI endpoints
    """
    return router


# Re-export for backward compatibility. tests/ui_contract/test_ui_contracts.py
# and scripts/generate_ui_contracts.py historically imported these classes
# directly from this module; the alias preserves their import path while the
# canonical home is now :mod:`agsignal.responses`.
__all__ = [
    "AuditEvent",
    "AuditEventListResponse",
    "AuditEventType",
    "AutonomyContextResponse",
    "DeliveryAttempt",
    "DeliveryTimelineListResponse",
    "DeliveryTimelineResponse",
    "DeliveryTimelineSummary",
    "EffectivePolicyResponse",
    "EffectivePolicyValues",
    "EnforcementType",
    "ErrorDetail",
    "ErrorResponse",  # alias for UIErrorResponse
    "EvidenceLink",
    "InvariantEnforcement",
    "InvariantEntry",
    "InvariantListResponse",
    "InvariantSeverity",
    "InvariantStatus",
    "InvariantSummaryResponse",
    "PaginationInfo",
    "ResolutionContext",
    "ResolutionSource",
    "ResolutionStep",
    "router",
]

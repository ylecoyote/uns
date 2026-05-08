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

Architecture (post-Phase-2 Task 3):
- Each route handler is a thin adapter: parameter parsing (Query/Depends)
  + log_endpoint_call observability + ``await agsignal.queries.X(...)``.
- The canonical implementation of each read operation lives in
  :mod:`agsignal.queries`. Routes do not contain business logic.
- Pydantic response models are co-located here for now (Phase 5 of the
  v0.2 cleanup will relocate them, eliminating the legacy import in
  :mod:`agsignal.queries`).

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
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from mcp_server.observability import (
    get_structured_logger,
    log_endpoint_call,
)
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/ui", tags=["ui"])


# =============================================================================
# Common Types (per ui-data-contracts.md)
# =============================================================================


class PaginationInfo(BaseModel):
    """Pagination metadata for list responses."""

    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for next page, null if no more pages"
    )
    has_more: bool = Field(default=False, description="Whether more pages exist")
    total_count: int | None = Field(
        default=None, description="Total count (included when efficient to compute)"
    )


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable description")
    details: dict[str, Any] | None = Field(default=None, description="Additional context")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: ErrorDetail
    request_id: str = Field(description="Request ID for correlation/support")


# =============================================================================
# Delivery Timeline Types
# =============================================================================


class DeliveryAttempt(BaseModel):
    """Single channel delivery attempt."""

    attempt_id: UUID
    channel: Channel
    status: str  # SUCCESS, FAILED, RATE_LIMITED, SKIPPED
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    error_message: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None


class AutonomyContextResponse(BaseModel):
    """Autonomy context in responses."""

    autonomy_mode: AutonomyMode
    agent_id: UUID
    plan_id: UUID | None = None
    decision_snapshot_id: UUID | None = None
    execution_snapshot_id: UUID | None = None
    skip_snapshot_id: UUID | None = None


class DeliveryTimelineResponse(BaseModel):
    """Full delivery timeline for a notification."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None = None
    attempts: list[DeliveryAttempt] = Field(default_factory=list)
    channels_attempted: list[Channel] = Field(default_factory=list)
    channels_succeeded: list[Channel] = Field(default_factory=list)
    channels_failed: list[Channel] = Field(default_factory=list)
    autonomy_context: AutonomyContextResponse


class DeliveryTimelineSummary(BaseModel):
    """Summary view of delivery timeline for list responses."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None = None
    channels_attempted: list[Channel] = Field(default_factory=list)
    channels_succeeded: list[Channel] = Field(default_factory=list)
    autonomy_mode: AutonomyMode
    agent_id: UUID


class DeliveryTimelineListResponse(BaseModel):
    """Paginated list of delivery timelines."""

    items: list[DeliveryTimelineSummary] = Field(default_factory=list)
    pagination: PaginationInfo


# =============================================================================
# Policy Resolution Types
# =============================================================================


class ResolutionSource(str, Enum):
    """Source of a policy resolution value."""

    EXPLICIT_OVERRIDE = "explicit_override"
    MODE_OVERRIDE = "mode_override"
    POLICY_BASE = "policy_base"
    SDK_DEFAULT = "sdk_default"


class ResolutionStep(BaseModel):
    """Single step in policy resolution chain."""

    source: ResolutionSource
    value: Any = Field(description="The value at this resolution step")
    applied: bool = Field(description="Whether this value was used")
    reason: str | None = Field(default=None, description="Explanation if not applied")


class EffectivePolicyValues(BaseModel):
    """Effective policy values that were actually used."""

    delivery_mode: DeliveryMode
    channels: list[Channel]
    require_ack: bool
    ack_timeout_minutes: int | None = None
    dedup_window_seconds: int


class ResolutionContext(BaseModel):
    """Context used for policy resolution."""

    intent: NotificationIntent
    autonomy_mode: AutonomyMode
    irreversible: bool
    policy_found: bool
    policy_notification_type: str | None = None


class EffectivePolicyResponse(BaseModel):
    """Response for effective policy resolution."""

    notification_type: str
    effective: EffectivePolicyValues
    resolution: dict[str, list[ResolutionStep]] = Field(
        description="Resolution trace for each field"
    )
    resolution_context: ResolutionContext


# =============================================================================
# Invariant Types
# =============================================================================


class EnforcementType(str, Enum):
    """Invariant enforcement mechanism."""

    GUARD = "guard"
    ISOLATION = "isolation"
    TEST = "test"
    EXCEPTION = "exception"


class InvariantSeverity(str, Enum):
    """Invariant severity level."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class InvariantStatus(str, Enum):
    """Invariant status."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class EvidenceLink(BaseModel):
    """Link to evidence for an invariant."""

    path: str = Field(description="Repo-relative path")
    note: str = Field(description="Description of what this evidences")
    line_ref: str | None = Field(default=None, description="Optional line reference")


class InvariantEnforcement(BaseModel):
    """Enforcement details for an invariant."""

    type: EnforcementType
    description: str


class InvariantEntry(BaseModel):
    """Single invariant entry."""

    id: str = Field(description="e.g., INV-ACK-001")
    statement: str = Field(description="The invariant claim")
    severity: InvariantSeverity
    status: InvariantStatus
    enforcement: InvariantEnforcement
    evidence: list[EvidenceLink] = Field(default_factory=list)
    owner: str = Field(description="Team/role responsible")
    last_reviewed: str = Field(description="ISO 8601 date")
    mitigation: list[str] | None = Field(default=None, description="For exceptions only")


class InvariantListResponse(BaseModel):
    """Paginated list of invariants."""

    items: list[InvariantEntry] = Field(default_factory=list)
    pagination: PaginationInfo


class InvariantSummaryResponse(BaseModel):
    """Summary statistics for invariants."""

    total_count: int
    by_severity: dict[str, int]
    by_enforcement_type: dict[str, int]
    by_status: dict[str, int]
    exceptions_requiring_review: int
    last_updated: str


# =============================================================================
# Audit Event Types
# =============================================================================


class AuditEventType(str, Enum):
    """Types of audit events."""

    NOTIFICATION_CREATED = "notification.created"
    DELIVERY_STARTED = "delivery.started"
    DELIVERY_CHANNEL_ATTEMPTED = "delivery.channel_attempted"
    DELIVERY_SUCCEEDED = "delivery.succeeded"
    DELIVERY_FAILED = "delivery.failed"
    DELIVERY_DEDUPLICATED = "delivery.deduplicated"
    DELIVERY_RATE_LIMITED = "delivery.rate_limited"
    ACK_PENDING = "ack.pending"
    ACK_RECEIVED = "ack.received"
    ACK_DISMISSED = "ack.dismissed"
    ACK_TIMED_OUT = "ack.timed_out"
    ESCALATION_TRIGGERED = "escalation.triggered"


class AuditEvent(BaseModel):
    """Single audit event."""

    audit_id: UUID
    event_type: AuditEventType
    event_time: datetime
    notification_id: UUID
    notification_type: str
    autonomy_context: AutonomyContextResponse
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class AuditEventListResponse(BaseModel):
    """Paginated list of audit events."""

    items: list[AuditEvent] = Field(default_factory=list)
    pagination: PaginationInfo


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

    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import list_deliveries as _query

    return await _query(
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
    """HTTP adapter — delegates to agsignal.queries.get_delivery_timeline."""
    log_endpoint_call(
        logger,
        "get_delivery_timeline",
        notification_id=str(notification_id),
    )

    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import get_delivery_timeline as _query

    return await _query(notification_id=notification_id)


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

    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import get_effective_policy as _query

    return await _query(
        notification_type=notification_type,
        intent=intent,
        autonomy_mode=autonomy_mode,
        irreversible=irreversible,
    )


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

    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import list_invariants as _query

    return await _query(
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

    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import get_invariants_summary as _query

    return await _query()


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

    # Local import avoids circular dependency: agsignal.queries imports
    # response models from this module.
    from agsignal.queries import list_audit_events as _query

    return await _query(
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

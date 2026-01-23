"""Read-only UI API routes for the Unified Notification Service.

This module provides HTTP endpoints for the UI dashboard per ui-data-contracts.md:
- GET /ui/deliveries - List delivery timelines with filtering
- GET /ui/deliveries/{id} - Get single delivery timeline
- GET /ui/policies/effective - Get effective policy resolution
- GET /ui/invariants - List system invariants
- GET /ui/audit - List audit events with filtering

All endpoints are READ-ONLY. No mutating actions are permitted.

Authentication/Authorization:
- All endpoints require read-only permissions (stub: no auth enforcement yet)
- Future: integrate with auth middleware for proper RBAC

Read Model Adapters:
- Endpoints are wired to read model adapters (see read_models.py)
- Default: InMemoryReadModelAdapter for local demo (data lost on restart)
- Production: Configure SQLAlchemyReadModelAdapter for persistence

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

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from mcp_server.observability import (
    create_error_response_with_request_id,
    get_structured_logger,
    log_endpoint_call,
    record_endpoint_error,
)
from mcp_server.read_models import (
    AuditEventFilter,
    DeliveryFilter,
    get_read_model_adapter,
)
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from notification.policies import (
    DEFAULT_DEDUP_WINDOW_SECONDS,
    get_default_ack_timeout,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
    get_policy_registry,
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
    """List delivery timelines with filtering.

    Queries the read model adapter for delivery summaries matching the
    provided filter criteria. Returns paginated results.

    Note: Default adapter is InMemoryReadModelAdapter (data not persisted).
    Configure SQLAlchemyReadModelAdapter for production persistence.
    """
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

    # Build filter criteria
    filter_criteria = DeliveryFilter(
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

    # Query read model adapter
    adapter = get_read_model_adapter()
    result = adapter.get_deliveries(filter_criteria, cursor, limit)

    # Convert to response model
    items = [
        DeliveryTimelineSummary(
            notification_id=item.notification_id,
            notification_type=item.notification_type,
            intent=item.intent,
            delivery_mode=item.delivery_mode,
            status=item.status,
            created_at=item.created_at,
            delivered_at=item.delivered_at,
            channels_attempted=item.channels_attempted,
            channels_succeeded=item.channels_succeeded,
            autonomy_mode=item.autonomy_mode,
            agent_id=item.agent_id,
        )
        for item in result.items
    ]

    return DeliveryTimelineListResponse(
        items=items,
        pagination=PaginationInfo(
            next_cursor=result.next_cursor,
            has_more=result.has_more,
            total_count=result.total_count,
        ),
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
    """Get delivery timeline for a specific notification.

    Queries the read model adapter for the full delivery timeline
    of a specific notification, including all channel attempts.

    Note: Default adapter is InMemoryReadModelAdapter (data not persisted).
    Configure SQLAlchemyReadModelAdapter for production persistence.
    """
    log_endpoint_call(
        logger,
        "get_delivery_timeline",
        notification_id=str(notification_id),
    )

    # Query read model adapter
    adapter = get_read_model_adapter()
    timeline = adapter.get_delivery_timeline(notification_id)

    if timeline is None:
        error_response = create_error_response_with_request_id(
            code="not_found",
            message=f"Notification not found: {notification_id}",
        )
        record_endpoint_error(
            endpoint="/ui/deliveries/{id}",
            error_code="not_found",
            error_message=f"Notification not found: {notification_id}",
            status_code=404,
        )
        logger.warning(
            "Delivery timeline not found",
            extra={"notification_id": str(notification_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response,
        )

    # Convert attempts to response model
    attempts = [
        DeliveryAttempt(
            attempt_id=attempt.attempt_id,
            channel=attempt.channel,
            status=attempt.status,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            duration_ms=attempt.duration_ms,
            error_message=attempt.error_message,
            error_code=attempt.error_code,
            metadata=attempt.metadata,
        )
        for attempt in timeline.attempts
    ]

    return DeliveryTimelineResponse(
        notification_id=timeline.notification_id,
        notification_type=timeline.notification_type,
        intent=timeline.intent,
        delivery_mode=timeline.delivery_mode,
        status=timeline.status,
        created_at=timeline.created_at,
        delivered_at=timeline.delivered_at,
        attempts=attempts,
        channels_attempted=timeline.channels_attempted,
        channels_succeeded=timeline.channels_succeeded,
        channels_failed=timeline.channels_failed,
        autonomy_context=AutonomyContextResponse(
            autonomy_mode=timeline.autonomy_mode,
            agent_id=timeline.agent_id,
            plan_id=timeline.plan_id,
            decision_snapshot_id=timeline.decision_snapshot_id,
            execution_snapshot_id=timeline.execution_snapshot_id,
            skip_snapshot_id=timeline.skip_snapshot_id,
        ),
    )


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
    """Get effective policy resolution for a notification type.

    Shows how policy values are resolved through the resolution chain:
    1. explicit_override - Values passed directly (not applicable here)
    2. mode_override - Policy mode-specific override
    3. policy_base - Policy base value
    4. sdk_default - SDK default derived from intent + autonomy_mode
    """
    log_endpoint_call(
        logger,
        "get_effective_policy",
        notification_type=notification_type,
        intent=intent.value,
        autonomy_mode=autonomy_mode.value,
        irreversible=irreversible,
    )

    registry = get_policy_registry()
    policy = registry.get_sync(notification_type)

    # Determine effective values
    effective_channels = get_default_channels(intent, autonomy_mode, irreversible)
    effective_delivery_mode = get_default_delivery_mode(intent)
    effective_require_ack = get_default_require_ack(intent, autonomy_mode)
    effective_ack_timeout = get_default_ack_timeout(intent)
    effective_dedup_window = DEFAULT_DEDUP_WINDOW_SECONDS

    # Build resolution traces
    resolution: dict[str, list[ResolutionStep]] = {
        "delivery_mode": [],
        "channels": [],
        "require_ack": [],
        "ack_timeout_minutes": [],
        "dedup_window_seconds": [],
    }

    policy_found = policy is not None

    if policy:
        # Check policy base values
        if policy.delivery_mode is not None:
            effective_delivery_mode = policy.delivery_mode
            resolution["delivery_mode"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=policy.delivery_mode.value,
                    applied=True,
                )
            )
        else:
            resolution["delivery_mode"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="Not configured in policy",
                )
            )

        policy_channels = policy.get_channels_for_mode(autonomy_mode, intent)
        if policy_channels:
            effective_channels = policy_channels
            resolution["channels"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=[c.value for c in policy_channels],
                    applied=True,
                )
            )
        else:
            resolution["channels"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="Not configured in policy",
                )
            )

        policy_require_ack = policy.get_require_ack_for_mode(autonomy_mode, intent)
        if policy_require_ack is not None:
            effective_require_ack = policy_require_ack
            resolution["require_ack"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=policy_require_ack,
                    applied=True,
                )
            )
        else:
            resolution["require_ack"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="Not configured in policy",
                )
            )

        if policy.ack_timeout_minutes is not None:
            effective_ack_timeout = policy.ack_timeout_minutes
            resolution["ack_timeout_minutes"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=policy.ack_timeout_minutes,
                    applied=True,
                )
            )
        else:
            resolution["ack_timeout_minutes"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="Not configured in policy",
                )
            )

        if policy.dedup_window_seconds is not None:
            effective_dedup_window = policy.dedup_window_seconds
            resolution["dedup_window_seconds"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=policy.dedup_window_seconds,
                    applied=True,
                )
            )
        else:
            resolution["dedup_window_seconds"].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="Not configured in policy",
                )
            )
    else:
        # No policy found - all use SDK defaults
        for field in resolution:
            resolution[field].append(
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="No policy registered for notification_type",
                )
            )

    # Add SDK default steps
    resolution["delivery_mode"].append(
        ResolutionStep(
            source=ResolutionSource.SDK_DEFAULT,
            value=get_default_delivery_mode(intent).value,
            applied=not policy_found or policy.delivery_mode is None,
        )
    )
    resolution["channels"].append(
        ResolutionStep(
            source=ResolutionSource.SDK_DEFAULT,
            value=[c.value for c in get_default_channels(intent, autonomy_mode, irreversible)],
            applied=not policy_found or not policy.get_channels_for_mode(autonomy_mode, intent),
        )
    )
    resolution["require_ack"].append(
        ResolutionStep(
            source=ResolutionSource.SDK_DEFAULT,
            value=get_default_require_ack(intent, autonomy_mode),
            applied=not policy_found
            or policy.get_require_ack_for_mode(autonomy_mode, intent) is None,
        )
    )
    resolution["ack_timeout_minutes"].append(
        ResolutionStep(
            source=ResolutionSource.SDK_DEFAULT,
            value=get_default_ack_timeout(intent),
            applied=not policy_found or policy.ack_timeout_minutes is None,
        )
    )
    resolution["dedup_window_seconds"].append(
        ResolutionStep(
            source=ResolutionSource.SDK_DEFAULT,
            value=DEFAULT_DEDUP_WINDOW_SECONDS,
            applied=not policy_found or policy.dedup_window_seconds is None,
        )
    )

    return EffectivePolicyResponse(
        notification_type=notification_type,
        effective=EffectivePolicyValues(
            delivery_mode=effective_delivery_mode,
            channels=effective_channels,
            require_ack=effective_require_ack,
            ack_timeout_minutes=effective_ack_timeout,
            dedup_window_seconds=effective_dedup_window,
        ),
        resolution=resolution,
        resolution_context=ResolutionContext(
            intent=intent,
            autonomy_mode=autonomy_mode,
            irreversible=irreversible,
            policy_found=policy_found,
            policy_notification_type=notification_type if policy_found else None,
        ),
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
    """List system invariants from the registry.

    Returns invariants from docs/verification/invariants.yml.
    Filters can be applied to narrow results.
    """
    # Handle case when called internally (params may not be resolved Query objects)
    severity_val = severity.value if severity and hasattr(severity, "value") else None
    enforcement_val = (
        enforcement_type.value if enforcement_type and hasattr(enforcement_type, "value") else None
    )
    status_val = (
        invariant_status.value if invariant_status and hasattr(invariant_status, "value") else None
    )

    log_endpoint_call(
        logger,
        "list_invariants",
        cursor=cursor,
        limit=limit,
        severity=severity_val,
        enforcement_type=enforcement_val,
        status=status_val,
        search=search,
    )

    # Load invariants from YAML file
    # This is a simplified implementation - in production you might
    # cache this or use a proper data store
    try:
        from pathlib import Path

        import yaml

        invariants_path = (
            Path(__file__).parent.parent.parent / "docs" / "verification" / "invariants.yml"
        )
        if invariants_path.exists():
            with open(invariants_path) as f:
                data = yaml.safe_load(f)

            items: list[InvariantEntry] = []
            for inv in data.get("invariants", []):
                # Parse enforcement
                enforcement_data = inv.get("enforcement", {})
                enforcement = InvariantEnforcement(
                    type=EnforcementType(enforcement_data.get("type", "test")),
                    description=enforcement_data.get("description", ""),
                )

                # Parse evidence
                evidence = [
                    EvidenceLink(
                        path=e.get("path", ""),
                        note=e.get("note", ""),
                        line_ref=e.get("line_ref"),
                    )
                    for e in inv.get("evidence", [])
                ]

                entry = InvariantEntry(
                    id=inv.get("id", ""),
                    statement=inv.get("statement", "").strip(),
                    severity=InvariantSeverity(inv.get("severity", "MEDIUM")),
                    status=InvariantStatus(inv.get("status", "active")),
                    enforcement=enforcement,
                    evidence=evidence,
                    owner=inv.get("owner", ""),
                    last_reviewed=inv.get("last_reviewed", ""),
                    mitigation=inv.get("mitigation"),
                )

                # Apply filters (check hasattr in case called internally without FastAPI resolution)
                if severity and hasattr(severity, "value") and entry.severity != severity:
                    continue
                if (
                    enforcement_type
                    and hasattr(enforcement_type, "value")
                    and entry.enforcement.type != enforcement_type
                ):
                    continue
                if (
                    invariant_status
                    and hasattr(invariant_status, "value")
                    and entry.status != invariant_status
                ):
                    continue
                if (
                    search
                    and isinstance(search, str)
                    and search.lower() not in entry.statement.lower()
                ):
                    continue

                items.append(entry)

            # Apply pagination (simple offset-based for stub)
            total = len(items)
            items = items[:limit]

            return InvariantListResponse(
                items=items,
                pagination=PaginationInfo(
                    next_cursor=None if len(items) < limit else "stub-cursor",
                    has_more=total > limit,
                    total_count=total,
                ),
            )
        else:
            logger.warning(
                "Invariants file not found",
                extra={"path": str(invariants_path)},
            )
    except Exception as e:
        logger.error(
            "Error loading invariants",
            extra={"error": str(e)},
        )
        record_endpoint_error(
            endpoint="/ui/invariants",
            error_code="invariants_load_error",
            error_message=str(e),
            status_code=200,  # Still returns empty response, not a 500
        )

    # Fallback empty response
    return InvariantListResponse(
        items=[],
        pagination=PaginationInfo(
            next_cursor=None,
            has_more=False,
            total_count=0,
        ),
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
    """Get summary statistics for invariants."""
    log_endpoint_call(logger, "get_invariants_summary")

    # Reuse list_invariants logic
    result = await list_invariants(limit=100)

    by_severity: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_enforcement: dict[str, int] = {"guard": 0, "isolation": 0, "test": 0, "exception": 0}
    by_status: dict[str, int] = {"active": 0, "inactive": 0}
    exceptions_count = 0

    for item in result.items:
        by_severity[item.severity.value] = by_severity.get(item.severity.value, 0) + 1
        by_enforcement[item.enforcement.type.value] = (
            by_enforcement.get(item.enforcement.type.value, 0) + 1
        )
        by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
        if item.enforcement.type == EnforcementType.EXCEPTION:
            exceptions_count += 1

    return InvariantSummaryResponse(
        total_count=len(result.items),
        by_severity=by_severity,
        by_enforcement_type=by_enforcement,
        by_status=by_status,
        exceptions_requiring_review=exceptions_count,
        last_updated=datetime.now().isoformat(),
    )


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
    """List audit events with filtering.

    Queries the read model adapter for audit events matching the
    provided filter criteria. Returns paginated results.

    Note: Default adapter is InMemoryReadModelAdapter (data not persisted).
    Configure SQLAlchemyReadModelAdapter for production persistence.
    """
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

    # Build filter criteria
    filter_criteria = AuditEventFilter(
        start_time=start_time,
        end_time=end_time,
        event_type=event_type.value if event_type else None,
        notification_id=notification_id,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        correlation_id=correlation_id,
    )

    # Query read model adapter
    adapter = get_read_model_adapter()
    result = adapter.get_audit_events(filter_criteria, cursor, limit)

    # Convert to response model
    items = [
        AuditEvent(
            audit_id=item.audit_id,
            event_type=AuditEventType(item.event_type),
            event_time=item.event_time,
            notification_id=item.notification_id,
            notification_type=item.notification_type,
            autonomy_context=AutonomyContextResponse(
                autonomy_mode=item.autonomy_mode,
                agent_id=item.agent_id,
                plan_id=item.plan_id,
                decision_snapshot_id=item.decision_snapshot_id,
                execution_snapshot_id=item.execution_snapshot_id,
                skip_snapshot_id=item.skip_snapshot_id,
            ),
            payload=item.payload,
            correlation_id=item.correlation_id,
        )
        for item in result.items
    ]

    return AuditEventListResponse(
        items=items,
        pagination=PaginationInfo(
            next_cursor=result.next_cursor,
            has_more=result.has_more,
            total_count=result.total_count,
        ),
    )


def create_ui_router() -> APIRouter:
    """Factory function to create the UI router.

    Returns:
        Configured APIRouter with UI endpoints
    """
    return router

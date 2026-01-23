"""Type definitions for the UI API client.

This module mirrors the response types from routes_ui.py, providing
Pydantic models for all UI endpoint responses. These types ensure
type safety when interacting with the UI API.

The types are intentionally kept as close as possible to the server-side
definitions to ensure compatibility and reduce maintenance burden.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

# Re-export core enums for convenience
__all__ = [
    # Re-exported from notification.models
    "NotificationIntent",
    "DeliveryMode",
    "DeliveryStatus",
    "AutonomyMode",
    "Channel",
    # Common types
    "PaginationInfo",
    "ErrorDetail",
    "ErrorResponse",
    # Delivery types
    "DeliveryAttempt",
    "AutonomyContextResponse",
    "DeliveryTimelineResponse",
    "DeliveryTimelineSummary",
    "DeliveryTimelineListResponse",
    # Policy types
    "ResolutionSource",
    "ResolutionStep",
    "EffectivePolicyValues",
    "ResolutionContext",
    "EffectivePolicyResponse",
    # Invariant types
    "EnforcementType",
    "InvariantSeverity",
    "InvariantStatus",
    "EvidenceLink",
    "InvariantEnforcement",
    "InvariantEntry",
    "InvariantListResponse",
    "InvariantSummaryResponse",
    # Audit types
    "AuditEventType",
    "AuditEvent",
    "AuditEventListResponse",
]


# =============================================================================
# Common Types
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

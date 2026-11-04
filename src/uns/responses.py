"""Pydantic Request/Response DTOs for the UNS service layer.

This module is the single canonical home for the HTTP-shape DTOs that both
the route adapters (``uns.api.routes_*``, ``notification.routes``) and
the service layer (``uns.queries``, ``uns.signaling``) consume.

It exists primarily to break the circular import that Phase 2 created
between ``uns.queries``/``signaling`` and the route modules. Routes
import DTOs from here; service modules import DTOs from here; this module
has no dependency on either side.

The 40 types relocated here include 23 top-level Pydantic Request/Response
classes plus 17 supporting types (12 sub-DTOs + 5 string enums) that the
Response classes reference structurally. The two ``ErrorResponse`` classes
that previously coexisted at ``routes_notification`` and ``routes_ui`` are
renamed here to ``NotificationErrorResponse`` and ``UIErrorResponse`` -
they were structurally incompatible and could not consolidate.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from notification.dlq import DLQEntry
from notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
    Priority,
)

MAX_METADATA_BYTES = 65_536


def _validate_metadata_size(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(value, default=str).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError(f"metadata must not exceed {MAX_METADATA_BYTES} serialized bytes")
    return value

# ────────────────────────────────────────────────────────────────────────────
# Console / read enums (relocated from uns/api/routes_ui.py)
# Defined first so Response classes that reference them resolve top-down.
# ────────────────────────────────────────────────────────────────────────────


class ResolutionSource(str, Enum):
    """Source of a policy resolution value."""

    EXPLICIT_OVERRIDE = "explicit_override"
    MODE_OVERRIDE = "mode_override"
    POLICY_BASE = "policy_base"
    SDK_DEFAULT = "sdk_default"


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


# ────────────────────────────────────────────────────────────────────────────
# Notification write DTOs (relocated from notification/routes.py)
# ────────────────────────────────────────────────────────────────────────────


class AutonomyContextRequest(BaseModel):
    """Producer-supplied autonomy context."""

    model_config = ConfigDict(extra="forbid")

    autonomy_mode: AutonomyMode = Field(description="Current autonomy mode")
    agent_id: UUID = Field(description="Agent identifier for attribution")
    plan_id: UUID | None = Field(default=None, description="Optional plan identifier")
    decision_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional decision snapshot identifier",
    )
    execution_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional execution snapshot identifier",
    )
    skip_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional skip snapshot identifier",
    )

    def to_domain(self) -> AutonomyContext:
        """Convert request context into the domain model."""
        return AutonomyContext(
            autonomy_mode=self.autonomy_mode,
            agent_id=self.agent_id,
            plan_id=self.plan_id,
            decision_snapshot_id=self.decision_snapshot_id,
            execution_snapshot_id=self.execution_snapshot_id,
            skip_snapshot_id=self.skip_snapshot_id,
        )


class SendNotificationRequest(BaseModel):
    """HTTP request for sending an UNS notification."""

    model_config = ConfigDict(extra="forbid")

    notification_type: str = Field(description="Namespaced signal type", min_length=1)
    intent: NotificationIntent = Field(description="Signal intent")
    title: str = Field(description="Signal title", min_length=1, max_length=200)
    message: str = Field(description="Signal body", min_length=1, max_length=4000)
    source: str = Field(description="Producer identifier", min_length=1)
    autonomy_context: AutonomyContextRequest = Field(description="Required autonomy context")
    irreversible: bool = Field(default=False, description="Whether the action is irreversible")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional JSON metadata",
    )
    correlation_id: str | None = Field(default=None, description="Optional trace correlation ID")
    delivery_mode: DeliveryMode | None = Field(
        default=None,
        description="Optional delivery mode override",
    )
    require_ack: bool | None = Field(
        default=None,
        description="Optional acknowledgment override",
    )
    priority: Priority | None = Field(default=None, description="Optional priority override")
    dedup_key: str | None = Field(default=None, description="Optional deduplication key")
    idempotency_key: str | None = Field(
        default=None,
        description="Producer retry key scoped by source",
        min_length=1,
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_metadata_size(v)


class SendNotificationResponse(BaseModel):
    """HTTP response for an accepted UNS notification."""

    notification_id: UUID = Field(description="Notification identifier")
    status: DeliveryStatus = Field(description="Delivery outcome")
    channels_attempted: list[Channel] = Field(description="Router-derived channels attempted")
    channels_succeeded: list[Channel] = Field(description="Channels that succeeded")
    channels_failed: list[Channel] = Field(description="Channels that failed")
    require_ack: bool = Field(description="Whether the signal requires acknowledgment")
    ack_status: AckStatus | None = Field(
        default=None,
        description="Current acknowledgment status when tracked",
    )
    obligation_owner_id: UUID | None = Field(
        default=None,
        description="Canonical delivery and response owner ID (differs when deduplicated or handed off)",
    )
    effective_ack_status: AckStatus | None = Field(
        default=None,
        description="Effective acknowledgment status, including inherited deduplication owner status",
    )
    ack_inherited: bool = Field(
        default=False,
        description="Whether the effective acknowledgment status is inherited from a deduplication owner",
    )
    obligation_resolution_status: Literal["RESOLVED", "UNRESOLVED"] | None = Field(
        default=None,
        description="Whether the canonical owner was resolved; null for legacy or missing records",
    )
    obligation_resolution_error: Literal["CYCLE", "MISSING_TARGET", "GROUP_MISMATCH"] | None = Field(
        default=None,
        description="Reason canonical owner resolution failed; null when resolved",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Producer idempotency key when supplied",
    )
    idempotent_replay: bool = Field(
        default=False,
        description="Whether this response was replayed from a previous producer request",
    )
    created_at: datetime = Field(
        description="Timestamp the notification was created (assigned by the SDK at signal acceptance)",
    )
    message: str = Field(description="Acceptance summary")


class SimulateNotificationResponse(BaseModel):
    """HTTP response for a simulated UNS notification."""

    notification_id: UUID = Field(description="Preview notification identifier")
    simulated: bool = Field(description="Whether delivery was simulated")
    status: DeliveryStatus = Field(description="Simulated delivery outcome")
    channels_attempted: list[Channel] = Field(description="Router-derived channels")
    delivery_mode: DeliveryMode = Field(description="Resolved delivery mode")
    require_ack: bool = Field(description="Whether the signal would require acknowledgment")
    ack_status: AckStatus | None = Field(
        default=None,
        description="Always null because simulation has no ack side effect",
    )
    dedup_key: str = Field(description="Resolved deduplication key")
    dedup_window_seconds: int | None = Field(
        default=None,
        description="Resolved deduplication window when configured",
    )
    policy_source: str = Field(description="Whether routing came from policy or defaults")
    warnings: list[str] = Field(description="Human-readable simulation caveats")
    message: str = Field(description="Simulation summary")


class DeliveryAuditItem(BaseModel):
    """Single persisted delivery audit entry."""

    audit_id: UUID = Field(description="Audit record identifier")
    status: DeliveryStatus = Field(description="Delivery outcome for this attempt")
    channels_attempted: list[Channel] = Field(description="Channels attempted")
    channels_succeeded: list[Channel] = Field(description="Channels that succeeded")
    channels_failed: list[Channel] = Field(description="Channels that failed")
    error_message: str | None = Field(default=None, description="Delivery error if present")
    policy_config_id: UUID | None = Field(
        default=None, description="Policy config used for routing"
    )
    policy_config_hash: str | None = Field(
        default=None, description="Exact policy config hash used"
    )
    policy_evaluation_id: UUID | None = Field(
        default=None, description="Policy evaluation identifier"
    )
    delivered_at: datetime = Field(description="Delivery attempt timestamp")
    audit_created_at: datetime = Field(description="Audit persistence timestamp")


class DeliveryStatusResponse(BaseModel):
    """HTTP response for persisted delivery status."""

    notification_id: UUID = Field(description="Notification identifier")
    notification_type: str = Field(description="Namespaced signal type")
    delivery_status: DeliveryStatus = Field(description="Latest persisted delivery status")
    channels_attempted: list[Channel] = Field(description="Channels attempted in latest audit")
    channels_succeeded: list[Channel] = Field(description="Channels that succeeded")
    channels_failed: list[Channel] = Field(description="Channels that failed")
    error_message: str | None = Field(default=None, description="Latest delivery error")
    delivered_at: datetime = Field(description="Latest delivery attempt timestamp")
    audit_count: int = Field(description="Number of persisted delivery audits")
    audits: list[DeliveryAuditItem] = Field(description="Delivery audits newest first")


class DLQListResponse(BaseModel):
    """HTTP response for DLQ inspection."""

    depth: int = Field(description="Current DLQ depth")
    items: list[DLQEntry] = Field(description="DLQ entries, newest first")


class DLQRemoveResponse(BaseModel):
    """HTTP response for DLQ entry removal."""

    entry_id: UUID = Field(description="Removed DLQ entry identifier")
    removed: bool = Field(description="Whether the entry was removed")
    depth: int = Field(description="Current DLQ depth after removal")


class PolicyReloadRequest(BaseModel):
    """Request body for reloading YAML notification policies."""

    model_config = ConfigDict(extra="forbid")

    policy_dir: str | None = Field(
        default=None,
        description="Directory containing YAML policy files (defaults to configured UNS_POLICY_DIR or config/notification_policies)",
    )


class PolicyReloadResponse(BaseModel):
    """HTTP response for policy reload operations."""

    loaded_count: int = Field(description="Number of policy files loaded")
    persisted_count: int = Field(description="Number of policies newly persisted")
    policy_count: int = Field(description="Number of policies active after reload")
    notification_types: list[str] = Field(description="Registered notification types")


# ────────────────────────────────────────────────────────────────────────────
# Acknowledgment DTOs (relocated from uns/api/routes_notification.py)
# ────────────────────────────────────────────────────────────────────────────


class AckRequest(BaseModel):
    """Request body for acknowledging a notification."""

    acked_by: str | None = Field(default=None, description="User or system identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional acknowledgment metadata"
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_metadata_size(v)


class DismissRequest(BaseModel):
    """Request body for dismissing a notification."""

    dismissed_by: str | None = Field(default=None, description="User or system identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional dismissal metadata"
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_metadata_size(v)


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
    obligation_owner_id: UUID | None = Field(
        default=None,
        description="Canonical delivery and response owner ID",
    )
    effective_ack_status: AckStatus | None = Field(
        default=None,
        description="Effective acknowledgment status, including inherited owner status",
    )
    ack_inherited: bool = Field(
        default=False,
        description="Whether acknowledgment state is inherited from a deduplication owner",
    )
    obligation_resolution_status: Literal["RESOLVED", "UNRESOLVED"] | None = Field(
        default=None,
        description="Whether the canonical owner was resolved; null for legacy or missing records",
    )
    obligation_resolution_error: Literal["CYCLE", "MISSING_TARGET", "GROUP_MISMATCH"] | None = Field(
        default=None,
        description="Reason canonical owner resolution failed; null when resolved",
    )


class NotificationStatusResponse(BaseModel):
    """Response for notification status queries."""

    notification_id: UUID = Field(description="ID of the notification")
    notification_type: str | None = Field(default=None, description="Type of notification")
    intent: str | None = Field(default=None, description="Notification intent")
    title: str | None = Field(default=None, description="Notification title")
    message: str | None = Field(default=None, description="Notification message")
    ack_status: AckStatus | None = Field(default=None, description="Current ack status")
    obligation_owner_id: UUID | None = Field(
        default=None,
        description="Canonical delivery and response owner ID",
    )
    effective_ack_status: AckStatus | None = Field(
        default=None,
        description="Effective acknowledgment status, including inherited owner status",
    )
    ack_inherited: bool = Field(
        default=False,
        description="Whether acknowledgment state is inherited from a deduplication owner",
    )
    obligation_resolution_status: Literal["RESOLVED", "UNRESOLVED"] | None = Field(
        default=None,
        description="Whether the canonical owner was resolved; null for legacy or missing records",
    )
    obligation_resolution_error: Literal["CYCLE", "MISSING_TARGET", "GROUP_MISMATCH"] | None = Field(
        default=None,
        description="Reason canonical owner resolution failed; null when resolved",
    )
    require_ack: bool | None = Field(default=None, description="Whether ack is required")
    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    found: bool = Field(description="Whether the notification was found")


# Note (internal): renamed during Phase 3 from ``ErrorResponse`` (in
# ``uns.api.routes_notification``) to disambiguate from
# :class:`UIErrorResponse`, which has a structurally incompatible field set.
class NotificationErrorResponse(BaseModel):
    """Standard error response for notification-write endpoints."""

    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    notification_id: UUID | None = Field(default=None, description="Related notification ID")


# ────────────────────────────────────────────────────────────────────────────
# Console / read sub-DTOs (relocated from uns/api/routes_ui.py)
# ────────────────────────────────────────────────────────────────────────────


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


# Note (internal): renamed during Phase 3 from ``ErrorResponse`` (in
# ``uns.api.routes_ui``) to disambiguate from
# :class:`NotificationErrorResponse`, which has a structurally incompatible
# field set.
class UIErrorResponse(BaseModel):
    """Standard error response for console / read endpoints."""

    error: ErrorDetail
    request_id: str = Field(description="Request ID for correlation/support")


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

    runtime_state: dict[str, Any] | None = None

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


class ActivePolicySummary(BaseModel):
    """Summary of an active notification routing policy for the console catalog."""

    notification_type: str = Field(description="Policy notification_type identifier")
    version: str = Field(description="Policy version")
    status: str = Field(description="Lifecycle status (e.g., ACTIVE)")
    intent: NotificationIntent | None = Field(default=None, description="Default notification intent")
    channels: list[Channel] = Field(default_factory=list, description="Default LIVE channels")
    delivery_mode: DeliveryMode | None = Field(default=None, description="Default LIVE delivery mode")
    require_ack: bool | None = Field(default=None, description="Default LIVE ack requirement")
    ack_timeout_minutes: int | None = Field(default=None, description="Default LIVE ack timeout in minutes")
    ack_timeout_seconds: int | None = Field(default=None, description="Default LIVE ack timeout in seconds")
    dedup_window_seconds: int = Field(description="Deduplication window in seconds")


class ActivePolicyListResponse(BaseModel):
    """Catalog of active notification routing policies."""

    items: list[ActivePolicySummary] = Field(default_factory=list)
    total_count: int = Field(description="Total number of active policies")


class PolicyRevisionSummary(BaseModel):
    """Summary of a persisted notification routing policy revision for governance and lineage."""

    policy_id: UUID | None = Field(default=None, description="Persisted policy revision identifier")
    notification_type: str = Field(description="Policy notification_type identifier")
    version: str = Field(description="Policy version")
    status: str = Field(description="Lifecycle status (ACTIVE, DRAFT, PREVIEW, RETIRED)")
    config_hash: str | None = Field(default=None, description="Semantic policy content hash")
    previous_version_id: UUID | None = Field(
        default=None, description="Previous policy version ID in lifecycle lineage"
    )
    intent: NotificationIntent | None = Field(default=None, description="Default notification intent")
    channels: list[Channel] = Field(default_factory=list, description="Default LIVE channels")
    delivery_mode: DeliveryMode | None = Field(default=None, description="Default LIVE delivery mode")
    require_ack: bool | None = Field(default=None, description="Default LIVE ack requirement")
    ack_timeout_minutes: int | None = Field(default=None, description="Default LIVE ack timeout in minutes")
    ack_timeout_seconds: int | None = Field(default=None, description="Default LIVE ack timeout in seconds")
    dedup_window_seconds: int = Field(description="Deduplication window in seconds")
    created_at: datetime | None = Field(default=None, description="When the policy revision was created")
    updated_at: datetime | None = Field(default=None, description="When the policy revision was last updated")
    activated_at: datetime | None = Field(default=None, description="When the policy revision became ACTIVE")
    retired_at: datetime | None = Field(default=None, description="When the policy revision was retired")


class PolicyRevisionListResponse(BaseModel):
    """Catalog of notification routing policy revisions across lifecycle statuses."""

    items: list[PolicyRevisionSummary] = Field(default_factory=list)
    total_count: int = Field(description="Total number of policy revisions")


class PolicyProposalCreateRequest(BaseModel):
    """Request body for proposing a governed policy delta."""

    model_config = ConfigDict(extra="forbid")

    policy_type: str = Field(min_length=1, max_length=255, description="Target notification_type")
    field_path: str = Field(min_length=1, max_length=512, description="Dotted policy field path")
    proposed_value: Any = Field(description="Proposed replacement value")
    reasoning: str = Field(min_length=1, max_length=2000, description="Human-readable rationale")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Proposal confidence score")
    evidence_count: int = Field(default=1, ge=1, description="Number of supporting observations")
    promote_to_shadow: bool = Field(
        default=False,
        description="Immediately promote to SHADOW and materialize PREVIEW revision",
    )


class PolicyProposalActionRequest(BaseModel):
    """Optional reason payload for proposal state transitions."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000, description="Transition rationale")


class ShadowEvaluationSummaryItem(BaseModel):
    """Aggregate shadow evaluation summary for a policy delta."""

    aggregate_id: UUID
    delta_id: UUID
    baseline_hash: str | None = None
    candidate_hash: str | None = None
    evaluated_by: str | None = None
    total_decisions: int
    improved_decisions: int
    degraded_decisions: int
    neutral_decisions: int
    win_rate: float
    min_sample_met: bool
    accuracy_threshold_met: bool
    status: str
    can_promote_to_approval: bool
    computed_at: datetime


class ShadowEvaluationSampleItem(BaseModel):
    """Individual shadow evaluation decision sample."""

    result_id: UUID
    delta_id: UUID
    decision_id: str
    original_outcome: dict[str, Any] = Field(default_factory=dict)
    shadow_outcome: dict[str, Any] = Field(default_factory=dict)
    changed: bool
    improvement_score: float | None = None
    evaluated_at: datetime


class PolicyGuardResultItem(BaseModel):
    """Guard check evidence for a policy delta transition."""

    candidate_hash: str | None = None
    stage: str
    allowed: bool
    reason: str | None = None
    reason_detail: str | None = None
    checks: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime


class PolicyTransitionItem(BaseModel):
    """Audit entry for a policy delta state transition."""

    from_state: str | None = None
    to_state: str
    actor: str
    reason: str | None = None
    guard_stage: str | None = None
    transitioned_at: datetime


class PolicyProposalSummary(BaseModel):
    """Full representation of a PolicyDelta proposal, shadow evidence, and guard status."""

    delta_id: UUID
    policy_type: str
    field_path: str
    current_value: Any
    proposed_value: Any
    reasoning: str
    confidence: float
    evidence_count: int
    state: str
    baseline_hash: str | None = None
    baseline_version: int | None = None
    candidate_hash: str
    approval_candidate_hash: str | None = None
    current_active_hash: str | None = None
    current_active_version: int | None = None
    baseline_hash_matches: bool = False
    evidence_hash_matches: bool = False
    can_promote_to_shadow: bool = False
    can_approve: bool = False
    can_activate: bool = False
    draft_policy_id: str | None = None
    draft_version: str | None = None
    required_guards: list[str] = Field(default_factory=list)
    guard_results: list[PolicyGuardResultItem] = Field(default_factory=list)
    transition_history: list[PolicyTransitionItem] = Field(default_factory=list)
    shadow_aggregate: ShadowEvaluationSummaryItem | None = None
    shadow_results: list[ShadowEvaluationSampleItem] = Field(default_factory=list)
    proposed_by: str
    approved_by: str | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PolicyProposalListResponse(BaseModel):
    """List of governed policy delta proposals and shadow evidence."""

    items: list[PolicyProposalSummary] = Field(default_factory=list)
    total_count: int


class PolicyPromotionResponse(BaseModel):
    """Response from approving a delta into DRAFT or activating DRAFT -> ACTIVE."""

    delta: PolicyProposalSummary | None = None
    policy_id: UUID | None = None
    notification_type: str
    version: str
    status: str
    config_hash: str
    message: str


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


# Note (internal): this is the Pydantic version of ``AuditEvent``.
# ``uns.api.read_models.AuditEvent`` is a different ``@dataclass`` that
# shares the name; the two are NOT interchangeable.
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


class ConsoleSessionResponse(BaseModel):
    """Authenticated console principal and capability scopes."""

    subject: str
    scopes: list[str] = Field(default_factory=list)
    persistence_mode: str | None = None


__all__ = [
    # Notification write DTOs
    "AutonomyContextRequest",
    "DLQListResponse",
    "DLQRemoveResponse",
    "DeliveryAuditItem",
    "DeliveryStatusResponse",
    "PolicyReloadRequest",
    "PolicyReloadResponse",
    "SendNotificationRequest",
    "SendNotificationResponse",
    "SimulateNotificationResponse",
    # Acknowledgment DTOs
    "AckRequest",
    "AckResponse",
    "AckStatusResponse",
    "DismissRequest",
    "NotificationErrorResponse",
    "NotificationStatusResponse",
    # Console / read enums
    "AuditEventType",
    "EnforcementType",
    "InvariantSeverity",
    "InvariantStatus",
    "ResolutionSource",
    # Console / read sub-DTOs
    "DeliveryAttempt",
    "ErrorDetail",
    "EvidenceLink",
    "InvariantEnforcement",
    "PaginationInfo",
    "ResolutionContext",
    "ResolutionStep",
    # Console / read composite Response classes
    "ActivePolicyListResponse",
    "ActivePolicySummary",
    "AuditEvent",
    "AuditEventListResponse",
    "AutonomyContextResponse",
    "ConsoleSessionResponse",
    "DeliveryTimelineListResponse",
    "DeliveryTimelineResponse",
    "DeliveryTimelineSummary",
    "EffectivePolicyResponse",
    "EffectivePolicyValues",
    "InvariantEntry",
    "InvariantListResponse",
    "InvariantSummaryResponse",
    "PolicyGuardResultItem",
    "PolicyPromotionResponse",
    "PolicyProposalActionRequest",
    "PolicyProposalCreateRequest",
    "PolicyProposalListResponse",
    "PolicyProposalSummary",
    "PolicyRevisionListResponse",
    "PolicyRevisionSummary",
    "PolicyTransitionItem",
    "ShadowEvaluationSampleItem",
    "ShadowEvaluationSummaryItem",
    "UIErrorResponse",
]

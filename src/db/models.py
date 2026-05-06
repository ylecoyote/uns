"""Database models for the Unified Notification Service.

This module defines SQLAlchemy models for persisting notification
and audit data. These models support the audit/persistence requirements
specified in the PRD Task 11.

Models:
- NotificationAuditRecord: Audit trail for notification delivery attempts
- AckAuditRecord: Audit trail for acknowledgment state changes
- NotificationPolicy: Persisted policy configurations (optional)
- WebSocketReplayRecord: Durable WebSocket replay payload read model
- PersistedPolicyDelta: Policy learning delta proposals
- PersistedShadowEvaluationResult: Per-decision shadow evaluation records
- PersistedShadowEvaluationAggregate: Per-delta shadow evaluation aggregates
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class DeliveryStatusDB(str, Enum):
    """Database enum for delivery status."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"


class AckStatusDB(str, Enum):
    """Database enum for acknowledgment status."""

    PENDING = "PENDING"
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"


class NotificationAuditRecord(Base):
    """SQLAlchemy model for notification delivery audit records.

    This table captures the complete audit trail for all notification
    delivery attempts, including:
    - Successful deliveries
    - Failed deliveries
    - Deduplicated notifications
    - Rate-limited notifications

    Indexes are optimized for common query patterns:
    - By notification_id (single notification history)
    - By agent_id + created_at (agent activity queries)
    - By status + created_at (failure analysis)
    - By notification_type + created_at (type-based analysis)
    """

    __tablename__ = "notification_audit_records"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique audit record ID"
    )

    # Core identifiers
    notification_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="ID of the notification"
    )
    notification_type: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Namespaced notification type"
    )

    # Delivery outcome
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Delivery status (SUCCESS, FAILED, etc.)"
    )
    channels_attempted: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="List of channels attempted"
    )
    channels_succeeded: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="List of channels that succeeded"
    )
    channels_failed: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="List of channels that failed"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error details if failed"
    )

    # Notification context
    intent: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Notification intent"
    )
    delivery_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Delivery mode (GUARANTEED, BEST_EFFORT)"
    )
    autonomy_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Autonomy mode (PREVIEW, SHADOW, LIVE)"
    )
    agent_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="Agent ID for attribution"
    )

    # Optional context IDs for traceability
    plan_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, comment="Optional plan ID"
    )
    decision_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, comment="Optional decision snapshot ID"
    )
    execution_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, comment="Optional execution snapshot ID"
    )
    skip_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, comment="Optional skip snapshot ID"
    )

    # Notification content
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Notification title"
    )
    source: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Producer identifier"
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Optional correlation ID"
    )

    # Metadata
    notification_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, comment="Notification metadata"
    )
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, comment="Audit-specific metadata"
    )

    # Timestamps
    notification_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When notification was created"
    )
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When delivery was attempted"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When audit record was created",
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_notif_audit_agent_created", "agent_id", "created_at"),
        Index("ix_notif_audit_status_created", "status", "created_at"),
        Index("ix_notif_audit_type_created", "notification_type", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"NotificationAuditRecord(id={self.id}, "
            f"notification_id={self.notification_id}, "
            f"status={self.status})"
        )


class AckAuditRecord(Base):
    """SQLAlchemy model for acknowledgment audit records.

    Captures all acknowledgment state transitions for notifications
    that require acknowledgment.

    This provides a complete history of acknowledgment events including:
    - Initial ack requirement (PENDING state)
    - User acknowledgments (ACKED)
    - User dismissals (DISMISSED)
    - Timeouts (TIMED_OUT)
    """

    __tablename__ = "ack_audit_records"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique audit record ID"
    )

    # Reference to notification
    notification_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="ID of the notification"
    )

    # State transition
    old_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Previous ack status (null for initial)"
    )
    new_status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="New ack status"
    )

    # Actor information
    acked_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="User/system that triggered change"
    )

    # Timestamps
    acked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the ack action occurred"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When audit record was created",
    )

    # Metadata
    ack_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, comment="Additional metadata"
    )

    # Indexes
    __table_args__ = (
        Index("ix_ack_audit_new_status_created", "new_status", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"AckAuditRecord(id={self.id}, "
            f"notification_id={self.notification_id}, "
            f"new_status={self.new_status})"
        )


class PersistedNotificationPolicy(Base):
    """SQLAlchemy model for persisted notification policies.

    Allows policies to be stored in the database rather than
    (or in addition to) code-defined policies.

    This enables runtime policy configuration without redeployment.
    """

    __tablename__ = "notification_policies"

    policy_id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique persisted policy row ID"
    )

    notification_type: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Namespaced notification type"
    )
    version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="1.0.0", comment="Policy version"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ACTIVE", index=True, comment="Policy lifecycle status"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="Semantic policy content hash"
    )
    previous_version_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("notification_policies.policy_id"),
        nullable=True,
        comment="Previous policy version in the lifecycle chain",
    )

    # Policy configuration
    delivery_mode: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Override delivery mode"
    )
    channels: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="Override channels"
    )
    delivery_mode_by_autonomy: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Per-autonomy delivery mode overrides"
    )
    require_ack: Mapped[Any | None] = mapped_column(
        JSON, nullable=True, comment="Override ack requirement or per-mode ack map"
    )
    channels_escalation: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Escalation channel routing by autonomy mode"
    )
    ack_timeout_minutes: Mapped[int | None] = mapped_column(
        nullable=True, comment="Override ack timeout"
    )
    dedup_window_seconds: Mapped[int | None] = mapped_column(
        nullable=True, comment="Override dedup window"
    )

    # Mode-specific overrides stored as JSON
    mode_overrides: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Per-mode override configuration"
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Human-readable policy description"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Whether policy is active"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When policy was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="When policy was last updated",
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When policy became ACTIVE"
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When policy was retired"
    )

    __table_args__ = (
        Index("ix_notification_policy_type_status", "notification_type", "status"),
    )

    def __repr__(self) -> str:
        return (
            "PersistedNotificationPolicy("
            f"notification_type={self.notification_type}, "
            f"version={self.version}, status={self.status})"
        )


class WebSocketReplayRecord(Base):
    """SQLAlchemy model for reconnect replay of WebSocket notifications."""

    __tablename__ = "websocket_replay_records"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique replay row ID"
    )
    agent_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="Target agent identifier"
    )
    notification_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="Notification identifier"
    )
    replay_cursor: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="Reconnect replay cursor"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, comment="WebSocket notification payload"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When the replay payload was recorded",
    )

    __table_args__ = (
        Index("ix_websocket_replay_agent_created", "agent_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            "WebSocketReplayRecord("
            f"notification_id={self.notification_id}, agent_id={self.agent_id})"
        )


class PersistedPolicyDelta(Base):
    """SQLAlchemy model for AGSignal policy learning delta proposals."""

    __tablename__ = "policy_deltas"

    delta_id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique policy delta ID"
    )
    policy_type: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Domain-neutral policy type"
    )
    field_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="Dotted policy field path"
    )
    current_value: Mapped[Any] = mapped_column(
        JSON, nullable=False, comment="Current active policy value"
    )
    proposed_value: Mapped[Any] = mapped_column(
        JSON, nullable=False, comment="Proposed policy value"
    )
    reasoning: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Human-readable proposal reasoning"
    )
    confidence: Mapped[float] = mapped_column(
        nullable=False, comment="Proposal confidence in [0, 1]"
    )
    evidence_count: Mapped[int] = mapped_column(
        nullable=False, default=1, comment="Number of supporting observations"
    )
    state: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PROPOSED", index=True, comment="Delta lifecycle state"
    )
    transition_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="Append-only transition history"
    )
    shadow_evaluation_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, comment="Associated shadow aggregate ID"
    )
    proposed_by: Mapped[str] = mapped_column(
        String(255), nullable=False, default="policy_learning", comment="Proposal actor"
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Approving actor"
    )
    rejected_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Rejecting actor"
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Structured or free-text rejection reason"
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When delta was applied"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When delta was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="When delta was last updated",
    )

    __table_args__ = (
        Index("ix_policy_delta_type_state", "policy_type", "state"),
    )


class PersistedShadowEvaluationResult(Base):
    """SQLAlchemy model for one shadow evaluation decision result."""

    __tablename__ = "policy_shadow_results"

    result_id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique shadow result ID"
    )
    delta_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_deltas.delta_id"),
        nullable=False,
        index=True,
        comment="Policy delta being evaluated",
    )
    decision_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Host decision/signal identifier"
    )
    original_outcome: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Outcome under current policy"
    )
    shadow_outcome: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Outcome under candidate policy"
    )
    changed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Whether candidate changed outcome"
    )
    improvement_score: Mapped[float | None] = mapped_column(
        nullable=True, comment="Domain-neutral improvement score"
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When shadow result was evaluated",
    )


class PersistedShadowEvaluationAggregate(Base):
    """SQLAlchemy model for aggregate shadow evaluation results."""

    __tablename__ = "policy_shadow_aggregates"

    aggregate_id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique shadow aggregate ID"
    )
    delta_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_deltas.delta_id"),
        nullable=False,
        unique=True,
        index=True,
        comment="Policy delta summarized by this aggregate",
    )
    total_decisions: Mapped[int] = mapped_column(
        nullable=False, default=0, comment="Total decisions evaluated"
    )
    improved_decisions: Mapped[int] = mapped_column(
        nullable=False, default=0, comment="Decisions that improved"
    )
    degraded_decisions: Mapped[int] = mapped_column(
        nullable=False, default=0, comment="Decisions that degraded"
    )
    neutral_decisions: Mapped[int] = mapped_column(
        nullable=False, default=0, comment="Decisions with no material change"
    )
    win_rate: Mapped[float] = mapped_column(
        nullable=False, default=0.0, comment="Improved decisions divided by total decisions"
    )
    min_sample_met: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Whether sample size passed"
    )
    accuracy_threshold_met: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Whether quality threshold passed"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING", index=True, comment="Shadow status"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When aggregate was computed",
    )

"""Database models for the Unified Notification Service.

This module defines SQLAlchemy models for persisting notification
and audit data. These models support the audit/persistence requirements
specified in the PRD Task 11.

Models:
- NotificationAuditRecord: Audit trail for notification delivery attempts
- AckAuditRecord: Audit trail for acknowledgment state changes
- NotificationPolicy: Persisted policy configurations (optional)
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

    # Primary key (notification_type is the natural key)
    notification_type: Mapped[str] = mapped_column(
        String(255), primary_key=True, comment="Namespaced notification type"
    )

    # Policy configuration
    delivery_mode: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Override delivery mode"
    )
    channels: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="Override channels"
    )
    require_ack: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="Override ack requirement"
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

    def __repr__(self) -> str:
        return f"PersistedNotificationPolicy(notification_type={self.notification_type})"

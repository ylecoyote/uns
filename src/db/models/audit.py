"""Audit-trail tables (compliance-critical, append-only).

These tables capture the immutable record of notification delivery attempts
and acknowledgment state transitions. They are append-only by convention and
must remain stable across releases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.models._base import Base


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
    policy_config_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, index=True, comment="Policy config used for routing"
    )
    policy_config_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="Exact policy config hash used"
    )
    policy_evaluation_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, index=True, comment="Policy evaluation audit correlation ID"
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

"""Persisted notification-policy table.

Holds runtime-configurable policy rows that the routing layer consults.
Distinct from policy-learning artefacts (see ``policy_learning.py``): these
rows describe currently active policies, while learning artefacts track
proposed deltas and shadow evaluations.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from sqlalchemy.orm import Mapped, mapped_column

from db.models._base import Base


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

    __table_args__ = (Index("ix_notification_policy_type_status", "notification_type", "status"),)

    def __repr__(self) -> str:
        return (
            "PersistedNotificationPolicy("
            f"notification_type={self.notification_type}, "
            f"version={self.version}, status={self.status})"
        )


class NotificationPolicyRevision(Base):
    """Singleton serialization point shared by activation and notification intake."""

    __tablename__ = "notification_policy_revision"

    singleton: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(nullable=False)


class NotificationPolicySnapshot(Base):
    """Append-only, complete policy content for one activated runtime revision."""

    __tablename__ = "notification_policy_snapshots"

    revision: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

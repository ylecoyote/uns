"""Policy-learning tables (experimental).

Captures policy delta proposals and shadow evaluation results/aggregates that
feed UNS's policy-learning loop. Schema here may evolve more aggressively
than the audit tables; isolating it keeps that churn out of the audit/policy
modules.
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


class PersistedPolicyDelta(Base):
    """SQLAlchemy model for UNS policy learning delta proposals."""

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


class PolicyEvidenceBinding(Base):
    """Additive provenance for existing policy delta and shadow records."""
    __tablename__ = "uns_policy_evidence_bindings"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

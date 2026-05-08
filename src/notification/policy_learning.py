"""AGSignal-native policy learning primitives.

This module ports the reusable policy-delta lifecycle concepts from MIP without
bringing over trading-specific policy names or payload schemas.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

#: Default cap on the per-delta transition history. Defense-in-depth against
#: future evolution of the state machine that could allow ping-pong cycles.
#: Configurable via ``AGSIGNAL_TRANSITION_HISTORY_LIMIT``; set to ``0`` to
#: disable capping (operator opt-out).
DEFAULT_TRANSITION_HISTORY_LIMIT = 100


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _transition_history_limit() -> int:
    """Resolve the configured cap from the environment, with a safe default."""
    raw = os.environ.get("AGSIGNAL_TRANSITION_HISTORY_LIMIT")
    if raw is None or raw.strip() == "":
        return DEFAULT_TRANSITION_HISTORY_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TRANSITION_HISTORY_LIMIT
    return value


class DeltaState(str, Enum):
    """Lifecycle state of a policy delta proposal."""

    PROPOSED = "PROPOSED"
    SHADOW = "SHADOW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


class DeltaRejectionReason(str, Enum):
    """Reason a policy delta was rejected by guards or reviewers."""

    DELTA_OUT_OF_BOUNDS = "DELTA_OUT_OF_BOUNDS"
    DELTA_STEP_TOO_LARGE = "DELTA_STEP_TOO_LARGE"
    LEARNING_PAUSED = "LEARNING_PAUSED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    SHADOW_NOT_PASSED = "SHADOW_NOT_PASSED"
    NOT_APPROVED = "NOT_APPROVED"


class GuardStage(str, Enum):
    """Stage at which a guard check is applied."""

    PROPOSE = "PROPOSE"
    PROMOTE_SHADOW = "PROMOTE_SHADOW"
    APPROVE = "APPROVE"
    APPLY = "APPLY"


class ShadowStatus(str, Enum):
    """Aggregate evaluation status for shadow testing a delta."""

    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class FieldBound(BaseModel):
    """Numeric bounds for a policy field guard."""

    field_path: str = Field(description="Dotted path to the bounded policy field")
    min_value: float | None = Field(
        default=None,
        description="Minimum allowed value",
    )
    max_value: float | None = Field(
        default=None,
        description="Maximum allowed value",
    )
    max_abs_change_per_delta: float | None = Field(
        default=None,
        ge=0.0,
        description="Maximum absolute change allowed in one delta",
    )
    max_rel_change_per_delta: float | None = Field(
        default=None,
        ge=0.0,
        description="Maximum relative change allowed in one delta",
    )

    model_config = ConfigDict(frozen=True)

    def allows(self, *, current_value: float, proposed_value: float) -> bool:
        """Return whether proposed_value satisfies configured bounds."""
        if self.min_value is not None and proposed_value < self.min_value:
            return False
        if self.max_value is not None and proposed_value > self.max_value:
            return False

        abs_change = abs(proposed_value - current_value)
        if (
            self.max_abs_change_per_delta is not None
            and abs_change > self.max_abs_change_per_delta
        ):
            return False

        if self.max_rel_change_per_delta is not None:
            if current_value == 0:
                return abs_change == 0
            rel_change = abs_change / abs(current_value)
            if rel_change > self.max_rel_change_per_delta:
                return False

        return True


class GuardResult(BaseModel):
    """Auditable result from guard checks for a delta transition."""

    stage: GuardStage = Field(description="Stage this guard result applies to")
    allowed: bool = Field(description="Whether the guarded transition may proceed")
    reason: DeltaRejectionReason | None = Field(
        default=None,
        description="Structured rejection reason when blocked",
    )
    reason_detail: str | None = Field(
        default=None,
        description="Human-readable rejection detail",
    )
    checks: dict[str, Any] = Field(
        default_factory=dict,
        description="Named guard checks and their observed values",
    )
    checked_at: datetime = Field(
        default_factory=_utc_now,
        description="When the guard result was produced",
    )

    model_config = ConfigDict(frozen=True)

    @property
    def is_blocking(self) -> bool:
        """Whether this guard result blocks a transition."""
        return not self.allowed


class ShadowEvaluationResult(BaseModel):
    """Per-decision shadow evaluation result for a candidate delta."""

    result_id: UUID = Field(
        default_factory=uuid4,
        description="Stable result identifier",
    )
    delta_id: UUID = Field(description="Delta being shadow evaluated")
    decision_id: str = Field(description="Host decision/signal identifier")
    original_outcome: dict[str, Any] = Field(
        description="Outcome from the current policy",
    )
    shadow_outcome: dict[str, Any] = Field(
        description="Outcome from the candidate policy",
    )
    changed: bool = Field(
        default=False,
        description="Whether the candidate policy changed the decision",
    )
    improvement_score: float | None = Field(
        default=None,
        description="Domain-neutral improvement score, if available",
    )
    evaluated_at: datetime = Field(
        default_factory=_utc_now,
        description="When the shadow decision was evaluated",
    )

    model_config = ConfigDict(frozen=True)


class ShadowEvaluationAggregate(BaseModel):
    """Aggregate shadow evaluation result for one policy delta."""

    aggregate_id: UUID = Field(
        default_factory=uuid4,
        description="Stable aggregate identifier",
    )
    delta_id: UUID = Field(description="Delta summarized by this aggregate")
    total_decisions: int = Field(ge=0, description="Total decisions evaluated")
    improved_decisions: int = Field(ge=0, description="Decisions that improved")
    degraded_decisions: int = Field(ge=0, description="Decisions that degraded")
    neutral_decisions: int = Field(ge=0, description="Decisions with no material change")
    win_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Improved decisions divided by total decisions",
    )
    min_sample_met: bool = Field(
        default=False,
        description="Whether enough samples were evaluated",
    )
    accuracy_threshold_met: bool = Field(
        default=False,
        description="Whether the shadow evaluation passed its quality threshold",
    )
    status: ShadowStatus = Field(
        default=ShadowStatus.PENDING,
        description="Overall shadow evaluation status",
    )
    computed_at: datetime = Field(
        default_factory=_utc_now,
        description="When this aggregate was computed",
    )

    model_config = ConfigDict(frozen=True)

    @property
    def can_promote_to_approval(self) -> bool:
        """Whether this aggregate satisfies approval preconditions."""
        return (
            self.status == ShadowStatus.PASSED
            and self.min_sample_met
            and self.accuracy_threshold_met
        )


class PolicyDeltaTransition(BaseModel):
    """Auditable state transition for a policy delta."""

    from_state: DeltaState | None = Field(
        default=None,
        description="Previous state; None only for externally imported history",
    )
    to_state: DeltaState = Field(description="State after the transition")
    actor: str = Field(description="Actor that performed the transition")
    reason: str | DeltaRejectionReason | None = Field(
        default=None,
        description="Human-readable reason or structured rejection reason",
    )
    guard_stage: GuardStage | None = Field(
        default=None,
        description="Guard stage associated with this transition",
    )
    transitioned_at: datetime = Field(
        default_factory=_utc_now,
        description="When this transition occurred",
    )

    model_config = ConfigDict(frozen=True)


class PolicyDelta(BaseModel):
    """Domain-neutral proposed change to a policy field."""

    VALID_TRANSITIONS: ClassVar[dict[DeltaState, tuple[DeltaState, ...]]] = {
        DeltaState.PROPOSED: (DeltaState.SHADOW, DeltaState.REJECTED),
        DeltaState.SHADOW: (DeltaState.APPROVED, DeltaState.REJECTED),
        DeltaState.APPROVED: (DeltaState.APPLIED, DeltaState.REJECTED),
        DeltaState.REJECTED: (),
        DeltaState.APPLIED: (),
    }

    delta_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identifier for this delta",
    )
    policy_type: str = Field(description="AGSignal policy type this delta targets")
    field_path: str = Field(description="Dotted path to the policy field")
    current_value: Any = Field(description="Current value in the active policy")
    proposed_value: Any = Field(description="Proposed replacement value")
    reasoning: str = Field(description="Human-readable reason for the proposal")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this proposal",
    )
    evidence_count: int = Field(
        default=1,
        ge=1,
        description="Number of observations supporting this proposal",
    )
    state: DeltaState = Field(
        default=DeltaState.PROPOSED,
        description="Current lifecycle state",
    )
    transition_history: tuple[PolicyDeltaTransition, ...] = Field(
        default_factory=tuple,
        description="Append-only state transition history",
    )
    shadow_evaluation_id: UUID | None = Field(
        default=None,
        description="Shadow evaluation aggregate attached when entering SHADOW",
    )
    proposed_by: str = Field(
        default="policy_learning",
        description="Actor that proposed this delta",
    )
    approved_by: str | None = Field(
        default=None,
        description="Actor that approved this delta",
    )
    rejected_by: str | None = Field(
        default=None,
        description="Actor that rejected this delta",
    )
    rejection_reason: str | DeltaRejectionReason | None = Field(
        default=None,
        description="Reason for rejection",
    )
    applied_at: datetime | None = Field(
        default=None,
        description="Timestamp when this delta was applied",
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        description="Last update timestamp",
    )

    model_config = ConfigDict(frozen=True)

    def can_transition_to(self, new_state: DeltaState) -> bool:
        """Return whether this delta can move from its current state to new_state."""
        return new_state in self.VALID_TRANSITIONS[self.state]

    def transition_to(
        self,
        new_state: DeltaState,
        *,
        actor: str,
        reason: str | DeltaRejectionReason | None = None,
        guard_stage: GuardStage | None = None,
        shadow_evaluation_id: UUID | None = None,
        transitioned_at: datetime | None = None,
    ) -> PolicyDelta:
        """Return a new delta with an appended auditable state transition."""
        if not self.can_transition_to(new_state):
            allowed = ", ".join(state.value for state in self.VALID_TRANSITIONS[self.state])
            allowed_text = allowed or "none"
            raise ValueError(
                f"Invalid state transition: {self.state.value} -> {new_state.value}. "
                f"Valid transitions from {self.state.value}: {allowed_text}"
            )

        now = transitioned_at or _utc_now()
        transition = PolicyDeltaTransition(
            from_state=self.state,
            to_state=new_state,
            actor=actor,
            reason=reason,
            guard_stage=guard_stage,
            transitioned_at=now,
        )
        new_history: tuple[PolicyDeltaTransition, ...] = (*self.transition_history, transition)
        limit = _transition_history_limit()
        if limit > 0 and len(new_history) > limit:
            new_history = new_history[-limit:]
        updates: dict[str, Any] = {
            "state": new_state,
            "transition_history": new_history,
            "updated_at": now,
        }

        if new_state == DeltaState.SHADOW:
            updates["shadow_evaluation_id"] = shadow_evaluation_id
        elif new_state == DeltaState.APPROVED:
            updates["approved_by"] = actor
        elif new_state == DeltaState.REJECTED:
            updates["rejected_by"] = actor
            updates["rejection_reason"] = reason
        elif new_state == DeltaState.APPLIED:
            updates["applied_at"] = now

        return self.model_copy(update=updates)

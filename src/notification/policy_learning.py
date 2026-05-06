"""AGSignal-native policy learning primitives.

This module ports the reusable policy-delta lifecycle concepts from MIP without
bringing over trading-specific policy names or payload schemas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


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
        updates: dict[str, Any] = {
            "state": new_state,
            "transition_history": (*self.transition_history, transition),
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

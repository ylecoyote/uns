"""Tests for UNS-native policy learning primitives."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from notification.policy_learning import (
    DeltaRejectionReason,
    DeltaState,
    FieldBound,
    GuardResult,
    GuardStage,
    PolicyDelta,
    ShadowEvaluationAggregate,
    ShadowEvaluationResult,
    ShadowStatus,
)


def _delta() -> PolicyDelta:
    return PolicyDelta(
        policy_type="notification.routing",
        field_path="channels.LIVE",
        current_value=["SLACK", "WEBSOCKET"],
        proposed_value=["SLACK", "WEBSOCKET", "PAGERDUTY"],
        reasoning="Safety escalations should include PagerDuty in LIVE mode.",
        confidence=0.82,
        evidence_count=3,
    )


def test_policy_learning_primitives_are_exported_from_notification_package() -> None:
    from notification import DeltaState as ExportedDeltaState
    from notification import PolicyDelta as ExportedPolicyDelta

    assert ExportedDeltaState is DeltaState
    assert ExportedPolicyDelta is PolicyDelta


def test_delta_starts_proposed_with_no_transition_history() -> None:
    delta = _delta()

    assert delta.state == DeltaState.PROPOSED
    assert delta.transition_history == ()
    assert delta.can_transition_to(DeltaState.SHADOW) is True
    assert delta.can_transition_to(DeltaState.APPLIED) is False


def test_delta_transition_returns_new_copy_and_preserves_history() -> None:
    delta = _delta()
    shadow_evaluation_id = uuid4()

    shadow = delta.transition_to(
        DeltaState.SHADOW,
        actor="policy_guard",
        reason="bounds passed",
        guard_stage=GuardStage.PROMOTE_SHADOW,
        shadow_evaluation_id=shadow_evaluation_id,
    )
    approved = shadow.transition_to(
        DeltaState.APPROVED,
        actor="operator@example.com",
        reason="shadow passed",
        guard_stage=GuardStage.APPROVE,
    )
    applied = approved.transition_to(
        DeltaState.APPLIED,
        actor="operator@example.com",
        reason="rollout approved",
        guard_stage=GuardStage.APPLY,
    )

    assert delta.state == DeltaState.PROPOSED
    assert shadow.state == DeltaState.SHADOW
    assert shadow.shadow_evaluation_id == shadow_evaluation_id
    assert applied.state == DeltaState.APPLIED
    assert applied.approved_by == "operator@example.com"
    assert applied.applied_at is not None
    assert [entry.to_state for entry in applied.transition_history] == [
        DeltaState.SHADOW,
        DeltaState.APPROVED,
        DeltaState.APPLIED,
    ]
    assert applied.transition_history[0].from_state == DeltaState.PROPOSED
    assert applied.transition_history[0].actor == "policy_guard"
    assert applied.transition_history[0].guard_stage == GuardStage.PROMOTE_SHADOW


def test_transition_history_caps_to_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When UNS_TRANSITION_HISTORY_LIMIT is set, oldest entries are dropped."""
    monkeypatch.setenv("UNS_TRANSITION_HISTORY_LIMIT", "2")

    delta = _delta()
    delta = delta.transition_to(DeltaState.SHADOW, actor="learner")
    delta = delta.transition_to(DeltaState.APPROVED, actor="reviewer")
    delta = delta.transition_to(DeltaState.APPLIED, actor="applier")

    # Three real transitions occurred but the cap retained only the newest two.
    assert len(delta.transition_history) == 2
    assert [entry.to_state for entry in delta.transition_history] == [
        DeltaState.APPROVED,
        DeltaState.APPLIED,
    ]


def test_transition_history_uncapped_when_limit_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting the limit to 0 explicitly disables capping (operator opt-out)."""
    monkeypatch.setenv("UNS_TRANSITION_HISTORY_LIMIT", "0")

    delta = _delta()
    delta = delta.transition_to(DeltaState.SHADOW, actor="learner")
    delta = delta.transition_to(DeltaState.APPROVED, actor="reviewer")
    delta = delta.transition_to(DeltaState.APPLIED, actor="applier")

    assert len(delta.transition_history) == 3


def test_delta_rejection_records_reviewer_reason_and_becomes_terminal() -> None:
    delta = _delta()

    rejected = delta.transition_to(
        DeltaState.REJECTED,
        actor="operator@example.com",
        reason=DeltaRejectionReason.SHADOW_NOT_PASSED,
        guard_stage=GuardStage.APPROVE,
    )

    assert rejected.state == DeltaState.REJECTED
    assert rejected.rejected_by == "operator@example.com"
    assert rejected.rejection_reason == DeltaRejectionReason.SHADOW_NOT_PASSED
    assert rejected.can_transition_to(DeltaState.SHADOW) is False

    with pytest.raises(ValueError, match="Invalid state transition"):
        rejected.transition_to(DeltaState.SHADOW, actor="policy_guard")


def test_invalid_transition_fails_loudly_without_mutating_original() -> None:
    delta = _delta()

    with pytest.raises(ValueError, match="Invalid state transition"):
        delta.transition_to(DeltaState.APPLIED, actor="policy_guard")

    assert delta.state == DeltaState.PROPOSED
    assert delta.transition_history == ()


def test_delta_validates_confidence_and_evidence_count() -> None:
    with pytest.raises(ValidationError):
        PolicyDelta(
            policy_type="notification.routing",
            field_path="channels.LIVE",
            current_value=[],
            proposed_value=["PAGERDUTY"],
            reasoning="invalid confidence",
            confidence=1.5,
            evidence_count=1,
        )

    with pytest.raises(ValidationError):
        PolicyDelta(
            policy_type="notification.routing",
            field_path="channels.LIVE",
            current_value=[],
            proposed_value=["PAGERDUTY"],
            reasoning="invalid evidence count",
            confidence=0.5,
            evidence_count=0,
        )


def test_shadow_aggregate_requires_sample_and_passed_status_for_approval() -> None:
    delta_id = uuid4()
    aggregate = ShadowEvaluationAggregate(
        delta_id=delta_id,
        total_decisions=12,
        improved_decisions=8,
        degraded_decisions=2,
        neutral_decisions=2,
        win_rate=0.67,
        min_sample_met=True,
        accuracy_threshold_met=True,
        status=ShadowStatus.PASSED,
    )

    assert aggregate.can_promote_to_approval is True

    failed = aggregate.model_copy(update={"status": ShadowStatus.FAILED})
    assert failed.can_promote_to_approval is False


def test_shadow_result_preserves_original_and_candidate_outcomes() -> None:
    result = ShadowEvaluationResult(
        delta_id=uuid4(),
        decision_id="signal-123",
        original_outcome={"channels": ["SLACK"], "require_ack": False},
        shadow_outcome={"channels": ["SLACK", "PAGERDUTY"], "require_ack": True},
        changed=True,
        improvement_score=0.4,
    )

    assert result.changed is True
    assert result.original_outcome["require_ack"] is False
    assert result.shadow_outcome["require_ack"] is True


def test_guard_result_allows_only_when_all_checks_pass() -> None:
    passed = GuardResult(
        stage=GuardStage.APPROVE,
        allowed=True,
        checks={"shadow_passed": True, "operator_present": True},
    )
    blocked = GuardResult(
        stage=GuardStage.APPROVE,
        allowed=False,
        reason=DeltaRejectionReason.SHADOW_NOT_PASSED,
        reason_detail="Shadow aggregate did not pass.",
        checks={"shadow_passed": False, "operator_present": True},
    )

    assert passed.is_blocking is False
    assert blocked.is_blocking is True
    assert blocked.reason == DeltaRejectionReason.SHADOW_NOT_PASSED


def test_field_bound_validates_numeric_bounds_and_step_sizes() -> None:
    bound = FieldBound(
        field_path="ack_timeout_minutes",
        min_value=1,
        max_value=60,
        max_abs_change_per_delta=10,
    )

    assert bound.allows(current_value=15, proposed_value=20) is True
    assert bound.allows(current_value=15, proposed_value=90) is False
    assert bound.allows(current_value=15, proposed_value=30) is False

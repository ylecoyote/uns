"""Tests for AGSignal-native policy learning primitives."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from notification.policy_learning import (
    DeltaRejectionReason,
    DeltaState,
    GuardStage,
    PolicyDelta,
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

"""Tests for generic policy config envelopes and evaluation records."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from notification.policies import PolicyStatus
from notification.policy_config import (
    PolicyConfigEnvelope,
    PolicyEvaluationRecord,
    apply_policy_delta,
    compute_config_hash,
)
from notification.policy_learning import DeltaState, PolicyDelta


def _approved_delta(field_path: str = "routing.channels.LIVE") -> PolicyDelta:
    return PolicyDelta(
        policy_type="notification.routing",
        field_path=field_path,
        current_value=["SLACK", "WEBSOCKET"],
        proposed_value=["SLACK", "WEBSOCKET", "PAGERDUTY"],
        reasoning="Escalate LIVE safety routing.",
        confidence=0.9,
    ).model_copy(update={"state": DeltaState.APPROVED, "approved_by": "operator"})


def test_config_hash_is_stable_for_equivalent_payload_ordering() -> None:
    left = {"routing": {"channels": {"LIVE": ["SLACK"]}}, "version": 1}
    right = {"version": 1, "routing": {"channels": {"LIVE": ["SLACK"]}}}

    assert compute_config_hash(left) == compute_config_hash(right)


def test_policy_config_envelope_computes_hash_and_is_immutable() -> None:
    envelope = PolicyConfigEnvelope(
        policy_type="notification.routing",
        version=1,
        status=PolicyStatus.ACTIVE,
        config_json={"routing": {"channels": {"LIVE": ["SLACK", "WEBSOCKET"]}}},
        created_by="operator@example.com",
    )

    assert envelope.config_hash == compute_config_hash(envelope.config_json)

    with pytest.raises(ValidationError):
        envelope.version = 2


def test_apply_policy_delta_requires_approved_delta() -> None:
    envelope = PolicyConfigEnvelope(
        policy_type="notification.routing",
        version=1,
        status=PolicyStatus.ACTIVE,
        config_json={"routing": {"channels": {"LIVE": ["SLACK", "WEBSOCKET"]}}},
        created_by="operator@example.com",
    )
    proposed = _approved_delta().model_copy(update={"state": DeltaState.SHADOW})

    with pytest.raises(ValueError, match="Only APPROVED deltas"):
        apply_policy_delta(envelope, proposed, actor="operator@example.com")


def test_apply_policy_delta_creates_next_draft_version_with_new_hash() -> None:
    envelope = PolicyConfigEnvelope(
        policy_type="notification.routing",
        version=1,
        status=PolicyStatus.ACTIVE,
        config_json={"routing": {"channels": {"LIVE": ["SLACK", "WEBSOCKET"]}}},
        created_by="operator@example.com",
    )
    delta = _approved_delta()

    updated = apply_policy_delta(envelope, delta, actor="operator@example.com")

    assert updated.policy_type == envelope.policy_type
    assert updated.version == 2
    assert updated.status == PolicyStatus.DRAFT
    assert updated.config_json["routing"]["channels"]["LIVE"] == [
        "SLACK",
        "WEBSOCKET",
        "PAGERDUTY",
    ]
    assert updated.config_hash != envelope.config_hash
    assert updated.source_delta_id == delta.delta_id
    assert envelope.config_json["routing"]["channels"]["LIVE"] == ["SLACK", "WEBSOCKET"]


def test_apply_policy_delta_rejects_policy_type_mismatch() -> None:
    envelope = PolicyConfigEnvelope(
        policy_type="notification.delivery",
        version=1,
        status=PolicyStatus.ACTIVE,
        config_json={"delivery": {"mode": "BEST_EFFORT"}},
        created_by="operator@example.com",
    )

    with pytest.raises(ValueError, match="does not target policy type"):
        apply_policy_delta(envelope, _approved_delta(), actor="operator@example.com")


def test_policy_evaluation_record_captures_exact_config_hash() -> None:
    envelope = PolicyConfigEnvelope(
        config_id=uuid4(),
        policy_type="notification.routing",
        version=1,
        status=PolicyStatus.ACTIVE,
        config_json={"routing": {"channels": {"LIVE": ["SLACK", "WEBSOCKET"]}}},
        created_by="operator@example.com",
    )

    record = PolicyEvaluationRecord.from_envelope(
        envelope,
        decision="ALLOW",
        evaluation_context={"notification_type": "safety.kill_switch"},
        result={"channels": ["SLACK", "WEBSOCKET"]},
    )

    assert record.policy_type == envelope.policy_type
    assert record.config_id == envelope.config_id
    assert record.config_hash == envelope.config_hash
    assert record.evaluation_context["notification_type"] == "safety.kill_switch"

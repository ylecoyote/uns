import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base
from db.policy_learning_store import SQLAlchemyPolicyLearningStore
from notification.policy_config import PolicyConfigEnvelope, apply_policy_delta
from notification.policy_learning import (
    DeltaState,
    GuardResult,
    GuardStage,
    PolicyDelta,
    ShadowEvaluationAggregate,
    ShadowStatus,
)


def proposal():
    envelope = PolicyConfigEnvelope(
        policy_type="limits", version=1, config_json={"limit": 10}, created_by="p"
    )
    delta = PolicyDelta(
        policy_type="limits",
        field_path="limit",
        current_value=10,
        proposed_value=12,
        reasoning="test",
        confidence=0.8,
        baseline_hash=envelope.config_hash,
        baseline_version=1,
        required_guards=["bounds"],
    )
    return envelope, delta


def store():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return SQLAlchemyPolicyLearningStore(sessionmaker(engine))


def test_blocking_or_missing_required_guard_cannot_promote():
    _, delta = proposal()
    s = store()
    s.create_delta(delta)
    with pytest.raises(ValueError, match="guard"):
        s.transition_delta(delta.delta_id, DeltaState.SHADOW, actor="p")
    with pytest.raises(ValueError, match="guard"):
        s.transition_delta(
            delta.delta_id,
            DeltaState.SHADOW,
            actor="p",
            guard_result=GuardResult(stage=GuardStage.PROMOTE_SHADOW, allowed=False),
        )


def test_stale_baseline_and_unapproved_application_rejected():
    envelope, delta = proposal()
    with pytest.raises(ValueError, match="APPROVED"):
        apply_policy_delta(envelope, delta, actor="p")
    approved = delta.model_copy(update={"state": DeltaState.APPROVED})
    newer = envelope.model_copy(update={"version": 2})
    with pytest.raises(ValueError, match="baseline"):
        apply_policy_delta(newer, approved, actor="p")


def test_shadow_must_bind_candidate_and_baseline():
    _, delta = proposal()
    delta = delta.model_copy(update={"required_guards": []})
    s = store()
    s.create_delta(delta)
    s.transition_delta(delta.delta_id, DeltaState.SHADOW, actor="p")
    s.persist_shadow_aggregate(
        ShadowEvaluationAggregate(
            delta_id=delta.delta_id,
            total_decisions=10,
            improved_decisions=10,
            degraded_decisions=0,
            neutral_decisions=0,
            win_rate=1,
            min_sample_met=True,
            accuracy_threshold_met=True,
            status=ShadowStatus.PASSED,
            baseline_hash=delta.baseline_hash,
            candidate_hash="wrong",
            evaluated_by="reviewer",
        )
    )
    with pytest.raises(ValueError, match="candidate"):
        s.transition_delta(delta.delta_id, DeltaState.APPROVED, actor="p")


def test_changed_candidate_invalidates_approval_before_application():
    envelope, delta = proposal()
    approved = delta.transition_to(DeltaState.SHADOW, actor="p").transition_to(
        DeltaState.APPROVED, actor="reviewer"
    )
    changed = approved.model_copy(update={"proposed_value": 999})
    with pytest.raises(ValueError, match="candidate"):
        apply_policy_delta(envelope, changed, actor="p")


def test_bound_shadow_and_guard_evidence_creates_only_a_draft():
    envelope, delta = proposal()
    s = store()
    s.create_delta(delta)
    guard = GuardResult(
        stage=GuardStage.PROMOTE_SHADOW,
        allowed=True,
        checks={"bounds": True},
        candidate_hash=delta.candidate_hash,
    )
    shadow = s.transition_delta(delta.delta_id, DeltaState.SHADOW, actor="p", guard_result=guard)
    s.persist_shadow_aggregate(
        ShadowEvaluationAggregate(
            delta_id=delta.delta_id,
            total_decisions=10,
            improved_decisions=10,
            degraded_decisions=0,
            neutral_decisions=0,
            win_rate=1,
            min_sample_met=True,
            accuracy_threshold_met=True,
            status=ShadowStatus.PASSED,
            baseline_hash=delta.baseline_hash,
            candidate_hash=delta.candidate_hash,
            evaluated_by="reviewer",
        )
    )
    approved = s.transition_delta(
        shadow.delta_id,
        DeltaState.APPROVED,
        actor="reviewer",
        guard_result=guard.model_copy(update={"stage": GuardStage.APPROVE}),
    )
    assert approved.approval_candidate_hash == delta.candidate_hash
    assert len(approved.guard_results) == 2
    draft = apply_policy_delta(envelope, approved, actor="operator")
    assert draft.status.value == "DRAFT" and draft.version == 2
    assert draft.config_json["limit"] == 12 and envelope.config_json["limit"] == 10


def test_retired_policy_cannot_silently_disappear_after_reload():
    from db.policy_store import SQLAlchemyPolicyStore
    from notification.models import Channel
    from notification.policies import NotificationPolicy

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    policies = SQLAlchemyPolicyStore(sessionmaker(engine))
    old = NotificationPolicy(
        notification_type="test.version", channels=[Channel.SLACK], version="1"
    )
    new = old.model_copy(update={"channels": [Channel.EMAIL], "version": "2"})
    policies.save_snapshot([old])
    policies.save_snapshot([new])
    with pytest.raises(ValueError, match="retired"):
        policies.save_snapshot([old])
    assert policies.load_runtime_registry().get_sync("test.version").channels == [Channel.EMAIL]

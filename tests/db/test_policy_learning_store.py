"""Tests for DB-backed policy learning persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import (
    Base,
    PersistedPolicyDelta,
    PersistedShadowEvaluationAggregate,
    PersistedShadowEvaluationResult,
)
from db.policy_learning_store import SQLAlchemyPolicyLearningStore
from notification.policy_learning import (
    DeltaRejectionReason,
    DeltaState,
    GuardResult,
    GuardStage,
    PolicyDelta,
    ShadowEvaluationAggregate,
    ShadowEvaluationResult,
    ShadowStatus,
)


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _delta(policy_type: str = "notification.routing") -> PolicyDelta:
    return PolicyDelta(
        policy_type=policy_type,
        field_path="channels.LIVE",
        current_value=["SLACK", "WEBSOCKET"],
        proposed_value=["SLACK", "WEBSOCKET", "PAGERDUTY"],
        reasoning="Safety escalations should include PagerDuty in LIVE mode.",
        baseline_hash="baseline-v1",
        baseline_version=1,
        confidence=0.82,
        evidence_count=3,
    )


def test_policy_learning_models_have_standalone_tables_without_atp_schema() -> None:
    assert PersistedPolicyDelta.__table__.schema is None
    assert PersistedShadowEvaluationResult.__table__.schema is None
    assert PersistedShadowEvaluationAggregate.__table__.schema is None

    assert PersistedPolicyDelta.__tablename__ == "policy_deltas"
    assert PersistedShadowEvaluationResult.__tablename__ == "policy_shadow_results"
    assert PersistedShadowEvaluationAggregate.__tablename__ == "policy_shadow_aggregates"


def test_policy_learning_migration_has_no_atp_schema_reference() -> None:
    migration = Path("src/db/migrations/002_policy_learning.sql").read_text()

    assert "policy_deltas" in migration
    assert "policy_shadow_results" in migration
    assert "policy_shadow_aggregates" in migration
    assert "atp." not in migration.lower()
    assert "schema atp" not in migration.lower()


def test_create_get_and_list_delta_round_trips_domain_neutral_values() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    created = store.create_delta(_delta())

    loaded = store.get_delta(created.delta_id)
    listed = store.list_deltas(policy_type="notification.routing")

    assert loaded == created
    assert len(listed) == 1
    assert listed[0].delta_id == created.delta_id
    assert listed[0].state == DeltaState.PROPOSED
    assert listed[0].proposed_value == ["SLACK", "WEBSOCKET", "PAGERDUTY"]


def test_transition_delta_persists_transition_history() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    created = store.create_delta(_delta())

    transitioned = store.transition_delta(
        created.delta_id,
        DeltaState.SHADOW,
        actor="policy_guard",
        reason="bounds passed",
        guard_result=GuardResult(
            stage=GuardStage.PROMOTE_SHADOW,
            allowed=True,
            checks={"bounds": True},
        ),
    )
    reloaded = store.get_delta(created.delta_id)

    assert transitioned.state == DeltaState.SHADOW
    assert reloaded is not None
    assert reloaded.state == DeltaState.SHADOW
    assert len(reloaded.transition_history) == 1
    assert reloaded.transition_history[0].from_state == DeltaState.PROPOSED
    assert reloaded.transition_history[0].to_state == DeltaState.SHADOW
    assert reloaded.transition_history[0].guard_stage == GuardStage.PROMOTE_SHADOW


def test_invalid_transition_fails_loudly_and_does_not_mutate_row() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    created = store.create_delta(_delta())

    with pytest.raises(ValueError, match="Invalid state transition"):
        store.transition_delta(created.delta_id, DeltaState.APPLIED, actor="policy_guard")

    reloaded = store.get_delta(created.delta_id)
    assert reloaded is not None
    assert reloaded.state == DeltaState.PROPOSED
    assert reloaded.transition_history == ()


def test_approval_requires_passed_shadow_aggregate() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    created = store.create_delta(_delta())
    shadow = store.transition_delta(
        created.delta_id,
        DeltaState.SHADOW,
        actor="policy_guard",
        reason="bounds passed",
    )

    with pytest.raises(ValueError, match="Shadow evaluation must pass"):
        store.transition_delta(
            shadow.delta_id,
            DeltaState.APPROVED,
            actor="operator@example.com",
            reason="trying too early",
        )

    store.persist_shadow_aggregate(
        ShadowEvaluationAggregate(
            delta_id=shadow.delta_id,
            baseline_hash=shadow.baseline_hash, candidate_hash=shadow.candidate_hash, evaluated_by="reviewer",
            total_decisions=10,
            improved_decisions=7,
            degraded_decisions=1,
            neutral_decisions=2,
            win_rate=0.7,
            min_sample_met=True,
            accuracy_threshold_met=True,
            status=ShadowStatus.PASSED,
        )
    )

    approved = store.transition_delta(
        shadow.delta_id,
        DeltaState.APPROVED,
        actor="operator@example.com",
        reason="shadow passed",
    )

    assert approved.state == DeltaState.APPROVED
    assert approved.approved_by == "operator@example.com"


def test_rejection_records_structured_reason() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    created = store.create_delta(_delta())

    rejected = store.transition_delta(
        created.delta_id,
        DeltaState.REJECTED,
        actor="operator@example.com",
        reason=DeltaRejectionReason.DELTA_OUT_OF_BOUNDS,
    )

    assert rejected.state == DeltaState.REJECTED
    assert rejected.rejection_reason == DeltaRejectionReason.DELTA_OUT_OF_BOUNDS
    assert rejected.rejected_by == "operator@example.com"


def test_shadow_results_and_aggregate_round_trip() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    created = store.create_delta(_delta())
    result = ShadowEvaluationResult(
        delta_id=created.delta_id,
        decision_id="signal-123",
        original_outcome={"channels": ["SLACK"]},
        shadow_outcome={"channels": ["SLACK", "PAGERDUTY"]},
        changed=True,
        improvement_score=0.5,
    )
    aggregate = ShadowEvaluationAggregate(
        delta_id=created.delta_id,
        total_decisions=1,
        improved_decisions=1,
        degraded_decisions=0,
        neutral_decisions=0,
        win_rate=1.0,
        min_sample_met=False,
        accuracy_threshold_met=True,
        status=ShadowStatus.PENDING,
    )

    result_id = store.persist_shadow_result(result)
    first_aggregate_id = store.persist_shadow_aggregate(aggregate)
    second_aggregate_id = store.persist_shadow_aggregate(
        aggregate.model_copy(
            update={
                "total_decisions": 2,
                "improved_decisions": 2,
                "win_rate": 1.0,
                "min_sample_met": True,
                "status": ShadowStatus.PASSED,
            }
        )
    )

    results = store.list_shadow_results(created.delta_id)
    loaded_aggregate = store.get_shadow_aggregate(created.delta_id)

    assert results[0].result_id == result_id
    assert results[0].shadow_outcome == {"channels": ["SLACK", "PAGERDUTY"]}
    assert second_aggregate_id == first_aggregate_id
    assert loaded_aggregate is not None
    assert loaded_aggregate.status == ShadowStatus.PASSED
    assert loaded_aggregate.total_decisions == 2


def test_get_pending_deltas_returns_approved_oldest_first() -> None:
    store = SQLAlchemyPolicyLearningStore(_session_factory())
    first = store.create_delta(_delta(policy_type="notification.routing"))
    second = store.create_delta(_delta(policy_type="notification.delivery"))

    for delta in (first, second):
        shadow = store.transition_delta(delta.delta_id, DeltaState.SHADOW, actor="guard")
        store.persist_shadow_aggregate(
            ShadowEvaluationAggregate(
                delta_id=shadow.delta_id,
            baseline_hash=shadow.baseline_hash, candidate_hash=shadow.candidate_hash, evaluated_by="reviewer",
                total_decisions=10,
                improved_decisions=7,
                degraded_decisions=1,
                neutral_decisions=2,
                win_rate=0.7,
                min_sample_met=True,
                accuracy_threshold_met=True,
                status=ShadowStatus.PASSED,
            )
        )
        store.transition_delta(shadow.delta_id, DeltaState.APPROVED, actor="operator")

    pending = store.get_pending_deltas()

    assert [delta.delta_id for delta in pending] == [first.delta_id, second.delta_id]

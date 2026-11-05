"""SQLAlchemy-backed policy learning persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Table, select, update
from sqlalchemy.orm import Session, object_session, sessionmaker
from sqlalchemy.schema import CreateTable

from db.models import (
    PersistedPolicyDelta,
    PersistedShadowEvaluationAggregate,
    PersistedShadowEvaluationResult,
)
from db.models.policy_learning import PolicyEvidenceBinding
from notification.policy_learning import (
    DeltaRejectionReason,
    DeltaState,
    GuardResult,
    GuardStage,
    PolicyDelta,
    PolicyDeltaTransition,
    ShadowEvaluationAggregate,
    ShadowEvaluationResult,
    ShadowStatus,
)


class SQLAlchemyPolicyLearningStore:
    """SQLAlchemy-backed store for policy deltas and shadow evaluations."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._write_seq: int = 0
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Ensure policy learning tables exist in the bound database engine."""
        from typing import cast

        engine = self._session_factory.kw.get("bind")
        if engine is None:
            return
        with engine.begin() as connection:
            for model in (
                PersistedPolicyDelta,
                PersistedShadowEvaluationResult,
                PersistedShadowEvaluationAggregate,
                PolicyEvidenceBinding,
            ):
                connection.execute(CreateTable(cast(Table, model.__table__), if_not_exists=True))

    def _get_session(self) -> Session:
        return self._session_factory()

    def create_delta(self, delta: PolicyDelta) -> PolicyDelta:
        """Persist a new delta proposal in its current state."""
        if delta.state != DeltaState.PROPOSED or delta.transition_history:
            raise ValueError("New deltas must start as unreviewed PROPOSED records")
        session = self._get_session()
        try:
            row = PersistedPolicyDelta(
                delta_id=delta.delta_id,
                policy_type=delta.policy_type,
                field_path=delta.field_path,
                current_value=delta.current_value,
                proposed_value=delta.proposed_value,
                reasoning=delta.reasoning,
                confidence=delta.confidence,
                evidence_count=delta.evidence_count,
                state=delta.state.value,
                transition_history=[
                    _transition_to_payload(transition) for transition in delta.transition_history
                ],
                shadow_evaluation_id=delta.shadow_evaluation_id,
                proposed_by=delta.proposed_by,
                approved_by=delta.approved_by,
                rejected_by=delta.rejected_by,
                rejection_reason=_reason_to_value(delta.rejection_reason),
                applied_at=delta.applied_at,
                created_at=delta.created_at,
                updated_at=delta.updated_at,
            )
            session.add(row)
            session.add(
                PolicyEvidenceBinding(
                    id=delta.delta_id,
                    payload={
                        "baseline_hash": delta.baseline_hash,
                        "baseline_version": delta.baseline_version,
                        "required_guards": list(delta.required_guards),
                        "field_bound": delta.field_bound.model_dump(mode="json")
                        if delta.field_bound
                        else None,
                    },
                )
            )
            session.commit()
            self._write_seq += 1
            return _row_to_delta(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_delta(self, delta_id: UUID) -> PolicyDelta | None:
        """Return a persisted delta by ID."""
        session = self._get_session()
        try:
            row = session.get(PersistedPolicyDelta, delta_id)
            return _row_to_delta(row) if row is not None else None
        finally:
            session.close()

    def list_deltas(
        self,
        *,
        policy_type: str | None = None,
        state: DeltaState | None = None,
        limit: int = 50,
    ) -> list[PolicyDelta]:
        """List deltas with optional filters."""
        session = self._get_session()
        try:
            query = select(PersistedPolicyDelta)
            if policy_type is not None:
                query = query.where(PersistedPolicyDelta.policy_type == policy_type)
            if state is not None:
                query = query.where(PersistedPolicyDelta.state == state.value)
            query = query.order_by(PersistedPolicyDelta.created_at.desc()).limit(limit)
            rows = session.execute(query).scalars().all()
            return [_row_to_delta(row) for row in rows]
        finally:
            session.close()

    def get_evidence_binding(self, delta_id: UUID) -> dict[str, Any]:
        """Return the durable evidence binding payload for a delta."""
        session = self._get_session()
        try:
            binding = session.get(PolicyEvidenceBinding, delta_id)
            return dict(binding.payload) if binding is not None and binding.payload else {}
        finally:
            session.close()

    def transition_delta(
        self,
        delta_id: UUID,
        new_state: DeltaState,
        *,
        actor: str,
        reason: str | DeltaRejectionReason | None = None,
        guard_result: GuardResult | None = None,
        binding_updates: dict[str, Any] | None = None,
    ) -> PolicyDelta:
        """Validate and persist a delta state transition."""
        session = self._get_session()
        try:
            row = session.get(PersistedPolicyDelta, delta_id)
            if row is None:
                raise ValueError(f"Policy delta {delta_id} not found")

            current = _row_to_delta(row)
            if guard_result is not None and guard_result.is_blocking:
                raise ValueError("Blocking guard prevents transition")
            if (
                new_state != DeltaState.REJECTED
                and current.required_guards
                and (
                    guard_result is None
                    or any(guard_result.checks.get(g) is not True for g in current.required_guards)
                )
            ):
                raise ValueError("Required guards must pass")
            if (
                current.required_guards
                and new_state != DeltaState.REJECTED
                and (guard_result is None or guard_result.candidate_hash != current.candidate_hash)
            ):
                raise ValueError("Required guard evidence must match the exact candidate")
            if (
                new_state != DeltaState.REJECTED
                and current.field_bound is not None
                and not current.field_bound.allows(
                    current_value=current.current_value, proposed_value=current.proposed_value
                )
            ):
                raise ValueError("Configured field bound guard failed")
            if new_state == DeltaState.APPROVED:
                aggregate = _get_aggregate_row(session, delta_id)
                if (
                    aggregate is None
                    or not _row_to_shadow_aggregate(aggregate).can_promote_to_approval
                ):
                    raise ValueError("Shadow evaluation must pass before approval")
                evidence = _row_to_shadow_aggregate(aggregate)
                if (
                    not current.baseline_hash
                    or not evidence.evaluated_by
                    or evidence.baseline_hash != current.baseline_hash
                    or evidence.candidate_hash != current.candidate_hash
                ):
                    raise ValueError(
                        "Shadow candidate and baseline evidence must match the exact proposal"
                    )

            transitioned = current.transition_to(
                new_state,
                actor=actor,
                reason=reason,
                guard_stage=guard_result.stage if guard_result else None,
                shadow_evaluation_id=current.shadow_evaluation_id,
            )
            if new_state == DeltaState.SHADOW:
                aggregate = _get_aggregate_row(session, delta_id)
                if aggregate is not None:
                    transitioned = transitioned.model_copy(
                        update={"shadow_evaluation_id": aggregate.aggregate_id}
                    )

            changed = (
                session.connection()
                .execute(
                    update(PersistedPolicyDelta)
                    .where(
                        PersistedPolicyDelta.delta_id == delta_id,
                        PersistedPolicyDelta.state == current.state.value,
                    )
                    .values(state=new_state.value),
                    execution_options={"synchronize_session": False},
                )
                .rowcount
            )
            if not changed:
                raise ValueError("Policy delta changed concurrently")
            if guard_result is not None:
                transitioned = transitioned.model_copy(
                    update={"guard_results": (*current.guard_results, guard_result)}
                )
            binding = session.get(PolicyEvidenceBinding, delta_id)
            if binding is not None:
                binding.payload = {
                    **binding.payload,
                    "approval_candidate_hash": transitioned.approval_candidate_hash,
                    "guard_results": [
                        guard.model_dump(mode="json") for guard in transitioned.guard_results
                    ],
                    **(binding_updates or {}),
                }
            _apply_delta_to_row(row, transitioned)
            session.commit()
            self._write_seq += 1
            return _row_to_delta(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_pending_deltas(self) -> list[PolicyDelta]:
        """Return APPROVED deltas ready for application, oldest first."""
        session = self._get_session()
        try:
            rows = (
                session.execute(
                    select(PersistedPolicyDelta)
                    .where(PersistedPolicyDelta.state == DeltaState.APPROVED.value)
                    .order_by(PersistedPolicyDelta.created_at.asc())
                )
                .scalars()
                .all()
            )
            return [_row_to_delta(row) for row in rows]
        finally:
            session.close()

    def persist_shadow_result(self, result: ShadowEvaluationResult) -> UUID:
        """Persist one shadow-evaluation result."""
        session = self._get_session()
        try:
            row = PersistedShadowEvaluationResult(
                result_id=result.result_id,
                delta_id=result.delta_id,
                decision_id=result.decision_id,
                original_outcome=result.original_outcome,
                shadow_outcome=result.shadow_outcome,
                changed=result.changed,
                improvement_score=result.improvement_score,
                evaluated_at=result.evaluated_at,
            )
            session.add(row)
            session.commit()
            return row.result_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_shadow_results(
        self,
        delta_id: UUID,
        *,
        limit: int = 100,
    ) -> list[ShadowEvaluationResult]:
        """List shadow results for a delta."""
        session = self._get_session()
        try:
            rows = (
                session.execute(
                    select(PersistedShadowEvaluationResult)
                    .where(PersistedShadowEvaluationResult.delta_id == delta_id)
                    .order_by(PersistedShadowEvaluationResult.evaluated_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [_row_to_shadow_result(row) for row in rows]
        finally:
            session.close()

    def get_shadow_result_counts(self, delta_id: UUID) -> tuple[int, int, int]:
        """Return ``(total, improved, degraded)`` counts for a delta using SQL aggregates."""
        from sqlalchemy import case, func

        session = self._get_session()
        try:
            row = session.execute(
                select(
                    func.count(PersistedShadowEvaluationResult.result_id),
                    func.coalesce(
                        func.sum(
                            case(
                                (PersistedShadowEvaluationResult.improvement_score > 0.0, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (PersistedShadowEvaluationResult.improvement_score < 0.0, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(PersistedShadowEvaluationResult.delta_id == delta_id)
            ).one()
            return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
        finally:
            session.close()

    def persist_shadow_aggregate(self, aggregate: ShadowEvaluationAggregate) -> UUID:
        """Insert or update the single shadow aggregate for a delta."""
        session = self._get_session()
        try:
            row = _get_aggregate_row(session, aggregate.delta_id)
            if row is None:
                row = PersistedShadowEvaluationAggregate(
                    aggregate_id=aggregate.aggregate_id,
                    delta_id=aggregate.delta_id,
                )
                session.add(row)
            _apply_aggregate_to_row(row, aggregate)
            session.merge(
                PolicyEvidenceBinding(
                    id=aggregate.aggregate_id,
                    payload={
                        "baseline_hash": aggregate.baseline_hash,
                        "candidate_hash": aggregate.candidate_hash,
                        "evaluated_by": aggregate.evaluated_by,
                    },
                )
            )

            delta_row = session.get(PersistedPolicyDelta, aggregate.delta_id)
            if delta_row is not None:
                delta_row.shadow_evaluation_id = row.aggregate_id

            session.commit()
            return row.aggregate_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_shadow_aggregate(self, delta_id: UUID) -> ShadowEvaluationAggregate | None:
        """Return the shadow aggregate for a delta."""
        session = self._get_session()
        try:
            row = _get_aggregate_row(session, delta_id)
            return _row_to_shadow_aggregate(row) if row is not None else None
        finally:
            session.close()


def _get_aggregate_row(
    session: Session, delta_id: UUID
) -> PersistedShadowEvaluationAggregate | None:
    return session.execute(
        select(PersistedShadowEvaluationAggregate).where(
            PersistedShadowEvaluationAggregate.delta_id == delta_id
        )
    ).scalar_one_or_none()


def _apply_delta_to_row(row: PersistedPolicyDelta, delta: PolicyDelta) -> None:
    row.policy_type = delta.policy_type
    row.field_path = delta.field_path
    row.current_value = delta.current_value
    row.proposed_value = delta.proposed_value
    row.reasoning = delta.reasoning
    row.confidence = delta.confidence
    row.evidence_count = delta.evidence_count
    row.state = delta.state.value
    row.transition_history = [
        _transition_to_payload(transition) for transition in delta.transition_history
    ]
    row.shadow_evaluation_id = delta.shadow_evaluation_id
    row.proposed_by = delta.proposed_by
    row.approved_by = delta.approved_by
    row.rejected_by = delta.rejected_by
    row.rejection_reason = _reason_to_value(delta.rejection_reason)
    row.applied_at = delta.applied_at
    row.updated_at = delta.updated_at


def _apply_aggregate_to_row(
    row: PersistedShadowEvaluationAggregate,
    aggregate: ShadowEvaluationAggregate,
) -> None:
    row.total_decisions = aggregate.total_decisions
    row.improved_decisions = aggregate.improved_decisions
    row.degraded_decisions = aggregate.degraded_decisions
    row.neutral_decisions = aggregate.neutral_decisions
    row.win_rate = aggregate.win_rate
    row.min_sample_met = aggregate.min_sample_met
    row.accuracy_threshold_met = aggregate.accuracy_threshold_met
    row.status = aggregate.status.value
    row.computed_at = aggregate.computed_at


def _row_to_delta(row: PersistedPolicyDelta) -> PolicyDelta:
    return PolicyDelta(
        **_binding(row, row.delta_id),
        delta_id=row.delta_id,
        policy_type=row.policy_type,
        field_path=row.field_path,
        current_value=row.current_value,
        proposed_value=row.proposed_value,
        reasoning=row.reasoning,
        confidence=row.confidence,
        evidence_count=row.evidence_count,
        state=DeltaState(row.state),
        transition_history=tuple(
            _payload_to_transition(payload) for payload in row.transition_history
        ),
        shadow_evaluation_id=row.shadow_evaluation_id,
        proposed_by=row.proposed_by,
        approved_by=row.approved_by,
        rejected_by=row.rejected_by,
        rejection_reason=_payload_to_reason(row.rejection_reason),
        applied_at=row.applied_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_shadow_result(row: PersistedShadowEvaluationResult) -> ShadowEvaluationResult:
    return ShadowEvaluationResult(
        result_id=row.result_id,
        delta_id=row.delta_id,
        decision_id=row.decision_id,
        original_outcome=row.original_outcome,
        shadow_outcome=row.shadow_outcome,
        changed=row.changed,
        improvement_score=row.improvement_score,
        evaluated_at=row.evaluated_at,
    )


def _row_to_shadow_aggregate(
    row: PersistedShadowEvaluationAggregate,
) -> ShadowEvaluationAggregate:
    return ShadowEvaluationAggregate(
        **_binding(row, row.aggregate_id),
        aggregate_id=row.aggregate_id,
        delta_id=row.delta_id,
        total_decisions=row.total_decisions,
        improved_decisions=row.improved_decisions,
        degraded_decisions=row.degraded_decisions,
        neutral_decisions=row.neutral_decisions,
        win_rate=row.win_rate,
        min_sample_met=row.min_sample_met,
        accuracy_threshold_met=row.accuracy_threshold_met,
        status=ShadowStatus(row.status),
        computed_at=row.computed_at,
    )


def _transition_to_payload(transition: PolicyDeltaTransition) -> dict[str, Any]:
    return {
        "from_state": transition.from_state.value if transition.from_state else None,
        "to_state": transition.to_state.value,
        "actor": transition.actor,
        "reason": _reason_to_value(transition.reason),
        "guard_stage": transition.guard_stage.value if transition.guard_stage else None,
        "transitioned_at": transition.transitioned_at.isoformat(),
    }


def _payload_to_transition(payload: dict[str, Any]) -> PolicyDeltaTransition:
    return PolicyDeltaTransition(
        from_state=DeltaState(payload["from_state"]) if payload.get("from_state") else None,
        to_state=DeltaState(payload["to_state"]),
        actor=payload["actor"],
        reason=_payload_to_reason(payload.get("reason")),
        guard_stage=(GuardStage(payload["guard_stage"]) if payload.get("guard_stage") else None),
        transitioned_at=datetime.fromisoformat(payload["transitioned_at"]),
    )


def _reason_to_value(reason: str | DeltaRejectionReason | None) -> str | None:
    if isinstance(reason, DeltaRejectionReason):
        return reason.value
    return reason


def _payload_to_reason(reason: str | None) -> str | DeltaRejectionReason | None:
    if reason is None:
        return None
    try:
        return DeltaRejectionReason(reason)
    except ValueError:
        return reason


def _binding(row: Any, identifier: UUID) -> dict[str, Any]:
    session = object_session(row)
    binding = session.get(PolicyEvidenceBinding, identifier) if session is not None else None
    return binding.payload if binding is not None else {}

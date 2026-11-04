"""Deterministic pure ``decide()`` and fail-mode-aware ``DecisionEngine.evaluate()``.

Implements ADR Decision Engine Internal Shape & ADR Fail-mode Semantics:
- ``decide(policy, context, ...)`` is a pure function:
  1. Iterates rules in ``(priority is None, priority, yaml_source_index)`` order.
  2. Evaluates each rule's ``when`` conditions left-to-right with short-circuit AND
     so ``field EXISTS`` guards protect subsequent comparisons on optional fields.
  3. Produces one ``Reason`` entry per rule evaluated (matched and unmatched).
  4. Combines matched outcomes using **deny-overrides**
     (``DENY`` > ``REQUIRE_APPROVAL`` > ``ALLOW``, default ``policy.default_decision or DENY``).
- ``DecisionEngine`` wraps ``decide()`` with:
  1. Named ``ContextSchema`` registration and load-time field/operator validation.
  2. Atomic policy hot-reload with last-known-good preservation on load errors.
  3. Per-intent fail-mode translation (``SAFETY`` / ``GOVERNANCE`` / ``OPERATIONAL``
     fail-closed to ``DENY``; ``INFORMATIONAL`` fail-open to ``ALLOW``).
  4. Optional ``GovernanceApprovalBridge`` integration that creates a durable UNS
     notification obligation whenever a rule evaluates to ``REQUIRE_APPROVAL``.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from notification.models import NotificationIntent
from uns import __version__ as uns_version
from uns.governance.context_schema import (
    ContextSchema,
    compute_context_hash,
    resolve_field_path,
    validate_context_capsule,
    validate_policy_against_schema,
)
from uns.governance.decision_record import (
    Decision,
    DecisionRecord,
    Reason,
    RequestOrigin,
)
from uns.governance.errors import (
    ContextSchemaViolation,
    EngineFailure,
    GovernanceError,
    MissingFieldError,
    PolicyEvaluationError,
    PolicyLoadError,
)
from uns.governance.operators import Operator, evaluate_operator
from uns.governance.policy_dsl import Condition, Policy, Rule
from uns.governance.policy_loader import (
    compute_policy_config_hash,
    load_policy_from_yaml,
)

if TYPE_CHECKING:
    from uns.governance.approval_workflow import GovernanceApprovalBridge

DECISION_RECORD_SCHEMA_VERSION = "0.4"


class FailModeType(str, Enum):
    """Closed set of engine failure categories per ADR Fail-mode Semantics §3."""

    DECIDE_EXCEPTION = "engine_failure_decide_exception"
    POLICY_MALFORMED = "engine_failure_policy_malformed"
    CONTEXT_INVALID = "engine_failure_context_invalid"
    EVALUATION_TIMEOUT = "engine_failure_evaluation_timeout"
    ATTRIBUTE_SOURCE = "engine_failure_attribute_source"
    INTERNAL = "engine_failure_internal"


class EvaluationOutcome(BaseModel):
    """Result envelope returned by ``DecisionEngine.evaluate()``."""

    model_config = ConfigDict(extra="forbid")

    record: DecisionRecord
    fail_mode: bool = False
    fail_mode_type: FailModeType | None = None
    fail_mode_detail: str | None = None
    matched_reviewer_role: str | None = None
    matched_reason_text: str | None = None
    approval_request_id: uuid.UUID | None = None
    obligation_notification_id: str | None = None
    operational_alert_notification_id: str | None = None


@dataclass(frozen=True)
class _LoadedPolicyBundle:
    policy: Policy
    policy_config_hash: str
    schema_cls: type[BaseModel]


def _format_condition_predicate(cond: Condition) -> str:
    if cond.operator in (Operator.EXISTS, Operator.NOT_EXISTS):
        return f"{cond.field} {cond.operator.value}"
    return f"{cond.field} {cond.operator.value} {cond.value!r}"


def _format_rule_predicate(rule: Rule) -> str:
    return " AND ".join(_format_condition_predicate(c) for c in rule.when)


def _deterministic_decision_id(
    *,
    policy_config_hash: str,
    context_hash: str,
    subject_id: str,
    tenant_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    correlation_id: str | None = None,
    parent_decision_id: str | None = None,
) -> uuid.UUID:
    seed = (
        f"{policy_config_hash}:{context_hash}:{subject_id or ''}:"
        f"{tenant_id or ''}:{resource_type or ''}:{resource_id or ''}:"
        f"{correlation_id or ''}:{parent_decision_id or ''}"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()[:16]
    return uuid.UUID(bytes=digest, version=4)


def _policy_hash_from_model(policy: Policy) -> str:
    canonical = yaml.safe_dump(
        policy.model_dump(mode="json"),
        sort_keys=True,
        default_flow_style=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _ordered_rules(rules: list[Rule]) -> list[Rule]:
    return [
        rule
        for _, rule in sorted(
            enumerate(rules),
            key=lambda item: (
                0 if item[1].priority is not None else 1,
                item[1].priority if item[1].priority is not None else 0,
                item[0],
            ),
        )
    ]


def decide(
    policy: Policy,
    context: BaseModel | Mapping[str, Any],
    *,
    subject_id: str = "system",
    policy_config_hash: str | None = None,
    context_schema: type[BaseModel] | None = None,
    evaluated_at: datetime | None = None,
    decision_id: uuid.UUID | None = None,
    engine_version: str = uns_version,
    schema_version: str = DECISION_RECORD_SCHEMA_VERSION,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    tenant_id: str | None = None,
    resource_id: str | None = None,
    resource_type: str | None = None,
    parent_decision_id: str | None = None,
    request_origin: RequestOrigin | None = None,
    model_id: str | None = None,
    model_version: str | None = None,
) -> DecisionRecord:
    """Pure, deterministic governance policy evaluator.

    Raises typed ``GovernanceError`` subclasses on contract violations
    (``ContextSchemaViolation``, ``MissingFieldError``, ``PolicyEvaluationError``).
    """
    validated_context: BaseModel | Mapping[str, Any] = context
    if context_schema is not None:
        validated_context = validate_context_capsule(
            context,
            context_schema,
            schema_name=policy.context_schema,
        )
    elif not isinstance(context, (BaseModel, Mapping)):
        raise ContextSchemaViolation(
            f"Context capsule must be a Mapping or BaseModel, got {type(context).__name__}",
            schema_name=policy.context_schema,
        )

    resolved_policy_hash = policy_config_hash or _policy_hash_from_model(policy)
    context_hash = compute_context_hash(validated_context)
    now = evaluated_at or datetime.now(UTC)
    resolved_decision_id = decision_id or _deterministic_decision_id(
        policy_config_hash=resolved_policy_hash,
        context_hash=context_hash,
        subject_id=subject_id,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        parent_decision_id=parent_decision_id,
    )

    reasons: list[Reason] = []
    matched_decisions: list[Decision] = []

    for rule in _ordered_rules(policy.rules):
        rule_matched = True
        for cond in rule.when:
            cond_pred = _format_condition_predicate(cond)
            exists, lhs_value = resolve_field_path(validated_context, cond.field)
            if cond.operator in (Operator.EXISTS, Operator.NOT_EXISTS):
                lhs_for_op = lhs_value if exists else None
                try:
                    cond_ok = evaluate_operator(cond.operator, lhs_for_op, cond.value)
                except PolicyEvaluationError as exc:
                    raise PolicyEvaluationError(
                        str(exc),
                        rule_id=rule.id,
                        predicate=cond_pred,
                    ) from exc
            else:
                if not exists:
                    raise MissingFieldError(
                        field_path=cond.field,
                        schema_name=policy.context_schema,
                    )
                try:
                    cond_ok = evaluate_operator(cond.operator, lhs_value, cond.value)
                except PolicyEvaluationError as exc:
                    raise PolicyEvaluationError(
                        str(exc),
                        rule_id=rule.id,
                        predicate=cond_pred,
                    ) from exc

            if not cond_ok:
                # Short-circuit boolean AND left-to-right
                rule_matched = False
                break

        reasons.append(
            Reason(
                rule_id=rule.id,
                matched=rule_matched,
                predicate=_format_rule_predicate(rule),
                then=rule.then.decision,
            )
        )
        if rule_matched:
            matched_decisions.append(rule.then.decision)

    # Deny-overrides combination (DENY > REQUIRE_APPROVAL > ALLOW)
    if Decision.DENY in matched_decisions:
        final_decision = Decision.DENY
    elif Decision.REQUIRE_APPROVAL in matched_decisions:
        final_decision = Decision.REQUIRE_APPROVAL
    elif Decision.ALLOW in matched_decisions:
        final_decision = Decision.ALLOW
    else:
        final_decision = (
            policy.default_decision if policy.default_decision is not None else Decision.DENY
        )

    return DecisionRecord(
        decision_id=resolved_decision_id,
        policy_config_hash=resolved_policy_hash,
        policy_id=policy.id,
        policy_version=policy.version,
        engine_version=engine_version,
        context_hash=context_hash,
        decision=final_decision,
        reasons=reasons,
        evaluated_at=now,
        schema_version=schema_version,
        subject_id=subject_id,
        correlation_id=correlation_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        tenant_id=tenant_id,
        resource_id=resource_id,
        resource_type=resource_type,
        parent_decision_id=parent_decision_id,
        request_origin=request_origin,
        model_id=model_id,
        model_version=model_version,
    )


class DecisionEngine:
    """Impure governance engine wrapping ``decide()`` with schema registration,
    last-known-good hot reload, per-intent fail-mode, and UNS obligation bridging.
    """

    def __init__(
        self,
        *,
        context_schemas: Mapping[str, ContextSchema],
        policies: Mapping[str, str | Policy] | None = None,
        approval_bridge: GovernanceApprovalBridge | None = None,
        evaluation_timeout_ms: float = 250.0,
        operational_fail_mode_decision: Decision = Decision.DENY,
        max_audit_entries: int = 1000,
    ) -> None:
        if not context_schemas:
            raise PolicyLoadError("DecisionEngine requires at least one registered ContextSchema")
        if operational_fail_mode_decision not in (
            Decision.DENY,
            Decision.REQUIRE_APPROVAL,
            Decision.ALLOW,
        ):
            raise PolicyLoadError(
                f"Invalid operational fail-mode decision: {operational_fail_mode_decision}"
            )

        self._schemas: dict[str, ContextSchema] = dict(context_schemas)
        self._bundles: dict[str, _LoadedPolicyBundle] = {}
        self._quarantined_reloads: dict[str, str] = {}
        self._audit_ledger: deque[EvaluationOutcome] = deque(maxlen=max(1, max_audit_entries))
        self.approval_bridge = approval_bridge
        self.evaluation_timeout_ms = evaluation_timeout_ms
        self.operational_fail_mode_decision = operational_fail_mode_decision

        if policies:
            for _, item in policies.items():
                if isinstance(item, str):
                    self.load_policy_yaml(item)
                else:
                    self.register_policy(item)

    @property
    def policies(self) -> dict[str, Policy]:
        """Return a snapshot of active loaded policies keyed by policy.id."""
        return {pid: bundle.policy for pid, bundle in self._bundles.items()}

    @property
    def quarantined_reloads(self) -> dict[str, str]:
        """Return quarantined hot-reload error messages keyed by policy_id."""
        return dict(self._quarantined_reloads)

    @property
    def audit_ledger(self) -> list[EvaluationOutcome]:
        """Return recorded evaluation outcomes in chronological order."""
        return list(self._audit_ledger)

    def register_policy(
        self,
        policy: Policy,
        *,
        policy_config_hash: str | None = None,
    ) -> Policy:
        """Validate a Policy against its bound ContextSchema and activate it."""
        if policy.context_schema not in self._schemas:
            raise PolicyLoadError(
                f"Policy {policy.id!r} references unregistered ContextSchema {policy.context_schema!r}. "
                f"Registered schemas: {sorted(self._schemas)}"
            )
        schema_cls = self._schemas[policy.context_schema]
        try:
            validate_policy_against_schema(
                policy,
                schema_cls,
                schema_name=policy.context_schema,
            )
        except ContextSchemaViolation as exc:
            raise PolicyLoadError(str(exc)) from exc

        resolved_hash = policy_config_hash or _policy_hash_from_model(policy)
        self._bundles[policy.id] = _LoadedPolicyBundle(
            policy=policy,
            policy_config_hash=resolved_hash,
            schema_cls=schema_cls,
        )
        self._quarantined_reloads.pop(policy.id, None)
        return policy

    def load_policy_yaml(self, yaml_text: str) -> Policy:
        """Parse, schema-validate, and activate a YAML governance policy."""
        policy = load_policy_from_yaml(yaml_text)
        config_hash = compute_policy_config_hash(yaml_text)
        return self.register_policy(policy, policy_config_hash=config_hash)

    def reload_policy_yaml(self, policy_id: str, yaml_text: str) -> bool:
        """Attempt an atomic hot-reload of ``policy_id``.

        If the candidate YAML is malformed or violates the bound ``ContextSchema``,
        the previous active policy remains in force (last-known-good) and ``False``
        is returned after recording the failure in ``quarantined_reloads``.
        """
        try:
            candidate = load_policy_from_yaml(yaml_text)
            if candidate.id != policy_id:
                raise PolicyLoadError(
                    f"Hot-reload policy id mismatch: expected {policy_id!r}, got {candidate.id!r}"
                )
            config_hash = compute_policy_config_hash(yaml_text)
            self.register_policy(candidate, policy_config_hash=config_hash)
            return True
        except GovernanceError as exc:
            self._quarantined_reloads[policy_id] = str(exc)
            return False

    def _fail_mode_decision_for_intent(self, intent: NotificationIntent) -> Decision:
        if intent in (NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE):
            return Decision.DENY
        if intent == NotificationIntent.OPERATIONAL:
            return self.operational_fail_mode_decision
        if intent == NotificationIntent.INFORMATIONAL:
            return Decision.ALLOW
        return Decision.DENY

    def evaluate(
        self,
        policy_id: str,
        context: BaseModel | Mapping[str, Any],
        *,
        subject_id: str = "system",
        intent: NotificationIntent = NotificationIntent.GOVERNANCE,
        evaluated_at: datetime | None = None,
        decision_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        tenant_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        parent_decision_id: str | None = None,
        request_origin: RequestOrigin | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
        callback_url: str | None = None,
    ) -> EvaluationOutcome:
        """Evaluate a governance policy with fail-mode protection and optional obligation bridging."""
        bundle = self._bundles.get(policy_id)
        if bundle is None:
            return self._emit_fail_mode(
                policy_id=policy_id,
                policy_version="unresolved",
                policy_config_hash="unresolved",
                context=context,
                subject_id=subject_id,
                intent=intent,
                fail_type=FailModeType.POLICY_MALFORMED,
                detail=f"Policy {policy_id!r} is not loaded",
                evaluated_at=evaluated_at,
                decision_id=decision_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_type=resource_type,
                parent_decision_id=parent_decision_id,
                request_origin=request_origin,
                model_id=model_id,
                model_version=model_version,
            )

        started = time.perf_counter()
        try:
            record = decide(
                bundle.policy,
                context,
                subject_id=subject_id,
                policy_config_hash=bundle.policy_config_hash,
                context_schema=bundle.schema_cls,
                evaluated_at=evaluated_at,
                decision_id=decision_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_type=resource_type,
                parent_decision_id=parent_decision_id,
                request_origin=request_origin,
                model_id=model_id,
                model_version=model_version,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if elapsed_ms > self.evaluation_timeout_ms:
                raise EngineFailure(
                    f"Evaluation elapsed {elapsed_ms:.1f}ms > budget {self.evaluation_timeout_ms:.1f}ms"
                )
        except ContextSchemaViolation as exc:
            return self._emit_fail_mode(
                policy_id=bundle.policy.id,
                policy_version=bundle.policy.version,
                policy_config_hash=bundle.policy_config_hash,
                context=context,
                subject_id=subject_id,
                intent=intent,
                fail_type=FailModeType.CONTEXT_INVALID,
                detail=f"{type(exc).__name__}: {exc}",
                evaluated_at=evaluated_at,
                decision_id=decision_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_type=resource_type,
                parent_decision_id=parent_decision_id,
                request_origin=request_origin,
                model_id=model_id,
                model_version=model_version,
            )
        except PolicyEvaluationError as exc:
            return self._emit_fail_mode(
                policy_id=bundle.policy.id,
                policy_version=bundle.policy.version,
                policy_config_hash=bundle.policy_config_hash,
                context=context,
                subject_id=subject_id,
                intent=intent,
                fail_type=FailModeType.DECIDE_EXCEPTION,
                detail=f"{type(exc).__name__}: {exc}",
                evaluated_at=evaluated_at,
                decision_id=decision_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_type=resource_type,
                parent_decision_id=parent_decision_id,
                request_origin=request_origin,
                model_id=model_id,
                model_version=model_version,
            )
        except EngineFailure as exc:
            fail_type = (
                FailModeType.EVALUATION_TIMEOUT
                if "budget" in str(exc) or "timeout" in str(exc).lower()
                else FailModeType.INTERNAL
            )
            return self._emit_fail_mode(
                policy_id=bundle.policy.id,
                policy_version=bundle.policy.version,
                policy_config_hash=bundle.policy_config_hash,
                context=context,
                subject_id=subject_id,
                intent=intent,
                fail_type=fail_type,
                detail=f"{type(exc).__name__}: {exc}",
                evaluated_at=evaluated_at,
                decision_id=decision_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_type=resource_type,
                parent_decision_id=parent_decision_id,
                request_origin=request_origin,
                model_id=model_id,
                model_version=model_version,
            )
        except Exception as exc:
            return self._emit_fail_mode(
                policy_id=bundle.policy.id,
                policy_version=bundle.policy.version,
                policy_config_hash=bundle.policy_config_hash,
                context=context,
                subject_id=subject_id,
                intent=intent,
                fail_type=FailModeType.INTERNAL,
                detail=f"{type(exc).__name__}: {exc}",
                evaluated_at=evaluated_at,
                decision_id=decision_id,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_type=resource_type,
                parent_decision_id=parent_decision_id,
                request_origin=request_origin,
                model_id=model_id,
                model_version=model_version,
            )

        # Extract matched reviewer role and reason prose from winning rules
        matched_role: str | None = None
        matched_reason: str | None = None
        matched_rule_ids = {
            r.rule_id for r in record.reasons if r.matched and r.then == record.decision
        }
        for rule in _ordered_rules(bundle.policy.rules):
            if rule.id in matched_rule_ids:
                if matched_role is None and rule.then.target_reviewer_role:
                    matched_role = rule.then.target_reviewer_role
                if matched_reason is None and rule.then.reason:
                    matched_reason = rule.then.reason

        approval_req_id: uuid.UUID | None = None
        obligation_notif_id: str | None = None
        if record.decision == Decision.REQUIRE_APPROVAL and self.approval_bridge is not None:
            approval_req = self.approval_bridge.request_approval(
                record,
                target_reviewer_role=matched_role,
                reason=matched_reason,
                callback_url=callback_url,
            )
            approval_req_id = approval_req.approval_id
            obligation_notif_id = approval_req.notification_id

        outcome = EvaluationOutcome(
            record=record,
            fail_mode=False,
            matched_reviewer_role=matched_role,
            matched_reason_text=matched_reason,
            approval_request_id=approval_req_id,
            obligation_notification_id=obligation_notif_id,
        )
        self._audit_ledger.append(outcome)
        return outcome

    def _emit_fail_mode(
        self,
        *,
        policy_id: str,
        policy_version: str,
        policy_config_hash: str,
        context: Any,
        subject_id: str,
        intent: NotificationIntent,
        fail_type: FailModeType,
        detail: str,
        evaluated_at: datetime | None,
        decision_id: uuid.UUID | None,
        correlation_id: str | None,
        trace_id: str | None,
        span_id: str | None,
        parent_span_id: str | None,
        tenant_id: str | None,
        resource_id: str | None,
        resource_type: str | None,
        parent_decision_id: str | None,
        request_origin: RequestOrigin | None,
        model_id: str | None,
        model_version: str | None,
    ) -> EvaluationOutcome:
        try:
            ctx_hash = (
                compute_context_hash(context)
                if isinstance(context, (BaseModel, Mapping))
                else f"sha256:{hashlib.sha256(repr(context).encode('utf-8')).hexdigest()}"
            )
        except Exception:
            ctx_hash = "sha256:unhashable"

        fallback_decision = self._fail_mode_decision_for_intent(intent)
        now = evaluated_at or datetime.now(UTC)
        resolved_id = decision_id or uuid.uuid4()

        record = DecisionRecord(
            decision_id=resolved_id,
            policy_config_hash=policy_config_hash,
            policy_id=policy_id,
            policy_version=policy_version,
            engine_version=uns_version,
            context_hash=ctx_hash,
            decision=fallback_decision,
            reasons=[
                Reason(
                    rule_id=fail_type.value,
                    matched=True,
                    predicate=detail[:256],
                    then=fallback_decision,
                )
            ],
            evaluated_at=now,
            schema_version=DECISION_RECORD_SCHEMA_VERSION,
            subject_id=subject_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            parent_decision_id=parent_decision_id,
            request_origin=request_origin,
            model_id=model_id,
            model_version=model_version,
        )
        alert_notif_id: str | None = None
        if fallback_decision == Decision.ALLOW and self.approval_bridge is not None:
            alert_notif_id = self.approval_bridge.emit_operational_alert(
                record,
                fail_type=fail_type.value,
                detail=detail,
            )

        outcome = EvaluationOutcome(
            record=record,
            fail_mode=True,
            fail_mode_type=fail_type,
            fail_mode_detail=detail,
            operational_alert_notification_id=alert_notif_id,
        )
        self._audit_ledger.append(outcome)
        return outcome

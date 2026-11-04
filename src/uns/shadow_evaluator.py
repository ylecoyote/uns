"""Automated shadow-policy evaluation runner and governed promotion workflow.

Implements Milestone v0.5.0:
- Issue #46: Side-effect-free background shadow evaluation of PREVIEW policies
  and SHADOW PolicyDelta proposals against live intake notifications, persisting
  ShadowEvaluationResult samples and rolling ShadowEvaluationAggregate metrics.
- Issue #47: Governed lifecycle operations (Propose -> Promote to SHADOW/PREVIEW
  -> Shadow Evidence Gate -> Approve into DRAFT -> Explicit Activate DRAFT -> ACTIVE).
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from db.policy_learning_store import SQLAlchemyPolicyLearningStore
from db.policy_store import PolicySaveResult, SQLAlchemyPolicyStore
from notification.models import AutonomyMode, Channel, DeliveryMode, NotificationIntent
from notification.policies import ModeOverride, NotificationPolicy, PolicyRegistry, PolicyStatus
from notification.policy_config import (
    PolicyConfigEnvelope,
    apply_policy_delta,
    compute_config_hash,
)
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
from uns.responses import (
    PolicyGuardResultItem,
    PolicyProposalSummary,
    PolicyTransitionItem,
    SendNotificationRequest,
    ShadowEvaluationSampleItem,
    ShadowEvaluationSummaryItem,
)
from uns.signaling import _resolve_notification

logger = logging.getLogger(__name__)

DEFAULT_SHADOW_MIN_SAMPLES = 3
DEFAULT_SHADOW_ACCURACY_THRESHOLD = 0.8

ALLOWED_POLICY_FIELD_PATHS: frozenset[str] = frozenset(
    {
        "channels",
        "delivery_mode",
        "require_ack",
        "ack_timeout_minutes",
        "dedup_window_seconds",
        "intent",
        "priority_override",
        "mode_overrides.LIVE.channels",
        "mode_overrides.SHADOW.channels",
        "mode_overrides.PREVIEW.channels",
        "mode_overrides.LIVE.require_ack",
        "mode_overrides.SHADOW.require_ack",
        "mode_overrides.PREVIEW.require_ack",
        "mode_overrides.LIVE.delivery_mode",
        "mode_overrides.SHADOW.delivery_mode",
        "mode_overrides.PREVIEW.delivery_mode",
        "mode_overrides.LIVE.ack_timeout_minutes",
        "mode_overrides.SHADOW.ack_timeout_minutes",
        "mode_overrides.PREVIEW.ack_timeout_minutes",
    }
)


def parse_version_int(version_str: str | None) -> int:
    """Parse a semantic or integer policy version string into a monotonic integer."""
    if not version_str:
        return 1
    cleaned = version_str.strip()
    try:
        return max(1, int(cleaned))
    except ValueError:
        digits = "".join(ch for ch in cleaned.split(".")[0] if ch.isdigit())
        return max(1, int(digits)) if digits else 1


def policy_to_config_dict(
    policy: NotificationPolicy | None, notification_type: str
) -> dict[str, Any]:
    """Build a canonical dictionary representation of a NotificationPolicy for hashing and delta application."""
    if policy is None:
        policy = NotificationPolicy(
            notification_type=notification_type,
            version="1",
            status=PolicyStatus.ACTIVE,
            channels=[],
            delivery_mode=None,
            require_ack=None,
            ack_timeout_minutes=None,
            dedup_window_seconds=300,
        )
    mode_overrides_dict: dict[str, dict[str, Any]] = {}
    for mode in AutonomyMode:
        override = policy._get_mode_override(mode)
        mode_entry: dict[str, Any] = {
            "channels": None,
            "require_ack": None,
            "delivery_mode": None,
            "ack_timeout_minutes": None,
        }
        if override is not None:
            if override.channels is not None:
                mode_entry["channels"] = [ch.value for ch in override.channels]
            if override.require_ack is not None:
                mode_entry["require_ack"] = override.require_ack
            if override.delivery_mode is not None:
                mode_entry["delivery_mode"] = override.delivery_mode.value
            if override.ack_timeout_minutes is not None:
                mode_entry["ack_timeout_minutes"] = override.ack_timeout_minutes
        mode_overrides_dict[mode.value] = mode_entry

    return {
        "notification_type": policy.notification_type,
        "intent": policy.intent.value if policy.intent is not None else None,
        "delivery_mode": (policy.delivery_mode.value if policy.delivery_mode is not None else None),
        "channels": [ch.value for ch in policy.channels],
        "require_ack": policy.require_ack,
        "ack_timeout_minutes": policy.ack_timeout_minutes,
        "dedup_window_seconds": policy.dedup_window_seconds,
        "priority_override": policy.priority_override,
        "mode_overrides": mode_overrides_dict,
    }


def policy_to_envelope(
    policy: NotificationPolicy | None,
    notification_type: str,
    *,
    created_by: str = "system",
) -> PolicyConfigEnvelope:
    """Wrap a NotificationPolicy into a hash-verified PolicyConfigEnvelope."""
    config_json = policy_to_config_dict(policy, notification_type)
    version = parse_version_int(policy.version if policy is not None else "1")
    status = policy.status if policy is not None else PolicyStatus.ACTIVE
    return PolicyConfigEnvelope(
        policy_type=notification_type,
        version=version,
        status=status,
        config_json=config_json,
        created_by=created_by,
    )


def config_dict_to_policy(
    config: dict[str, Any],
    *,
    version: str,
    status: PolicyStatus,
) -> NotificationPolicy:
    """Hydrate and validate a NotificationPolicy from a canonical config dictionary."""
    raw_overrides = config.get("mode_overrides") or {}
    mode_overrides: dict[AutonomyMode, ModeOverride] = {}
    if isinstance(raw_overrides, dict):
        for mode in AutonomyMode:
            entry = raw_overrides.get(mode.value)
            if not isinstance(entry, dict):
                continue
            cleaned = {k: v for k, v in entry.items() if v is not None}
            if not cleaned:
                continue
            if "channels" in cleaned and isinstance(cleaned["channels"], list):
                cleaned["channels"] = [Channel(str(ch).upper()) for ch in cleaned["channels"]]
            if "delivery_mode" in cleaned and cleaned["delivery_mode"] is not None:
                cleaned["delivery_mode"] = DeliveryMode(str(cleaned["delivery_mode"]).upper())
            mode_overrides[mode] = ModeOverride(**cleaned)

    raw_channels = config.get("channels") or []
    channels = [Channel(str(ch).upper()) for ch in raw_channels]
    raw_intent = config.get("intent")
    intent = NotificationIntent(str(raw_intent).upper()) if raw_intent else None
    raw_delivery_mode = config.get("delivery_mode")
    delivery_mode = DeliveryMode(str(raw_delivery_mode).upper()) if raw_delivery_mode else None

    raw_dedup = config.get("dedup_window_seconds")
    dedup_window_seconds = 300 if raw_dedup is None else int(raw_dedup)

    return NotificationPolicy(
        notification_type=str(config["notification_type"]),
        version=str(version),
        status=status,
        intent=intent,
        delivery_mode=delivery_mode,
        channels=channels,
        require_ack=config.get("require_ack"),
        ack_timeout_minutes=config.get("ack_timeout_minutes"),
        dedup_window_seconds=dedup_window_seconds,
        priority_override=config.get("priority_override"),
        mode_overrides=mode_overrides or None,
    )


def envelope_to_policy(
    envelope: PolicyConfigEnvelope,
    *,
    status: PolicyStatus | None = None,
) -> NotificationPolicy:
    """Convert a PolicyConfigEnvelope into a validated NotificationPolicy."""
    return config_dict_to_policy(
        envelope.config_json,
        version=str(envelope.version),
        status=status or envelope.status,
    )


def get_nested_field(config: dict[str, Any], field_path: str) -> Any:
    """Read a dotted field path from a canonical policy config dict."""
    cursor: Any = config
    for part in field_path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise ValueError(f"Unknown policy field path: {field_path}")
        cursor = cursor[part]
    return copy.deepcopy(cursor)


def set_nested_field(config: dict[str, Any], field_path: str, value: Any) -> dict[str, Any]:
    """Return a copy of config with field_path updated to value."""
    updated = copy.deepcopy(config)
    parts = field_path.split(".")
    cursor: Any = updated
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            raise ValueError(f"Invalid policy field path: {field_path}")
        cursor = cursor[part]
    if not isinstance(cursor, dict) or parts[-1] not in cursor:
        raise ValueError(f"Invalid policy field path: {field_path}")
    cursor[parts[-1]] = copy.deepcopy(value)
    return updated


def normalize_proposed_value(field_path: str, proposed_value: Any) -> Any:
    """Validate and normalize proposed_value for the target field_path."""
    if field_path not in ALLOWED_POLICY_FIELD_PATHS:
        raise ValueError(
            f"Unsupported field_path '{field_path}'. Allowed paths: "
            + ", ".join(sorted(ALLOWED_POLICY_FIELD_PATHS))
        )
    if field_path == "channels" or field_path.endswith(".channels"):
        if isinstance(proposed_value, str):
            items = [part.strip().upper() for part in proposed_value.split(",") if part.strip()]
        elif isinstance(proposed_value, (list, tuple)):
            items = [str(part).strip().upper() for part in proposed_value if str(part).strip()]
        else:
            raise ValueError("channels must be a list of channel names")
        if not items:
            raise ValueError("channels must contain at least one channel")
        return [Channel(ch).value for ch in items]

    if field_path == "delivery_mode" or field_path.endswith(".delivery_mode"):
        if proposed_value is None:
            return None
        return DeliveryMode(str(proposed_value).strip().upper()).value

    if field_path == "require_ack" or field_path.endswith(".require_ack"):
        if isinstance(proposed_value, bool):
            return proposed_value
        if isinstance(proposed_value, str):
            lowered = proposed_value.strip().lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no"):
                return False
        raise ValueError("require_ack must be a boolean")

    if field_path == "ack_timeout_minutes" or field_path.endswith(".ack_timeout_minutes"):
        if proposed_value is None or proposed_value == "":
            return None
        val = int(proposed_value)
        if val <= 0:
            raise ValueError("ack_timeout_minutes must be positive")
        return val

    if field_path == "dedup_window_seconds":
        val = int(proposed_value)
        if val < 0:
            raise ValueError("dedup_window_seconds must be non-negative")
        return val

    if field_path == "intent":
        if proposed_value is None or proposed_value == "":
            return None
        return NotificationIntent(str(proposed_value).strip().upper()).value

    if field_path == "priority_override":
        if proposed_value is None or proposed_value == "":
            return None
        val = int(proposed_value)
        if val < 1 or val > 10:
            raise ValueError("priority_override must be between 1 and 10")
        return val

    return proposed_value


class ShadowPolicyEvaluator:
    """Evaluates PREVIEW policies and SHADOW deltas against live intake without side effects."""

    def __init__(
        self,
        policy_store: SQLAlchemyPolicyStore,
        learning_store: SQLAlchemyPolicyLearningStore,
        *,
        enabled: bool | None = None,
        min_samples: int | None = None,
        accuracy_threshold: float | None = None,
        evaluator_id: str = "uns.shadow_evaluator",
    ) -> None:
        self.policy_store = policy_store
        self.learning_store = learning_store
        if enabled is None:
            raw_enabled = os.environ.get("UNS_SHADOW_EVALUATION_ENABLED", "true").strip().lower()
            self.enabled = raw_enabled in ("1", "true", "yes", "on")
        else:
            self.enabled = enabled

        if min_samples is None:
            raw_min = os.environ.get("UNS_SHADOW_MIN_SAMPLES")
            self.min_samples = (
                max(1, int(raw_min))
                if raw_min and raw_min.strip().isdigit()
                else DEFAULT_SHADOW_MIN_SAMPLES
            )
        else:
            self.min_samples = max(1, min_samples)

        if accuracy_threshold is None:
            raw_acc = os.environ.get("UNS_SHADOW_ACCURACY_THRESHOLD")
            try:
                self.accuracy_threshold = (
                    float(raw_acc) if raw_acc is not None else DEFAULT_SHADOW_ACCURACY_THRESHOLD
                )
            except ValueError:
                self.accuracy_threshold = DEFAULT_SHADOW_ACCURACY_THRESHOLD
        else:
            self.accuracy_threshold = accuracy_threshold

        self.evaluator_id = evaluator_id
        self._checked_seq: tuple[int, int] | None = None
        self._has_any_candidates: bool = False

    def _check_has_any_candidates(self) -> bool:
        has_shadow_deltas = bool(self.learning_store.list_deltas(state=DeltaState.SHADOW, limit=1))
        if has_shadow_deltas:
            self._has_any_candidates = True
            return True
        has_preview_policies = bool(
            self.policy_store.list_revisions(status=PolicyStatus.PREVIEW, limit=1)
        )
        self._has_any_candidates = has_preview_policies
        return self._has_any_candidates

    def get_active_baseline(
        self, notification_type: str
    ) -> tuple[NotificationPolicy | None, PolicyConfigEnvelope]:
        """Return the currently active policy and its canonical PolicyConfigEnvelope."""
        runtime_registry = self.policy_store.load_runtime_registry()
        active_policy = runtime_registry.get_sync(notification_type)
        envelope = policy_to_envelope(active_policy, notification_type)
        return active_policy, envelope

    def build_candidate_policy(self, delta: PolicyDelta) -> NotificationPolicy:
        """Build a PREVIEW candidate NotificationPolicy from a PolicyDelta."""
        active_policy, baseline_envelope = self.get_active_baseline(delta.policy_type)
        updated_config = set_nested_field(
            baseline_envelope.config_json,
            delta.field_path,
            delta.proposed_value,
        )
        next_version = str((delta.baseline_version or baseline_envelope.version) + 1)
        return config_dict_to_policy(
            updated_config,
            version=next_version,
            status=PolicyStatus.PREVIEW,
        )

    def _ensure_shadow_deltas_for_preview_policies(
        self, notification_type: str
    ) -> list[PolicyDelta]:
        """Return SHADOW deltas for notification_type, auto-binding standalone PREVIEW policies."""
        shadow_deltas = self.learning_store.list_deltas(
            policy_type=notification_type,
            state=DeltaState.SHADOW,
        )
        if shadow_deltas:
            return shadow_deltas

        preview_revs = self.policy_store.list_revisions(
            notification_type=notification_type,
            status=PolicyStatus.PREVIEW,
            limit=1,
        )
        if not preview_revs:
            return []
        preview_policy = preview_revs[0][1]
        if preview_policy.status != PolicyStatus.PREVIEW:
            return []

        active_policy, baseline_envelope = self.get_active_baseline(notification_type)
        preview_config = policy_to_config_dict(preview_policy, notification_type)
        baseline_config = baseline_envelope.config_json

        diff_field = "channels"
        current_val: Any = baseline_config.get("channels")
        proposed_val: Any = preview_config.get("channels")
        for candidate_field in (
            "channels",
            "delivery_mode",
            "require_ack",
            "ack_timeout_minutes",
            "dedup_window_seconds",
            "intent",
            "priority_override",
            "mode_overrides.LIVE.channels",
            "mode_overrides.LIVE.require_ack",
            "mode_overrides.LIVE.delivery_mode",
        ):
            cur = get_nested_field(baseline_config, candidate_field)
            prop = get_nested_field(preview_config, candidate_field)
            if cur != prop:
                diff_field = candidate_field
                current_val = cur
                proposed_val = prop
                break

        delta = PolicyDelta(
            policy_type=notification_type,
            field_path=diff_field,
            current_value=current_val,
            proposed_value=proposed_val,
            reasoning=f"Auto-bound from PREVIEW policy version {preview_policy.version}",
            confidence=0.9,
            baseline_hash=baseline_envelope.config_hash,
            baseline_version=baseline_envelope.version,
            proposed_by=self.evaluator_id,
            required_guards=("bounds", "schema_valid"),
        )
        created = self.learning_store.create_delta(delta)
        guard = GuardResult(
            candidate_hash=created.candidate_hash,
            stage=GuardStage.PROMOTE_SHADOW,
            allowed=True,
            checks={"bounds": True, "schema_valid": True},
        )
        promoted = self.learning_store.transition_delta(
            created.delta_id,
            DeltaState.SHADOW,
            actor=self.evaluator_id,
            reason="Bound to active PREVIEW policy",
            guard_result=guard,
        )
        return [promoted]

    @staticmethod
    def _outcome_dict(
        request: SendNotificationRequest,
        registry: PolicyRegistry,
    ) -> tuple[dict[str, Any], bool, str | None]:
        """Resolve a SendNotificationRequest against a PolicyRegistry with zero side effects."""
        try:
            _, resolved = _resolve_notification(request, policy_registry=registry)
            dedup_window = registry.get_dedup_window(resolved.notification_type)
            channels = [ch.value for ch in resolved.channels]
            delivery_mode = (
                resolved.delivery_mode.value
                if resolved.delivery_mode is not None
                else DeliveryMode.BEST_EFFORT.value
            )
            require_ack = bool(resolved.require_ack)

            # Check safety & delivery invariants
            degraded_reason: str | None = None
            if not channels:
                degraded_reason = "no_delivery_channels"
            elif resolved.delivery_mode == DeliveryMode.GUARANTEED and not any(
                ch != Channel.WEBSOCKET for ch in resolved.channels
            ):
                degraded_reason = "guaranteed_without_persistent_channel"
            elif (
                request.intent == NotificationIntent.SAFETY or request.irreversible
            ) and resolved.delivery_mode != DeliveryMode.GUARANTEED:
                degraded_reason = "safety_floor_violated"

            return (
                {
                    "notification_type": resolved.notification_type,
                    "channels": channels,
                    "delivery_mode": delivery_mode,
                    "require_ack": require_ack,
                    "ack_timeout_minutes": resolved.ack_timeout_minutes,
                    "dedup_window_seconds": dedup_window,
                    "priority": resolved.priority,
                    "degraded_reason": degraded_reason,
                },
                degraded_reason is not None,
                degraded_reason,
            )
        except Exception as exc:
            return (
                {
                    "notification_type": request.notification_type,
                    "error": str(exc),
                },
                True,
                str(exc),
            )

    def evaluate_intake(
        self,
        request: SendNotificationRequest,
        *,
        decision_id: str | UUID | None = None,
    ) -> list[ShadowEvaluationResult]:
        """Evaluate all SHADOW deltas / PREVIEW policies for request.notification_type."""
        if not self.enabled or not self._check_has_any_candidates():
            return []

        deltas = self._ensure_shadow_deltas_for_preview_policies(request.notification_type)
        if not deltas:
            return []

        runtime_registry = self.policy_store.load_runtime_registry()
        original_outcome, _, _ = self._outcome_dict(request, runtime_registry)
        preview_revs = self.policy_store.list_revisions(
            notification_type=request.notification_type,
            status=PolicyStatus.PREVIEW,
            limit=1,
        )
        persisted_preview = preview_revs[0][1] if preview_revs else None

        decision_key = str(decision_id or uuid4())
        emitted: list[ShadowEvaluationResult] = []

        for delta in deltas:
            try:
                candidate_policy = self.build_candidate_policy(delta)
            except Exception:
                if persisted_preview is not None:
                    candidate_policy = persisted_preview
                else:
                    continue

            candidate_registry = PolicyRegistry(runtime_only=False)
            for pol in runtime_registry.get_all().values():
                if pol.notification_type != request.notification_type:
                    candidate_registry.register(pol)
            candidate_registry.register(candidate_policy)

            shadow_outcome, is_degraded, _ = self._outcome_dict(request, candidate_registry)

            comparable_keys = (
                "channels",
                "delivery_mode",
                "require_ack",
                "ack_timeout_minutes",
                "dedup_window_seconds",
                "priority",
            )
            changed = is_degraded or any(
                original_outcome.get(k) != shadow_outcome.get(k) for k in comparable_keys
            )
            if is_degraded:
                improvement_score = -1.0
            elif changed:
                improvement_score = 1.0
            else:
                improvement_score = 0.0

            result = ShadowEvaluationResult(
                delta_id=delta.delta_id,
                decision_id=decision_key,
                original_outcome=original_outcome,
                shadow_outcome=shadow_outcome,
                changed=changed,
                improvement_score=improvement_score,
            )
            self.learning_store.persist_shadow_result(result)
            self._update_aggregate(delta, result)
            emitted.append(result)

        return emitted

    async def evaluate_intake_async(
        self,
        request: SendNotificationRequest,
        *,
        decision_id: str | UUID | None = None,
    ) -> list[ShadowEvaluationResult]:
        """Asynchronously evaluate PREVIEW/SHADOW policies in a worker thread."""
        return await asyncio.to_thread(
            self.evaluate_intake,
            request,
            decision_id=decision_id,
        )

    def _update_aggregate(
        self,
        delta: PolicyDelta,
        latest_result: ShadowEvaluationResult,
    ) -> ShadowEvaluationAggregate:
        """Recompute and persist rolling ShadowEvaluationAggregate for delta from persisted samples."""
        existing = self.learning_store.get_shadow_aggregate(delta.delta_id)
        samples = self.learning_store.list_shadow_results(delta.delta_id, limit=10_000)
        if samples:
            total = len(samples)
            improved = sum(1 for s in samples if (s.improvement_score or 0.0) > 0)
            degraded = sum(1 for s in samples if (s.improvement_score or 0.0) < 0)
            neutral = total - improved - degraded
        else:
            score = latest_result.improvement_score or 0.0
            total = 1
            improved = 1 if score > 0 else 0
            degraded = 1 if score < 0 else 0
            neutral = 1 if score == 0 else 0
        aggregate_id = existing.aggregate_id if existing is not None else uuid4()

        # Win rate reflects the proportion of non-degraded shadow evaluations
        # when the candidate policy is valid, or improved / total when changes occur.
        effective_positive = improved if (improved + degraded) > 0 else (total - degraded)
        win_rate = round(effective_positive / total, 4) if total > 0 else 0.0
        non_degraded_rate = (total - degraded) / total if total > 0 else 0.0

        min_sample_met = total >= self.min_samples
        accuracy_threshold_met = degraded == 0 and non_degraded_rate >= self.accuracy_threshold

        if degraded > 0 and non_degraded_rate < self.accuracy_threshold:
            status = ShadowStatus.FAILED
        elif min_sample_met and accuracy_threshold_met:
            status = ShadowStatus.PASSED
        else:
            status = ShadowStatus.PENDING

        aggregate = ShadowEvaluationAggregate(
            aggregate_id=aggregate_id,
            delta_id=delta.delta_id,
            baseline_hash=delta.baseline_hash,
            candidate_hash=delta.candidate_hash,
            evaluated_by=self.evaluator_id,
            total_decisions=total,
            improved_decisions=improved,
            degraded_decisions=degraded,
            neutral_decisions=neutral,
            win_rate=win_rate,
            min_sample_met=min_sample_met,
            accuracy_threshold_met=accuracy_threshold_met,
            status=status,
            computed_at=datetime.now(UTC),
        )
        self.learning_store.persist_shadow_aggregate(aggregate)
        return aggregate

    def propose_delta(
        self,
        *,
        policy_type: str,
        field_path: str,
        proposed_value: Any,
        reasoning: str,
        actor: str,
        confidence: float = 0.9,
        evidence_count: int = 1,
        field_bound: FieldBound | None = None,
        required_guards: tuple[str, ...] = ("bounds", "schema_valid"),
        promote_to_shadow: bool = False,
    ) -> PolicyDelta:
        """Create a governed PolicyDelta proposal against the current ACTIVE baseline."""
        normalized_value = normalize_proposed_value(field_path, proposed_value)
        _, baseline_envelope = self.get_active_baseline(policy_type)
        current_value = get_nested_field(baseline_envelope.config_json, field_path)
        if current_value == normalized_value:
            raise ValueError(
                f"Proposed value for '{field_path}' is identical to the current active value"
            )

        if (
            field_bound is not None
            and isinstance(current_value, (int, float))
            and isinstance(normalized_value, (int, float))
            and not field_bound.allows(
                current_value=float(current_value),
                proposed_value=float(normalized_value),
            )
        ):
            raise ValueError("Proposed value violates configured field_bound")

        # Validate that applying the proposed value produces a valid NotificationPolicy
        updated_config = set_nested_field(
            baseline_envelope.config_json,
            field_path,
            normalized_value,
        )
        config_dict_to_policy(
            updated_config,
            version=str(baseline_envelope.version + 1),
            status=PolicyStatus.PREVIEW,
        )

        delta = PolicyDelta(
            policy_type=policy_type,
            field_path=field_path,
            current_value=current_value,
            proposed_value=normalized_value,
            reasoning=reasoning.strip(),
            confidence=confidence,
            evidence_count=evidence_count,
            baseline_hash=baseline_envelope.config_hash,
            baseline_version=baseline_envelope.version,
            proposed_by=actor,
            field_bound=field_bound,
            required_guards=required_guards,
        )
        created = self.learning_store.create_delta(delta)
        if promote_to_shadow:
            return self.promote_to_shadow(created.delta_id, actor=actor)
        return created

    def promote_to_shadow(
        self,
        delta_id: UUID,
        *,
        actor: str,
        reason: str | None = None,
    ) -> PolicyDelta:
        """Run PROMOTE_SHADOW guard checks, transition PROPOSED -> SHADOW, and save PREVIEW policy."""
        delta = self.learning_store.get_delta(delta_id)
        if delta is None:
            raise KeyError(f"Policy delta {delta_id} not found")

        _, baseline_envelope = self.get_active_baseline(delta.policy_type)
        baseline_fresh = delta.baseline_hash == baseline_envelope.config_hash
        if not baseline_fresh:
            raise ValueError(
                "Policy delta baseline hash does not match current active policy; "
                "re-propose against the latest revision"
            )

        preview_policy = self.build_candidate_policy(delta)
        bounds_ok = True
        if (
            delta.field_bound is not None
            and isinstance(delta.current_value, (int, float))
            and isinstance(delta.proposed_value, (int, float))
        ):
            bounds_ok = delta.field_bound.allows(
                current_value=float(delta.current_value),
                proposed_value=float(delta.proposed_value),
            )

        checks: dict[str, Any] = {
            "bounds": bounds_ok,
            "schema_valid": True,
            "baseline_fresh": baseline_fresh,
        }
        for req_guard in delta.required_guards:
            checks.setdefault(req_guard, bounds_ok and baseline_fresh)

        guard = GuardResult(
            candidate_hash=delta.candidate_hash,
            stage=GuardStage.PROMOTE_SHADOW,
            allowed=bounds_ok and baseline_fresh,
            reason=None
            if (bounds_ok and baseline_fresh)
            else DeltaRejectionReason.DELTA_OUT_OF_BOUNDS,
            checks=checks,
        )
        if guard.is_blocking:
            raise ValueError("Blocking guard prevents transition")
        if delta.required_guards and any(
            guard.checks.get(g) is not True for g in delta.required_guards
        ):
            raise ValueError("Required guards must pass")

        # Validate state transition in-memory before persisting PREVIEW policy
        delta.transition_to(
            DeltaState.SHADOW,
            actor=actor,
            reason=reason or "Promoted to SHADOW for PREVIEW evaluation",
            guard_stage=guard.stage,
            shadow_evaluation_id=delta.shadow_evaluation_id,
        )

        # Persist PREVIEW candidate policy in SQLAlchemyPolicyStore first
        save_result = self.policy_store.save_policy(preview_policy)

        try:
            transitioned = self.learning_store.transition_delta(
                delta_id,
                DeltaState.SHADOW,
                actor=actor,
                reason=reason or "Promoted to SHADOW for PREVIEW evaluation",
                guard_result=guard,
                binding_updates={"preview_policy_id": str(save_result.policy_id)},
            )

            # Initialize PENDING shadow aggregate if none exists yet
            if self.learning_store.get_shadow_aggregate(delta_id) is None:
                initial_aggregate = ShadowEvaluationAggregate(
                    delta_id=delta_id,
                    baseline_hash=transitioned.baseline_hash,
                    candidate_hash=transitioned.candidate_hash,
                    evaluated_by=self.evaluator_id,
                    total_decisions=0,
                    improved_decisions=0,
                    degraded_decisions=0,
                    neutral_decisions=0,
                    win_rate=0.0,
                    min_sample_met=False,
                    accuracy_threshold_met=False,
                    status=ShadowStatus.PENDING,
                )
                self.learning_store.persist_shadow_aggregate(initial_aggregate)
                transitioned = self.learning_store.get_delta(delta_id) or transitioned
        except Exception:
            if save_result.created:
                self.policy_store.retire_policy_by_id(save_result.policy_id)
            raise

        return transitioned

    def approve_to_draft(
        self,
        delta_id: UUID,
        *,
        actor: str,
        reason: str | None = None,
    ) -> tuple[PolicyDelta, PolicySaveResult, NotificationPolicy]:
        """Verify shadow evidence and baseline hash, approve SHADOW -> APPROVED, and persist DRAFT policy."""
        delta = self.learning_store.get_delta(delta_id)
        if delta is None:
            raise KeyError(f"Policy delta {delta_id} not found")

        _, baseline_envelope = self.get_active_baseline(delta.policy_type)
        if (
            delta.baseline_hash != baseline_envelope.config_hash
            or delta.baseline_version != baseline_envelope.version
        ):
            raise ValueError(
                "Policy delta baseline hash/version is stale against the current active policy"
            )

        aggregate = self.learning_store.get_shadow_aggregate(delta_id)
        if aggregate is None or not aggregate.can_promote_to_approval:
            raise ValueError("Shadow evaluation must pass before approval")
        if (
            not delta.baseline_hash
            or not aggregate.evaluated_by
            or aggregate.baseline_hash != delta.baseline_hash
            or aggregate.candidate_hash != delta.candidate_hash
        ):
            raise ValueError("Shadow candidate and baseline evidence must match the exact proposal")

        checks: dict[str, Any] = {
            "bounds": True,
            "schema_valid": True,
            "shadow_passed": aggregate.can_promote_to_approval,
            "baseline_fresh": True,
        }
        for req_guard in delta.required_guards:
            checks.setdefault(req_guard, True)

        guard = GuardResult(
            candidate_hash=delta.candidate_hash,
            stage=GuardStage.APPROVE,
            allowed=True,
            checks=checks,
        )
        approved_preview = delta.transition_to(
            DeltaState.APPROVED,
            actor=actor,
            reason=reason or "Shadow evaluation passed; approved into DRAFT",
            guard_stage=guard.stage,
            shadow_evaluation_id=delta.shadow_evaluation_id,
        )
        draft_envelope = apply_policy_delta(baseline_envelope, approved_preview, actor=actor)
        draft_policy = envelope_to_policy(draft_envelope, status=PolicyStatus.DRAFT)
        save_result = self.policy_store.save_policy(draft_policy)

        try:
            approved = self.learning_store.transition_delta(
                delta_id,
                DeltaState.APPROVED,
                actor=actor,
                reason=reason or "Shadow evaluation passed; approved into DRAFT",
                guard_result=guard,
                binding_updates={
                    "draft_policy_id": str(save_result.policy_id),
                    "draft_content_hash": save_result.content_hash,
                    "approved_candidate_config": draft_envelope.config_json,
                    "approved_candidate_version": draft_policy.version,
                },
            )
        except Exception:
            if save_result.created:
                self.policy_store.retire_policy_by_id(save_result.policy_id)
            raise
        return approved, save_result, draft_policy

    def activate_draft(
        self,
        *,
        actor: str,
        delta_id: UUID | None = None,
        policy_id: UUID | None = None,
        notification_type: str | None = None,
        reason: str | None = None,
    ) -> tuple[PolicySaveResult, NotificationPolicy, PolicyDelta | None]:
        """Explicitly promote a DRAFT policy revision to ACTIVE and mark linked delta APPLIED."""
        target_policy: NotificationPolicy | None = None
        linked_delta: PolicyDelta | None = None

        if delta_id is not None:
            linked_delta = self.learning_store.get_delta(delta_id)
            if linked_delta is None:
                raise KeyError(f"Policy delta {delta_id} not found")
            if linked_delta.state != DeltaState.APPROVED:
                raise ValueError(
                    f"Only APPROVED deltas can be activated (current state: {linked_delta.state.value})"
                )
            notification_type = linked_delta.policy_type
            _, baseline_envelope = self.get_active_baseline(linked_delta.policy_type)
            if (
                linked_delta.baseline_hash != baseline_envelope.config_hash
                or linked_delta.baseline_version != baseline_envelope.version
            ):
                raise ValueError(
                    "Active baseline policy drifted after approval; cannot activate stale DRAFT"
                )
            expected_envelope = apply_policy_delta(baseline_envelope, linked_delta, actor=actor)
            expected_policy = envelope_to_policy(expected_envelope, status=PolicyStatus.DRAFT)
            expected_candidate_hash = compute_config_hash(
                policy_to_config_dict(expected_policy, linked_delta.policy_type)
            )
            if policy_id is not None:
                found = self.policy_store.get_policy_by_id(policy_id)
                if found is None:
                    raise KeyError(f"Policy revision {policy_id} not found")
                row, hydrated = found
                if row.status != PolicyStatus.DRAFT.value:
                    raise ValueError(
                        f"Only DRAFT policy revisions can be promoted to ACTIVE (current status: {row.status})"
                    )
                hydrated_hash = compute_config_hash(
                    policy_to_config_dict(hydrated, linked_delta.policy_type)
                )
                if hydrated_hash != expected_candidate_hash:
                    raise ValueError(
                        "Specified DRAFT policy revision does not match the approved proposal candidate"
                    )
                target_policy = hydrated
            else:
                draft_revs = self.policy_store.list_revisions(
                    notification_type=linked_delta.policy_type,
                    status=PolicyStatus.DRAFT,
                    limit=20,
                )
                for _row, hydrated in draft_revs:
                    hydrated_hash = compute_config_hash(
                        policy_to_config_dict(hydrated, linked_delta.policy_type)
                    )
                    if hydrated_hash == expected_candidate_hash:
                        target_policy = hydrated
                        break
                if target_policy is None:
                    target_policy = expected_policy
        elif policy_id is not None:
            found = self.policy_store.get_policy_by_id(policy_id)
            if found is None:
                raise KeyError(f"Policy revision {policy_id} not found")
            row, hydrated = found
            if row.status != PolicyStatus.DRAFT.value:
                raise ValueError(
                    f"Only DRAFT policy revisions can be promoted to ACTIVE (current status: {row.status})"
                )
            target_policy = hydrated
            notification_type = hydrated.notification_type
        elif notification_type is not None:
            draft_revs = self.policy_store.list_revisions(
                notification_type=notification_type,
                status=PolicyStatus.DRAFT,
                limit=1,
            )
            if draft_revs:
                target_policy = draft_revs[0][1]

        if target_policy is None:
            raise ValueError("No DRAFT policy revision found to activate")

        if linked_delta is None and notification_type is not None:
            target_candidate_hash = compute_config_hash(
                policy_to_config_dict(target_policy, notification_type)
            )
            approved_deltas = self.learning_store.list_deltas(
                policy_type=notification_type,
                state=DeltaState.APPROVED,
                limit=50,
            )
            for candidate_delta in approved_deltas:
                if candidate_delta.candidate_hash == target_candidate_hash:
                    linked_delta = candidate_delta
                    break

        apply_guard: GuardResult | None = None
        if linked_delta is not None:
            _, baseline_envelope = self.get_active_baseline(linked_delta.policy_type)
            if (
                linked_delta.baseline_hash != baseline_envelope.config_hash
                or linked_delta.baseline_version != baseline_envelope.version
            ):
                raise ValueError(
                    "Active baseline policy drifted after approval; cannot activate stale DRAFT"
                )
            checks = {
                "bounds": True,
                "schema_valid": True,
                "baseline_fresh": True,
                "draft_activated": True,
            }
            for req_guard in linked_delta.required_guards:
                checks.setdefault(req_guard, True)
            apply_guard = GuardResult(
                candidate_hash=linked_delta.candidate_hash,
                stage=GuardStage.APPLY,
                allowed=True,
                checks=checks,
            )
            linked_delta.transition_to(
                DeltaState.APPLIED,
                actor=actor,
                reason=reason or f"Activated DRAFT revision v{target_policy.version} to ACTIVE",
                guard_stage=apply_guard.stage,
                shadow_evaluation_id=linked_delta.shadow_evaluation_id,
            )

        active_policy = target_policy.model_copy(update={"status": PolicyStatus.ACTIVE})
        save_result = self.policy_store.save_policy(active_policy)
        if notification_type is not None:
            self.policy_store.retire_candidate_revisions(
                notification_type,
                statuses=(PolicyStatus.DRAFT,),
            )

        applied_delta: PolicyDelta | None = None
        if linked_delta is not None and apply_guard is not None:
            applied_delta = self.learning_store.transition_delta(
                linked_delta.delta_id,
                DeltaState.APPLIED,
                actor=actor,
                reason=reason or f"Activated DRAFT revision v{active_policy.version} to ACTIVE",
                guard_result=apply_guard,
                binding_updates={"activated_policy_id": str(save_result.policy_id)},
            )

        return save_result, active_policy, applied_delta

    def reject_delta(
        self,
        delta_id: UUID,
        *,
        actor: str,
        reason: str | DeltaRejectionReason = "Rejected by operator",
    ) -> PolicyDelta:
        """Reject a policy delta proposal and retire any non-ACTIVE candidate revisions."""
        delta = self.learning_store.get_delta(delta_id)
        if delta is None:
            raise KeyError(f"Policy delta {delta_id} not found")

        rejected = self.learning_store.transition_delta(
            delta_id,
            DeltaState.REJECTED,
            actor=actor,
            reason=reason,
        )
        # Retire any PREVIEW or DRAFT candidate revisions if no other active SHADOW/APPROVED delta exists
        remaining_active = [
            d
            for d in self.learning_store.list_deltas(policy_type=delta.policy_type)
            if d.delta_id != delta_id and d.state in (DeltaState.SHADOW, DeltaState.APPROVED)
        ]
        if not remaining_active:
            self.policy_store.retire_candidate_revisions(delta.policy_type)
        return rejected

    def inspect_delta_status(self, delta: PolicyDelta) -> dict[str, Any]:
        """Compute baseline verification, shadow aggregate, and action eligibility for a delta."""
        _, baseline_envelope = self.get_active_baseline(delta.policy_type)
        current_active_hash = baseline_envelope.config_hash or compute_config_hash(
            baseline_envelope.config_json
        )
        current_active_version = baseline_envelope.version
        baseline_hash_matches = (
            delta.baseline_hash == current_active_hash
            and delta.baseline_version == current_active_version
        )
        aggregate = self.learning_store.get_shadow_aggregate(delta.delta_id)
        candidate_hash = delta.candidate_hash
        evidence_hash_matches = (
            aggregate is not None
            and aggregate.baseline_hash == delta.baseline_hash
            and aggregate.candidate_hash == candidate_hash
        )
        can_promote_to_shadow = delta.state == DeltaState.PROPOSED and baseline_hash_matches
        can_approve = (
            delta.state == DeltaState.SHADOW
            and baseline_hash_matches
            and aggregate is not None
            and aggregate.can_promote_to_approval
            and evidence_hash_matches
        )
        draft_revs = self.policy_store.list_revisions(
            notification_type=delta.policy_type,
            status=PolicyStatus.DRAFT,
            limit=1,
        )
        draft_policy_id = str(draft_revs[0][0].policy_id) if draft_revs else None
        draft_version = draft_revs[0][0].version if draft_revs else None
        can_activate = delta.state == DeltaState.APPROVED and baseline_hash_matches
        return {
            "current_active_hash": current_active_hash,
            "current_active_version": current_active_version,
            "baseline_hash_matches": baseline_hash_matches,
            "candidate_hash": candidate_hash,
            "evidence_hash_matches": evidence_hash_matches,
            "can_promote_to_shadow": can_promote_to_shadow,
            "can_approve": can_approve,
            "can_activate": can_activate,
            "draft_policy_id": draft_policy_id,
            "draft_version": draft_version,
            "shadow_aggregate": aggregate,
        }

    def format_proposal_summary(
        self,
        delta: PolicyDelta,
        *,
        include_samples: bool = False,
        sample_limit: int = 25,
    ) -> PolicyProposalSummary:
        """Convert a PolicyDelta and its shadow/guard evidence into a PolicyProposalSummary DTO."""
        info = self.inspect_delta_status(delta)
        agg = info["shadow_aggregate"]
        agg_item: ShadowEvaluationSummaryItem | None = None
        if agg is not None:
            agg_item = ShadowEvaluationSummaryItem(
                aggregate_id=agg.aggregate_id,
                delta_id=agg.delta_id,
                baseline_hash=agg.baseline_hash,
                candidate_hash=agg.candidate_hash,
                evaluated_by=agg.evaluated_by,
                total_decisions=agg.total_decisions,
                improved_decisions=agg.improved_decisions,
                degraded_decisions=agg.degraded_decisions,
                neutral_decisions=agg.neutral_decisions,
                win_rate=agg.win_rate,
                min_sample_met=agg.min_sample_met,
                accuracy_threshold_met=agg.accuracy_threshold_met,
                status=agg.status.value,
                can_promote_to_approval=agg.can_promote_to_approval,
                computed_at=agg.computed_at,
            )

        samples: list[ShadowEvaluationSampleItem] = []
        if include_samples:
            raw_samples = self.learning_store.list_shadow_results(
                delta.delta_id, limit=sample_limit
            )
            samples = [
                ShadowEvaluationSampleItem(
                    result_id=item.result_id,
                    delta_id=item.delta_id,
                    decision_id=item.decision_id,
                    original_outcome=item.original_outcome,
                    shadow_outcome=item.shadow_outcome,
                    changed=item.changed,
                    improvement_score=item.improvement_score,
                    evaluated_at=item.evaluated_at,
                )
                for item in raw_samples
            ]

        guard_items = [
            PolicyGuardResultItem(
                candidate_hash=g.candidate_hash,
                stage=g.stage.value,
                allowed=g.allowed,
                reason=g.reason.value if g.reason else None,
                reason_detail=g.reason_detail,
                checks=g.checks,
                checked_at=g.checked_at,
            )
            for g in delta.guard_results
        ]
        transition_items = [
            PolicyTransitionItem(
                from_state=t.from_state.value if t.from_state else None,
                to_state=t.to_state.value,
                actor=t.actor,
                reason=(t.reason.value if isinstance(t.reason, DeltaRejectionReason) else t.reason),
                guard_stage=t.guard_stage.value if t.guard_stage else None,
                transitioned_at=t.transitioned_at,
            )
            for t in delta.transition_history
        ]
        rejection_reason_str = (
            delta.rejection_reason.value
            if isinstance(delta.rejection_reason, DeltaRejectionReason)
            else delta.rejection_reason
        )

        return PolicyProposalSummary(
            delta_id=delta.delta_id,
            policy_type=delta.policy_type,
            field_path=delta.field_path,
            current_value=delta.current_value,
            proposed_value=delta.proposed_value,
            reasoning=delta.reasoning,
            confidence=delta.confidence,
            evidence_count=delta.evidence_count,
            state=delta.state.value,
            baseline_hash=delta.baseline_hash,
            baseline_version=delta.baseline_version,
            candidate_hash=info["candidate_hash"],
            approval_candidate_hash=delta.approval_candidate_hash,
            current_active_hash=info["current_active_hash"],
            current_active_version=info["current_active_version"],
            baseline_hash_matches=info["baseline_hash_matches"],
            evidence_hash_matches=info["evidence_hash_matches"],
            can_promote_to_shadow=info["can_promote_to_shadow"],
            can_approve=info["can_approve"],
            can_activate=info["can_activate"],
            draft_policy_id=info["draft_policy_id"],
            draft_version=info["draft_version"],
            required_guards=list(delta.required_guards),
            guard_results=guard_items,
            transition_history=transition_items,
            shadow_aggregate=agg_item,
            shadow_results=samples,
            proposed_by=delta.proposed_by,
            approved_by=delta.approved_by,
            rejected_by=delta.rejected_by,
            rejection_reason=rejection_reason_str,
            applied_at=delta.applied_at,
            created_at=delta.created_at,
            updated_at=delta.updated_at,
        )


def resolve_shadow_evaluator(app_state: Any) -> ShadowPolicyEvaluator | None:
    """Resolve ShadowPolicyEvaluator from FastAPI app.state or its attached Runtime."""
    evaluator = getattr(app_state, "shadow_evaluator", None)
    if isinstance(evaluator, ShadowPolicyEvaluator):
        return evaluator
    runtime = getattr(app_state, "runtime", None)
    if runtime is not None and hasattr(runtime, "shadow_evaluator"):
        return runtime.shadow_evaluator  # type: ignore[no-any-return]
    policy_store = getattr(app_state, "policy_store", None)
    learning_store = getattr(app_state, "learning_store", None)
    if isinstance(policy_store, SQLAlchemyPolicyStore):
        if not isinstance(learning_store, SQLAlchemyPolicyLearningStore):
            learning_store = SQLAlchemyPolicyLearningStore(policy_store._session_factory)
            app_state.learning_store = learning_store
        evaluator = ShadowPolicyEvaluator(policy_store, learning_store)
        app_state.shadow_evaluator = evaluator
        return evaluator
    return None

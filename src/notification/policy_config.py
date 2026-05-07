"""Domain-neutral policy config envelopes and evaluation records."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from notification.policies import PolicyStatus
from notification.policy_learning import DeltaState, PolicyDelta


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def canonical_config_json(config: dict[str, Any]) -> str:
    """Return canonical JSON for stable policy config hashing."""
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def compute_config_hash(config: dict[str, Any]) -> str:
    """Return a SHA-256 hash of canonical policy config JSON."""
    canonical = canonical_config_json(config)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PolicyConfigEnvelope(BaseModel):
    """Generic, hash-bearing envelope for a policy config payload."""

    config_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identifier for this config envelope",
    )
    policy_type: str = Field(description="Domain-neutral policy type identifier")
    version: int = Field(ge=0, description="Monotonic policy config version")
    status: PolicyStatus = Field(
        default=PolicyStatus.DRAFT,
        description="Policy config lifecycle status",
    )
    schema_version: str = Field(
        default="1",
        description="Schema version for config_json",
    )
    config_json: dict[str, Any] = Field(description="Policy config payload")
    config_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of canonical config_json",
    )
    source_delta_id: UUID | None = Field(
        default=None,
        description="Delta that produced this config version",
    )
    created_by: str = Field(description="Actor that created this config")
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="When this config was created",
    )
    activated_at: datetime | None = Field(
        default=None,
        description="When this config became ACTIVE",
    )
    retired_at: datetime | None = Field(
        default=None,
        description="When this config became RETIRED",
    )
    notes: str | None = Field(
        default=None,
        description="Human-readable notes for this config",
    )

    model_config = ConfigDict(frozen=True)

    def __getattribute__(self, name: str) -> Any:
        """Return defensive copies for nested mutable config payloads."""
        value = super().__getattribute__(name)
        if name == "config_json":
            return copy.deepcopy(value)
        return value

    @model_validator(mode="after")
    def validate_or_compute_hash(self) -> PolicyConfigEnvelope:
        """Validate caller-provided config_hash or compute it from config_json."""
        config = copy.deepcopy(self.config_json)
        computed_hash = compute_config_hash(config)
        if self.config_hash is not None and self.config_hash != computed_hash:
            raise ValueError("config_hash does not match config_json")
        object.__setattr__(self, "config_json", config)
        object.__setattr__(self, "config_hash", computed_hash)
        return self


class PolicyEvaluationRecord(BaseModel):
    """Auditable record of a policy evaluation against an exact config hash."""

    evaluation_id: UUID = Field(
        default_factory=uuid4,
        description="Stable evaluation record ID",
    )
    policy_type: str = Field(description="Policy type evaluated")
    config_id: UUID = Field(description="Config envelope evaluated")
    config_hash: str = Field(description="Exact config hash used for evaluation")
    decision: str = Field(description="Domain-neutral policy decision")
    evaluation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Inputs or context used for evaluation",
    )
    result: dict[str, Any] = Field(
        default_factory=dict,
        description="Policy evaluation output",
    )
    evaluated_at: datetime = Field(
        default_factory=_utc_now,
        description="When evaluation occurred",
    )

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_envelope(
        cls,
        envelope: PolicyConfigEnvelope,
        *,
        decision: str,
        evaluation_context: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> PolicyEvaluationRecord:
        """Create an evaluation record pinned to an envelope's config hash."""
        return cls(
            policy_type=envelope.policy_type,
            config_id=envelope.config_id,
            config_hash=envelope.config_hash or compute_config_hash(envelope.config_json),
            decision=decision,
            evaluation_context=evaluation_context or {},
            result=result or {},
        )


def apply_policy_delta(
    envelope: PolicyConfigEnvelope,
    delta: PolicyDelta,
    *,
    actor: str,
) -> PolicyConfigEnvelope:
    """Return a new draft envelope with an approved delta applied."""
    if delta.state != DeltaState.APPROVED:
        raise ValueError("Only APPROVED deltas can be applied to policy configs")
    if delta.policy_type != envelope.policy_type:
        raise ValueError(
            f"Delta {delta.delta_id} does not target policy type {envelope.policy_type}"
        )

    config = copy.deepcopy(envelope.config_json)
    _set_dotted_path(config, delta.field_path, delta.proposed_value)
    return PolicyConfigEnvelope(
        policy_type=envelope.policy_type,
        version=envelope.version + 1,
        status=PolicyStatus.DRAFT,
        schema_version=envelope.schema_version,
        config_json=config,
        source_delta_id=delta.delta_id,
        created_by=actor,
        notes=f"Applied delta {delta.delta_id}",
    )


def _set_dotted_path(config: dict[str, Any], field_path: str, value: Any) -> None:
    parts = field_path.split(".")
    if not parts or any(part == "" for part in parts):
        raise ValueError(f"Invalid field_path: {field_path}")

    cursor = config
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if next_value is None:
            next_value = {}
            cursor[part] = next_value
        if not isinstance(next_value, dict):
            raise ValueError(f"Cannot set nested field through non-object path: {field_path}")
        cursor = next_value
    cursor[parts[-1]] = copy.deepcopy(value)

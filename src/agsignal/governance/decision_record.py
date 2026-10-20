"""DecisionRecord schema and supporting types.

Per the amended Approval Workflow Semantics ADR, the schema is locked at v0.4
to avoid v0.5 breaking changes. 11 required fields + 11 optional fields.

correlation_id and trace_id are SEMANTICALLY DISTINCT:
- correlation_id: cross-AGSignal-stream forensic linkage
  (Decision + Approval + Delivery audit streams)
- trace_id: distributed-trace integration (W3C Trace Context / OpenTelemetry)

Populating one does NOT satisfy the other. They serve different consumers.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Decision(str, Enum):
    """The three possible decision outcomes per the Decision Engine ADR."""

    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class Reason(BaseModel):
    """Structured per-rule reason record per ADR Decision Engine Internal Shape.

    `reasons[]` on a DecisionRecord contains one Reason per rule that was
    evaluated, including non-matched rules. This enables "why was this denied?"
    forensic reconstruction predicate-by-predicate without re-running the
    engine.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Stable identifier for the rule")
    matched: bool = Field(..., description="True if the rule's `when` predicate matched")
    predicate: str = Field(..., description="String representation of the matched/evaluated predicate")
    then: Decision = Field(..., description="The rule's `then` clause outcome (only meaningful when matched=True)")


class RequestOrigin(BaseModel):
    """Structured request-origin per the amended DecisionRecord schema.

    Single-string origins (URLs, hostnames alone) are insufficient for forensic
    jurisdiction analysis. All fields are optional; populate what's available.
    """

    model_config = ConfigDict(extra="forbid")

    ip: str | None = None
    hostname: str | None = None
    region: str | None = None
    jurisdiction: str | None = None


class DecisionRecord(BaseModel):
    """The canonical return type from `decide()` and `evaluate()`.

    Schema locked at v0.4 to avoid v0.5 breaking changes. 11 required fields +
    11 optional fields. See the amended Approval Workflow Semantics ADR for the
    full rationale + field-level ACs.

    Required fields are always populated, including in single-tenant non-traced
    deployments. Optional fields are None when not applicable; SHOULD be
    populated when context permits.
    """

    model_config = ConfigDict(extra="forbid")

    # === Required ===

    decision_id: UUID = Field(..., description="Deterministic, idempotency key for resume")
    policy_config_hash: str = Field(..., description="Hash of the GovernancePolicy YAML at evaluation time")
    policy_id: str = Field(..., description="Human-readable policy identifier")
    policy_version: str = Field(..., description="Semantic version of the policy")
    engine_version: str = Field(..., description="Semver of evaluator implementation, distinct from policy_version")
    context_hash: str = Field(..., description="Hash of the context capsule (audit without storing raw context)")
    decision: Decision = Field(..., description="ALLOW | REQUIRE_APPROVAL | DENY")
    reasons: list[Reason] = Field(..., description="Structured per-rule trace including non-matched rules")
    evaluated_at: datetime = Field(..., description="RFC 3339, UTC")
    schema_version: str = Field(..., description="DecisionRecord schema version, separate from policy/engine version")
    subject_id: str = Field(..., description="Who initiated the request (resolved via IdentityProvider hook)")

    # === Optional ===

    correlation_id: str | None = Field(None, description="Cross-AGSignal-stream forensic linkage")
    trace_id: str | None = Field(None, description="Distributed-trace integration (W3C Trace Context); distinct from correlation_id")
    span_id: str | None = Field(None, description="Sub-trace causal node")
    parent_span_id: str | None = Field(None, description="Trace tree reconstruction")
    tenant_id: str | None = Field(None, description="Multi-tenant scoping (org_id / account_id alias acceptable)")
    resource_id: str | None = Field(None, description="What the decision was about (model / tool / file / account / transaction)")
    resource_type: str | None = Field(None, description="Taxonomy of resource_id")
    parent_decision_id: str | None = Field(None, description="Replay/re-evaluation chain (NOT correlation_id; semantically distinct)")
    request_origin: RequestOrigin | None = Field(None, description="Structured: ip, hostname, region, jurisdiction")
    model_id: str | None = Field(None, description="AI provenance — model identifier (when agent provenance is recorded)")
    model_version: str | None = Field(None, description="Paired with model_id")

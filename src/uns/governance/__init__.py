"""UNS governance — Opt-in Pre-Execution Decision Engine, Policy DSL, ContextSchema & Approval Bridge.

Exposes the deterministic pre-execution governance primitives (`decide`, `DecisionEngine`,
`ContextSchema`, `Policy`, `DecisionRecord`) and the obligation-backed
`GovernanceApprovalBridge` (`ALLOW` / `REQUIRE_APPROVAL` / `DENY` wired to durable
`uns.Runtime` notification obligations and HMAC-SHA256 signed resume callbacks).
"""

from __future__ import annotations

from uns.governance.approval_workflow import (
    ApprovalRequestRecord,
    ApprovalStatus,
    GovernanceApprovalBridge,
    sign_approval_callback,
    verify_approval_callback,
)
from uns.governance.context_schema import (
    ContextSchema,
    compute_context_hash,
    parse_field_path,
    resolve_field_path,
    validate_context_capsule,
    validate_policy_against_schema,
)
from uns.governance.decision_engine import (
    DECISION_RECORD_SCHEMA_VERSION,
    DecisionEngine,
    EvaluationOutcome,
    FailModeType,
    decide,
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
from uns.governance.operators import (
    REGEX_PATTERN_LENGTH_CAP,
    Operator,
    evaluate_operator,
    parse_operator,
)
from uns.governance.policy_dsl import (
    Condition,
    Policy,
    Rule,
    ThenClause,
)
from uns.governance.policy_loader import (
    compute_policy_config_hash,
    load_policy_from_yaml,
)

__all__ = [
    "DECISION_RECORD_SCHEMA_VERSION",
    "REGEX_PATTERN_LENGTH_CAP",
    "ApprovalRequestRecord",
    "ApprovalStatus",
    "Condition",
    "ContextSchema",
    "ContextSchemaViolation",
    "Decision",
    "DecisionEngine",
    "DecisionRecord",
    "EngineFailure",
    "EvaluationOutcome",
    "FailModeType",
    "GovernanceApprovalBridge",
    "GovernanceError",
    "MissingFieldError",
    "Operator",
    "Policy",
    "PolicyEvaluationError",
    "PolicyLoadError",
    "Reason",
    "RequestOrigin",
    "Rule",
    "ThenClause",
    "compute_context_hash",
    "compute_policy_config_hash",
    "decide",
    "evaluate_operator",
    "load_policy_from_yaml",
    "parse_field_path",
    "parse_operator",
    "resolve_field_path",
    "sign_approval_callback",
    "validate_context_capsule",
    "validate_policy_against_schema",
    "verify_approval_callback",
]

"""Typed exceptions for the governance engine.

Per ADR Decision Engine Internal Shape: decide() raises typed exceptions for
context-schema mismatch, malformed policy at evaluate-time, and predicate
evaluation failures. evaluate() catches these and translates per fail-mode
(ADR Fail-mode Semantics).

This module is the single source of truth for governance-error types; downstream
code MUST NOT raise bare `Exception` or `ValueError` from the governance path.
"""

from __future__ import annotations


class GovernanceError(Exception):
    """Base class for all governance engine errors.

    Caught by evaluate() at the engine boundary; translated per fail-mode.
    """


class PolicyLoadError(GovernanceError):
    """Raised when policy YAML fails to parse, contains an operator outside
    the allowlist, or references a field not in the registered ContextSchema.

    Raised at policy-load time (before any evaluation). When a policy fails to
    load, the prior version remains active per hot-reload last-known-good
    semantics (ADR Fail-mode Semantics §6).
    """


class PolicyEvaluationError(GovernanceError):
    """Raised when a policy evaluation fails at decide()-time.

    Examples: operator type mismatch, regex compile failure (defense in depth;
    should be caught at load), arithmetic on incompatible types.
    """

    def __init__(
        self,
        message: str,
        rule_id: str | None = None,
        predicate: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.predicate = predicate

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.rule_id is not None:
            parts.append(f"rule_id={self.rule_id}")
        if self.predicate is not None:
            parts.append(f"predicate={self.predicate}")
        return " | ".join(parts)


class ContextSchemaViolation(GovernanceError):  # noqa: N818 - retained public exception name
    """Raised when a context capsule fails ContextSchema validation at
    evaluate-time, or when a policy field reference is not in the registered
    ContextSchema at policy-load time.
    """

    def __init__(
        self,
        message: str,
        field_path: str | None = None,
        schema_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field_path = field_path
        self.schema_name = schema_name


class MissingFieldError(ContextSchemaViolation):
    """Specialization of ContextSchemaViolation for the case where a field is
    declared in the schema but missing from the evaluation-time context capsule.

    Distinct from "field not in schema" (which is also ContextSchemaViolation
    but a different category — that one is a policy-load error; this one is
    evaluate-time).
    """

    def __init__(self, field_path: str, schema_name: str | None = None) -> None:
        super().__init__(
            message=f"Required field {field_path!r} missing from context capsule",
            field_path=field_path,
            schema_name=schema_name,
        )


class EngineFailure(GovernanceError):  # noqa: N818 - retained public exception name
    """Catch-all for engine-internal failures not classified above
    (e.g., evaluation timeout, attribute-source plugin error, unexpected
    exception inside decide()). Triggers fail-mode per ADR Fail-mode Semantics.
    """

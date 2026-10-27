"""Tests for typed governance engine exceptions."""


from uns.governance.errors import (
    ContextSchemaViolation,
    EngineFailure,
    GovernanceError,
    MissingFieldError,
    PolicyEvaluationError,
    PolicyLoadError,
)


def test_governance_error_is_base_class():
    assert issubclass(PolicyLoadError, GovernanceError)
    assert issubclass(PolicyEvaluationError, GovernanceError)
    assert issubclass(ContextSchemaViolation, GovernanceError)
    assert issubclass(MissingFieldError, GovernanceError)
    assert issubclass(EngineFailure, GovernanceError)


def test_policy_evaluation_error_carries_rule_context():
    err = PolicyEvaluationError(
        message="Operator EQ comparison failed",
        rule_id="high_notional",
        predicate="notional_usd EQ 'string'",
    )
    assert err.rule_id == "high_notional"
    assert "high_notional" in str(err)


def test_context_schema_violation_carries_field_path():
    err = ContextSchemaViolation(
        message="Field 'unknown_field' not in registered ContextSchema",
        field_path="order.unknown_field",
        schema_name="trading",
    )
    assert err.field_path == "order.unknown_field"
    assert err.schema_name == "trading"


def test_missing_field_error_is_schema_violation():
    """Missing-field at evaluate-time is a ContextSchemaViolation subtype."""
    err = MissingFieldError(field_path="order.notional_usd", schema_name="trading")
    assert isinstance(err, ContextSchemaViolation)

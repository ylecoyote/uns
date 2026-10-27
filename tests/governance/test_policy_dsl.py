"""Tests for Policy / Rule / Condition / ThenClause Pydantic models."""

import pytest
from pydantic import ValidationError

from uns.governance.decision_record import Decision
from uns.governance.operators import Operator
from uns.governance.policy_dsl import (
    Condition,
    Policy,
    Rule,
    ThenClause,
)


class TestCondition:
    def test_basic_condition(self):
        c = Condition(field="notional_usd", operator=Operator.GT, value=1000000)
        assert c.field == "notional_usd"
        assert c.operator == Operator.GT
        assert c.value == 1000000

    def test_condition_serializes(self):
        c = Condition(field="symbol", operator=Operator.IN, value=["AAPL", "MSFT"])
        d = c.model_dump()
        assert d["operator"] == "IN"
        assert d["value"] == ["AAPL", "MSFT"]


class TestThenClause:
    def test_then_clause_with_reason(self):
        t = ThenClause(decision=Decision.REQUIRE_APPROVAL, reason="High notional")
        assert t.decision == Decision.REQUIRE_APPROVAL
        assert t.reason == "High notional"

    def test_then_clause_without_reason(self):
        t = ThenClause(decision=Decision.ALLOW)
        assert t.reason is None


class TestRule:
    def test_rule_with_single_condition(self):
        r = Rule(
            id="high_notional",
            when=[Condition(field="notional_usd", operator=Operator.GT, value=1000000)],
            then=ThenClause(decision=Decision.REQUIRE_APPROVAL, reason="High notional"),
        )
        assert r.id == "high_notional"
        assert len(r.when) == 1
        assert r.priority is None  # priority is optional

    def test_rule_with_priority(self):
        r = Rule(
            id="urgent",
            when=[Condition(field="urgent", operator=Operator.EQ, value=True)],
            then=ThenClause(decision=Decision.DENY),
            priority=100,
        )
        assert r.priority == 100

    def test_rule_with_multiple_conditions_implicit_and(self):
        # Multiple conditions in `when` are AND-joined per ADR
        r = Rule(
            id="multi",
            when=[
                Condition(field="notional_usd", operator=Operator.GT, value=1000000),
                Condition(field="symbol", operator=Operator.NOT_IN, value=["VTI", "VOO"]),
            ],
            then=ThenClause(decision=Decision.REQUIRE_APPROVAL),
        )
        assert len(r.when) == 2

    def test_rule_rejects_empty_when(self):
        # ADR requires at least one condition; an empty `when` is structurally invalid
        with pytest.raises(ValidationError):
            Rule(
                id="bad",
                when=[],
                then=ThenClause(decision=Decision.ALLOW),
            )


class TestPolicy:
    def test_policy_with_single_rule(self):
        p = Policy(
            id="trade-approval",
            version="1.0",
            rules=[
                Rule(
                    id="r1",
                    when=[Condition(field="notional_usd", operator=Operator.GT, value=1_000_000)],
                    then=ThenClause(decision=Decision.REQUIRE_APPROVAL),
                ),
            ],
            context_schema="trading",
        )
        assert p.id == "trade-approval"
        assert len(p.rules) == 1

    def test_policy_default_no_match_is_deny(self):
        # Per ADR Decision Engine Internal Shape: deny-by-default no-match
        p = Policy(
            id="p",
            version="1.0",
            rules=[
                Rule(
                    id="r1",
                    when=[Condition(field="x", operator=Operator.EQ, value=1)],
                    then=ThenClause(decision=Decision.ALLOW),
                ),
            ],
            context_schema="trading",
        )
        # default is None, semantically meaning DENY-by-default; explicit catchall
        # if author wants different behavior
        assert p.default_decision is None

    def test_policy_explicit_default_decision(self):
        p = Policy(
            id="p",
            version="1.0",
            rules=[],
            context_schema="trading",
            default_decision=Decision.ALLOW,
        )
        assert p.default_decision == Decision.ALLOW

    def test_policy_rejects_duplicate_rule_ids(self):
        with pytest.raises(ValidationError) as exc:
            Policy(
                id="p",
                version="1.0",
                context_schema="trading",
                rules=[
                    Rule(id="dup", when=[Condition(field="x", operator=Operator.EQ, value=1)], then=ThenClause(decision=Decision.ALLOW)),
                    Rule(id="dup", when=[Condition(field="y", operator=Operator.EQ, value=2)], then=ThenClause(decision=Decision.DENY)),
                ],
            )
        assert "dup" in str(exc.value).lower() or "unique" in str(exc.value).lower()

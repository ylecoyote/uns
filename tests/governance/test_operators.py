"""Tests for the operator allowlist and evaluation."""

import pytest

from uns.governance.errors import PolicyEvaluationError, PolicyLoadError
from uns.governance.operators import Operator, evaluate_operator, parse_operator


class TestOperatorEnum:
    def test_all_allowed_operators(self):
        expected = {
            "EQ", "NEQ", "GT", "GTE", "LT", "LTE",
            "IN", "NOT_IN", "EXISTS", "NOT_EXISTS", "MATCHES",
        }
        assert {op.value for op in Operator} == expected

    def test_parse_operator_rejects_unknown(self):
        with pytest.raises(PolicyLoadError) as exc:
            parse_operator("CONTAINS")
        assert "CONTAINS" in str(exc.value)
        assert "allowlist" in str(exc.value).lower()

    def test_parse_operator_accepts_known(self):
        assert parse_operator("EQ") == Operator.EQ
        assert parse_operator("MATCHES") == Operator.MATCHES


class TestEvaluateOperator:
    def test_eq_numeric(self):
        assert evaluate_operator(Operator.EQ, 5, 5) is True
        assert evaluate_operator(Operator.EQ, 5, 6) is False

    def test_eq_string(self):
        assert evaluate_operator(Operator.EQ, "AAPL", "AAPL") is True

    def test_neq(self):
        assert evaluate_operator(Operator.NEQ, 5, 6) is True
        assert evaluate_operator(Operator.NEQ, 5, 5) is False

    def test_gt_lt_gte_lte(self):
        assert evaluate_operator(Operator.GT, 10, 5) is True
        assert evaluate_operator(Operator.LT, 5, 10) is True
        assert evaluate_operator(Operator.GTE, 5, 5) is True
        assert evaluate_operator(Operator.LTE, 5, 5) is True

    def test_in_not_in(self):
        assert evaluate_operator(Operator.IN, "AAPL", ["AAPL", "MSFT"]) is True
        assert evaluate_operator(Operator.IN, "GOOG", ["AAPL", "MSFT"]) is False
        assert evaluate_operator(Operator.NOT_IN, "GOOG", ["AAPL", "MSFT"]) is True

    def test_exists_not_exists(self):
        # Sentinel: missing fields surface as MISSING_FIELD; EXISTS evaluates accordingly
        assert evaluate_operator(Operator.EXISTS, "anything", None) is True
        assert evaluate_operator(Operator.EXISTS, None, None) is False
        assert evaluate_operator(Operator.NOT_EXISTS, None, None) is True

    def test_matches_regex_re2_anchored(self):
        # MATCHES is fully anchored per ADR (RE2 syntax)
        assert evaluate_operator(Operator.MATCHES, "trade.execute", r"trade\.[a-z]+") is True
        # NOT anchored at end => fails because RE2 anchors fullmatch
        assert evaluate_operator(Operator.MATCHES, "trade.execute_now", r"trade\.[a-z]+") is False

    def test_matches_caps_regex_complexity(self):
        # ReDoS defense in depth: pathological pattern length cap
        long_pattern = "a" * 5000
        with pytest.raises(PolicyEvaluationError) as exc:
            evaluate_operator(Operator.MATCHES, "x", long_pattern)
        assert "regex" in str(exc.value).lower()

    def test_type_mismatch_raises(self):
        # Comparing string to int with GT raises typed evaluation error
        with pytest.raises(PolicyEvaluationError) as exc:
            evaluate_operator(Operator.GT, "string", 5)
        assert "type" in str(exc.value).lower() or "compar" in str(exc.value).lower()

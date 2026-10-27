"""Tests for the DecisionRecord Pydantic model and supporting types."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from uns.governance.decision_record import (
    Decision,
    DecisionRecord,
    Reason,
    RequestOrigin,
)


class TestDecisionEnum:
    def test_decision_has_three_values(self):
        assert {d.value for d in Decision} == {"ALLOW", "REQUIRE_APPROVAL", "DENY"}


class TestReason:
    def test_reason_construction(self):
        r = Reason(
            rule_id="high_notional",
            matched=True,
            predicate="notional_usd GT 1000000",
            then=Decision.REQUIRE_APPROVAL,
        )
        assert r.rule_id == "high_notional"
        assert r.matched is True
        assert r.then == Decision.REQUIRE_APPROVAL

    def test_reason_serializes_to_json(self):
        r = Reason(
            rule_id="r1",
            matched=False,
            predicate="symbol IN ['AAPL']",
            then=Decision.ALLOW,
        )
        as_dict = r.model_dump()
        assert as_dict["rule_id"] == "r1"
        assert as_dict["matched"] is False


class TestRequestOrigin:
    def test_request_origin_optional_fields(self):
        ro = RequestOrigin(ip="10.0.0.1", region="us-east-1")
        assert ro.ip == "10.0.0.1"
        assert ro.hostname is None  # all fields optional


class TestDecisionRecord:
    def _required_fields(self) -> dict:
        return {
            "decision_id": uuid.uuid4(),
            "policy_config_hash": "sha256:abc123",
            "policy_id": "trade-approval",
            "policy_version": "3.2.1",
            "engine_version": "0.4.0",
            "context_hash": "sha256:def456",
            "decision": Decision.ALLOW,
            "reasons": [],
            "evaluated_at": datetime.now(timezone.utc),
            "schema_version": "0.4",
            "subject_id": "agent-123",
        }

    def test_decision_record_with_only_required_fields(self):
        dr = DecisionRecord(**self._required_fields())
        assert dr.decision == Decision.ALLOW
        # All optional fields default to None
        assert dr.correlation_id is None
        assert dr.trace_id is None
        assert dr.tenant_id is None
        assert dr.parent_decision_id is None

    def test_decision_record_rejects_missing_required_field(self):
        fields = self._required_fields()
        del fields["subject_id"]
        with pytest.raises(ValidationError) as exc:
            DecisionRecord(**fields)
        assert "subject_id" in str(exc.value)

    def test_decision_record_with_all_optional_fields(self):
        fields = self._required_fields()
        fields.update(
            {
                "correlation_id": "trace-business-1",
                "trace_id": "00-1234567890abcdef-1234567890abcdef-01",
                "span_id": "1234567890abcdef",
                "parent_span_id": "fedcba0987654321",
                "tenant_id": "tenant-acme",
                "resource_id": "trade-789",
                "resource_type": "trade.execution",
                "parent_decision_id": "01939c2a-7e10-7d3c-9a4f-3b8a4f5e6d7c",
                "request_origin": RequestOrigin(ip="10.0.0.1", region="us-east-1"),
                "model_id": "gpt-4-turbo",
                "model_version": "2024-04-09",
            }
        )
        dr = DecisionRecord(**fields)
        assert dr.tenant_id == "tenant-acme"
        assert dr.request_origin.region == "us-east-1"

    def test_decision_record_serializes_to_json(self):
        dr = DecisionRecord(**self._required_fields())
        payload = dr.model_dump_json()
        assert "decision_id" in payload
        assert "ALLOW" in payload

    def test_decision_record_strict_mode_rejects_extra_fields(self):
        fields = self._required_fields()
        fields["unknown_field"] = "should be rejected"
        with pytest.raises(ValidationError) as exc:
            DecisionRecord(**fields)
        assert "unknown_field" in str(exc.value).lower() or "extra" in str(exc.value).lower()

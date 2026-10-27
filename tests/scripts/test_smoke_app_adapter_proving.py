"""Tests for the reusable UNS app adapter proving smoke."""

from __future__ import annotations

from uuid import uuid4

from scripts.smoke_app_adapter_proving import build_proving_request, run_smoke


def test_build_proving_request_uses_public_uns_shape() -> None:
    agent_id = uuid4()
    request = build_proving_request(agent_id)

    assert request.notification_type == "app.governor.circuit_breaker_engaged"
    assert request.title == "Circuit breaker engaged"
    assert request.evidence is not None
    assert request.evidence.decision_snapshot_id is not None


def test_run_smoke_returns_ack_audit_and_evidence_result() -> None:
    result = run_smoke()

    assert result["status"] == "SUCCESS"
    assert result["ack_status"] == "PENDING"
    assert result["delivery_audits"] == 1
    assert result["ack_audits"] == 1
    assert result["decision_snapshot_attached"] is True
    assert result["app_evidence_attached"] is True

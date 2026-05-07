from __future__ import annotations

from uuid import UUID

from notification.integrations import AppSignalRequest
from notification.models import AutonomyMode, NotificationIntent

AGENT_ID = UUID("11111111-1111-1111-1111-111111111111")
PLAN_ID = UUID("22222222-2222-2222-2222-222222222222")
DECISION_ID = UUID("33333333-3333-3333-3333-333333333333")
EXECUTION_ID = UUID("44444444-4444-4444-4444-444444444444")
CONTRACT_ID = UUID("55555555-5555-5555-5555-555555555555")


class RecordingAppAdapter:
    def __init__(self) -> None:
        self.requests: list[AppSignalRequest] = []

    def send(self, request: AppSignalRequest) -> object:
        self.requests.append(request)
        return object()


def test_approval_required_builds_governance_signal_with_evidence() -> None:
    from notification.integrations.mip_adapter import MIPSignalAdapter

    recorder = RecordingAppAdapter()
    adapter = MIPSignalAdapter(app_adapter=recorder)

    adapter.approval_required(
        contract_id=CONTRACT_ID,
        capability="place_order",
        agent_id=AGENT_ID,
        autonomy_mode=AutonomyMode.SHADOW,
        plan_id=PLAN_ID,
        decision_snapshot_id=DECISION_ID,
        context_summary="Order exceeds governance threshold",
    )

    request = recorder.requests[0]
    assert request.notification_type == "governance.approval_required"
    assert request.intent == NotificationIntent.GOVERNANCE
    assert request.source == "agent_governor"
    assert request.require_ack_override is True
    assert request.correlation_id == str(CONTRACT_ID)
    assert request.autonomy_context is not None
    assert request.autonomy_context.agent_id == AGENT_ID
    assert request.autonomy_context.autonomy_mode == AutonomyMode.SHADOW
    assert request.evidence is not None
    assert request.evidence.plan_id == PLAN_ID
    assert request.evidence.decision_snapshot_id == DECISION_ID
    assert request.metadata["contract_id"] == str(CONTRACT_ID)
    assert request.metadata["capability"] == "place_order"


def test_circuit_breaker_engaged_builds_safety_signal_with_dedup_key() -> None:
    from notification.integrations.mip_adapter import MIPSignalAdapter

    recorder = RecordingAppAdapter()
    adapter = MIPSignalAdapter(app_adapter=recorder)

    adapter.circuit_breaker_engaged(
        breaker_type="volatility",
        agent_id=AGENT_ID,
        trigger_reason="Volatility exceeded threshold",
        metrics={"volatility": 0.15, "threshold": 0.075},
        plan_id=PLAN_ID,
    )

    request = recorder.requests[0]
    assert request.notification_type == "safety.circuit_breaker_engaged"
    assert request.intent == NotificationIntent.SAFETY
    assert request.source == "circuit_breaker"
    assert request.irreversible is True
    assert request.require_ack_override is True
    assert request.dedup_key == f"circuit_breaker:volatility:{AGENT_ID}:engaged"
    assert request.metadata["event"] == "engaged"
    assert request.metadata["metrics"]["volatility"] == 0.15
    assert request.evidence is not None
    assert request.evidence.plan_id == PLAN_ID


def test_execution_alert_maps_critical_slippage_to_safety_signal() -> None:
    from notification.integrations.mip_adapter import MIPExecutionAlert, MIPSignalAdapter

    recorder = RecordingAppAdapter()
    adapter = MIPSignalAdapter(app_adapter=recorder)

    adapter.execution_alert(
        MIPExecutionAlert(
            severity="critical",
            metric="avg_slippage",
            value=25.5,
            threshold=20.0,
            message="Average slippage exceeded threshold",
        ),
        agent_id=AGENT_ID,
        execution_snapshot_id=EXECUTION_ID,
    )

    request = recorder.requests[0]
    assert request.notification_type == "execution.slippage.critical"
    assert request.intent == NotificationIntent.SAFETY
    assert request.source == "execution_alerts"
    assert request.require_ack_override is True
    assert request.metadata["severity"] == "critical"
    assert request.metadata["metric"] == "avg_slippage"
    assert request.evidence is not None
    assert request.evidence.execution_snapshot_id == EXECUTION_ID


def test_agsignal_public_integration_alias_excludes_mip_adapter() -> None:
    import agsignal.integrations as agsignal_integrations
    from notification.integrations.mip_adapter import (
        MIPExecutionAlert as NotificationMIPExecutionAlert,
    )
    from notification.integrations.mip_adapter import (
        MIPSignalAdapter as NotificationMIPSignalAdapter,
    )

    assert not hasattr(agsignal_integrations, "MIPSignalAdapter")
    assert not hasattr(agsignal_integrations, "MIPExecutionAlert")
    assert NotificationMIPSignalAdapter.__name__ == "MIPSignalAdapter"
    assert NotificationMIPExecutionAlert.__name__ == "MIPExecutionAlert"

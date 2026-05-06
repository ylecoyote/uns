"""Tests for generic application integration boundaries."""

from __future__ import annotations

from uuid import uuid4

import pytest

from notification.integrations import (
    AppEvidenceContext,
    AppSignalAdapter,
    AppSignalContextProvider,
    AppSignalRequest,
    DefaultAppSignalContextProvider,
)
from notification.models import (
    AutonomyMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
)
from notification.sdk import NotificationSDK


def test_evidence_context_maps_to_autonomy_context_without_app_domain_imports() -> None:
    agent_id = uuid4()
    plan_id = uuid4()
    decision_snapshot_id = uuid4()
    evidence = AppEvidenceContext(
        plan_id=plan_id,
        decision_snapshot_id=decision_snapshot_id,
        metadata={"source_url": "app://decision/123"},
    )
    provider = DefaultAppSignalContextProvider(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id=agent_id,
    )

    context = provider.build_context(
        AppSignalRequest(
            notification_type="app.governor.circuit_breaker_engaged",
            intent=NotificationIntent.SAFETY,
            title="Circuit breaker engaged",
            message="Execution halted by the host application.",
            source="host-app",
            evidence=evidence,
        )
    )

    assert context.autonomy_mode == AutonomyMode.LIVE
    assert context.agent_id == agent_id
    assert context.plan_id == plan_id
    assert context.decision_snapshot_id == decision_snapshot_id


def test_app_signal_adapter_sends_through_sdk_with_evidence_metadata() -> None:
    captured: dict[str, Notification] = {}

    def deliver(notification: Notification) -> NotificationResult:
        captured["notification"] = notification
        return NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.SUCCESS,
            channels_attempted=notification.channels,
            channels_succeeded=[],
            channels_failed=[],
        )

    agent_id = uuid4()
    execution_snapshot_id = uuid4()
    adapter = AppSignalAdapter(
        sdk=NotificationSDK(delivery_handler=deliver),
        context_provider=DefaultAppSignalContextProvider(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        ),
    )

    result = adapter.send(
        AppSignalRequest(
            notification_type="app.execution.slippage",
            intent=NotificationIntent.GOVERNANCE,
            title="Execution slippage exceeded policy",
            message="Host application reported slippage outside configured tolerance.",
            source="host-app",
            evidence=AppEvidenceContext(
                execution_snapshot_id=execution_snapshot_id,
                metadata={"symbol": "BTC-USD"},
            ),
            metadata={"threshold_bps": 25},
        )
    )

    assert result.status == DeliveryStatus.SUCCESS
    notification = captured["notification"]
    assert notification.autonomy_context.agent_id == agent_id
    assert notification.autonomy_context.execution_snapshot_id == execution_snapshot_id
    assert notification.metadata["threshold_bps"] == 25
    assert notification.metadata["app_evidence"]["execution_snapshot_id"] == str(
        execution_snapshot_id
    )
    assert notification.metadata["app_evidence"]["metadata"] == {"symbol": "BTC-USD"}


def test_context_provider_protocol_is_runtime_checkable() -> None:
    provider = DefaultAppSignalContextProvider(
        autonomy_mode=AutonomyMode.PREVIEW,
        agent_id=uuid4(),
    )

    assert isinstance(provider, AppSignalContextProvider)


def test_default_context_provider_requires_agent_when_request_has_no_context() -> None:
    provider = DefaultAppSignalContextProvider(autonomy_mode=AutonomyMode.LIVE)

    with pytest.raises(RuntimeError, match="No app agent_id configured"):
        provider.build_context(
            AppSignalRequest(
                notification_type="app.event",
                intent=NotificationIntent.OPERATIONAL,
                title="Host event",
                message="Host application event",
                source="host-app",
            )
        )

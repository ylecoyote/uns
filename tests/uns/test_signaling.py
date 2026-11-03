"""Unit tests for the uns.signaling service layer."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from notification.models import AckStatus, AutonomyContext, AutonomyMode, NotificationIntent


def _build_send_request_payload(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid SendNotificationRequest payload."""
    payload: dict[str, Any] = {
        "notification_type": "agent.risk_limit_breach",
        "intent": NotificationIntent.SAFETY,
        "title": "Risk limit breached",
        "message": "Agent entered a position outside configured limits.",
        "source": "agent-runtime",
        "autonomy_context": {
            "autonomy_mode": AutonomyMode.LIVE,
            "agent_id": uuid4(),
        },
    }
    payload.update(overrides)
    return payload


def _build_send_request() -> Any:
    """Build a minimal valid SendNotificationRequest model instance."""
    from notification.routes import SendNotificationRequest

    return SendNotificationRequest.model_validate(_build_send_request_payload())


@pytest.mark.asyncio
async def test_acknowledge_marks_notification_as_acked_and_persists_audit() -> None:
    """acknowledge() transitions ack state and writes audit."""
    from notification.acknowledgment import (
        InMemoryAckStorage,
        configure_ack_engine,
    )
    from notification.audit import InMemoryAuditStore
    from uns.signaling import acknowledge

    audit_store = InMemoryAuditStore()
    engine = configure_ack_engine(storage=InMemoryAckStorage())

    # Register the notification with the ack engine first so it's ackable.
    # The route layer does this via send_signal — when we test acknowledge in
    # isolation, the test must establish the precondition.
    notification_id = uuid4()
    engine.register_notification(
        notification_id=notification_id,
        intent=NotificationIntent.GOVERNANCE,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
    )

    response = await acknowledge(
        notification_id=notification_id,
        acked_by="ops-rotation@example.com",
        metadata={"reason": "manual ack"},
        audit_store=audit_store,
    )

    assert response.notification_id == notification_id
    assert response.ack_status == AckStatus.ACKED
    assert response.acked_by == "ops-rotation@example.com"

    # Audit row was persisted. InMemoryAuditStore exposes ack audits via
    # get_ack_audits_for_notification(notification_id) — see
    # src/notification/audit.py:281.
    rows = audit_store.get_ack_audits_for_notification(notification_id)
    assert rows, "audit row not persisted"
    assert rows[0].new_status == AckStatus.ACKED
    assert rows[0].acked_by == "ops-rotation@example.com"


@pytest.mark.asyncio
async def test_dismiss_marks_notification_as_dismissed_and_persists_audit() -> None:
    """dismiss() transitions ack state to DISMISSED and writes audit."""
    from notification.acknowledgment import (
        InMemoryAckStorage,
        configure_ack_engine,
    )
    from notification.audit import InMemoryAuditStore
    from uns.signaling import dismiss

    audit_store = InMemoryAuditStore()
    engine = configure_ack_engine(storage=InMemoryAckStorage())

    notification_id = uuid4()
    engine.register_notification(
        notification_id=notification_id,
        intent=NotificationIntent.GOVERNANCE,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
    )

    response = await dismiss(
        notification_id=notification_id,
        dismissed_by="ops-rotation@example.com",
        metadata={"reason": "manual dismiss"},
        audit_store=audit_store,
    )

    assert response.notification_id == notification_id
    assert response.ack_status == AckStatus.DISMISSED
    assert response.acked_by == "ops-rotation@example.com"

    rows = audit_store.get_ack_audits_for_notification(notification_id)
    assert rows, "audit row not persisted"
    assert rows[0].new_status == AckStatus.DISMISSED
    assert rows[0].acked_by == "ops-rotation@example.com"


@pytest.mark.asyncio
async def test_send_signal_returns_response_with_uuid_notification_id() -> None:
    """send_signal() returns a SendNotificationResponse and persists a delivery audit."""
    from uuid import UUID

    from notification.audit import InMemoryAuditStore
    from uns.signaling import send_signal

    audit_store = InMemoryAuditStore()
    request = _build_send_request()

    response = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        transport_metadata={"runtime": "standalone_http"},
    )

    assert isinstance(response.notification_id, UUID)
    assert response.idempotent_replay is False
    assert response.message == "notification accepted"

    rows = audit_store.get_delivery_audits_for_notification(response.notification_id)
    assert rows, "delivery audit row not persisted"


@pytest.mark.asyncio
async def test_send_signal_replays_idempotent_response_when_key_recurs() -> None:
    """send_signal() replays a stored response when the idempotency key recurs."""
    from notification.audit import InMemoryAuditStore
    from uns.signaling import send_signal

    audit_store = InMemoryAuditStore()
    idempotency_store: dict[str, Any] = {}
    request = _build_send_request_payload(idempotency_key="retry-key-1")
    from notification.routes import SendNotificationRequest

    request_model = SendNotificationRequest.model_validate(request)

    first = await send_signal(
        request=request_model,
        audit_store=audit_store,
        idempotency_store=idempotency_store,
        transport_metadata={"runtime": "standalone_http"},
    )
    assert first.idempotent_replay is False

    second = await send_signal(
        request=request_model,
        audit_store=audit_store,
        idempotency_store=idempotency_store,
        transport_metadata={"runtime": "standalone_http"},
    )
    assert second.idempotent_replay is True
    assert second.notification_id == first.notification_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime_tag",
    ["standalone_http", "uns_mcp"],
)
async def test_send_signal_preserves_caller_supplied_transport_metadata(
    runtime_tag: str,
) -> None:
    """The transport tag the caller supplies is the tag the audit row carries."""
    from notification.audit import InMemoryAuditStore
    from uns.signaling import send_signal

    audit_store = InMemoryAuditStore()
    request = _build_send_request()

    response = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        transport_metadata={"runtime": runtime_tag},
    )

    rows = audit_store.get_delivery_audits_for_notification(response.notification_id)
    assert rows, "audit row not persisted"
    assert rows[0].audit_metadata.get("runtime") == runtime_tag


@pytest.mark.asyncio
async def test_simulate_signal_has_no_ack_or_audit_side_effects() -> None:
    """simulate_signal() returns a simulation response with no ack/audit side effects."""
    from notification.acknowledgment import (
        InMemoryAckStorage,
        configure_ack_engine,
    )
    from uns.signaling import simulate_signal

    # Reset the ack engine so any rogue registration would be visible.
    configure_ack_engine(storage=InMemoryAckStorage())
    request = _build_send_request()

    response = await simulate_signal(request=request)

    assert response.simulated is True
    assert response.ack_status is None
    assert response.message == "notification simulated"


@pytest.mark.asyncio
async def test_send_signal_dispatches_through_delivery_service_and_returns_delivered() -> None:
    """send_signal() invokes delivery_service and returns DELIVERED on channel success."""
    from unittest.mock import AsyncMock

    from notification.audit import InMemoryAuditStore
    from notification.models import Channel, DeliveryStatus, NotificationResult
    from uns.signaling import send_signal

    audit_store = InMemoryAuditStore()
    request = _build_send_request()

    delivery_service = AsyncMock()
    delivery_service.deliver.side_effect = lambda n: NotificationResult(
        notification_id=n.notification_id,
        status=DeliveryStatus.DELIVERED,
        channels_attempted=[Channel.SLACK],
        channels_succeeded=[Channel.SLACK],
        channels_failed=[],
    )

    dlq_service = AsyncMock()

    response = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        delivery_service=delivery_service,
        dlq_service=dlq_service,
    )

    assert response.status == DeliveryStatus.DELIVERED
    assert response.channels_succeeded == [Channel.SLACK]
    assert response.message == "notification delivered"
    delivery_service.deliver.assert_called_once()
    assert dlq_service.enqueue.call_count == 0
    assert dlq_service.add.call_count == 0

    rows = audit_store.get_delivery_audits_for_notification(response.notification_id)
    assert len(rows) == 1
    assert rows[0].status == DeliveryStatus.DELIVERED


@pytest.mark.asyncio
async def test_send_signal_dispatches_through_sync_delivery_service() -> None:
    """send_signal() supports synchronous delivery_service.deliver."""
    from notification.audit import InMemoryAuditStore
    from notification.models import Channel, DeliveryStatus, Notification, NotificationResult
    from uns.signaling import send_signal

    class SyncDeliveryService:
        def __init__(self) -> None:
            self.delivered: list[Notification] = []

        def deliver(self, notification: Notification) -> NotificationResult:
            self.delivered.append(notification)
            return NotificationResult(
                notification_id=notification.notification_id,
                status=DeliveryStatus.DELIVERED,
                channels_attempted=[Channel.EMAIL],
                channels_succeeded=[Channel.EMAIL],
                channels_failed=[],
            )

    audit_store = InMemoryAuditStore()
    request = _build_send_request()
    service = SyncDeliveryService()

    response = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        delivery_service=service,
    )

    assert response.status == DeliveryStatus.DELIVERED
    assert len(service.delivered) == 1


@pytest.mark.asyncio
async def test_send_signal_enqueues_to_dlq_when_guaranteed_delivery_fails() -> None:
    """send_signal() pushes to dlq_service when GUARANTEED delivery fails all persistent channels."""
    from unittest.mock import MagicMock

    from notification.acknowledgment import get_ack_engine
    from notification.audit import InMemoryAuditStore
    from notification.models import Channel, DeliveryMode, DeliveryStatus, NotificationResult
    from notification.routes import SendNotificationRequest
    from uns.signaling import send_signal

    audit_store = InMemoryAuditStore()
    request_payload = _build_send_request_payload(
        delivery_mode=DeliveryMode.GUARANTEED,
        require_ack=True,
    )
    request = SendNotificationRequest.model_validate(request_payload)

    class FailingDeliveryService:
        async def deliver(self, notification: Any) -> NotificationResult:
            return NotificationResult(
                notification_id=notification.notification_id,
                status=DeliveryStatus.FAILED,
                channels_attempted=[Channel.SLACK, Channel.PAGERDUTY],
                channels_succeeded=[],
                channels_failed=[Channel.SLACK, Channel.PAGERDUTY],
                error_message="All persistent delivery channels unreachable",
            )

    dlq_service = MagicMock()
    dlq_service.enqueue = MagicMock(return_value=None)

    response = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        delivery_service=FailingDeliveryService(),
        dlq_service=dlq_service,
    )

    assert response.status == DeliveryStatus.FAILED
    assert response.message == "notification delivery failed"
    assert response.ack_status is None
    assert get_ack_engine().get_status(response.notification_id) is None
    dlq_service.enqueue.assert_called_once()
    call_args, call_kwargs = dlq_service.enqueue.call_args
    assert call_args[0].notification_id == response.notification_id
    assert call_kwargs["reason"] == "guaranteed_delivery_failed"
    metadata = call_kwargs["metadata"]
    assert Channel.SLACK.value in metadata["channels_attempted"]
    assert Channel.PAGERDUTY.value in metadata["channels_attempted"]
    assert Channel.SLACK.value in metadata["channels_failed"]
    assert Channel.PAGERDUTY.value in metadata["channels_failed"]
    assert metadata["channel_errors"][Channel.SLACK.value] == "All persistent delivery channels unreachable"

    # Also test dlq_service with .add instead of .enqueue
    dlq_service_add = MagicMock(spec=["add"])
    dlq_service_add.add = MagicMock(return_value=None)

    response_add = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        delivery_service=FailingDeliveryService(),
        dlq_service=dlq_service_add,
    )
    assert response_add.status == DeliveryStatus.FAILED
    assert response_add.ack_status is None
    assert get_ack_engine().get_status(response_add.notification_id) is None
    dlq_service_add.add.assert_called_once()
    assert dlq_service_add.add.call_args[1]["reason"] == "guaranteed_delivery_failed"


@pytest.mark.asyncio
async def test_send_signal_registers_ack_with_delivered_at_on_delivery_success() -> None:
    """When delivery succeeds, ack registration created_at uses result.delivered_at."""
    from datetime import UTC, datetime, timedelta

    from notification.acknowledgment import get_ack_engine
    from notification.audit import InMemoryAuditStore
    from notification.models import Channel, DeliveryMode, DeliveryStatus, NotificationResult
    from notification.routes import SendNotificationRequest
    from uns.signaling import send_signal

    audit_store = InMemoryAuditStore()
    request_payload = _build_send_request_payload(
        delivery_mode=DeliveryMode.GUARANTEED,
        require_ack=True,
    )
    request = SendNotificationRequest.model_validate(request_payload)
    delivered_timestamp = datetime.now(UTC) + timedelta(seconds=10)

    class SuccessfulDeliveryService:
        async def deliver(self, notification: Any) -> NotificationResult:
            return NotificationResult(
                notification_id=notification.notification_id,
                status=DeliveryStatus.DELIVERED,
                channels_attempted=[Channel.SLACK],
                channels_succeeded=[Channel.SLACK],
                channels_failed=[],
                delivered_at=delivered_timestamp,
            )

    response = await send_signal(
        request=request,
        audit_store=audit_store,
        idempotency_store={},
        delivery_service=SuccessfulDeliveryService(),
    )

    assert response.status == DeliveryStatus.DELIVERED
    assert response.ack_status is not None
    engine = get_ack_engine()
    state = engine._storage.get_ack_state(response.notification_id)
    assert state is not None
    assert state.created_at == delivered_timestamp

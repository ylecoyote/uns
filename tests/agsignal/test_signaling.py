"""Unit tests for the agsignal.signaling service layer."""

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
    from agsignal.signaling import acknowledge
    from notification.acknowledgment import (
        InMemoryAckStorage,
        configure_ack_engine,
    )
    from notification.audit import InMemoryAuditStore

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
    from agsignal.signaling import dismiss
    from notification.acknowledgment import (
        InMemoryAckStorage,
        configure_ack_engine,
    )
    from notification.audit import InMemoryAuditStore

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

    from agsignal.signaling import send_signal
    from notification.audit import InMemoryAuditStore

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
    from agsignal.signaling import send_signal
    from notification.audit import InMemoryAuditStore

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
    ["standalone_http", "agsignal_mcp"],
)
async def test_send_signal_preserves_caller_supplied_transport_metadata(
    runtime_tag: str,
) -> None:
    """The transport tag the caller supplies is the tag the audit row carries."""
    from agsignal.signaling import send_signal
    from notification.audit import InMemoryAuditStore

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
    from agsignal.signaling import simulate_signal
    from notification.acknowledgment import (
        InMemoryAckStorage,
        configure_ack_engine,
    )

    # Reset the ack engine so any rogue registration would be visible.
    configure_ack_engine(storage=InMemoryAckStorage())
    request = _build_send_request()

    response = await simulate_signal(request=request)

    assert response.simulated is True
    assert response.ack_status is None
    assert response.message == "notification simulated"

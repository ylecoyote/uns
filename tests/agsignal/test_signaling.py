"""Unit tests for the agsignal.signaling service layer."""

from __future__ import annotations

from uuid import uuid4

import pytest

from notification.models import AckStatus, AutonomyContext, AutonomyMode, NotificationIntent


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

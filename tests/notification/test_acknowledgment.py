"""Tests for the Acknowledgment Engine.

Tests cover:
- AckState serialization and timeout calculation
- AcknowledgmentEngine registration, ack, and timeout handling
- Idempotency of ack operations
- SAFETY timeout escalation in LIVE mode
- Callback invocation
"""

from datetime import UTC, datetime, timedelta
from threading import Thread
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.acknowledgment import (
    DEFAULT_ACK_TIMEOUTS,
    AcknowledgmentEngine,
    AckState,
    InMemoryAckStorage,
    LoggingEscalationHandler,
)
from notification.models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    NotificationIntent,
)


class TestAckState:
    """Tests for AckState class."""

    def test_creation_with_defaults(self) -> None:
        """Test AckState creation with default values."""
        notification_id = uuid4()
        state = AckState(notification_id=notification_id)

        assert state.notification_id == notification_id
        assert state.status == AckStatus.PENDING
        assert state.intent is None
        assert state.autonomy_context is None
        assert state.timeout_minutes is None
        assert state.acked_by is None
        assert state.acked_at is None
        assert state.metadata == {}
        assert state.created_at is not None

    def test_creation_with_full_context(self) -> None:
        """Test AckState creation with all fields."""
        notification_id = uuid4()
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )
        created_at = datetime.now(UTC)

        state = AckState(
            notification_id=notification_id,
            status=AckStatus.PENDING,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
            metadata={"key": "value"},
        )

        assert state.notification_id == notification_id
        assert state.status == AckStatus.PENDING
        assert state.intent == NotificationIntent.SAFETY
        assert state.autonomy_context == context
        assert state.timeout_minutes == 15
        assert state.created_at == created_at
        assert state.metadata == {"key": "value"}

    def test_timeout_at_calculation(self) -> None:
        """Test timeout_at property calculates correctly."""
        notification_id = uuid4()
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = AckState(
            notification_id=notification_id,
            timeout_minutes=15,
            created_at=created_at,
        )

        expected_timeout = datetime(2025, 1, 1, 12, 15, 0, tzinfo=UTC)
        assert state.timeout_at == expected_timeout

    def test_timeout_at_none_when_no_timeout(self) -> None:
        """Test timeout_at is None when no timeout configured."""
        state = AckState(notification_id=uuid4())
        assert state.timeout_at is None

    def test_is_timed_out_false_before_timeout(self) -> None:
        """Test is_timed_out returns False before timeout."""
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        now = datetime(2025, 1, 1, 12, 10, 0, tzinfo=UTC)

        state = AckState(
            notification_id=uuid4(),
            timeout_minutes=15,
            created_at=created_at,
        )

        assert state.is_timed_out(now) is False

    def test_is_timed_out_true_after_timeout(self) -> None:
        """Test is_timed_out returns True after timeout."""
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        now = datetime(2025, 1, 1, 12, 20, 0, tzinfo=UTC)

        state = AckState(
            notification_id=uuid4(),
            timeout_minutes=15,
            created_at=created_at,
        )

        assert state.is_timed_out(now) is True

    def test_is_timed_out_true_at_exact_timeout(self) -> None:
        """Test is_timed_out returns True at exact timeout time."""
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        now = datetime(2025, 1, 1, 12, 15, 0, tzinfo=UTC)

        state = AckState(
            notification_id=uuid4(),
            timeout_minutes=15,
            created_at=created_at,
        )

        assert state.is_timed_out(now) is True

    def test_is_timed_out_false_when_no_timeout_configured(self) -> None:
        """Test is_timed_out returns False when no timeout set."""
        state = AckState(notification_id=uuid4())
        assert state.is_timed_out() is False

    def test_to_dict_serialization(self) -> None:
        """Test AckState serialization to dict."""
        notification_id = uuid4()
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        acked_at = datetime(2025, 1, 1, 12, 5, 0, tzinfo=UTC)

        state = AckState(
            notification_id=notification_id,
            status=AckStatus.ACKED,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
            acked_by="user@example.com",
            acked_at=acked_at,
            metadata={"key": "value"},
        )

        data = state.to_dict()

        assert data["notification_id"] == str(notification_id)
        assert data["status"] == "ACKED"
        assert data["intent"] == "SAFETY"
        assert data["autonomy_mode"] == "LIVE"
        assert data["agent_id"] == str(agent_id)
        assert data["timeout_minutes"] == 15
        assert data["created_at"] == "2025-01-01T12:00:00+00:00"
        assert data["acked_by"] == "user@example.com"
        assert data["acked_at"] == "2025-01-01T12:05:00+00:00"
        assert data["metadata"] == {"key": "value"}

    def test_from_dict_deserialization(self) -> None:
        """Test AckState deserialization from dict."""
        notification_id = uuid4()
        agent_id = uuid4()

        data = {
            "notification_id": str(notification_id),
            "status": "ACKED",
            "intent": "SAFETY",
            "autonomy_mode": "LIVE",
            "agent_id": str(agent_id),
            "timeout_minutes": 15,
            "created_at": "2025-01-01T12:00:00+00:00",
            "acked_by": "user@example.com",
            "acked_at": "2025-01-01T12:05:00+00:00",
            "metadata": {"key": "value"},
        }

        state = AckState.from_dict(data)

        assert state.notification_id == notification_id
        assert state.status == AckStatus.ACKED
        assert state.intent == NotificationIntent.SAFETY
        assert state.autonomy_context is not None
        assert state.autonomy_context.autonomy_mode == AutonomyMode.LIVE
        assert state.autonomy_context.agent_id == agent_id
        assert state.timeout_minutes == 15
        assert state.acked_by == "user@example.com"
        assert state.metadata == {"key": "value"}

    def test_roundtrip_serialization(self) -> None:
        """Test that to_dict -> from_dict preserves data."""
        notification_id = uuid4()
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.SHADOW,
            agent_id=agent_id,
        )

        original = AckState(
            notification_id=notification_id,
            status=AckStatus.PENDING,
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=context,
            timeout_minutes=30,
        )

        restored = AckState.from_dict(original.to_dict())

        assert restored.notification_id == original.notification_id
        assert restored.status == original.status
        assert restored.intent == original.intent
        assert restored.timeout_minutes == original.timeout_minutes


class TestInMemoryAckStorage:
    """Tests for InMemoryAckStorage."""

    def test_set_and_get_state(self) -> None:
        """Test storing and retrieving state."""
        storage = InMemoryAckStorage()
        notification_id = uuid4()
        state = AckState(notification_id=notification_id)

        storage.set_ack_state(state)
        retrieved = storage.get_ack_state(notification_id)

        assert retrieved is state

    def test_get_nonexistent_state(self) -> None:
        """Test retrieving nonexistent state returns None."""
        storage = InMemoryAckStorage()
        assert storage.get_ack_state(uuid4()) is None

    def test_get_pending_notifications(self) -> None:
        """Test retrieving pending notifications."""
        storage = InMemoryAckStorage()

        pending_id = uuid4()
        acked_id = uuid4()

        pending_state = AckState(notification_id=pending_id, status=AckStatus.PENDING)
        acked_state = AckState(notification_id=acked_id, status=AckStatus.ACKED)

        storage.set_ack_state(pending_state)
        storage.set_ack_state(acked_state)

        pending = storage.get_pending_notifications()

        assert len(pending) == 1
        assert pending[0].notification_id == pending_id

    def test_get_pending_notifications_with_before_filter(self) -> None:
        """Test filtering pending notifications by creation time."""
        storage = InMemoryAckStorage()

        old_id = uuid4()
        new_id = uuid4()
        cutoff = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        old_state = AckState(
            notification_id=old_id,
            status=AckStatus.PENDING,
            created_at=datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC),
        )
        new_state = AckState(
            notification_id=new_id,
            status=AckStatus.PENDING,
            created_at=datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC),
        )

        storage.set_ack_state(old_state)
        storage.set_ack_state(new_state)

        pending = storage.get_pending_notifications(before=cutoff)

        assert len(pending) == 1
        assert pending[0].notification_id == old_id

    def test_clear_storage(self) -> None:
        """Test clearing all stored states."""
        storage = InMemoryAckStorage()
        storage.set_ack_state(AckState(notification_id=uuid4()))
        storage.set_ack_state(AckState(notification_id=uuid4()))

        storage.clear()

        assert storage.get_pending_notifications() == []


class MockCallback:
    """Mock callback for testing."""

    def __init__(self) -> None:
        self.ack_events: list[AckEvent] = []
        self.dismiss_events: list[AckEvent] = []
        self.timeout_events: list[AckEvent] = []
        self.status_changes: list[dict[str, Any]] = []

    def on_ack(self, event: AckEvent) -> None:
        self.ack_events.append(event)

    def on_dismiss(self, event: AckEvent) -> None:
        self.dismiss_events.append(event)

    def on_timeout(self, event: AckEvent) -> None:
        self.timeout_events.append(event)

    def on_status_change(
        self,
        notification_id: Any,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.status_changes.append(
            {
                "notification_id": notification_id,
                "old_status": old_status,
                "new_status": new_status,
                "metadata": metadata,
            }
        )


class MockEscalationHandler:
    """Mock escalation handler for testing."""

    def __init__(self) -> None:
        self.escalations: list[dict[str, Any]] = []

    def escalate(
        self,
        notification_id: Any,
        intent: NotificationIntent | None,
        autonomy_context: AutonomyContext | None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.escalations.append(
            {
                "notification_id": notification_id,
                "intent": intent,
                "autonomy_context": autonomy_context,
                "reason": reason,
                "metadata": metadata,
            }
        )


class TestAcknowledgmentEngine:
    """Tests for AcknowledgmentEngine."""

    def test_register_notification(self) -> None:
        """Test registering a notification for ack tracking."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        state = engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        assert state.notification_id == notification_id
        assert state.status == AckStatus.PENDING
        assert state.intent == NotificationIntent.SAFETY
        assert state.autonomy_context == context
        assert state.timeout_minutes == DEFAULT_ACK_TIMEOUTS[NotificationIntent.SAFETY]

    def test_register_notification_with_custom_timeout(self) -> None:
        """Test registering with custom timeout override."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        state = engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=5,
        )

        assert state.timeout_minutes == 5

    def test_register_notification_operational_no_default_timeout(self) -> None:
        """Test OPERATIONAL notifications have no default timeout."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        state = engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=context,
        )

        assert state.timeout_minutes is None

    def test_ack_notification(self) -> None:
        """Test acknowledging a notification."""
        callback = MockCallback()
        engine = AcknowledgmentEngine(callback=callback)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        event = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="user@example.com",
            metadata={"note": "Acknowledged"},
        )

        assert event.notification_id == notification_id
        assert event.ack_status == AckStatus.ACKED
        assert event.acked_by == "user@example.com"

        # Verify callbacks were invoked
        assert len(callback.ack_events) == 1
        assert len(callback.status_changes) == 1
        assert callback.status_changes[0]["old_status"] == AckStatus.PENDING
        assert callback.status_changes[0]["new_status"] == AckStatus.ACKED

    def test_dismiss_notification(self) -> None:
        """Test dismissing a notification."""
        callback = MockCallback()
        engine = AcknowledgmentEngine(callback=callback)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=context,
        )

        event = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.DISMISSED,
            acked_by="user@example.com",
        )

        assert event.ack_status == AckStatus.DISMISSED

        # Verify dismiss callback was invoked
        assert len(callback.dismiss_events) == 1

    def test_ack_idempotency(self) -> None:
        """Test that repeated ack calls are idempotent."""
        callback = MockCallback()
        engine = AcknowledgmentEngine(callback=callback)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        # First ack
        event1 = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="user1@example.com",
        )

        # Second ack (idempotent)
        event2 = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="user2@example.com",
        )

        assert event1.ack_status == event2.ack_status
        # Only one ack callback should be invoked
        assert len(callback.ack_events) == 1
        # Only one status change
        assert len(callback.status_changes) == 1

    def test_concurrent_duplicate_ack_is_idempotent(self) -> None:
        """Concurrent duplicate ACK calls should not clobber actor or callbacks."""
        callback = MockCallback()
        engine = AcknowledgmentEngine(callback=callback)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        errors: list[Exception] = []

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        def ack() -> None:
            try:
                engine.ack(
                    notification_id=notification_id,
                    ack_status=AckStatus.ACKED,
                    acked_by="operator@example.com",
                )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [Thread(target=ack) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        state = engine.get_state(notification_id)

        assert errors == []
        assert state is not None
        assert state.acked_by == "operator@example.com"
        assert len(callback.ack_events) == 1
        assert len(callback.status_changes) == 1

    def test_ack_invalid_status_raises(self) -> None:
        """Test that invalid ack status raises ValueError."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        with pytest.raises(ValueError, match="Invalid ack_status"):
            engine.ack(
                notification_id=notification_id,
                ack_status=AckStatus.TIMED_OUT,
            )

    def test_ack_unknown_notification_raises(self) -> None:
        """Test that acking unknown notification raises KeyError."""
        engine = AcknowledgmentEngine()

        with pytest.raises(KeyError):
            engine.ack(
                notification_id=uuid4(),
                ack_status=AckStatus.ACKED,
            )

    def test_ack_timed_out_notification_returns_timed_out_event(self) -> None:
        """Test that acking timed out notification returns TIMED_OUT status."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        created_at = datetime.now(UTC) - timedelta(minutes=20)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
        )

        # Trigger timeout
        engine.check_ack_timeout(notification_id)

        # Try to ack after timeout
        event = engine.ack(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="user@example.com",
        )

        assert event.ack_status == AckStatus.TIMED_OUT
        assert "error" in event.metadata

    def test_check_ack_timeout_not_timed_out(self) -> None:
        """Test check_ack_timeout returns None when not timed out."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
        )

        result = engine.check_ack_timeout(notification_id)
        assert result is None

    def test_check_ack_timeout_timed_out(self) -> None:
        """Test check_ack_timeout handles timeout correctly."""
        callback = MockCallback()
        engine = AcknowledgmentEngine(callback=callback)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )
        created_at = datetime.now(UTC) - timedelta(minutes=20)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
        )

        event = engine.check_ack_timeout(notification_id)

        assert event is not None
        assert event.ack_status == AckStatus.TIMED_OUT
        assert len(callback.timeout_events) == 1

    def test_check_ack_timeout_unknown_notification(self) -> None:
        """Test check_ack_timeout returns None for unknown notification."""
        engine = AcknowledgmentEngine()
        result = engine.check_ack_timeout(uuid4())
        assert result is None

    def test_check_ack_timeout_already_acked(self) -> None:
        """Test check_ack_timeout returns None for already acked notification."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        created_at = datetime.now(UTC) - timedelta(minutes=20)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
        )

        # Ack before timeout check
        engine.ack(notification_id=notification_id, ack_status=AckStatus.ACKED)

        result = engine.check_ack_timeout(notification_id)
        assert result is None

    def test_check_all_timeouts(self) -> None:
        """Test check_all_timeouts processes multiple timeouts."""
        callback = MockCallback()
        engine = AcknowledgmentEngine(callback=callback)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )
        old_time = datetime.now(UTC) - timedelta(minutes=20)

        # Create multiple notifications
        for _ in range(3):
            engine.register_notification(
                notification_id=uuid4(),
                intent=NotificationIntent.SAFETY,
                autonomy_context=context,
                timeout_minutes=15,
                created_at=old_time,
            )

        events = engine.check_all_timeouts()

        assert len(events) == 3
        assert len(callback.timeout_events) == 3

    def test_safety_timeout_in_live_mode_escalates(self) -> None:
        """Test SAFETY timeout in LIVE mode triggers escalation."""
        callback = MockCallback()
        escalation = MockEscalationHandler()
        engine = AcknowledgmentEngine(callback=callback, escalation_handler=escalation)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        created_at = datetime.now(UTC) - timedelta(minutes=20)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
        )

        engine.check_ack_timeout(notification_id)

        # Verify escalation was triggered
        assert len(escalation.escalations) == 1
        assert escalation.escalations[0]["notification_id"] == notification_id
        assert escalation.escalations[0]["intent"] == NotificationIntent.SAFETY
        assert escalation.escalations[0]["reason"] == "Acknowledgment timeout"

    def test_safety_timeout_in_preview_mode_does_not_escalate(self) -> None:
        """Test SAFETY timeout in PREVIEW mode does not escalate."""
        escalation = MockEscalationHandler()
        engine = AcknowledgmentEngine(escalation_handler=escalation)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )
        created_at = datetime.now(UTC) - timedelta(minutes=20)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
            timeout_minutes=15,
            created_at=created_at,
        )

        engine.check_ack_timeout(notification_id)

        # No escalation for PREVIEW mode
        assert len(escalation.escalations) == 0

    def test_governance_timeout_does_not_escalate(self) -> None:
        """Test GOVERNANCE timeout does not trigger escalation (only SAFETY does)."""
        escalation = MockEscalationHandler()
        engine = AcknowledgmentEngine(escalation_handler=escalation)
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        created_at = datetime.now(UTC) - timedelta(minutes=35)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=context,
            timeout_minutes=30,
            created_at=created_at,
        )

        engine.check_ack_timeout(notification_id)

        # No escalation for GOVERNANCE
        assert len(escalation.escalations) == 0

    def test_get_status(self) -> None:
        """Test getting notification status."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        assert engine.get_status(notification_id) == AckStatus.PENDING

        engine.ack(notification_id=notification_id, ack_status=AckStatus.ACKED)

        assert engine.get_status(notification_id) == AckStatus.ACKED

    def test_get_status_unknown_notification(self) -> None:
        """Test get_status returns None for unknown notification."""
        engine = AcknowledgmentEngine()
        assert engine.get_status(uuid4()) is None

    def test_get_state(self) -> None:
        """Test getting full notification state."""
        engine = AcknowledgmentEngine()
        notification_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=context,
        )

        state = engine.get_state(notification_id)

        assert state is not None
        assert state.notification_id == notification_id
        assert state.intent == NotificationIntent.SAFETY

    def test_default_ack_timeouts(self) -> None:
        """Test default timeout values are correct per PRD."""
        assert DEFAULT_ACK_TIMEOUTS[NotificationIntent.SAFETY] == 15
        assert DEFAULT_ACK_TIMEOUTS[NotificationIntent.GOVERNANCE] == 30
        assert NotificationIntent.OPERATIONAL not in DEFAULT_ACK_TIMEOUTS
        assert NotificationIntent.INFORMATIONAL not in DEFAULT_ACK_TIMEOUTS


class TestLoggingEscalationHandler:
    """Tests for LoggingEscalationHandler."""

    def test_escalate_logs_critical(self) -> None:
        """Test that escalation logs at CRITICAL level."""
        mock_logger = MagicMock()
        handler = LoggingEscalationHandler(logger_instance=mock_logger)

        handler.escalate(
            notification_id=uuid4(),
            intent=NotificationIntent.SAFETY,
            autonomy_context=None,
            reason="Test reason",
            metadata={"key": "value"},
        )

        mock_logger.critical.assert_called_once()
        call_args = mock_logger.critical.call_args
        assert "ESCALATION TRIGGERED" in call_args[0][0]

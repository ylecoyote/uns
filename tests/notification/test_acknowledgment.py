"""Tests for the acknowledgment engine.

Tests the acknowledgment module per PRD Task 9:
- ack(): Acknowledge a notification
- dismiss(): Dismiss a notification
- check_ack_timeout(): Handle timeout with SAFETY escalation
- Idempotency: repeated ack is safe
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.acknowledgment import (
    AcknowledgmentEngine,
    InMemoryAckStorage,
    InvalidAckTransitionError,
    NoOpEscalationHandler,
    NotificationNotFoundError,
    configure_ack_engine,
    get_ack_engine,
)
from notification.interfaces import NoOpAcknowledgmentCallback
from notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Notification,
    NotificationIntent,
)


@pytest.fixture
def storage() -> InMemoryAckStorage:
    """Create a fresh in-memory storage."""
    return InMemoryAckStorage()


@pytest.fixture
def callback() -> MagicMock:
    """Create a mock callback for testing."""
    mock = MagicMock(spec=NoOpAcknowledgmentCallback)
    return mock


@pytest.fixture
def escalation_handler() -> MagicMock:
    """Create a mock escalation handler."""
    mock = MagicMock(spec=NoOpEscalationHandler)
    return mock


@pytest.fixture
def engine(
    storage: InMemoryAckStorage,
    callback: MagicMock,
    escalation_handler: MagicMock,
) -> AcknowledgmentEngine:
    """Create an engine with mocked dependencies."""
    return AcknowledgmentEngine(
        storage=storage,
        callback=callback,
        escalation_handler=escalation_handler,
    )


@pytest.fixture
def safety_notification() -> Notification:
    """Create a SAFETY notification for testing."""
    return Notification(
        notification_type="safety.alert",
        intent=NotificationIntent.SAFETY,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
        title="Safety Alert",
        message="Critical safety notification",
        source="test",
        require_ack=True,
    )


@pytest.fixture
def operational_notification() -> Notification:
    """Create an OPERATIONAL notification for testing."""
    return Notification(
        notification_type="ops.alert",
        intent=NotificationIntent.OPERATIONAL,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.SHADOW,
            agent_id=uuid4(),
        ),
        title="Ops Alert",
        message="Operational notification",
        source="test",
        require_ack=False,
    )


class TestAck:
    """Tests for the ack() method."""

    def test_ack_success(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test successful acknowledgment."""
        engine.register_notification(safety_notification)

        event = engine.ack(
            safety_notification.notification_id,
            acked_by="test_user",
            metadata={"note": "reviewed"},
        )

        assert event.notification_id == safety_notification.notification_id
        assert event.ack_status == AckStatus.ACKED
        assert event.acked_by == "test_user"
        assert event.metadata["note"] == "reviewed"

    def test_ack_triggers_callback(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
        callback: MagicMock,
    ):
        """Test that ack triggers callback."""
        engine.register_notification(safety_notification)
        engine.ack(safety_notification.notification_id, acked_by="user")

        callback.on_ack.assert_called_once()
        callback.on_status_change.assert_called_once()

    def test_ack_idempotent(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test that repeated ack is idempotent."""
        engine.register_notification(safety_notification)

        event1 = engine.ack(safety_notification.notification_id, acked_by="user1")
        event2 = engine.ack(safety_notification.notification_id, acked_by="user2")

        assert event1.ack_status == AckStatus.ACKED
        assert event2.ack_status == AckStatus.ACKED

    def test_ack_not_found_raises(
        self,
        engine: AcknowledgmentEngine,
    ):
        """Test that acking non-existent notification raises."""
        fake_id = uuid4()

        with pytest.raises(NotificationNotFoundError) as exc_info:
            engine.ack(fake_id, acked_by="user")

        assert exc_info.value.notification_id == fake_id

    def test_ack_dismissed_raises(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test that acking dismissed notification raises."""
        engine.register_notification(safety_notification)
        engine.dismiss(safety_notification.notification_id)

        with pytest.raises(InvalidAckTransitionError) as exc_info:
            engine.ack(safety_notification.notification_id)

        assert exc_info.value.current_status == AckStatus.DISMISSED
        assert exc_info.value.requested_status == AckStatus.ACKED


class TestDismiss:
    """Tests for the dismiss() method."""

    def test_dismiss_success(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test successful dismissal."""
        engine.register_notification(safety_notification)

        event = engine.dismiss(
            safety_notification.notification_id,
            dismissed_by="test_user",
        )

        assert event.notification_id == safety_notification.notification_id
        assert event.ack_status == AckStatus.DISMISSED
        assert event.acked_by == "test_user"

    def test_dismiss_triggers_callback(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
        callback: MagicMock,
    ):
        """Test that dismiss triggers callback."""
        engine.register_notification(safety_notification)
        engine.dismiss(safety_notification.notification_id)

        callback.on_dismiss.assert_called_once()
        callback.on_status_change.assert_called_once()

    def test_dismiss_acked_raises(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test that dismissing acked notification raises."""
        engine.register_notification(safety_notification)
        engine.ack(safety_notification.notification_id)

        with pytest.raises(InvalidAckTransitionError) as exc_info:
            engine.dismiss(safety_notification.notification_id)

        assert exc_info.value.current_status == AckStatus.ACKED
        assert exc_info.value.requested_status == AckStatus.DISMISSED


class TestCheckAckTimeout:
    """Tests for the check_ack_timeout() method."""

    def test_timeout_pending_notification(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
        callback: MagicMock,
    ):
        """Test timeout of pending notification."""
        engine.register_notification(safety_notification)

        event = engine.check_ack_timeout(
            safety_notification.notification_id,
            safety_notification.intent,
            safety_notification.autonomy_context,
        )

        assert event is not None
        assert event.ack_status == AckStatus.TIMED_OUT
        assert event.acked_by == "system:timeout"
        callback.on_timeout.assert_called_once()

    def test_timeout_safety_live_escalates(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
        escalation_handler: MagicMock,
    ):
        """Test that SAFETY timeout in LIVE mode triggers escalation."""
        engine.register_notification(safety_notification)

        engine.check_ack_timeout(
            safety_notification.notification_id,
            safety_notification.intent,
            safety_notification.autonomy_context,
        )

        escalation_handler.escalate.assert_called_once()
        call_args = escalation_handler.escalate.call_args
        assert call_args[1]["reason"] == "SAFETY ack timeout in LIVE mode"

    def test_timeout_operational_no_escalation(
        self,
        engine: AcknowledgmentEngine,
        operational_notification: Notification,
        escalation_handler: MagicMock,
    ):
        """Test that OPERATIONAL timeout doesn't escalate."""
        engine.register_notification(operational_notification)
        engine.storage.set_ack_status(operational_notification.notification_id, AckStatus.PENDING)

        engine.check_ack_timeout(
            operational_notification.notification_id,
            operational_notification.intent,
            operational_notification.autonomy_context,
        )

        escalation_handler.escalate.assert_not_called()

    def test_timeout_already_acked_skips(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test that already acked notification skips timeout."""
        engine.register_notification(safety_notification)
        engine.ack(safety_notification.notification_id)

        event = engine.check_ack_timeout(
            safety_notification.notification_id,
            safety_notification.intent,
            safety_notification.autonomy_context,
        )

        assert event is None

    def test_can_ack_after_timeout(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test that notification can be acked after timeout."""
        engine.register_notification(safety_notification)
        engine.check_ack_timeout(
            safety_notification.notification_id,
            safety_notification.intent,
            safety_notification.autonomy_context,
        )

        # Should be able to ack after timeout
        event = engine.ack(safety_notification.notification_id, acked_by="late_user")

        assert event.ack_status == AckStatus.ACKED


class TestGetStatus:
    """Tests for the get_status() method."""

    def test_get_status_pending(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test getting pending status."""
        engine.register_notification(safety_notification)

        status = engine.get_status(safety_notification.notification_id)

        assert status == AckStatus.PENDING

    def test_get_status_not_found(
        self,
        engine: AcknowledgmentEngine,
    ):
        """Test getting status of non-existent notification."""
        fake_id = uuid4()

        status = engine.get_status(fake_id)

        assert status is None


class TestRegisterNotification:
    """Tests for the register_notification() method."""

    def test_register_with_require_ack(
        self,
        engine: AcknowledgmentEngine,
        safety_notification: Notification,
    ):
        """Test registering notification that requires ack."""
        engine.register_notification(safety_notification)

        status = engine.get_status(safety_notification.notification_id)
        notification = engine.get_notification(safety_notification.notification_id)

        assert status == AckStatus.PENDING
        assert notification is not None
        assert notification.notification_id == safety_notification.notification_id

    def test_register_without_require_ack(
        self,
        engine: AcknowledgmentEngine,
        operational_notification: Notification,
    ):
        """Test registering notification that doesn't require ack."""
        engine.register_notification(operational_notification)

        status = engine.get_status(operational_notification.notification_id)
        notification = engine.get_notification(operational_notification.notification_id)

        # No status set since require_ack=False
        assert status is None
        assert notification is not None


class TestGlobalEngine:
    """Tests for global engine configuration."""

    def test_configure_and_get(self):
        """Test configuring and getting global engine."""
        storage = InMemoryAckStorage()
        engine = configure_ack_engine(storage=storage)

        retrieved = get_ack_engine()

        assert retrieved is engine

    def test_get_unconfigured_raises(self):
        """Test that getting unconfigured engine raises."""
        # Reset global state
        import notification.acknowledgment as module

        module._ack_engine = None

        with pytest.raises(RuntimeError):
            get_ack_engine()

        # Clean up - reconfigure
        configure_ack_engine()

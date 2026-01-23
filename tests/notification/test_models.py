"""Tests for core models module.

Tests cover:
- Enum definitions and values
- Model creation and validation
- Field constraints (title/message length)
- Autonomy context requirements
- Serialization
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.notification.models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
    Priority,
    get_default_ack_timeout_minutes,
    get_default_delivery_mode,
    get_default_priority,
    get_default_require_ack,
)


class TestEnums:
    """Tests for enum definitions."""

    def test_notification_intent_values(self) -> None:
        """NotificationIntent has all required values."""
        assert NotificationIntent.SAFETY.value == "SAFETY"
        assert NotificationIntent.GOVERNANCE.value == "GOVERNANCE"
        assert NotificationIntent.OPERATIONAL.value == "OPERATIONAL"
        assert NotificationIntent.INFORMATIONAL.value == "INFORMATIONAL"

    def test_delivery_mode_values(self) -> None:
        """DeliveryMode has all required values."""
        assert DeliveryMode.GUARANTEED.value == "GUARANTEED"
        assert DeliveryMode.BEST_EFFORT.value == "BEST_EFFORT"

    def test_autonomy_mode_values(self) -> None:
        """AutonomyMode has all required values."""
        assert AutonomyMode.PREVIEW.value == "PREVIEW"
        assert AutonomyMode.SHADOW.value == "SHADOW"
        assert AutonomyMode.LIVE.value == "LIVE"

    def test_ack_status_values(self) -> None:
        """AckStatus has all required values."""
        assert AckStatus.PENDING.value == "PENDING"
        assert AckStatus.ACKED.value == "ACKED"
        assert AckStatus.DISMISSED.value == "DISMISSED"
        assert AckStatus.TIMED_OUT.value == "TIMED_OUT"

    def test_channel_values(self) -> None:
        """Channel has all required values."""
        assert Channel.SLACK.value == "SLACK"
        assert Channel.EMAIL.value == "EMAIL"
        assert Channel.WEBSOCKET.value == "WEBSOCKET"
        assert Channel.PAGERDUTY.value == "PAGERDUTY"

    def test_priority_values(self) -> None:
        """Priority has all required values."""
        assert Priority.HIGH.value == "HIGH"
        assert Priority.NORMAL.value == "NORMAL"
        assert Priority.LOW.value == "LOW"

    def test_delivery_status_values(self) -> None:
        """DeliveryStatus has all required values."""
        assert DeliveryStatus.PENDING.value == "PENDING"
        assert DeliveryStatus.DELIVERED.value == "DELIVERED"
        assert DeliveryStatus.FAILED.value == "FAILED"
        assert DeliveryStatus.DEDUPLICATED.value == "DEDUPLICATED"
        assert DeliveryStatus.RATE_LIMITED.value == "RATE_LIMITED"


class TestAutonomyContext:
    """Tests for AutonomyContext model."""

    def test_create_minimal(self) -> None:
        """Create with only required fields."""
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=agent_id,
        )
        assert context.autonomy_mode == AutonomyMode.PREVIEW
        assert context.agent_id == agent_id
        assert context.plan_id is None
        assert context.decision_snapshot_id is None

    def test_create_full(self) -> None:
        """Create with all fields."""
        agent_id = uuid4()
        plan_id = uuid4()
        decision_id = uuid4()
        exec_id = uuid4()
        skip_id = uuid4()

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
            plan_id=plan_id,
            decision_snapshot_id=decision_id,
            execution_snapshot_id=exec_id,
            skip_snapshot_id=skip_id,
        )

        assert context.autonomy_mode == AutonomyMode.LIVE
        assert context.agent_id == agent_id
        assert context.plan_id == plan_id
        assert context.decision_snapshot_id == decision_id
        assert context.execution_snapshot_id == exec_id
        assert context.skip_snapshot_id == skip_id

    def test_missing_required_fields(self) -> None:
        """Raises error when required fields missing."""
        with pytest.raises(ValidationError):
            AutonomyContext()  # type: ignore

        with pytest.raises(ValidationError):
            AutonomyContext(autonomy_mode=AutonomyMode.LIVE)  # type: ignore

    def test_immutable(self) -> None:
        """Context is frozen (immutable)."""
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )
        with pytest.raises(ValidationError):
            context.autonomy_mode = AutonomyMode.LIVE  # type: ignore


class TestNotification:
    """Tests for Notification model."""

    @pytest.fixture
    def valid_context(self) -> AutonomyContext:
        """Create a valid autonomy context for tests."""
        return AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

    def test_create_minimal(self, valid_context: AutonomyContext) -> None:
        """Create notification with only required fields."""
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test Title",
            message="Test message",
            source="test-service",
        )
        assert notification.notification_type == "test.event"
        assert notification.intent == NotificationIntent.INFORMATIONAL
        assert notification.autonomy_context == valid_context
        assert notification.title == "Test Title"
        assert notification.message == "Test message"
        assert notification.source == "test-service"
        assert notification.notification_id is not None
        assert notification.created_at is not None

    def test_create_full(self, valid_context: AutonomyContext) -> None:
        """Create notification with all fields."""
        notification = Notification(
            notification_type="trading.order.executed",
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            irreversible=True,
            autonomy_context=valid_context,
            require_ack=True,
            ack_timeout_minutes=15,
            priority=Priority.HIGH,
            title="Order Executed",
            message="Your order has been executed.",
            metadata={"order_id": "12345"},
            channels=[Channel.SLACK, Channel.WEBSOCKET],
            dedup_key="order-12345",
            source="trading-engine",
            correlation_id="corr-abc",
        )
        assert notification.irreversible is True
        assert notification.require_ack is True
        assert notification.ack_timeout_minutes == 15
        assert notification.priority == Priority.HIGH
        assert notification.metadata == {"order_id": "12345"}
        assert notification.channels == [Channel.SLACK, Channel.WEBSOCKET]
        assert notification.dedup_key == "order-12345"
        assert notification.correlation_id == "corr-abc"

    def test_autonomy_context_required(self) -> None:
        """Hard guard: autonomy_context must not be None."""
        with pytest.raises(ValidationError):
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                title="Test",
                message="Test message",
                source="test",
                # autonomy_context missing
            )

    def test_title_max_length(self, valid_context: AutonomyContext) -> None:
        """Title must be <= 200 characters."""
        # Valid: exactly 200 chars
        Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="a" * 200,
            message="Test",
            source="test",
        )

        # Invalid: 201 chars
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                autonomy_context=valid_context,
                title="a" * 201,
                message="Test",
                source="test",
            )
        assert "title" in str(exc_info.value).lower()

    def test_message_max_length(self, valid_context: AutonomyContext) -> None:
        """Message must be <= 4000 characters."""
        # Valid: exactly 4000 chars
        Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="a" * 4000,
            source="test",
        )

        # Invalid: 4001 chars
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                autonomy_context=valid_context,
                title="Test",
                message="a" * 4001,
                source="test",
            )
        assert "message" in str(exc_info.value).lower()

    def test_serialization(self, valid_context: AutonomyContext) -> None:
        """Notification can be serialized to dict/JSON."""
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message",
            source="test",
        )
        data = notification.model_dump()
        assert data["notification_type"] == "test.event"
        assert data["intent"] == "INFORMATIONAL"
        assert data["title"] == "Test"

        # Can serialize to JSON
        json_str = notification.model_dump_json()
        assert "test.event" in json_str


class TestNotificationResult:
    """Tests for NotificationResult model."""

    def test_create_result(self) -> None:
        """Create a notification result."""
        notification_id = uuid4()
        now = datetime.now(UTC)
        result = NotificationResult(
            notification_id=notification_id,
            status=DeliveryStatus.DELIVERED,
            channels_attempted=[Channel.SLACK, Channel.WEBSOCKET],
            channels_succeeded=[Channel.SLACK, Channel.WEBSOCKET],
            channels_failed=[],
            delivered_at=now,
        )
        assert result.notification_id == notification_id
        assert result.status == DeliveryStatus.DELIVERED
        assert result.channels_succeeded == [Channel.SLACK, Channel.WEBSOCKET]
        assert result.error_message is None

    def test_failed_result(self) -> None:
        """Create a failed result with error message."""
        result = NotificationResult(
            notification_id=uuid4(),
            status=DeliveryStatus.FAILED,
            channels_attempted=[Channel.SLACK],
            channels_failed=[Channel.SLACK],
            error_message="Slack API error: rate limited",
        )
        assert result.status == DeliveryStatus.FAILED
        assert result.error_message == "Slack API error: rate limited"


class TestAckEvent:
    """Tests for AckEvent model."""

    def test_create_ack_event(self) -> None:
        """Create an acknowledgment event."""
        notification_id = uuid4()
        event = AckEvent(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="user@example.com",
            metadata={"reason": "acknowledged"},
        )
        assert event.notification_id == notification_id
        assert event.ack_status == AckStatus.ACKED
        assert event.acked_by == "user@example.com"
        assert event.acked_at is not None

    def test_create_timeout_event(self) -> None:
        """Create a timeout event (no acked_by)."""
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.TIMED_OUT,
        )
        assert event.ack_status == AckStatus.TIMED_OUT
        assert event.acked_by is None


class TestDefaultDerivationFunctions:
    """Tests for default value derivation helper functions."""

    def test_get_default_delivery_mode(self) -> None:
        """Delivery mode derivation based on intent."""
        safety = get_default_delivery_mode(NotificationIntent.SAFETY)
        assert safety == DeliveryMode.GUARANTEED
        governance = get_default_delivery_mode(NotificationIntent.GOVERNANCE)
        assert governance == DeliveryMode.GUARANTEED
        operational = get_default_delivery_mode(NotificationIntent.OPERATIONAL)
        assert operational == DeliveryMode.BEST_EFFORT
        informational = get_default_delivery_mode(NotificationIntent.INFORMATIONAL)
        assert informational == DeliveryMode.BEST_EFFORT

    def test_get_default_priority(self) -> None:
        """Priority derivation based on intent."""
        assert get_default_priority(NotificationIntent.SAFETY) == Priority.HIGH
        assert get_default_priority(NotificationIntent.GOVERNANCE) == Priority.HIGH
        assert get_default_priority(NotificationIntent.OPERATIONAL) == Priority.NORMAL
        assert get_default_priority(NotificationIntent.INFORMATIONAL) == Priority.LOW

    def test_get_default_ack_timeout_minutes(self) -> None:
        """Ack timeout derivation based on intent."""
        assert get_default_ack_timeout_minutes(NotificationIntent.SAFETY) == 15
        assert get_default_ack_timeout_minutes(NotificationIntent.GOVERNANCE) == 30
        assert get_default_ack_timeout_minutes(NotificationIntent.OPERATIONAL) is None
        assert get_default_ack_timeout_minutes(NotificationIntent.INFORMATIONAL) is None

    def test_get_default_require_ack(self) -> None:
        """Require ack derivation based on intent + mode."""
        # SAFETY + LIVE = True
        result = get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.LIVE)
        assert result is True

        # SAFETY + non-LIVE = False
        preview = get_default_require_ack(
            NotificationIntent.SAFETY, AutonomyMode.PREVIEW
        )
        assert preview is False
        shadow = get_default_require_ack(
            NotificationIntent.SAFETY, AutonomyMode.SHADOW
        )
        assert shadow is False

        # Non-SAFETY = always False by default
        gov = get_default_require_ack(
            NotificationIntent.GOVERNANCE, AutonomyMode.LIVE
        )
        assert gov is False
        op = get_default_require_ack(
            NotificationIntent.OPERATIONAL, AutonomyMode.LIVE
        )
        assert op is False
        info = get_default_require_ack(
            NotificationIntent.INFORMATIONAL, AutonomyMode.LIVE
        )
        assert info is False

"""Tests for core notification models.

These tests verify the data contracts defined in the PRD.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from notification.models import (
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
)


class TestEnums:
    """Tests for enum definitions."""

    def test_notification_intent_values(self) -> None:
        """Verify NotificationIntent has required values."""
        assert NotificationIntent.SAFETY == "SAFETY"
        assert NotificationIntent.GOVERNANCE == "GOVERNANCE"
        assert NotificationIntent.OPERATIONAL == "OPERATIONAL"
        assert NotificationIntent.INFORMATIONAL == "INFORMATIONAL"

    def test_delivery_mode_values(self) -> None:
        """Verify DeliveryMode has required values."""
        assert DeliveryMode.GUARANTEED == "GUARANTEED"
        assert DeliveryMode.BEST_EFFORT == "BEST_EFFORT"

    def test_autonomy_mode_values(self) -> None:
        """Verify AutonomyMode has required values."""
        assert AutonomyMode.PREVIEW == "PREVIEW"
        assert AutonomyMode.SHADOW == "SHADOW"
        assert AutonomyMode.LIVE == "LIVE"

    def test_ack_status_values(self) -> None:
        """Verify AckStatus has required values."""
        assert AckStatus.PENDING == "PENDING"
        assert AckStatus.ACKED == "ACKED"
        assert AckStatus.DISMISSED == "DISMISSED"
        assert AckStatus.TIMED_OUT == "TIMED_OUT"

    def test_channel_values(self) -> None:
        """Verify Channel has required values."""
        assert Channel.SLACK == "SLACK"
        assert Channel.EMAIL == "EMAIL"
        assert Channel.WEBSOCKET == "WEBSOCKET"
        assert Channel.PAGERDUTY == "PAGERDUTY"

    def test_priority_values(self) -> None:
        """Verify Priority has required values."""
        assert Priority.HIGH == "HIGH"
        assert Priority.NORMAL == "NORMAL"
        assert Priority.LOW == "LOW"

    def test_delivery_status_values(self) -> None:
        """Verify DeliveryStatus has required values."""
        assert DeliveryStatus.SUCCESS == "SUCCESS"
        assert DeliveryStatus.FAILED == "FAILED"
        assert DeliveryStatus.DEDUPLICATED == "DEDUPLICATED"
        assert DeliveryStatus.RATE_LIMITED == "RATE_LIMITED"


class TestAutonomyContext:
    """Tests for AutonomyContext model."""

    def test_required_fields(self) -> None:
        """Test that required fields are enforced."""
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )
        assert context.autonomy_mode == AutonomyMode.LIVE
        assert context.agent_id == agent_id

    def test_optional_fields_default_to_none(self) -> None:
        """Test that optional fields default to None."""
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )
        assert context.plan_id is None
        assert context.decision_snapshot_id is None
        assert context.execution_snapshot_id is None
        assert context.skip_snapshot_id is None

    def test_all_fields_populated(self) -> None:
        """Test creating context with all fields."""
        agent_id = uuid4()
        plan_id = uuid4()
        decision_id = uuid4()
        execution_id = uuid4()
        skip_id = uuid4()

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.SHADOW,
            agent_id=agent_id,
            plan_id=plan_id,
            decision_snapshot_id=decision_id,
            execution_snapshot_id=execution_id,
            skip_snapshot_id=skip_id,
        )

        assert context.agent_id == agent_id
        assert context.plan_id == plan_id
        assert context.decision_snapshot_id == decision_id
        assert context.execution_snapshot_id == execution_id
        assert context.skip_snapshot_id == skip_id

    def test_context_is_immutable(self) -> None:
        """Test that AutonomyContext is frozen/immutable."""
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        with pytest.raises(ValidationError):
            context.autonomy_mode = AutonomyMode.PREVIEW

    def test_missing_required_field_raises(self) -> None:
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError):
            AutonomyContext(autonomy_mode=AutonomyMode.LIVE)  # Missing agent_id


class TestNotification:
    """Tests for Notification model."""

    @pytest.fixture
    def valid_context(self) -> AutonomyContext:
        """Create a valid AutonomyContext for testing."""
        return AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

    def test_minimal_notification(self, valid_context: AutonomyContext) -> None:
        """Test creating notification with minimal required fields."""
        notification = Notification(
            notification_type="trading.order_placed",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Order Placed",
            message="An order has been placed.",
            source="order_service",
        )
        assert notification.notification_type == "trading.order_placed"
        assert notification.intent == NotificationIntent.OPERATIONAL
        assert notification.title == "Order Placed"

    def test_notification_id_auto_generated(self, valid_context: AutonomyContext) -> None:
        """Test that notification_id is auto-generated."""
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message",
            source="test",
        )
        assert notification.notification_id is not None

    def test_created_at_auto_generated(self, valid_context: AutonomyContext) -> None:
        """Test that created_at is auto-generated."""
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message",
            source="test",
        )
        assert notification.created_at is not None
        assert isinstance(notification.created_at, datetime)

    def test_title_max_length_enforced(self, valid_context: AutonomyContext) -> None:
        """Test that title max length (200) is enforced."""
        long_title = "x" * 201
        with pytest.raises(ValidationError):
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                autonomy_context=valid_context,
                title=long_title,
                message="Test message",
                source="test",
            )

    def test_title_at_max_length_ok(self, valid_context: AutonomyContext) -> None:
        """Test that title at exactly 200 chars is valid."""
        title_200 = "x" * 200
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title=title_200,
            message="Test message",
            source="test",
        )
        assert len(notification.title) == 200

    def test_message_max_length_enforced(self, valid_context: AutonomyContext) -> None:
        """Test that message max length (4000) is enforced."""
        long_message = "x" * 4001
        with pytest.raises(ValidationError):
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                autonomy_context=valid_context,
                title="Test",
                message=long_message,
                source="test",
            )

    def test_message_at_max_length_ok(self, valid_context: AutonomyContext) -> None:
        """Test that message at exactly 4000 chars is valid."""
        message_4000 = "x" * 4000
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message=message_4000,
            source="test",
        )
        assert len(notification.message) == 4000

    def test_autonomy_context_required(self) -> None:
        """Test that autonomy_context is required (hard guard)."""
        with pytest.raises(ValidationError):
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                title="Test",
                message="Test message",
                source="test",
                # Missing autonomy_context
            )

    def test_default_values(self, valid_context: AutonomyContext) -> None:
        """Test default values for optional fields."""
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message",
            source="test",
        )
        assert notification.irreversible is False
        assert notification.delivery_mode is None  # Derived later
        assert notification.require_ack is None  # Derived later
        assert notification.channels == []
        assert notification.metadata == {}

    def test_serialization(self, valid_context: AutonomyContext) -> None:
        """Test that notification can be serialized to dict/JSON."""
        notification = Notification(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message",
            source="test",
        )
        data = notification.model_dump()
        assert isinstance(data, dict)
        assert data["notification_type"] == "test.event"
        assert data["intent"] == "INFORMATIONAL"


class TestNotificationResult:
    """Tests for NotificationResult model."""

    def test_create_success_result(self) -> None:
        """Test creating a success result."""
        notification_id = uuid4()
        result = NotificationResult(
            notification_id=notification_id,
            status=DeliveryStatus.SUCCESS,
            channels_attempted=[Channel.SLACK, Channel.EMAIL],
            channels_succeeded=[Channel.SLACK, Channel.EMAIL],
        )
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_succeeded

    def test_create_failed_result(self) -> None:
        """Test creating a failed result."""
        result = NotificationResult(
            notification_id=uuid4(),
            status=DeliveryStatus.FAILED,
            channels_attempted=[Channel.SLACK],
            channels_failed=[Channel.SLACK],
            error_message="Slack API error",
        )
        assert result.status == DeliveryStatus.FAILED
        assert result.error_message == "Slack API error"

    def test_create_deduplicated_result(self) -> None:
        """Test creating a deduplicated result."""
        result = NotificationResult(
            notification_id=uuid4(),
            status=DeliveryStatus.DEDUPLICATED,
        )
        assert result.status == DeliveryStatus.DEDUPLICATED
        assert result.channels_attempted == []


class TestAckEvent:
    """Tests for AckEvent model."""

    def test_create_ack_event(self) -> None:
        """Test creating an acknowledgment event."""
        notification_id = uuid4()
        event = AckEvent(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="operator@example.com",
        )
        assert event.notification_id == notification_id
        assert event.ack_status == AckStatus.ACKED
        assert event.acked_by == "operator@example.com"

    def test_acked_at_auto_generated(self) -> None:
        """Test that acked_at is auto-generated."""
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.ACKED,
        )
        assert event.acked_at is not None
        assert isinstance(event.acked_at, datetime)

    def test_metadata_default_empty(self) -> None:
        """Test that metadata defaults to empty dict."""
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.PENDING,
        )
        assert event.metadata == {}

    def test_ack_event_with_metadata(self) -> None:
        """Test creating ack event with metadata."""
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.ACKED,
            acked_by="user",
            metadata={"action": "approved", "notes": "LGTM"},
        )
        assert event.metadata["action"] == "approved"

"""Unit tests for core enums and models.

Tests cover:
- Enum value correctness
- Model validation guards (autonomy_context required, title/message length)
- Derived field computation (delivery_mode, priority, ack_timeout)
- Serialization (model_dump / JSON)
- Invariants from PRD
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.notification.models import (
    DEFAULT_ACK_TIMEOUTS,
    INTENT_DELIVERY_MODE_MAP,
    INTENT_PRIORITY_MAP,
    MESSAGE_MAX_LENGTH,
    TITLE_MAX_LENGTH,
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


class TestNotificationIntentEnum:
    """Tests for NotificationIntent enum."""

    def test_all_values_present(self):
        assert NotificationIntent.SAFETY.value == "SAFETY"
        assert NotificationIntent.GOVERNANCE.value == "GOVERNANCE"
        assert NotificationIntent.OPERATIONAL.value == "OPERATIONAL"
        assert NotificationIntent.INFORMATIONAL.value == "INFORMATIONAL"

    def test_enum_is_string(self):
        """Enum values should be strings for JSON serialization."""
        for intent in NotificationIntent:
            assert isinstance(intent.value, str)


class TestDeliveryModeEnum:
    """Tests for DeliveryMode enum."""

    def test_all_values_present(self):
        assert DeliveryMode.GUARANTEED.value == "GUARANTEED"
        assert DeliveryMode.BEST_EFFORT.value == "BEST_EFFORT"

    def test_intent_delivery_mode_invariants(self):
        """SAFETY and GOVERNANCE should map to GUARANTEED."""
        assert INTENT_DELIVERY_MODE_MAP[NotificationIntent.SAFETY] == DeliveryMode.GUARANTEED
        assert INTENT_DELIVERY_MODE_MAP[NotificationIntent.GOVERNANCE] == DeliveryMode.GUARANTEED
        assert INTENT_DELIVERY_MODE_MAP[NotificationIntent.OPERATIONAL] == DeliveryMode.BEST_EFFORT
        assert (
            INTENT_DELIVERY_MODE_MAP[NotificationIntent.INFORMATIONAL] == DeliveryMode.BEST_EFFORT
        )


class TestAutonomyModeEnum:
    """Tests for AutonomyMode enum."""

    def test_all_values_present(self):
        assert AutonomyMode.PREVIEW.value == "PREVIEW"
        assert AutonomyMode.SHADOW.value == "SHADOW"
        assert AutonomyMode.LIVE.value == "LIVE"


class TestAckStatusEnum:
    """Tests for AckStatus enum."""

    def test_all_values_present(self):
        assert AckStatus.PENDING.value == "PENDING"
        assert AckStatus.ACKED.value == "ACKED"
        assert AckStatus.DISMISSED.value == "DISMISSED"
        assert AckStatus.TIMED_OUT.value == "TIMED_OUT"


class TestChannelEnum:
    """Tests for Channel enum."""

    def test_all_values_present(self):
        assert Channel.SLACK.value == "SLACK"
        assert Channel.EMAIL.value == "EMAIL"
        assert Channel.WEBSOCKET.value == "WEBSOCKET"
        assert Channel.PAGERDUTY.value == "PAGERDUTY"


class TestPriorityEnum:
    """Tests for Priority enum."""

    def test_all_values_present(self):
        assert Priority.HIGH.value == "HIGH"
        assert Priority.NORMAL.value == "NORMAL"
        assert Priority.LOW.value == "LOW"

    def test_intent_priority_mapping(self):
        """SAFETY and GOVERNANCE should be HIGH priority."""
        assert INTENT_PRIORITY_MAP[NotificationIntent.SAFETY] == Priority.HIGH
        assert INTENT_PRIORITY_MAP[NotificationIntent.GOVERNANCE] == Priority.HIGH
        assert INTENT_PRIORITY_MAP[NotificationIntent.OPERATIONAL] == Priority.NORMAL
        assert INTENT_PRIORITY_MAP[NotificationIntent.INFORMATIONAL] == Priority.LOW


class TestDeliveryStatusEnum:
    """Tests for DeliveryStatus enum."""

    def test_all_values_present(self):
        assert DeliveryStatus.PENDING.value == "PENDING"
        assert DeliveryStatus.DELIVERED.value == "DELIVERED"
        assert DeliveryStatus.FAILED.value == "FAILED"
        assert DeliveryStatus.DEDUPLICATED.value == "DEDUPLICATED"
        assert DeliveryStatus.RATE_LIMITED.value == "RATE_LIMITED"


class TestAutonomyContext:
    """Tests for AutonomyContext model."""

    def test_valid_minimal_context(self):
        ctx = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        assert ctx.autonomy_mode == AutonomyMode.LIVE
        assert ctx.plan_id is None
        assert ctx.decision_snapshot_id is None

    def test_valid_full_context(self):
        agent_id = uuid4()
        plan_id = uuid4()
        decision_id = uuid4()
        execution_id = uuid4()
        skip_id = uuid4()

        ctx = AutonomyContext(
            autonomy_mode=AutonomyMode.SHADOW,
            agent_id=agent_id,
            plan_id=plan_id,
            decision_snapshot_id=decision_id,
            execution_snapshot_id=execution_id,
            skip_snapshot_id=skip_id,
        )

        assert ctx.agent_id == agent_id
        assert ctx.plan_id == plan_id
        assert ctx.decision_snapshot_id == decision_id
        assert ctx.execution_snapshot_id == execution_id
        assert ctx.skip_snapshot_id == skip_id

    def test_missing_autonomy_mode_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            AutonomyContext(agent_id=uuid4())
        assert "autonomy_mode" in str(exc_info.value)

    def test_missing_agent_id_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            AutonomyContext(autonomy_mode=AutonomyMode.LIVE)
        assert "agent_id" in str(exc_info.value)

    def test_serialization(self):
        agent_id = uuid4()
        ctx = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=agent_id,
        )
        data = ctx.model_dump()
        assert data["autonomy_mode"] == "PREVIEW"
        assert data["agent_id"] == agent_id

    def test_json_serialization(self):
        ctx = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        json_str = ctx.model_dump_json()
        assert "LIVE" in json_str

    def test_immutability(self):
        ctx = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )
        with pytest.raises(ValidationError):
            ctx.autonomy_mode = AutonomyMode.SHADOW


class TestNotification:
    """Tests for Notification model."""

    @pytest.fixture
    def valid_context(self):
        return AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

    def test_valid_minimal_notification(self, valid_context):
        notif = Notification(
            notification_type="trading.order_placed",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Order Placed",
            message="Order 12345 has been placed.",
            source="order-service",
        )
        assert notif.notification_id is not None
        assert notif.created_at is not None
        assert notif.irreversible is False
        assert notif.metadata == {}

    def test_derived_delivery_mode_safety(self, valid_context):
        """SAFETY intent should derive GUARANTEED delivery mode."""
        notif = Notification(
            notification_type="risk.breach_detected",
            intent=NotificationIntent.SAFETY,
            autonomy_context=valid_context,
            title="Risk Breach",
            message="Position limit exceeded.",
            source="risk-service",
        )
        assert notif.delivery_mode == DeliveryMode.GUARANTEED

    def test_derived_delivery_mode_informational(self, valid_context):
        """INFORMATIONAL intent should derive BEST_EFFORT delivery mode."""
        notif = Notification(
            notification_type="report.generated",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Report Ready",
            message="Daily report is available.",
            source="reporting-service",
        )
        assert notif.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_derived_priority(self, valid_context):
        """Priority should be derived from intent."""
        safety_notif = Notification(
            notification_type="risk.breach",
            intent=NotificationIntent.SAFETY,
            autonomy_context=valid_context,
            title="Alert",
            message="Critical alert.",
            source="test",
        )
        assert safety_notif.priority == Priority.HIGH

        info_notif = Notification(
            notification_type="info.update",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=valid_context,
            title="Info",
            message="FYI message.",
            source="test",
        )
        assert info_notif.priority == Priority.LOW

    def test_derived_ack_timeout_safety(self, valid_context):
        """SAFETY intent should have 15 minute ack timeout by default."""
        notif = Notification(
            notification_type="risk.breach",
            intent=NotificationIntent.SAFETY,
            autonomy_context=valid_context,
            title="Alert",
            message="Critical alert.",
            source="test",
        )
        assert notif.ack_timeout_minutes == DEFAULT_ACK_TIMEOUTS[NotificationIntent.SAFETY]
        assert notif.ack_timeout_minutes == 15

    def test_derived_ack_timeout_governance(self, valid_context):
        """GOVERNANCE intent should have 30 minute ack timeout by default."""
        notif = Notification(
            notification_type="compliance.review",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=valid_context,
            title="Review Required",
            message="Compliance review needed.",
            source="test",
        )
        assert notif.ack_timeout_minutes == DEFAULT_ACK_TIMEOUTS[NotificationIntent.GOVERNANCE]
        assert notif.ack_timeout_minutes == 30

    def test_no_ack_timeout_for_operational(self, valid_context):
        """OPERATIONAL intent should not have default ack timeout."""
        notif = Notification(
            notification_type="ops.status",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Status Update",
            message="System status changed.",
            source="test",
        )
        assert notif.ack_timeout_minutes is None

    def test_explicit_delivery_mode_overrides_default(self, valid_context):
        """Explicitly set delivery_mode should not be overridden."""
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.SAFETY,
            autonomy_context=valid_context,
            title="Test",
            message="Test message.",
            source="test",
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )
        assert notif.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_missing_autonomy_context_raises(self):
        """Hard guard: autonomy_context is required."""
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.OPERATIONAL,
                title="Test",
                message="Test message.",
                source="test",
            )
        assert "autonomy_context" in str(exc_info.value)

    def test_title_max_length_validation(self, valid_context):
        """Title must be at most 200 characters."""
        long_title = "x" * (TITLE_MAX_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.OPERATIONAL,
                autonomy_context=valid_context,
                title=long_title,
                message="Test message.",
                source="test",
            )
        assert "title" in str(exc_info.value).lower()

    def test_title_at_max_length_valid(self, valid_context):
        """Title at exactly max length should be valid."""
        max_title = "x" * TITLE_MAX_LENGTH
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title=max_title,
            message="Test message.",
            source="test",
        )
        assert len(notif.title) == TITLE_MAX_LENGTH

    def test_message_max_length_validation(self, valid_context):
        """Message must be at most 4000 characters."""
        long_message = "y" * (MESSAGE_MAX_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.OPERATIONAL,
                autonomy_context=valid_context,
                title="Test",
                message=long_message,
                source="test",
            )
        assert "message" in str(exc_info.value).lower()

    def test_message_at_max_length_valid(self, valid_context):
        """Message at exactly max length should be valid."""
        max_message = "y" * MESSAGE_MAX_LENGTH
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message=max_message,
            source="test",
        )
        assert len(notif.message) == MESSAGE_MAX_LENGTH

    def test_empty_notification_type_raises(self, valid_context):
        """notification_type must not be empty."""
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="",
                intent=NotificationIntent.OPERATIONAL,
                autonomy_context=valid_context,
                title="Test",
                message="Test message.",
                source="test",
            )
        assert "notification_type" in str(exc_info.value)

    def test_empty_source_raises(self, valid_context):
        """source must not be empty."""
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.OPERATIONAL,
                autonomy_context=valid_context,
                title="Test",
                message="Test message.",
                source="",
            )
        assert "source" in str(exc_info.value)

    def test_serialization(self, valid_context):
        """Notification should serialize to dict correctly."""
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.SAFETY,
            autonomy_context=valid_context,
            title="Test Title",
            message="Test message content.",
            source="test-service",
            irreversible=True,
            metadata={"key": "value"},
            correlation_id="corr-123",
        )

        data = notif.model_dump()
        assert data["notification_type"] == "test.event"
        assert data["intent"] == "SAFETY"
        assert data["title"] == "Test Title"
        assert data["irreversible"] is True
        assert data["metadata"] == {"key": "value"}
        assert data["correlation_id"] == "corr-123"
        assert "autonomy_context" in data

    def test_json_serialization(self, valid_context):
        """Notification should serialize to JSON correctly."""
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message.",
            source="test",
        )

        json_str = notif.model_dump_json()
        assert "test.event" in json_str
        assert "OPERATIONAL" in json_str

    def test_notification_id_auto_generated(self, valid_context):
        """notification_id should be auto-generated as UUID."""
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message.",
            source="test",
        )
        assert isinstance(notif.notification_id, UUID)

    def test_created_at_auto_generated(self, valid_context):
        """created_at should be auto-generated."""
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message.",
            source="test",
        )
        assert isinstance(notif.created_at, datetime)

    def test_immutability(self, valid_context):
        """Notification should be immutable (frozen)."""
        notif = Notification(
            notification_type="test.event",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=valid_context,
            title="Test",
            message="Test message.",
            source="test",
        )
        with pytest.raises(ValidationError):
            notif.title = "New Title"


class TestNotificationResult:
    """Tests for NotificationResult model."""

    def test_valid_result(self):
        notif_id = uuid4()
        result = NotificationResult(
            notification_id=notif_id,
            status=DeliveryStatus.DELIVERED,
            channels_attempted=[Channel.SLACK, Channel.WEBSOCKET],
            channels_succeeded=[Channel.SLACK, Channel.WEBSOCKET],
            channels_failed=[],
            delivered_at=datetime.now(UTC),
        )
        assert result.notification_id == notif_id
        assert result.status == DeliveryStatus.DELIVERED
        assert Channel.SLACK in result.channels_succeeded

    def test_failed_result(self):
        result = NotificationResult(
            notification_id=uuid4(),
            status=DeliveryStatus.FAILED,
            channels_attempted=[Channel.SLACK],
            channels_succeeded=[],
            channels_failed=[Channel.SLACK],
            error_message="Slack API error: rate limited",
        )
        assert result.status == DeliveryStatus.FAILED
        assert result.error_message is not None

    def test_deduplicated_result(self):
        result = NotificationResult(
            notification_id=uuid4(),
            status=DeliveryStatus.DEDUPLICATED,
            deduplicated=True,
        )
        assert result.status == DeliveryStatus.DEDUPLICATED
        assert result.deduplicated is True

    def test_serialization(self):
        result = NotificationResult(
            notification_id=uuid4(),
            status=DeliveryStatus.DELIVERED,
        )
        data = result.model_dump()
        assert data["status"] == "DELIVERED"


class TestAckEvent:
    """Tests for AckEvent model."""

    def test_valid_ack_event(self):
        notif_id = uuid4()
        event = AckEvent(
            notification_id=notif_id,
            status=AckStatus.ACKED,
            acked_by="user@example.com",
            metadata={"channel": "slack"},
        )
        assert event.notification_id == notif_id
        assert event.status == AckStatus.ACKED
        assert event.acked_by == "user@example.com"
        assert event.acked_at is not None

    def test_timeout_event(self):
        event = AckEvent(
            notification_id=uuid4(),
            status=AckStatus.TIMED_OUT,
        )
        assert event.status == AckStatus.TIMED_OUT
        assert event.acked_by is None

    def test_dismissed_event(self):
        event = AckEvent(
            notification_id=uuid4(),
            status=AckStatus.DISMISSED,
            acked_by="admin@example.com",
            metadata={"reason": "false_positive"},
        )
        assert event.status == AckStatus.DISMISSED
        assert event.metadata["reason"] == "false_positive"

    def test_serialization(self):
        event = AckEvent(
            notification_id=uuid4(),
            status=AckStatus.ACKED,
            acked_by="user@example.com",
        )
        data = event.model_dump()
        assert data["status"] == "ACKED"
        assert data["acked_by"] == "user@example.com"

    def test_json_serialization(self):
        event = AckEvent(
            notification_id=uuid4(),
            status=AckStatus.PENDING,
        )
        json_str = event.model_dump_json()
        assert "PENDING" in json_str


class TestInvariants:
    """Tests for PRD-defined invariants."""

    @pytest.fixture
    def live_context(self):
        return AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

    def test_safety_implies_guaranteed(self, live_context):
        """Invariant: SAFETY -> GUARANTEED delivery mode."""
        notif = Notification(
            notification_type="risk.alert",
            intent=NotificationIntent.SAFETY,
            autonomy_context=live_context,
            title="Safety Alert",
            message="Critical safety issue detected.",
            source="safety-service",
        )
        assert notif.delivery_mode == DeliveryMode.GUARANTEED

    def test_governance_implies_guaranteed(self, live_context):
        """Invariant: GOVERNANCE -> GUARANTEED delivery mode."""
        notif = Notification(
            notification_type="compliance.review",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=live_context,
            title="Compliance Review",
            message="Review required for trade.",
            source="compliance-service",
        )
        assert notif.delivery_mode == DeliveryMode.GUARANTEED

    def test_operational_implies_best_effort(self, live_context):
        """Invariant: OPERATIONAL -> BEST_EFFORT delivery mode."""
        notif = Notification(
            notification_type="ops.status",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=live_context,
            title="Status Update",
            message="System status changed.",
            source="ops-service",
        )
        assert notif.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_informational_implies_best_effort(self, live_context):
        """Invariant: INFORMATIONAL -> BEST_EFFORT delivery mode."""
        notif = Notification(
            notification_type="report.ready",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=live_context,
            title="Report Available",
            message="Your daily report is ready.",
            source="reporting-service",
        )
        assert notif.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_autonomy_context_hard_guard(self):
        """Hard guard: Notification creation MUST FAIL if autonomy_context is missing."""
        with pytest.raises(ValidationError) as exc_info:
            Notification(
                notification_type="test.event",
                intent=NotificationIntent.OPERATIONAL,
                title="Test",
                message="Test message.",
                source="test",
            )
        errors = exc_info.value.errors()
        assert any("autonomy_context" in str(e) for e in errors)

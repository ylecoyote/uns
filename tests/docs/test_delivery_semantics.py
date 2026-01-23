"""Tests for delivery-semantics.md documentation.

Tests cover:
- Document structure and completeness
- Truth table accuracy (intent × delivery_mode × autonomy_mode → channels)
- GUARANTEED delivery invariants
- BEST_EFFORT delivery invariants
- DLQ visibility and escalation behavior
"""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.adapters.base import (
    AdapterStatus,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)
from notification.deduplication import (
    InMemoryDeduplicationStore,
    configure_deduplication_engine,
)
from notification.models import (
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
)
from notification.policies import (
    PolicyRegistry,
    configure_policy_registry,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
)
from notification.rate_limiting import (
    RateLimitConfig,
    configure_rate_limiter,
)
from notification.service import (
    PERSISTENT_CHANNELS_FALLBACK_ORDER,
    DeliveryError,
    DeliveryService,
    SimpleAdapterRegistry,
)

# Path to the delivery semantics documentation
DELIVERY_SEMANTICS_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "sections" / "delivery-semantics.md"
)


@pytest.fixture
def delivery_semantics_doc() -> str:
    """Load the delivery semantics documentation."""
    assert DELIVERY_SEMANTICS_PATH.exists(), (
        f"delivery-semantics.md not found at {DELIVERY_SEMANTICS_PATH}"
    )
    return DELIVERY_SEMANTICS_PATH.read_text()


class MockAdapter(BaseAdapter):
    """Mock adapter for testing delivery semantics."""

    def __init__(
        self,
        channel: Channel,
        success: bool = True,
        error: str | None = None,
    ):
        self._channel = channel
        self._success = success
        self._error = error
        self.deliver_calls: list[Notification] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        self.deliver_calls.append(notification)
        return DeliveryResult(
            success=self._success,
            channel=self._channel,
            message_id=f"msg-{notification.notification_id}" if self._success else None,
            error=self._error,
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status=AdapterStatus.HEALTHY, message="OK")


def create_notification(
    intent: NotificationIntent = NotificationIntent.OPERATIONAL,
    autonomy_mode: AutonomyMode = AutonomyMode.LIVE,
    channels: list[Channel] | None = None,
    delivery_mode: DeliveryMode | None = None,
    irreversible: bool = False,
) -> Notification:
    """Create test notification with specified properties."""
    return Notification(
        notification_type="test.notification",
        intent=intent,
        autonomy_context=AutonomyContext(
            autonomy_mode=autonomy_mode,
            agent_id=uuid4(),
        ),
        title="Test",
        message="Test message",
        source="test",
        channels=channels or [],
        delivery_mode=delivery_mode,
        irreversible=irreversible,
    )


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test."""
    configure_deduplication_engine(InMemoryDeduplicationStore())
    configure_policy_registry(PolicyRegistry())
    configure_rate_limiter({
        Channel.SLACK: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
        Channel.EMAIL: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
        Channel.WEBSOCKET: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
        Channel.PAGERDUTY: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
    })


class TestDeliverySemanticsDocExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify delivery-semantics.md exists."""
        assert DELIVERY_SEMANTICS_PATH.exists()

    def test_file_not_empty(self, delivery_semantics_doc: str) -> None:
        """Verify file is not empty."""
        assert len(delivery_semantics_doc) > 0

    def test_is_markdown(self, delivery_semantics_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in delivery_semantics_doc


class TestDeliverySemanticsDocStructure:
    """Test the structure of the delivery semantics documentation."""

    def test_has_title(self, delivery_semantics_doc: str) -> None:
        """Verify document has correct title."""
        assert delivery_semantics_doc.startswith("# Delivery Semantics")

    def test_has_overview_section(self, delivery_semantics_doc: str) -> None:
        """Verify document has overview section."""
        assert "## Overview" in delivery_semantics_doc

    def test_has_intent_delivery_mode_mapping(self, delivery_semantics_doc: str) -> None:
        """Verify document has intent to delivery mode mapping."""
        assert "## Intent × Delivery Mode Mapping" in delivery_semantics_doc

    def test_has_channel_truth_table(self, delivery_semantics_doc: str) -> None:
        """Verify document has channel routing truth table."""
        assert "## Intent × Autonomy Mode × Channels Truth Table" in delivery_semantics_doc

    def test_has_guaranteed_section(self, delivery_semantics_doc: str) -> None:
        """Verify document has GUARANTEED delivery section."""
        assert "## GUARANTEED Delivery Semantics" in delivery_semantics_doc

    def test_has_best_effort_section(self, delivery_semantics_doc: str) -> None:
        """Verify document has BEST_EFFORT delivery section."""
        assert "## BEST_EFFORT Delivery Semantics" in delivery_semantics_doc

    def test_has_dlq_section(self, delivery_semantics_doc: str) -> None:
        """Verify document has DLQ visibility section."""
        assert "## DLQ (Dead Letter Queue) Visibility" in delivery_semantics_doc

    def test_has_acknowledgment_section(self, delivery_semantics_doc: str) -> None:
        """Verify document has acknowledgment requirements."""
        assert "## Acknowledgment Requirements" in delivery_semantics_doc


class TestDeliverySemanticsDocContent:
    """Test the content completeness of the documentation."""

    def test_documents_all_intents(self, delivery_semantics_doc: str) -> None:
        """Verify all intents are documented."""
        assert "SAFETY" in delivery_semantics_doc
        assert "GOVERNANCE" in delivery_semantics_doc
        assert "OPERATIONAL" in delivery_semantics_doc
        assert "INFORMATIONAL" in delivery_semantics_doc

    def test_documents_all_delivery_modes(self, delivery_semantics_doc: str) -> None:
        """Verify both delivery modes are documented."""
        assert "GUARANTEED" in delivery_semantics_doc
        assert "BEST_EFFORT" in delivery_semantics_doc

    def test_documents_all_autonomy_modes(self, delivery_semantics_doc: str) -> None:
        """Verify all autonomy modes are documented."""
        assert "PREVIEW" in delivery_semantics_doc
        assert "SHADOW" in delivery_semantics_doc
        assert "LIVE" in delivery_semantics_doc

    def test_documents_all_channels(self, delivery_semantics_doc: str) -> None:
        """Verify all channels are documented."""
        assert "Slack" in delivery_semantics_doc
        assert "Email" in delivery_semantics_doc
        assert "WebSocket" in delivery_semantics_doc
        assert "PagerDuty" in delivery_semantics_doc

    def test_documents_fallback_order(self, delivery_semantics_doc: str) -> None:
        """Verify fallback order is documented."""
        assert "Slack" in delivery_semantics_doc
        assert "Email" in delivery_semantics_doc
        assert "PagerDuty" in delivery_semantics_doc
        assert "fallback" in delivery_semantics_doc.lower()

    def test_documents_escalation_callback(self, delivery_semantics_doc: str) -> None:
        """Verify escalation callback is documented."""
        assert "escalation_callback" in delivery_semantics_doc

    def test_documents_delivery_error(self, delivery_semantics_doc: str) -> None:
        """Verify DeliveryError is documented."""
        assert "DeliveryError" in delivery_semantics_doc


class TestIntentDeliveryModeMapping:
    """Test that intent to delivery mode mapping matches documentation."""

    @pytest.mark.parametrize(
        "intent,expected_mode",
        [
            (NotificationIntent.SAFETY, DeliveryMode.GUARANTEED),
            (NotificationIntent.GOVERNANCE, DeliveryMode.GUARANTEED),
            (NotificationIntent.OPERATIONAL, DeliveryMode.BEST_EFFORT),
            (NotificationIntent.INFORMATIONAL, DeliveryMode.BEST_EFFORT),
        ],
    )
    def test_intent_maps_to_delivery_mode(
        self, intent: NotificationIntent, expected_mode: DeliveryMode
    ) -> None:
        """Verify documented intent to delivery mode mapping."""
        actual_mode = get_default_delivery_mode(intent)
        assert actual_mode == expected_mode


class TestChannelRoutingTruthTable:
    """Test that channel routing truth table matches implementation."""

    @pytest.mark.parametrize(
        "intent,mode,expected_channels",
        [
            # PREVIEW mode - all intents -> WebSocket only
            (NotificationIntent.SAFETY, AutonomyMode.PREVIEW, [Channel.WEBSOCKET]),
            (NotificationIntent.GOVERNANCE, AutonomyMode.PREVIEW, [Channel.WEBSOCKET]),
            (NotificationIntent.OPERATIONAL, AutonomyMode.PREVIEW, [Channel.WEBSOCKET]),
            (NotificationIntent.INFORMATIONAL, AutonomyMode.PREVIEW, [Channel.WEBSOCKET]),
            # SHADOW mode
            (NotificationIntent.SAFETY, AutonomyMode.SHADOW, [Channel.SLACK, Channel.WEBSOCKET]),
            (NotificationIntent.GOVERNANCE, AutonomyMode.SHADOW, [Channel.SLACK, Channel.WEBSOCKET]),
            (NotificationIntent.OPERATIONAL, AutonomyMode.SHADOW, [Channel.WEBSOCKET]),
            (NotificationIntent.INFORMATIONAL, AutonomyMode.SHADOW, [Channel.WEBSOCKET]),
            # LIVE mode
            (NotificationIntent.SAFETY, AutonomyMode.LIVE, [Channel.SLACK, Channel.WEBSOCKET]),
            (NotificationIntent.GOVERNANCE, AutonomyMode.LIVE, [Channel.SLACK, Channel.WEBSOCKET]),
            (NotificationIntent.OPERATIONAL, AutonomyMode.LIVE, [Channel.SLACK]),
            (NotificationIntent.INFORMATIONAL, AutonomyMode.LIVE, [Channel.WEBSOCKET]),
        ],
    )
    def test_channel_routing_matches_truth_table(
        self,
        intent: NotificationIntent,
        mode: AutonomyMode,
        expected_channels: list[Channel],
    ) -> None:
        """Verify documented channel routing matches implementation."""
        actual_channels = get_default_channels(intent, mode)
        assert actual_channels == expected_channels

    def test_safety_irreversible_live_adds_pagerduty(self) -> None:
        """Verify SAFETY + irreversible + LIVE adds PagerDuty."""
        channels = get_default_channels(
            NotificationIntent.SAFETY, AutonomyMode.LIVE, irreversible=True
        )
        assert Channel.PAGERDUTY in channels
        assert Channel.SLACK in channels
        assert Channel.WEBSOCKET in channels


class TestAcknowledgmentRequirements:
    """Test acknowledgment requirements match documentation."""

    @pytest.mark.parametrize(
        "intent,mode,expected_require_ack",
        [
            # Only SAFETY + LIVE requires ack
            (NotificationIntent.SAFETY, AutonomyMode.LIVE, True),
            (NotificationIntent.SAFETY, AutonomyMode.SHADOW, False),
            (NotificationIntent.SAFETY, AutonomyMode.PREVIEW, False),
            # All other intents do not require ack
            (NotificationIntent.GOVERNANCE, AutonomyMode.LIVE, False),
            (NotificationIntent.GOVERNANCE, AutonomyMode.SHADOW, False),
            (NotificationIntent.GOVERNANCE, AutonomyMode.PREVIEW, False),
            (NotificationIntent.OPERATIONAL, AutonomyMode.LIVE, False),
            (NotificationIntent.INFORMATIONAL, AutonomyMode.LIVE, False),
        ],
    )
    def test_ack_requirements_match_documentation(
        self,
        intent: NotificationIntent,
        mode: AutonomyMode,
        expected_require_ack: bool,
    ) -> None:
        """Verify documented ack requirements match implementation."""
        actual = get_default_require_ack(intent, mode)
        assert actual == expected_require_ack


class TestGuaranteedDeliveryInvariants:
    """Test GUARANTEED delivery invariants documented in truth table."""

    @pytest.mark.asyncio
    async def test_guaranteed_must_raise_on_all_failures(self) -> None:
        """Invariant: GUARANTEED must raise DeliveryError if all persistent channels fail."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=registry)

        with pytest.raises(DeliveryError) as exc_info:
            await service.deliver(notification)

        assert "GUARANTEED delivery failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_guaranteed_sequential_fallback(self) -> None:
        """Invariant: GUARANTEED uses sequential fallback, stops at first success."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        pagerduty_adapter = MockAdapter(Channel.PAGERDUTY, success=True)
        registry.register(slack_adapter)
        registry.register(email_adapter)
        registry.register(pagerduty_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        assert len(slack_adapter.deliver_calls) == 1
        assert len(email_adapter.deliver_calls) == 1
        # PagerDuty should not be tried since Email succeeded
        assert len(pagerduty_adapter.deliver_calls) == 0

    @pytest.mark.asyncio
    async def test_guaranteed_escalation_callback_invoked_before_exception(self) -> None:
        """Invariant: Escalation callback is invoked BEFORE DeliveryError is raised."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        callback_invoked = []

        def escalation_callback(notif: Notification, errors: dict) -> None:
            callback_invoked.append((notif.notification_id, errors))

        service = DeliveryService(
            adapter_registry=registry,
            escalation_callback=escalation_callback,
        )

        with pytest.raises(DeliveryError):
            await service.deliver(notification)

        # Callback should have been invoked before exception
        assert len(callback_invoked) == 1
        assert callback_invoked[0][0] == notification.notification_id

    @pytest.mark.asyncio
    async def test_guaranteed_websocket_failure_does_not_affect_status(self) -> None:
        """Invariant: WebSocket failure does NOT affect GUARANTEED status."""
        registry = SimpleAdapterRegistry()
        ws_adapter = MockAdapter(Channel.WEBSOCKET, success=False, error="WS failed")
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(ws_adapter)
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.WEBSOCKET, Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        # Should succeed despite WebSocket failure
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.WEBSOCKET in result.channels_failed
        assert Channel.SLACK in result.channels_succeeded

    def test_fallback_order_matches_documentation(self) -> None:
        """Invariant: Fallback order is Slack -> Email -> PagerDuty."""
        expected_order = [Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY]
        assert expected_order == PERSISTENT_CHANNELS_FALLBACK_ORDER


class TestBestEffortDeliveryInvariants:
    """Test BEST_EFFORT delivery invariants documented in truth table."""

    @pytest.mark.asyncio
    async def test_best_effort_no_exception_on_failure(self) -> None:
        """Invariant: BEST_EFFORT does not raise exception on failure."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)

        # Should NOT raise - just return FAILED status
        result = await service.deliver(notification)
        assert result.status == DeliveryStatus.FAILED

    @pytest.mark.asyncio
    async def test_best_effort_attempts_all_channels_concurrently(self) -> None:
        """Invariant: BEST_EFFORT attempts all channels (concurrent delivery)."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        registry.register(slack_adapter)
        registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        # Both channels should be attempted
        assert len(slack_adapter.deliver_calls) == 1
        assert len(email_adapter.deliver_calls) == 1
        assert result.status == DeliveryStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_best_effort_partial_success_counts_as_success(self) -> None:
        """Invariant: BEST_EFFORT with partial success is STATUS=SUCCESS."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        email_adapter = MockAdapter(Channel.EMAIL, success=False, error="Failed")
        registry.register(slack_adapter)
        registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        # Should be SUCCESS with partial delivery
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_succeeded
        assert Channel.EMAIL in result.channels_failed


class TestDLQInvariants:
    """Test DLQ visibility invariants documented in truth table."""

    @pytest.mark.asyncio
    async def test_only_guaranteed_failures_trigger_escalation(self) -> None:
        """Invariant: Only GUARANTEED failures trigger escalation callback."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        registry.register(slack_adapter)

        escalation_called = []

        def escalation_callback(notif: Notification, errors: dict) -> None:
            escalation_called.append(notif.notification_id)

        service = DeliveryService(
            adapter_registry=registry,
            escalation_callback=escalation_callback,
        )

        # BEST_EFFORT failure - should NOT trigger escalation
        best_effort_notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )
        await service.deliver(best_effort_notification)
        assert len(escalation_called) == 0

        # GUARANTEED failure - should trigger escalation
        guaranteed_notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        with pytest.raises(DeliveryError):
            await service.deliver(guaranteed_notification)
        assert len(escalation_called) == 1

    @pytest.mark.asyncio
    async def test_escalation_callback_receives_full_context(self) -> None:
        """Invariant: Escalation callback receives notification and all channel errors."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Slack error")
        email_adapter = MockAdapter(Channel.EMAIL, success=False, error="Email error")
        registry.register(slack_adapter)
        registry.register(email_adapter)

        received_context = []

        def escalation_callback(notif: Notification, errors: dict) -> None:
            received_context.append({
                "notification_id": notif.notification_id,
                "intent": notif.intent,
                "agent_id": notif.autonomy_context.agent_id,
                "errors": errors,
            })

        service = DeliveryService(
            adapter_registry=registry,
            escalation_callback=escalation_callback,
        )

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        with pytest.raises(DeliveryError):
            await service.deliver(notification)

        assert len(received_context) == 1
        ctx = received_context[0]
        assert ctx["notification_id"] == notification.notification_id
        assert ctx["intent"] == NotificationIntent.SAFETY
        assert ctx["agent_id"] == notification.autonomy_context.agent_id
        assert Channel.SLACK in ctx["errors"]
        assert Channel.EMAIL in ctx["errors"]

    @pytest.mark.asyncio
    async def test_escalation_callback_failure_does_not_prevent_delivery_error(self) -> None:
        """Invariant: Callback failures are logged but don't prevent DeliveryError."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        registry.register(slack_adapter)

        def failing_callback(notif: Notification, errors: dict) -> None:
            raise RuntimeError("Callback failed!")

        service = DeliveryService(
            adapter_registry=registry,
            escalation_callback=failing_callback,
        )

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        # DeliveryError should still be raised despite callback failure
        with pytest.raises(DeliveryError):
            await service.deliver(notification)


class TestAuditInvariants:
    """Test audit trail invariants documented in truth table."""

    @pytest.mark.asyncio
    async def test_all_deliveries_generate_audit_record(self) -> None:
        """Invariant: All deliveries (success or failure) generate audit record."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(slack_adapter)

        mock_audit = MagicMock()
        service = DeliveryService(
            adapter_registry=registry,
            audit_logger=mock_audit,
        )

        # Success case
        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
        )
        await service.deliver(notification)

        # Verify audit was logged
        mock_audit.log_delivery.assert_called()
        call_args = mock_audit.log_delivery.call_args
        logged_notification = call_args[0][0]
        logged_result = call_args[0][1]
        assert logged_notification.notification_id == notification.notification_id
        assert logged_result.status == DeliveryStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_audit_record_contains_required_fields(self) -> None:
        """Invariant: Audit record contains notification metadata and autonomy context."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(slack_adapter)

        mock_audit = MagicMock()
        service = DeliveryService(
            adapter_registry=registry,
            audit_logger=mock_audit,
        )

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            autonomy_mode=AutonomyMode.LIVE,
            channels=[Channel.SLACK],
        )
        await service.deliver(notification)

        # Verify notification passed to audit has required context
        call_args = mock_audit.log_delivery.call_args
        logged_notification = call_args[0][0]

        # Required fields per documentation
        assert logged_notification.notification_id is not None
        assert logged_notification.notification_type is not None
        assert logged_notification.intent is not None
        assert logged_notification.autonomy_context is not None
        assert logged_notification.autonomy_context.agent_id is not None
        assert logged_notification.autonomy_context.autonomy_mode is not None


class TestDegradationBehavior:
    """Test degradation behavior documented in truth table."""

    @pytest.mark.asyncio
    async def test_guaranteed_fallback_on_channel_unavailable(self) -> None:
        """Degradation: GUARANTEED falls back to next channel when primary fails."""
        registry = SimpleAdapterRegistry()
        # No Slack adapter registered (simulating unavailability)
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        # Should succeed via Email fallback
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_failed  # No adapter
        assert Channel.EMAIL in result.channels_succeeded

    @pytest.mark.asyncio
    async def test_best_effort_logs_and_continues_on_failure(self) -> None:
        """Degradation: BEST_EFFORT logs and continues when channels fail."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Slack down")
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        registry.register(slack_adapter)
        registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        # Should succeed with partial delivery
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_failed
        assert Channel.EMAIL in result.channels_succeeded
        # Error message should be logged
        assert result.error_message is not None
        assert "Slack" in result.error_message

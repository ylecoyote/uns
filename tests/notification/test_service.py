"""Unit tests for the delivery service.

Tests cover:
- GUARANTEED delivery semantics (sequential fallback, raises on all failures)
- BEST_EFFORT delivery semantics (concurrent, logs failures)
- Deduplication integration
- Rate limiting integration
- Ack timeout scheduling
- Audit logging
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.adapters.base import (
    AdapterDeliveryError,
    AdapterStatus,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)
from notification.deduplication import (
    InMemoryDeduplicationStore,
    configure_deduplication_engine,
)
from notification.dlq import DLQService
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
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
)
from notification.rate_limiting import (
    RateLimitConfig,
    configure_rate_limiter,
)
from notification.service import (
    DeliveryError,
    DeliveryService,
    SimpleAdapterRegistry,
    configure_delivery_service,
    deliver,
)


class MockAdapter(BaseAdapter):
    """Mock adapter for testing."""

    def __init__(
        self,
        channel: Channel,
        success: bool = True,
        error: str | None = None,
        raise_error: bool = False,
    ):
        self._channel = channel
        self._success = success
        self._error = error
        self._raise_error = raise_error
        self.deliver_calls: list[Notification] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        self.deliver_calls.append(notification)
        if self._raise_error:
            raise AdapterDeliveryError(
                self._error or "Adapter error",
                channel=self._channel,
                retryable=True,
            )
        return DeliveryResult(
            success=self._success,
            channel=self._channel,
            message_id=f"msg-{notification.notification_id}" if self._success else None,
            error=self._error,
            delivered_at=datetime.now(UTC),
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="OK",
        )


class FakeRedisList:
    """Minimal Redis-list fake for DLQ tests."""

    def __init__(self) -> None:
        self.values: list[str] = []

    def lpush(self, key: str, value: str) -> int:
        self.values.insert(0, value)
        return len(self.values)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        stop = None if end == -1 else end + 1
        return self.values[start:stop]

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        next_values = []
        for item in self.values:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            next_values.append(item)
        self.values = next_values
        return removed

    def llen(self, key: str) -> int:
        return len(self.values)


def create_notification(
    notification_type: str = "test.notification",
    intent: NotificationIntent = NotificationIntent.OPERATIONAL,
    autonomy_mode: AutonomyMode = AutonomyMode.LIVE,
    channels: list[Channel] | None = None,
    delivery_mode: DeliveryMode | None = None,
    dedup_key: str | None = None,
    irreversible: bool = False,
    title: str = "Test Notification",
    message: str = "This is a test message",
) -> Notification:
    """Helper to create test notifications with desired properties."""
    return Notification(
        notification_type=notification_type,
        intent=intent,
        autonomy_context=AutonomyContext(
            autonomy_mode=autonomy_mode,
            agent_id=uuid4(),
        ),
        title=title,
        message=message,
        source="test",
        channels=channels or [],
        delivery_mode=delivery_mode,
        dedup_key=dedup_key,
        irreversible=irreversible,
    )


@pytest.fixture
def notification() -> Notification:
    """Create a test notification."""
    return create_notification()


@pytest.fixture
def safety_notification() -> Notification:
    """Create a SAFETY notification (GUARANTEED delivery)."""
    return create_notification(
        notification_type="safety.alert",
        intent=NotificationIntent.SAFETY,
        title="Safety Alert",
        message="Critical safety alert",
        irreversible=True,
    )


@pytest.fixture
def adapter_registry() -> SimpleAdapterRegistry:
    """Create an adapter registry with mock adapters."""
    registry = SimpleAdapterRegistry()
    return registry


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test."""
    # Reset deduplication engine with fresh in-memory store
    configure_deduplication_engine(InMemoryDeduplicationStore())

    # Reset policy registry
    configure_policy_registry(PolicyRegistry())

    # Reset rate limiter with generous limits
    configure_rate_limiter({
        Channel.SLACK: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
        Channel.EMAIL: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
        Channel.WEBSOCKET: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
        Channel.PAGERDUTY: RateLimitConfig(tokens_per_second=100, bucket_size=1000),
    })


class TestDeliveryServiceBasic:
    """Basic delivery service tests."""

    @pytest.mark.asyncio
    async def test_successful_delivery(self, adapter_registry: SimpleAdapterRegistry):
        """Test successful delivery to a single channel."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        notification = create_notification(channels=[Channel.SLACK])

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_succeeded
        assert len(slack_adapter.deliver_calls) == 1

    @pytest.mark.asyncio
    async def test_delivery_with_websocket_fire_and_forget(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test WebSocket delivery is fire-and-forget."""
        ws_adapter = MockAdapter(Channel.WEBSOCKET, success=False, error="WS failed")
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(ws_adapter)
        adapter_registry.register(slack_adapter)

        notification = create_notification(channels=[Channel.WEBSOCKET, Channel.SLACK])

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        # Should succeed despite WebSocket failure
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_succeeded
        assert Channel.WEBSOCKET in result.channels_failed


class TestGuaranteedDelivery:
    """Tests for GUARANTEED delivery semantics."""

    @pytest.mark.asyncio
    async def test_guaranteed_sequential_fallback(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test GUARANTEED delivery tries channels sequentially."""
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Slack failed")
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        adapter_registry.register(slack_adapter)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_failed
        assert Channel.EMAIL in result.channels_succeeded
        # Slack tried first, then Email
        assert len(slack_adapter.deliver_calls) == 1
        assert len(email_adapter.deliver_calls) == 1

    @pytest.mark.asyncio
    async def test_guaranteed_stops_after_success(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test GUARANTEED delivery stops after first success."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        adapter_registry.register(slack_adapter)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        assert len(slack_adapter.deliver_calls) == 1
        # Email should not be tried since Slack succeeded
        assert len(email_adapter.deliver_calls) == 0

    @pytest.mark.asyncio
    async def test_guaranteed_raises_on_all_failures(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test GUARANTEED delivery raises DeliveryError when all channels fail."""
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Slack failed")
        email_adapter = MockAdapter(Channel.EMAIL, success=False, error="Email failed")
        adapter_registry.register(slack_adapter)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=adapter_registry)

        with pytest.raises(DeliveryError) as exc_info:
            await service.deliver(notification)

        assert "GUARANTEED delivery failed" in str(exc_info.value)
        assert exc_info.value.notification == notification
        assert Channel.SLACK in exc_info.value.channel_errors
        assert Channel.EMAIL in exc_info.value.channel_errors

    @pytest.mark.asyncio
    async def test_guaranteed_escalation_callback(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test GUARANTEED delivery calls escalation callback on failure."""
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        adapter_registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        escalation_called = []

        def escalation_callback(notif: Notification, errors: dict):
            escalation_called.append((notif, errors))

        service = DeliveryService(
            adapter_registry=adapter_registry,
            escalation_callback=escalation_callback,
        )

        with pytest.raises(DeliveryError):
            await service.deliver(notification)

        assert len(escalation_called) == 1
        assert escalation_called[0][0] == notification

    @pytest.mark.asyncio
    async def test_guaranteed_failure_enqueues_dlq_entry(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """GUARANTEED all-channel failure should be visible through the DLQ."""
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        adapter_registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        dlq_service = DLQService(FakeRedisList(), key="test:dlq")
        service = DeliveryService(
            adapter_registry=adapter_registry,
            dlq_service=dlq_service,
        )

        with pytest.raises(DeliveryError):
            await service.deliver(notification)

        assert dlq_service.depth() == 1
        entry = dlq_service.list_entries()[0]
        assert entry.notification_id == notification.notification_id
        assert entry.reason == "guaranteed_delivery_failed"
        assert entry.metadata["channel_errors"] == {"SLACK": "Failed"}

    @pytest.mark.asyncio
    async def test_guaranteed_with_adapter_exception(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test GUARANTEED delivery handles adapter exceptions."""
        slack_adapter = MockAdapter(
            Channel.SLACK, success=False, error="Exception!", raise_error=True
        )
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        adapter_registry.register(slack_adapter)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_failed
        assert Channel.EMAIL in result.channels_succeeded


class TestBestEffortDelivery:
    """Tests for BEST_EFFORT delivery semantics."""

    @pytest.mark.asyncio
    async def test_best_effort_attempts_all_channels(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test BEST_EFFORT delivery attempts all channels."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        adapter_registry.register(slack_adapter)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        # Both channels should be attempted
        assert len(slack_adapter.deliver_calls) == 1
        assert len(email_adapter.deliver_calls) == 1
        assert Channel.SLACK in result.channels_succeeded
        assert Channel.EMAIL in result.channels_succeeded

    @pytest.mark.asyncio
    async def test_best_effort_does_not_raise_on_failure(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test BEST_EFFORT delivery doesn't raise on all failures."""
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        adapter_registry.register(slack_adapter)

        notification = create_notification(
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        # Should not raise, just return FAILED status
        assert result.status == DeliveryStatus.FAILED
        assert Channel.SLACK in result.channels_failed

    @pytest.mark.asyncio
    async def test_best_effort_partial_success(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test BEST_EFFORT delivery with partial success."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        email_adapter = MockAdapter(Channel.EMAIL, success=False, error="Email failed")
        adapter_registry.register(slack_adapter)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            channels=[Channel.SLACK, Channel.EMAIL],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        # Should succeed with at least one channel working
        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in result.channels_succeeded
        assert Channel.EMAIL in result.channels_failed


class TestDeduplication:
    """Tests for deduplication integration."""

    @pytest.mark.asyncio
    async def test_duplicate_notification_deduplicated(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test duplicate notifications are deduplicated."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        notification = create_notification(
            channels=[Channel.SLACK],
            dedup_key="test-dedup-key",
        )

        service = DeliveryService(adapter_registry=adapter_registry)

        # First delivery should succeed
        result1 = await service.deliver(notification)
        assert result1.status == DeliveryStatus.SUCCESS

        # Second delivery (same dedup_key) should be deduplicated
        result2 = await service.deliver(notification)
        assert result2.status == DeliveryStatus.DEDUPLICATED

        # Adapter should only be called once
        assert len(slack_adapter.deliver_calls) == 1

    @pytest.mark.asyncio
    async def test_different_dedup_keys_both_delivered(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test different dedup keys are not deduplicated."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        service = DeliveryService(adapter_registry=adapter_registry)

        # First notification
        notification1 = create_notification(
            channels=[Channel.SLACK],
            dedup_key="key-1",
        )
        result1 = await service.deliver(notification1)
        assert result1.status == DeliveryStatus.SUCCESS

        # Second notification with different key
        notification2 = create_notification(
            channels=[Channel.SLACK],
            dedup_key="key-2",
        )
        result2 = await service.deliver(notification2)
        assert result2.status == DeliveryStatus.SUCCESS

        # Both should be delivered
        assert len(slack_adapter.deliver_calls) == 2

    @pytest.mark.asyncio
    async def test_policy_dedup_window_is_honored(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """A policy dedup window of zero should allow immediate redelivery."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.policy-dedup",
                dedup_window_seconds=0,
            )
        )
        configure_policy_registry(registry)

        notification = create_notification(
            notification_type="test.policy-dedup",
            channels=[Channel.SLACK],
            dedup_key="policy-window-key",
        )

        service = DeliveryService(adapter_registry=adapter_registry)
        result1 = await service.deliver(notification)
        result2 = await service.deliver(notification)

        assert result1.status == DeliveryStatus.SUCCESS
        assert result2.status == DeliveryStatus.SUCCESS
        assert len(slack_adapter.deliver_calls) == 2


class TestRateLimiting:
    """Tests for rate limiting integration."""

    @pytest.mark.asyncio
    async def test_rate_limited_channel_fails(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test rate limited channels fail gracefully."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        # Configure very restrictive rate limit
        configure_rate_limiter({
            Channel.SLACK: RateLimitConfig(tokens_per_second=0.001, bucket_size=1),
        })

        service = DeliveryService(adapter_registry=adapter_registry)

        # First delivery should work
        notification1 = create_notification(
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
            dedup_key="unique-key-1",
        )
        result1 = await service.deliver(notification1)
        assert result1.status == DeliveryStatus.SUCCESS

        # Second delivery should be rate limited
        notification2 = create_notification(
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
            dedup_key="unique-key-2",
            title="Second notification",
            message="Different message",
        )
        result2 = await service.deliver(notification2)
        assert result2.status == DeliveryStatus.FAILED
        assert "Rate limit" in (result2.error_message or "")


class TestAckScheduling:
    """Tests for acknowledgment timeout scheduling."""

    @pytest.mark.asyncio
    async def test_ack_scheduled_for_safety_live(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test ack timeout is scheduled for SAFETY + LIVE."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        notification = create_notification(
            notification_type="safety.alert",
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
        )

        mock_scheduler = MagicMock()
        service = DeliveryService(
            adapter_registry=adapter_registry,
            ack_scheduler=mock_scheduler,
        )

        await service.deliver(notification)

        # Should schedule ack timeout
        mock_scheduler.schedule_timeout.assert_called_once()
        call_args = mock_scheduler.schedule_timeout.call_args
        assert call_args[0][0] == notification
        assert call_args[0][1] == 15  # Default SAFETY timeout

    @pytest.mark.asyncio
    async def test_no_ack_for_informational(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test no ack scheduling for INFORMATIONAL intent."""
        ws_adapter = MockAdapter(Channel.WEBSOCKET, success=True)
        adapter_registry.register(ws_adapter)

        notification = create_notification(
            intent=NotificationIntent.INFORMATIONAL,
            channels=[Channel.WEBSOCKET],
        )

        mock_scheduler = MagicMock()
        service = DeliveryService(
            adapter_registry=adapter_registry,
            ack_scheduler=mock_scheduler,
        )

        await service.deliver(notification)

        # Should NOT schedule ack timeout
        mock_scheduler.schedule_timeout.assert_not_called()


class TestAuditLogging:
    """Tests for audit logging."""

    @pytest.mark.asyncio
    async def test_audit_log_on_success(self, adapter_registry: SimpleAdapterRegistry):
        """Test audit logging on successful delivery."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        notification = create_notification(channels=[Channel.SLACK])

        mock_logger = MagicMock()
        service = DeliveryService(
            adapter_registry=adapter_registry,
            audit_logger=mock_logger,
        )

        await service.deliver(notification)

        mock_logger.log_delivery.assert_called_once()
        call_args = mock_logger.log_delivery.call_args
        assert call_args[0][0] == notification
        assert call_args[0][1].status == DeliveryStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_audit_log_on_dedup(self, adapter_registry: SimpleAdapterRegistry):
        """Test audit logging on deduplicated delivery."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        notification = create_notification(
            channels=[Channel.SLACK],
            dedup_key="audit-dedup-test",
        )

        mock_logger = MagicMock()
        service = DeliveryService(
            adapter_registry=adapter_registry,
            audit_logger=mock_logger,
        )

        # First delivery
        await service.deliver(notification)

        # Second delivery (duplicate)
        await service.deliver(notification)

        # Should have 2 audit logs
        assert mock_logger.log_delivery.call_count == 2

        # Second call should have DEDUPLICATED status
        second_call = mock_logger.log_delivery.call_args_list[1]
        assert second_call[0][1].status == DeliveryStatus.DEDUPLICATED


class TestPolicyIntegration:
    """Tests for policy registry integration."""

    @pytest.mark.asyncio
    async def test_notification_delivery_mode_takes_precedence_over_policy(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test that notification's delivery_mode takes precedence over policy.

        The Notification model automatically derives delivery_mode from intent,
        and this takes precedence over policy settings. This is by design:
        the notification sender can always specify explicit behavior.
        """
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        adapter_registry.register(slack_adapter)

        # OPERATIONAL intent automatically gets BEST_EFFORT
        notification = create_notification(
            notification_type="policy.test",
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
        )

        # Register policy that would force GUARANTEED - but it won't be used
        # because notification already has delivery_mode set
        policy_registry = PolicyRegistry()
        policy_registry.register(
            NotificationPolicy(
                notification_type="policy.test",
                delivery_mode=DeliveryMode.GUARANTEED,
            )
        )
        configure_policy_registry(policy_registry)

        service = DeliveryService(adapter_registry=adapter_registry)

        # Should NOT raise because notification's BEST_EFFORT takes precedence
        result = await service.deliver(notification)
        assert result.status == DeliveryStatus.FAILED  # BEST_EFFORT doesn't raise

    @pytest.mark.asyncio
    async def test_policy_overrides_channels(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test policy can override channels."""
        email_adapter = MockAdapter(Channel.EMAIL, success=True)
        adapter_registry.register(email_adapter)

        notification = create_notification(
            notification_type="channel.override.test",
            intent=NotificationIntent.OPERATIONAL,
            channels=[],  # Let policy decide
        )

        # Register policy that forces Email channel
        policy_registry = PolicyRegistry()
        policy_registry.register(
            NotificationPolicy(
                notification_type="channel.override.test",
                channels=[Channel.EMAIL],
            )
        )
        configure_policy_registry(policy_registry)

        service = DeliveryService(adapter_registry=adapter_registry)
        result = await service.deliver(notification)

        assert result.status == DeliveryStatus.SUCCESS
        assert Channel.EMAIL in result.channels_succeeded
        assert len(email_adapter.deliver_calls) == 1


class TestGlobalServiceConfiguration:
    """Tests for global service configuration."""

    @pytest.mark.asyncio
    async def test_configure_and_use_global_service(
        self, adapter_registry: SimpleAdapterRegistry
    ):
        """Test configuring and using global delivery service."""
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        adapter_registry.register(slack_adapter)

        notification = create_notification(channels=[Channel.SLACK])

        configure_delivery_service(adapter_registry=adapter_registry)

        result = await deliver(notification)
        assert result.status == DeliveryStatus.SUCCESS

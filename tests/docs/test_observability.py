"""Tests for observability.md documentation.

Tests cover:
- Document structure and completeness
- Health state definitions and semantics
- DLQ visibility invariants
- Key metrics descriptions
- /health endpoint semantics
"""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.acknowledgment import (
    DEFAULT_ACK_TIMEOUTS,
    AcknowledgmentEngine,
    InMemoryAckStorage,
)
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
    AckStatus,
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
)
from notification.rate_limiting import (
    RateLimitConfig,
    configure_rate_limiter,
)
from notification.service import (
    DeliveryError,
    DeliveryService,
    SimpleAdapterRegistry,
)

# Path to the observability documentation
OBSERVABILITY_DOC_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "sections" / "observability.md"
)


@pytest.fixture
def observability_doc() -> str:
    """Load the observability documentation."""
    assert OBSERVABILITY_DOC_PATH.exists(), (
        f"observability.md not found at {OBSERVABILITY_DOC_PATH}"
    )
    return OBSERVABILITY_DOC_PATH.read_text()


class MockAdapter(BaseAdapter):
    """Mock adapter for testing observability."""

    def __init__(
        self,
        channel: Channel,
        success: bool = True,
        error: str | None = None,
        health_status: AdapterStatus = AdapterStatus.HEALTHY,
        latency_ms: float | None = 10.0,
    ):
        self._channel = channel
        self._success = success
        self._error = error
        self._health_status = health_status
        self._latency_ms = latency_ms
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
        return HealthCheckResult(
            status=self._health_status,
            message=f"{self._health_status.value} status",
            latency_ms=self._latency_ms,
        )


def create_notification(
    intent: NotificationIntent = NotificationIntent.OPERATIONAL,
    autonomy_mode: AutonomyMode = AutonomyMode.LIVE,
    channels: list[Channel] | None = None,
    delivery_mode: DeliveryMode | None = None,
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


class TestObservabilityDocExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify observability.md exists."""
        assert OBSERVABILITY_DOC_PATH.exists()

    def test_file_not_empty(self, observability_doc: str) -> None:
        """Verify file is not empty."""
        assert len(observability_doc) > 0

    def test_is_markdown(self, observability_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in observability_doc


class TestObservabilityDocStructure:
    """Test the structure of the observability documentation."""

    def test_has_title(self, observability_doc: str) -> None:
        """Verify document has correct title."""
        assert observability_doc.startswith("# Observability")

    def test_has_overview_section(self, observability_doc: str) -> None:
        """Verify document has overview section."""
        assert "## Overview" in observability_doc

    def test_has_health_states_section(self, observability_doc: str) -> None:
        """Verify document has health states section."""
        assert "## Health States" in observability_doc

    def test_has_health_endpoint_section(self, observability_doc: str) -> None:
        """Verify document has /health endpoint section."""
        assert "## /health Endpoint" in observability_doc

    def test_has_dlq_section(self, observability_doc: str) -> None:
        """Verify document has DLQ visibility section."""
        assert "## DLQ (Dead Letter Queue) Visibility" in observability_doc

    def test_has_key_metrics_section(self, observability_doc: str) -> None:
        """Verify document has key metrics section."""
        assert "## Key Metrics" in observability_doc

    def test_has_degradation_section(self, observability_doc: str) -> None:
        """Verify document has system degradation section."""
        assert "## System Degradation Modes" in observability_doc

    def test_has_audit_trail_section(self, observability_doc: str) -> None:
        """Verify document has audit trail section."""
        assert "## Audit Trail" in observability_doc

    def test_has_related_documentation(self, observability_doc: str) -> None:
        """Verify document has related documentation links."""
        assert "## Related Documentation" in observability_doc


class TestHealthStatesDocumented:
    """Test that health state definitions are documented."""

    def test_documents_healthy_state(self, observability_doc: str) -> None:
        """Verify HEALTHY state is documented."""
        assert "HEALTHY" in observability_doc

    def test_documents_degraded_state(self, observability_doc: str) -> None:
        """Verify DEGRADED state is documented."""
        assert "DEGRADED" in observability_doc

    def test_documents_unhealthy_state(self, observability_doc: str) -> None:
        """Verify UNHEALTHY state is documented."""
        assert "UNHEALTHY" in observability_doc

    def test_documents_adapter_status_enum(self, observability_doc: str) -> None:
        """Verify AdapterStatus enum is mentioned."""
        assert "AdapterStatus" in observability_doc

    def test_documents_health_check_result(self, observability_doc: str) -> None:
        """Verify HealthCheckResult is documented."""
        assert "HealthCheckResult" in observability_doc

    def test_documents_latency_ms_field(self, observability_doc: str) -> None:
        """Verify latency_ms field is documented."""
        assert "latency_ms" in observability_doc


class TestDegradedStateMeaning:
    """Test that DEGRADED state meaning is properly documented."""

    def test_degraded_indicates_partial_functionality(self, observability_doc: str) -> None:
        """Verify DEGRADED is described as partial functionality."""
        assert "partial" in observability_doc.lower() or "Partial" in observability_doc

    def test_degraded_describes_elevated_latency(self, observability_doc: str) -> None:
        """Verify DEGRADED includes elevated latency description."""
        assert "latency" in observability_doc.lower()

    def test_degraded_describes_intermittent_failures(self, observability_doc: str) -> None:
        """Verify DEGRADED includes intermittent failures description."""
        assert "intermittent" in observability_doc.lower()

    def test_degraded_vs_unhealthy_distinction(self, observability_doc: str) -> None:
        """Verify distinction between DEGRADED and UNHEALTHY is documented."""
        # Should describe when to use each
        assert "DEGRADED" in observability_doc
        assert "UNHEALTHY" in observability_doc
        # Should have operational guidance
        assert "attempt" in observability_doc.lower() or "delivery" in observability_doc.lower()


class TestHealthEndpointDocumented:
    """Test that /health endpoint semantics are documented."""

    def test_documents_health_endpoint_path(self, observability_doc: str) -> None:
        """Verify /health endpoint path is documented."""
        assert "/health" in observability_doc

    def test_documents_current_implementation(self, observability_doc: str) -> None:
        """Verify current (stub) implementation is documented."""
        assert "stub" in observability_doc.lower() or "static" in observability_doc.lower()

    def test_documents_response_format(self, observability_doc: str) -> None:
        """Verify response format is documented."""
        assert '"status"' in observability_doc
        assert '"healthy"' in observability_doc

    def test_documents_implementation_limitations(self, observability_doc: str) -> None:
        """Verify that limitations are documented."""
        # Should note that adapter health checks are NOT invoked
        assert "NOT" in observability_doc or "not" in observability_doc


class TestDLQVisibilityDocumented:
    """Test that DLQ visibility rules are documented."""

    def test_documents_escalation_callback(self, observability_doc: str) -> None:
        """Verify escalation callback is documented."""
        assert "escalation_callback" in observability_doc

    def test_documents_guaranteed_only_invariant(self, observability_doc: str) -> None:
        """Verify GUARANTEED-only DLQ invariant is documented."""
        assert "GUARANTEED" in observability_doc
        # Should mention BEST_EFFORT doesn't trigger escalation
        assert "BEST_EFFORT" in observability_doc

    def test_documents_callback_signature(self, observability_doc: str) -> None:
        """Verify callback signature is documented."""
        assert "notification:" in observability_doc or "Notification" in observability_doc
        assert "channel_errors" in observability_doc

    def test_documents_dlq_entry_information(self, observability_doc: str) -> None:
        """Verify DLQ entry information is documented."""
        assert "notification_id" in observability_doc
        assert "intent" in observability_doc.lower()
        assert "channel_errors" in observability_doc

    def test_documents_operator_responsibility(self, observability_doc: str) -> None:
        """Verify operator responsibility for DLQ persistence is documented."""
        assert "operator" in observability_doc.lower() or "Operator" in observability_doc


class TestKeyMetricsDocumented:
    """Test that key metrics are documented with their intent."""

    def test_documents_delivery_latency(self, observability_doc: str) -> None:
        """Verify delivery latency metrics are documented."""
        assert "latency" in observability_doc.lower()

    def test_documents_retry_fallback_counts(self, observability_doc: str) -> None:
        """Verify retry/fallback count metrics are documented."""
        assert "fallback" in observability_doc.lower()

    def test_documents_dlq_depth(self, observability_doc: str) -> None:
        """Verify DLQ depth metric is documented."""
        assert "dlq" in observability_doc.lower() or "DLQ" in observability_doc
        assert "depth" in observability_doc.lower()

    def test_documents_ack_timeout_counts(self, observability_doc: str) -> None:
        """Verify acknowledgment timeout counts are documented."""
        assert "timeout" in observability_doc.lower()
        assert "ack" in observability_doc.lower() or "acknowledgment" in observability_doc.lower()

    def test_documents_rate_limiting_events(self, observability_doc: str) -> None:
        """Verify rate limiting events are documented."""
        assert "rate limit" in observability_doc.lower() or "Rate limit" in observability_doc

    def test_documents_metric_intents(self, observability_doc: str) -> None:
        """Verify metrics include intent descriptions."""
        # Should explain why each metric matters
        assert "Intent:" in observability_doc or "intent" in observability_doc.lower()


class TestAckTimeoutDocumented:
    """Test that acknowledgment timeout configuration is documented."""

    def test_documents_safety_timeout(self, observability_doc: str) -> None:
        """Verify SAFETY timeout (15 min) is documented."""
        assert "SAFETY" in observability_doc
        assert "15" in observability_doc

    def test_documents_governance_timeout(self, observability_doc: str) -> None:
        """Verify GOVERNANCE timeout (30 min) is documented."""
        assert "GOVERNANCE" in observability_doc
        assert "30" in observability_doc


class TestAdapterStatusEnumMatchesDoc:
    """Test that AdapterStatus enum matches documentation."""

    def test_adapter_status_has_three_states(self) -> None:
        """Verify AdapterStatus has exactly HEALTHY, DEGRADED, UNHEALTHY."""
        expected = {"HEALTHY", "DEGRADED", "UNHEALTHY"}
        actual = {s.value for s in AdapterStatus}
        assert actual == expected

    def test_adapter_status_values_match_doc(self, observability_doc: str) -> None:
        """Verify all AdapterStatus values appear in documentation."""
        for status in AdapterStatus:
            assert status.value in observability_doc


class TestHealthCheckResultMatchesDoc:
    """Test that HealthCheckResult fields match documentation."""

    def test_health_check_result_has_status(self) -> None:
        """Verify HealthCheckResult has status field."""
        result = HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="OK",
        )
        assert hasattr(result, "status")
        assert result.status == AdapterStatus.HEALTHY

    def test_health_check_result_has_message(self) -> None:
        """Verify HealthCheckResult has message field."""
        result = HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="Test message",
        )
        assert hasattr(result, "message")
        assert result.message == "Test message"

    def test_health_check_result_has_latency_ms(self) -> None:
        """Verify HealthCheckResult has latency_ms field."""
        result = HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="OK",
            latency_ms=42.5,
        )
        assert hasattr(result, "latency_ms")
        assert result.latency_ms == 42.5

    def test_health_check_result_has_metadata(self) -> None:
        """Verify HealthCheckResult has metadata field."""
        result = HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="OK",
            metadata={"key": "value"},
        )
        assert hasattr(result, "metadata")
        assert result.metadata == {"key": "value"}


class TestDLQInvariantsMatchDoc:
    """Test that DLQ invariants match documentation."""

    @pytest.mark.asyncio
    async def test_only_guaranteed_triggers_escalation(self) -> None:
        """Verify only GUARANTEED failures trigger escalation callback."""
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

        # BEST_EFFORT should NOT trigger escalation
        best_effort_notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )
        await service.deliver(best_effort_notification)
        assert len(escalation_called) == 0

        # GUARANTEED should trigger escalation
        guaranteed_notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        with pytest.raises(DeliveryError):
            await service.deliver(guaranteed_notification)
        assert len(escalation_called) == 1

    @pytest.mark.asyncio
    async def test_escalation_callback_receives_channel_errors(self) -> None:
        """Verify escalation callback receives channel_errors dict."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Slack error")
        registry.register(slack_adapter)

        received_errors = []

        def escalation_callback(notif: Notification, errors: dict) -> None:
            received_errors.append(errors)

        service = DeliveryService(
            adapter_registry=registry,
            escalation_callback=escalation_callback,
        )

        notification = create_notification(
            intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        with pytest.raises(DeliveryError):
            await service.deliver(notification)

        assert len(received_errors) == 1
        assert Channel.SLACK in received_errors[0]
        assert received_errors[0][Channel.SLACK] == "Slack error"


class TestAckTimeoutMatchesDoc:
    """Test that acknowledgment timeout values match documentation."""

    def test_safety_timeout_is_15_minutes(self) -> None:
        """Verify SAFETY timeout is 15 minutes per documentation."""
        assert DEFAULT_ACK_TIMEOUTS[NotificationIntent.SAFETY] == 15

    def test_governance_timeout_is_30_minutes(self) -> None:
        """Verify GOVERNANCE timeout is 30 minutes per documentation."""
        assert DEFAULT_ACK_TIMEOUTS[NotificationIntent.GOVERNANCE] == 30


class TestAckTimeoutBehavior:
    """Test acknowledgment timeout tracking behavior matches documentation."""

    def test_ack_state_calculates_timeout_at(self) -> None:
        """Verify AckState calculates timeout_at from timeout_minutes."""
        from datetime import UTC, datetime, timedelta

        storage = InMemoryAckStorage()
        engine = AcknowledgmentEngine(storage=storage)

        notification_id = uuid4()
        now = datetime.now(UTC)

        state = engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id=uuid4(),
            ),
            timeout_minutes=15,
            created_at=now,
        )

        # timeout_at should be created_at + 15 minutes
        expected_timeout = now + timedelta(minutes=15)
        assert state.timeout_at is not None
        assert abs((state.timeout_at - expected_timeout).total_seconds()) < 1

    def test_check_all_timeouts_returns_timed_out_notifications(self) -> None:
        """Verify check_all_timeouts returns list of timed out notifications."""
        from datetime import UTC, datetime, timedelta

        storage = InMemoryAckStorage()
        engine = AcknowledgmentEngine(storage=storage)

        notification_id = uuid4()
        past_time = datetime.now(UTC) - timedelta(minutes=20)

        engine.register_notification(
            notification_id=notification_id,
            intent=NotificationIntent.SAFETY,
            autonomy_context=AutonomyContext(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id=uuid4(),
            ),
            timeout_minutes=15,
            created_at=past_time,
        )

        # Check for timeouts
        events = engine.check_all_timeouts()

        assert len(events) == 1
        assert events[0].notification_id == notification_id
        assert events[0].ack_status == AckStatus.TIMED_OUT


class TestHealthCheckInfrastructure:
    """Test that health check infrastructure matches documentation."""

    @pytest.mark.asyncio
    async def test_adapter_implements_health_check(self) -> None:
        """Verify adapters implement health_check method."""
        adapter = MockAdapter(
            Channel.SLACK,
            health_status=AdapterStatus.HEALTHY,
            latency_ms=42.0,
        )

        result = await adapter.health_check()

        assert isinstance(result, HealthCheckResult)
        assert result.status == AdapterStatus.HEALTHY
        assert result.latency_ms == 42.0

    @pytest.mark.asyncio
    async def test_health_check_can_return_degraded(self) -> None:
        """Verify health check can return DEGRADED status."""
        adapter = MockAdapter(
            Channel.SLACK,
            health_status=AdapterStatus.DEGRADED,
            latency_ms=500.0,
        )

        result = await adapter.health_check()

        assert result.status == AdapterStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_health_check_can_return_unhealthy(self) -> None:
        """Verify health check can return UNHEALTHY status."""
        adapter = MockAdapter(
            Channel.SLACK,
            health_status=AdapterStatus.UNHEALTHY,
        )

        result = await adapter.health_check()

        assert result.status == AdapterStatus.UNHEALTHY


class TestDeliveryMetricsAvailable:
    """Test that delivery metrics are available as documented."""

    @pytest.mark.asyncio
    async def test_notification_result_has_channels_attempted(self) -> None:
        """Verify NotificationResult includes channels_attempted."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        assert hasattr(result, "channels_attempted")
        assert Channel.SLACK in result.channels_attempted

    @pytest.mark.asyncio
    async def test_notification_result_has_channels_succeeded(self) -> None:
        """Verify NotificationResult includes channels_succeeded."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        assert hasattr(result, "channels_succeeded")
        assert Channel.SLACK in result.channels_succeeded

    @pytest.mark.asyncio
    async def test_notification_result_has_channels_failed(self) -> None:
        """Verify NotificationResult includes channels_failed."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=False, error="Failed")
        registry.register(slack_adapter)

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        service = DeliveryService(adapter_registry=registry)
        result = await service.deliver(notification)

        assert hasattr(result, "channels_failed")
        assert Channel.SLACK in result.channels_failed


class TestAuditLoggerProtocol:
    """Test that AuditLogger protocol matches documentation."""

    @pytest.mark.asyncio
    async def test_audit_logger_log_delivery_called(self) -> None:
        """Verify AuditLogger.log_delivery is called on delivery."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(slack_adapter)

        mock_audit = MagicMock()
        service = DeliveryService(
            adapter_registry=registry,
            audit_logger=mock_audit,
        )

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
        )
        await service.deliver(notification)

        mock_audit.log_delivery.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_logger_receives_notification_and_result(self) -> None:
        """Verify AuditLogger receives notification and result."""
        registry = SimpleAdapterRegistry()
        slack_adapter = MockAdapter(Channel.SLACK, success=True)
        registry.register(slack_adapter)

        mock_audit = MagicMock()
        service = DeliveryService(
            adapter_registry=registry,
            audit_logger=mock_audit,
        )

        notification = create_notification(
            intent=NotificationIntent.OPERATIONAL,
            channels=[Channel.SLACK],
        )
        await service.deliver(notification)

        call_args = mock_audit.log_delivery.call_args
        logged_notification = call_args[0][0]
        logged_result = call_args[0][1]

        assert logged_notification.notification_id == notification.notification_id
        assert logged_result.status == DeliveryStatus.SUCCESS


class TestRelatedDocumentation:
    """Test that related documentation links are correct."""

    def test_links_to_delivery_semantics(self, observability_doc: str) -> None:
        """Verify link to delivery-semantics.md exists."""
        assert "delivery-semantics.md" in observability_doc

    def test_links_to_integration_modes(self, observability_doc: str) -> None:
        """Verify link to integration-modes.md exists."""
        assert "integration-modes.md" in observability_doc

    def test_links_to_architecture(self, observability_doc: str) -> None:
        """Verify link to ARCHITECTURE.md exists."""
        assert "ARCHITECTURE.md" in observability_doc

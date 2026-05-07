"""Tests for the Notification SDK.

These tests verify the SDK's validation guards, policy overrides,
and channel/delivery mode derivation logic.
"""

from uuid import uuid4

import pytest

from notification.interfaces import DefaultContextProvider
from notification.models import (
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
from notification.policies import ModeOverride, NotificationPolicy, PolicyRegistry
from notification.sdk import NotificationSDK, ValidationError, create_sdk, get_sdk


class TestSDKValidationGuards:
    """Tests for SDK validation guards (hard requirements)."""

    @pytest.fixture
    def sdk(self) -> NotificationSDK:
        """Create a basic SDK instance for testing."""
        return NotificationSDK()

    @pytest.fixture
    def valid_context(self) -> AutonomyContext:
        """Create a valid AutonomyContext."""
        return AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

    def test_autonomy_context_required(self, sdk: NotificationSDK) -> None:
        """Test that autonomy_context is required (hard guard)."""
        with pytest.raises(ValidationError) as exc_info:
            sdk.send(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                title="Test",
                message="Test message",
                source="test",
                autonomy_context=None,
            )
        assert "autonomy_context is required" in str(exc_info.value)

    def test_context_from_provider(self) -> None:
        """Test that context can be obtained from provider."""
        agent_id = uuid4()
        provider = DefaultContextProvider(
            default_mode=AutonomyMode.LIVE,
            default_agent_id=agent_id,
        )
        sdk = NotificationSDK(context_provider=provider)

        result = sdk.send(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            title="Test",
            message="Test message",
            source="test",
        )

        assert result.status == DeliveryStatus.SUCCESS

    def test_provider_error_raises_validation_error(self) -> None:
        """Test that provider errors are wrapped in ValidationError."""
        # Provider without default agent_id will raise RuntimeError
        provider = DefaultContextProvider(default_mode=AutonomyMode.LIVE)
        sdk = NotificationSDK(context_provider=provider)

        with pytest.raises(ValidationError) as exc_info:
            sdk.send(
                notification_type="test.event",
                intent=NotificationIntent.INFORMATIONAL,
                title="Test",
                message="Test message",
                source="test",
            )
        assert "Failed to get autonomy context" in str(exc_info.value)

    def test_explicit_context_takes_precedence(self) -> None:
        """Test that explicit context overrides provider."""
        provider_agent_id = uuid4()
        explicit_agent_id = uuid4()

        provider = DefaultContextProvider(
            default_mode=AutonomyMode.PREVIEW,
            default_agent_id=provider_agent_id,
        )

        explicit_context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=explicit_agent_id,
        )

        delivered_notification: Notification | None = None

        def capture_handler(n: Notification) -> NotificationResult:
            nonlocal delivered_notification
            delivered_notification = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(
            context_provider=provider,
            delivery_handler=capture_handler,
        )

        sdk.send(
            notification_type="test.event",
            intent=NotificationIntent.INFORMATIONAL,
            title="Test",
            message="Test message",
            source="test",
            autonomy_context=explicit_context,
        )

        assert delivered_notification is not None
        assert delivered_notification.autonomy_context.agent_id == explicit_agent_id
        assert delivered_notification.autonomy_context.autonomy_mode == AutonomyMode.LIVE


class TestSDKDeliveryModeDeriation:
    """Tests for delivery mode derivation."""

    @pytest.fixture
    def sdk(self) -> NotificationSDK:
        return NotificationSDK()

    @pytest.fixture
    def live_context(self) -> AutonomyContext:
        return AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

    def test_safety_defaults_to_guaranteed(
        self, sdk: NotificationSDK, live_context: AutonomyContext
    ) -> None:
        """SAFETY intent should default to GUARANTEED delivery."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical safety issue",
            source="test",
            autonomy_context=live_context,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.GUARANTEED

    def test_governance_defaults_to_guaranteed(
        self, sdk: NotificationSDK, live_context: AutonomyContext
    ) -> None:
        """GOVERNANCE intent should default to GUARANTEED delivery."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        sdk.send_governance(
            notification_type="test.governance",
            title="Governance Alert",
            message="Governance issue",
            source="test",
            autonomy_context=live_context,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.GUARANTEED

    def test_operational_defaults_to_best_effort(
        self, sdk: NotificationSDK, live_context: AutonomyContext
    ) -> None:
        """OPERATIONAL intent should default to BEST_EFFORT delivery."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        sdk.send_operational(
            notification_type="test.operational",
            title="Operational Alert",
            message="Operational issue",
            source="test",
            autonomy_context=live_context,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_informational_defaults_to_best_effort(
        self, sdk: NotificationSDK, live_context: AutonomyContext
    ) -> None:
        """INFORMATIONAL intent should default to BEST_EFFORT delivery."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Information message",
            source="test",
            autonomy_context=live_context,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_delivery_mode_override(
        self, sdk: NotificationSDK, live_context: AutonomyContext
    ) -> None:
        """Explicit delivery_mode_override should take precedence."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        sdk.send(
            notification_type="test.info",
            intent=NotificationIntent.INFORMATIONAL,
            title="Info",
            message="Information message",
            source="test",
            autonomy_context=live_context,
            delivery_mode_override=DeliveryMode.GUARANTEED,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.GUARANTEED


class TestSDKChannelDerivation:
    """Tests for channel derivation based on intent and mode."""

    def test_live_safety_channels(self) -> None:
        """SAFETY in LIVE mode should route to Slack + WebSocket."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert Channel.SLACK in delivered.channels
        assert Channel.WEBSOCKET in delivered.channels

    def test_live_safety_irreversible_adds_pagerduty(self) -> None:
        """SAFETY with irreversible=True in LIVE mode should add PagerDuty."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Irreversible Action",
            message="Critical irreversible action",
            source="test",
            autonomy_context=context,
            irreversible=True,
        )

        assert delivered is not None
        assert Channel.PAGERDUTY in delivered.channels

    def test_preview_mode_websocket_only(self) -> None:
        """PREVIEW mode should route to WebSocket only for all intents."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.channels == [Channel.WEBSOCKET]

    def test_live_informational_websocket_only(self) -> None:
        """INFORMATIONAL in LIVE mode should route to WebSocket only."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.channels == [Channel.WEBSOCKET]

    def test_channels_override(self) -> None:
        """Explicit channels_override should take precedence."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
            channels_override=[Channel.EMAIL, Channel.SLACK],
        )

        assert delivered is not None
        assert Channel.EMAIL in delivered.channels
        assert Channel.SLACK in delivered.channels
        assert Channel.WEBSOCKET not in delivered.channels


class TestSDKRequireAck:
    """Tests for require_ack derivation."""

    def test_safety_live_requires_ack_by_default(self) -> None:
        """SAFETY in LIVE mode should require ack by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.require_ack is True

    def test_safety_preview_no_ack_required(self) -> None:
        """SAFETY in PREVIEW mode should NOT require ack by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.require_ack is False

    def test_operational_no_ack_required(self) -> None:
        """OPERATIONAL should NOT require ack by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_operational(
            notification_type="test.operational",
            title="Operational",
            message="Operational message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.require_ack is False

    def test_require_ack_override(self) -> None:
        """Explicit require_ack_override should take precedence."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        # SAFETY in LIVE normally requires ack, but we override to False
        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical",
            source="test",
            autonomy_context=context,
            require_ack_override=False,
        )

        assert delivered is not None
        assert delivered.require_ack is False


class TestSDKAckTimeout:
    """Tests for ack timeout derivation."""

    def test_safety_default_timeout(self) -> None:
        """SAFETY should have 15-minute default timeout."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety Alert",
            message="Critical",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.ack_timeout_minutes == 15

    def test_governance_default_timeout(self) -> None:
        """GOVERNANCE should have 30-minute default timeout when ack required."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        # Force require_ack to see the timeout
        sdk.send_governance(
            notification_type="test.governance",
            title="Governance Alert",
            message="Governance issue",
            source="test",
            autonomy_context=context,
            require_ack_override=True,
        )

        assert delivered is not None
        assert delivered.ack_timeout_minutes == 30

    def test_no_ack_no_timeout(self) -> None:
        """When require_ack is False, timeout should be None."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.ack_timeout_minutes is None


class TestSDKPolicyOverrides:
    """Tests for policy-based overrides."""

    def test_policy_overrides_delivery_mode(self) -> None:
        """Policy delivery_mode should override intent default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.info",
                delivery_mode=DeliveryMode.GUARANTEED,
            )
        )

        sdk = NotificationSDK(
            policy_registry=registry,
            delivery_handler=handler,
        )

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        # INFORMATIONAL normally gets BEST_EFFORT, but policy overrides
        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.GUARANTEED

    def test_policy_mode_override_controls_delivery_mode(self) -> None:
        """Policy delivery_mode_by_autonomy should override base policy mode."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.safety",
                delivery_mode=DeliveryMode.GUARANTEED,
                preview_override=ModeOverride(delivery_mode=DeliveryMode.BEST_EFFORT),
            )
        )

        sdk = NotificationSDK(
            policy_registry=registry,
            delivery_handler=handler,
        )

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety preview",
            message="Preview should be best effort",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.delivery_mode == DeliveryMode.BEST_EFFORT

    def test_policy_overrides_channels(self) -> None:
        """Policy channels_by_mode should override defaults."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.info",
                channels_by_mode={
                    AutonomyMode.LIVE: [Channel.EMAIL, Channel.SLACK],
                },
            )
        )

        sdk = NotificationSDK(
            policy_registry=registry,
            delivery_handler=handler,
        )

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        # INFORMATIONAL in LIVE normally gets WebSocket only
        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert Channel.EMAIL in delivered.channels
        assert Channel.SLACK in delivered.channels
        assert Channel.WEBSOCKET not in delivered.channels

    def test_policy_overrides_require_ack(self) -> None:
        """Policy require_ack should override defaults."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.operational",
                require_ack=True,
            )
        )

        sdk = NotificationSDK(
            policy_registry=registry,
            delivery_handler=handler,
        )

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        # OPERATIONAL normally doesn't require ack
        sdk.send_operational(
            notification_type="test.operational",
            title="Operational",
            message="Operational message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.require_ack is True

    def test_explicit_override_takes_precedence_over_policy(self) -> None:
        """Explicit overrides should take precedence over policy."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.info",
                delivery_mode=DeliveryMode.GUARANTEED,
                channels_by_mode={
                    AutonomyMode.LIVE: [Channel.EMAIL],
                },
            )
        )

        sdk = NotificationSDK(
            policy_registry=registry,
            delivery_handler=handler,
        )

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send(
            notification_type="test.info",
            intent=NotificationIntent.INFORMATIONAL,
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
            delivery_mode_override=DeliveryMode.BEST_EFFORT,
            channels_override=[Channel.SLACK],
        )

        assert delivered is not None
        # Explicit override beats policy
        assert delivered.delivery_mode == DeliveryMode.BEST_EFFORT
        assert delivered.channels == [Channel.SLACK]


class TestSDKPriority:
    """Tests for priority derivation."""

    def test_safety_high_priority(self) -> None:
        """SAFETY should have HIGH priority by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_safety(
            notification_type="test.safety",
            title="Safety",
            message="Safety message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.priority == Priority.HIGH

    def test_governance_high_priority(self) -> None:
        """GOVERNANCE should have HIGH priority by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_governance(
            notification_type="test.governance",
            title="Governance",
            message="Governance message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.priority == Priority.HIGH

    def test_operational_normal_priority(self) -> None:
        """OPERATIONAL should have NORMAL priority by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_operational(
            notification_type="test.operational",
            title="Operational",
            message="Operational message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.priority == Priority.NORMAL

    def test_informational_low_priority(self) -> None:
        """INFORMATIONAL should have LOW priority by default."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.priority == Priority.LOW


class TestSDKDedupKey:
    """Tests for dedup key generation."""

    def test_dedup_key_generated(self) -> None:
        """Dedup key should be auto-generated if not provided."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
        )

        assert delivered is not None
        assert delivered.dedup_key is not None
        assert len(delivered.dedup_key) == 16  # SHA256 truncated to 16 chars

    def test_custom_dedup_key(self) -> None:
        """Custom dedup_key should be used if provided."""
        delivered: Notification | None = None

        def handler(n: Notification) -> NotificationResult:
            nonlocal delivered
            delivered = n
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info",
            message="Info message",
            source="test",
            autonomy_context=context,
            dedup_key="custom-dedup-key-123",
        )

        assert delivered is not None
        assert delivered.dedup_key == "custom-dedup-key-123"

    def test_dedup_key_stable_for_same_inputs(self) -> None:
        """Same notification_type + agent_id should produce same dedup key."""
        notifications: list[Notification] = []

        def handler(n: Notification) -> NotificationResult:
            notifications.append(n)
            return NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.SUCCESS,
            )

        sdk = NotificationSDK(delivery_handler=handler)
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )

        # Send two notifications with same type and agent
        sdk.send_info(
            notification_type="test.info",
            title="Info 1",
            message="First message",
            source="test",
            autonomy_context=context,
        )

        sdk.send_info(
            notification_type="test.info",
            title="Info 2",
            message="Second message",
            source="test",
            autonomy_context=context,
        )

        assert len(notifications) == 2
        assert notifications[0].dedup_key == notifications[1].dedup_key


class TestSDKFactory:
    """Tests for SDK factory functions."""

    def test_create_sdk(self) -> None:
        """create_sdk should return a configured SDK instance."""
        sdk = create_sdk()
        assert isinstance(sdk, NotificationSDK)

    def test_get_sdk_singleton(self) -> None:
        """get_sdk should return the same instance."""
        sdk1 = get_sdk()
        sdk2 = get_sdk()
        assert sdk1 is sdk2

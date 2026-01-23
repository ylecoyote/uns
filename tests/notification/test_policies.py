"""Unit tests for the policy module."""

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)
from notification.policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
)


class TestDefaultDeliveryMode:
    """Tests for default delivery mode resolution."""

    def test_safety_is_guaranteed(self):
        """Test SAFETY intent defaults to GUARANTEED."""
        assert get_default_delivery_mode(NotificationIntent.SAFETY) == DeliveryMode.GUARANTEED

    def test_governance_is_guaranteed(self):
        """Test GOVERNANCE intent defaults to GUARANTEED."""
        assert get_default_delivery_mode(NotificationIntent.GOVERNANCE) == DeliveryMode.GUARANTEED

    def test_operational_is_best_effort(self):
        """Test OPERATIONAL intent defaults to BEST_EFFORT."""
        assert get_default_delivery_mode(NotificationIntent.OPERATIONAL) == DeliveryMode.BEST_EFFORT

    def test_informational_is_best_effort(self):
        """Test INFORMATIONAL intent defaults to BEST_EFFORT."""
        assert (
            get_default_delivery_mode(NotificationIntent.INFORMATIONAL) == DeliveryMode.BEST_EFFORT
        )


class TestDefaultChannels:
    """Tests for default channel resolution."""

    def test_preview_mode_websocket_only(self):
        """Test PREVIEW mode routes all intents to WebSocket only."""
        for intent in NotificationIntent:
            channels = get_default_channels(intent, AutonomyMode.PREVIEW)
            assert channels == [Channel.WEBSOCKET]

    def test_live_mode_safety_channels(self):
        """Test LIVE mode SAFETY intent routes to Slack + WebSocket."""
        channels = get_default_channels(NotificationIntent.SAFETY, AutonomyMode.LIVE)
        assert Channel.SLACK in channels
        assert Channel.WEBSOCKET in channels

    def test_live_mode_safety_irreversible_adds_pagerduty(self):
        """Test LIVE mode SAFETY with irreversible adds PagerDuty."""
        channels = get_default_channels(
            NotificationIntent.SAFETY, AutonomyMode.LIVE, irreversible=True
        )
        assert Channel.PAGERDUTY in channels

    def test_live_mode_informational_websocket_only(self):
        """Test LIVE mode INFORMATIONAL routes to WebSocket only."""
        channels = get_default_channels(NotificationIntent.INFORMATIONAL, AutonomyMode.LIVE)
        assert channels == [Channel.WEBSOCKET]

    def test_shadow_mode_operational_websocket(self):
        """Test SHADOW mode OPERATIONAL routes to WebSocket."""
        channels = get_default_channels(NotificationIntent.OPERATIONAL, AutonomyMode.SHADOW)
        assert channels == [Channel.WEBSOCKET]

    def test_shadow_mode_governance_slack_websocket(self):
        """Test SHADOW mode GOVERNANCE routes to Slack + WebSocket."""
        channels = get_default_channels(NotificationIntent.GOVERNANCE, AutonomyMode.SHADOW)
        assert Channel.SLACK in channels
        assert Channel.WEBSOCKET in channels


class TestDefaultRequireAck:
    """Tests for default ack requirement resolution."""

    def test_safety_live_requires_ack(self):
        """Test SAFETY + LIVE requires acknowledgment."""
        assert get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.LIVE) is True

    def test_safety_preview_no_ack(self):
        """Test SAFETY + PREVIEW doesn't require ack."""
        assert get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.PREVIEW) is False

    def test_governance_live_no_ack(self):
        """Test GOVERNANCE + LIVE doesn't require ack by default."""
        assert get_default_require_ack(NotificationIntent.GOVERNANCE, AutonomyMode.LIVE) is False

    def test_operational_live_no_ack(self):
        """Test OPERATIONAL doesn't require ack."""
        assert get_default_require_ack(NotificationIntent.OPERATIONAL, AutonomyMode.LIVE) is False


class TestDefaultAckTimeout:
    """Tests for default ack timeout."""

    def test_safety_timeout(self):
        """Test SAFETY has 15 minute timeout."""
        assert get_default_ack_timeout(NotificationIntent.SAFETY) == 15

    def test_governance_timeout(self):
        """Test GOVERNANCE has 30 minute timeout."""
        assert get_default_ack_timeout(NotificationIntent.GOVERNANCE) == 30


class TestPolicyRegistry:
    """Tests for PolicyRegistry."""

    def test_register_and_get_policy(self):
        """Test registering and retrieving a policy."""
        registry = PolicyRegistry()
        policy = NotificationPolicy(
            notification_type="test.notification",
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        registry.register(policy)

        retrieved = registry.get_sync("test.notification")
        assert retrieved == policy

    def test_get_nonexistent_returns_none(self):
        """Test getting nonexistent policy returns None."""
        registry = PolicyRegistry()
        assert registry.get_sync("nonexistent") is None

    def test_unregister_policy(self):
        """Test unregistering a policy."""
        registry = PolicyRegistry()
        policy = NotificationPolicy(notification_type="test.notification")
        registry.register(policy)
        registry.unregister("test.notification")

        assert registry.get_sync("test.notification") is None

    def test_get_delivery_mode_from_policy(self):
        """Test policy overrides delivery mode."""
        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                delivery_mode=DeliveryMode.GUARANTEED,
            )
        )

        mode = registry.get_delivery_mode("test.notification", NotificationIntent.OPERATIONAL)
        assert mode == DeliveryMode.GUARANTEED

    def test_get_delivery_mode_defaults_without_policy(self):
        """Test delivery mode falls back to default without policy."""
        registry = PolicyRegistry()

        mode = registry.get_delivery_mode("test.notification", NotificationIntent.SAFETY)
        assert mode == DeliveryMode.GUARANTEED

    def test_get_channels_from_policy(self):
        """Test policy overrides channels."""
        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                channels=[Channel.EMAIL, Channel.PAGERDUTY],
            )
        )

        channels = registry.get_channels_for_mode(
            "test.notification",
            NotificationIntent.INFORMATIONAL,
            AutonomyMode.LIVE,
        )
        assert channels == [Channel.EMAIL, Channel.PAGERDUTY]

    def test_get_channels_with_mode_override(self):
        """Test mode-specific channel override."""
        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                channels=[Channel.SLACK],
                mode_overrides={
                    AutonomyMode.PREVIEW: ModeOverride(channels=[Channel.WEBSOCKET]),
                },
            )
        )

        # PREVIEW mode should use override
        preview_channels = registry.get_channels_for_mode(
            "test.notification",
            NotificationIntent.SAFETY,
            AutonomyMode.PREVIEW,
        )
        assert preview_channels == [Channel.WEBSOCKET]

        # LIVE mode should use policy default
        live_channels = registry.get_channels_for_mode(
            "test.notification",
            NotificationIntent.SAFETY,
            AutonomyMode.LIVE,
        )
        assert live_channels == [Channel.SLACK]

    def test_get_require_ack_from_policy(self):
        """Test policy overrides require_ack."""
        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                require_ack=True,
            )
        )

        # Even for INFORMATIONAL, policy forces ack
        require_ack = registry.get_require_ack_for_mode(
            "test.notification",
            NotificationIntent.INFORMATIONAL,
            AutonomyMode.LIVE,
        )
        assert require_ack is True

    def test_get_ack_timeout_from_policy(self):
        """Test policy overrides ack timeout."""
        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                ack_timeout_minutes=5,
            )
        )

        timeout = registry.get_ack_timeout("test.notification", NotificationIntent.SAFETY)
        assert timeout == 5

    def test_get_dedup_window_from_policy(self):
        """Test policy overrides dedup window."""
        registry = PolicyRegistry()
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                dedup_window_seconds=60,
            )
        )

        window = registry.get_dedup_window("test.notification")
        assert window == 60

    def test_get_dedup_window_default(self):
        """Test dedup window falls back to default."""
        registry = PolicyRegistry()

        window = registry.get_dedup_window("nonexistent")
        assert window == 300  # DEFAULT_DEDUP_WINDOW_SECONDS

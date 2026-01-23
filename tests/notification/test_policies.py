"""Tests for the notification policy registry.

These tests verify policy lookup, default derivation, and mode-aware routing.
"""

import pytest

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)
from notification.policies import (
    NotificationPolicy,
    PolicyRegistry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
    get_policy_registry,
)


class TestNotificationPolicy:
    """Tests for NotificationPolicy dataclass."""

    def test_create_minimal_policy(self) -> None:
        """Test creating a policy with just notification_type."""
        policy = NotificationPolicy(notification_type="test.event")
        assert policy.notification_type == "test.event"
        assert policy.delivery_mode is None
        assert policy.require_ack is None
        assert policy.channels_by_mode == {}

    def test_create_full_policy(self) -> None:
        """Test creating a policy with all fields."""
        policy = NotificationPolicy(
            notification_type="trading.order_placed",
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            channels_by_mode={
                AutonomyMode.LIVE: [Channel.SLACK, Channel.WEBSOCKET],
                AutonomyMode.SHADOW: [Channel.WEBSOCKET],
            },
            ack_timeout_minutes=10,
            dedup_window_seconds=600,
            priority_override="HIGH",
        )
        assert policy.delivery_mode == DeliveryMode.GUARANTEED
        assert policy.require_ack is True
        assert policy.ack_timeout_minutes == 10

    def test_get_channels_for_mode(self) -> None:
        """Test getting channels for a specific mode."""
        policy = NotificationPolicy(
            notification_type="test.event",
            channels_by_mode={
                AutonomyMode.LIVE: [Channel.SLACK, Channel.EMAIL],
                AutonomyMode.PREVIEW: [Channel.WEBSOCKET],
            },
        )
        assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [
            Channel.SLACK,
            Channel.EMAIL,
        ]
        assert policy.get_channels_for_mode(AutonomyMode.PREVIEW) == [Channel.WEBSOCKET]
        assert policy.get_channels_for_mode(AutonomyMode.SHADOW) is None

    def test_get_require_ack_for_mode(self) -> None:
        """Test getting require_ack for a mode."""
        policy = NotificationPolicy(
            notification_type="test.event",
            require_ack=True,
        )
        assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is True

        policy_no_ack = NotificationPolicy(notification_type="test.event")
        assert policy_no_ack.get_require_ack_for_mode(AutonomyMode.LIVE) is None

    def test_policy_is_immutable(self) -> None:
        """Test that policy is frozen/immutable."""
        from dataclasses import FrozenInstanceError

        policy = NotificationPolicy(notification_type="test.event")
        with pytest.raises(FrozenInstanceError):
            policy.notification_type = "modified"  # type: ignore


class TestPolicyRegistry:
    """Tests for PolicyRegistry."""

    @pytest.fixture
    def registry(self) -> PolicyRegistry:
        """Create a fresh registry for each test."""
        return PolicyRegistry()

    def test_register_and_get(self, registry: PolicyRegistry) -> None:
        """Test registering and retrieving a policy."""
        policy = NotificationPolicy(notification_type="test.event")
        registry.register(policy)
        assert registry.get_sync("test.event") == policy

    def test_get_missing_returns_none(self, registry: PolicyRegistry) -> None:
        """Test that get_sync returns None for missing policies."""
        assert registry.get_sync("nonexistent") is None

    def test_unregister(self, registry: PolicyRegistry) -> None:
        """Test unregistering a policy."""
        policy = NotificationPolicy(notification_type="test.event")
        registry.register(policy)
        registry.unregister("test.event")
        assert registry.get_sync("test.event") is None

    def test_unregister_missing_raises(self, registry: PolicyRegistry) -> None:
        """Test that unregistering a missing policy raises KeyError."""
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")

    def test_get_all(self, registry: PolicyRegistry) -> None:
        """Test getting all registered policies."""
        policy1 = NotificationPolicy(notification_type="test.event1")
        policy2 = NotificationPolicy(notification_type="test.event2")
        registry.register(policy1)
        registry.register(policy2)

        all_policies = registry.get_all()
        assert len(all_policies) == 2
        assert "test.event1" in all_policies
        assert "test.event2" in all_policies

    def test_clear(self, registry: PolicyRegistry) -> None:
        """Test clearing all policies."""
        registry.register(NotificationPolicy(notification_type="test.event1"))
        registry.register(NotificationPolicy(notification_type="test.event2"))
        registry.clear()
        assert registry.get_all() == {}

    def test_load_from_dict(self, registry: PolicyRegistry) -> None:
        """Test loading policies from dictionary data."""
        policies_data = [
            {
                "notification_type": "trading.order_placed",
                "delivery_mode": "GUARANTEED",
                "require_ack": True,
                "channels_by_mode": {
                    "LIVE": ["SLACK", "WEBSOCKET"],
                    "PREVIEW": ["WEBSOCKET"],
                },
                "ack_timeout_minutes": 15,
            },
            {
                "notification_type": "trading.price_update",
                "delivery_mode": "BEST_EFFORT",
            },
        ]

        registry.load_from_dict(policies_data)

        policy1 = registry.get_sync("trading.order_placed")
        assert policy1 is not None
        assert policy1.delivery_mode == DeliveryMode.GUARANTEED
        assert policy1.require_ack is True
        assert policy1.get_channels_for_mode(AutonomyMode.LIVE) == [
            Channel.SLACK,
            Channel.WEBSOCKET,
        ]

        policy2 = registry.get_sync("trading.price_update")
        assert policy2 is not None
        assert policy2.delivery_mode == DeliveryMode.BEST_EFFORT


class TestDefaultFunctions:
    """Tests for default derivation functions."""

    def test_get_default_delivery_mode_safety(self) -> None:
        """SAFETY should default to GUARANTEED."""
        assert get_default_delivery_mode(NotificationIntent.SAFETY) == DeliveryMode.GUARANTEED

    def test_get_default_delivery_mode_governance(self) -> None:
        """GOVERNANCE should default to GUARANTEED."""
        assert get_default_delivery_mode(NotificationIntent.GOVERNANCE) == DeliveryMode.GUARANTEED

    def test_get_default_delivery_mode_operational(self) -> None:
        """OPERATIONAL should default to BEST_EFFORT."""
        assert get_default_delivery_mode(NotificationIntent.OPERATIONAL) == DeliveryMode.BEST_EFFORT

    def test_get_default_delivery_mode_informational(self) -> None:
        """INFORMATIONAL should default to BEST_EFFORT."""
        assert (
            get_default_delivery_mode(NotificationIntent.INFORMATIONAL) == DeliveryMode.BEST_EFFORT
        )

    def test_get_default_require_ack_safety_live(self) -> None:
        """SAFETY in LIVE should require ack."""
        assert get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.LIVE) is True

    def test_get_default_require_ack_safety_preview(self) -> None:
        """SAFETY in PREVIEW should not require ack."""
        assert get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.PREVIEW) is False

    def test_get_default_require_ack_operational(self) -> None:
        """OPERATIONAL should not require ack."""
        assert get_default_require_ack(NotificationIntent.OPERATIONAL, AutonomyMode.LIVE) is False

    def test_get_default_ack_timeout_safety(self) -> None:
        """SAFETY should have 15-minute timeout."""
        assert get_default_ack_timeout(NotificationIntent.SAFETY) == 15

    def test_get_default_ack_timeout_governance(self) -> None:
        """GOVERNANCE should have 30-minute timeout."""
        assert get_default_ack_timeout(NotificationIntent.GOVERNANCE) == 30

    def test_get_default_ack_timeout_operational(self) -> None:
        """OPERATIONAL should have no timeout."""
        assert get_default_ack_timeout(NotificationIntent.OPERATIONAL) is None


class TestDefaultChannels:
    """Tests for default channel derivation."""

    def test_safety_live_channels(self) -> None:
        """SAFETY in LIVE should use Slack + WebSocket."""
        channels = get_default_channels(NotificationIntent.SAFETY, AutonomyMode.LIVE)
        assert Channel.SLACK in channels
        assert Channel.WEBSOCKET in channels

    def test_safety_live_irreversible_adds_pagerduty(self) -> None:
        """SAFETY in LIVE with irreversible=True should add PagerDuty."""
        channels = get_default_channels(
            NotificationIntent.SAFETY, AutonomyMode.LIVE, irreversible=True
        )
        assert Channel.PAGERDUTY in channels

    def test_preview_mode_websocket_only(self) -> None:
        """PREVIEW mode should use WebSocket only for all intents."""
        for intent in NotificationIntent:
            channels = get_default_channels(intent, AutonomyMode.PREVIEW)
            assert channels == [Channel.WEBSOCKET]

    def test_informational_live_websocket_only(self) -> None:
        """INFORMATIONAL in LIVE should use WebSocket only."""
        channels = get_default_channels(NotificationIntent.INFORMATIONAL, AutonomyMode.LIVE)
        assert channels == [Channel.WEBSOCKET]

    def test_operational_live_slack(self) -> None:
        """OPERATIONAL in LIVE should use Slack."""
        channels = get_default_channels(NotificationIntent.OPERATIONAL, AutonomyMode.LIVE)
        assert channels == [Channel.SLACK]

    def test_operational_shadow_websocket(self) -> None:
        """OPERATIONAL in SHADOW should use WebSocket."""
        channels = get_default_channels(NotificationIntent.OPERATIONAL, AutonomyMode.SHADOW)
        assert channels == [Channel.WEBSOCKET]


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_policy_registry_singleton(self) -> None:
        """get_policy_registry should return the same instance."""
        registry1 = get_policy_registry()
        registry2 = get_policy_registry()
        assert registry1 is registry2

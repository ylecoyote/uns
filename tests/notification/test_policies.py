"""Tests for the policy schema and registry module.

Tests cover:
- NotificationPolicy creation and configuration
- Mode-aware channel resolution
- Mode-aware ack requirement resolution
- PolicyRegistry operations
- Fallback to SDK defaults when no policy exists
- Mode overrides apply deterministically
"""

import pytest

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
    get_default_delivery_mode,
    get_default_require_ack,
)
from notification.policies import (
    DEFAULT_DEDUP_WINDOW_SECONDS,
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    _get_default_channels,
    get_default_ack_timeout,
    get_default_channels,
    get_default_registry,
    get_policy_registry,
    configure_policy_registry,
    resolve_channels,
    resolve_delivery_mode,
    resolve_require_ack,
    set_default_registry,
)


class TestModeOverride:
    """Tests for ModeOverride model."""

    def test_create_empty_override(self) -> None:
        """Empty override should have all None values."""
        override = ModeOverride()
        assert override.channels is None
        assert override.require_ack is None
        assert override.delivery_mode is None

    def test_create_with_channels(self) -> None:
        """Override with channels only."""
        override = ModeOverride(channels=[Channel.WEBSOCKET])
        assert override.channels == [Channel.WEBSOCKET]
        assert override.require_ack is None

    def test_create_with_all_fields(self) -> None:
        """Override with all fields specified."""
        override = ModeOverride(
            channels=[Channel.SLACK, Channel.EMAIL],
            require_ack=True,
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        assert override.channels == [Channel.SLACK, Channel.EMAIL]
        assert override.require_ack is True
        assert override.delivery_mode == DeliveryMode.GUARANTEED


class TestNotificationPolicy:
    """Tests for NotificationPolicy model."""

    def test_create_minimal_policy(self) -> None:
        """Policy with only required field."""
        policy = NotificationPolicy(notification_type="test.event")
        assert policy.notification_type == "test.event"
        assert policy.channels == []
        assert policy.require_ack is None

    def test_create_full_policy(self) -> None:
        """Policy with all fields specified."""
        policy = NotificationPolicy(
            notification_type="trading.order.executed",
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.SLACK, Channel.WEBSOCKET],
            require_ack=True,
            ack_timeout_minutes=15,
            dedup_window_seconds=300,
        )
        assert policy.notification_type == "trading.order.executed"
        assert policy.intent == NotificationIntent.SAFETY
        assert policy.delivery_mode == DeliveryMode.GUARANTEED
        assert policy.channels == [Channel.SLACK, Channel.WEBSOCKET]
        assert policy.require_ack is True
        assert policy.ack_timeout_minutes == 15
        assert policy.dedup_window_seconds == 300

    def test_policy_with_mode_overrides(self) -> None:
        """Policy with mode-specific overrides."""
        policy = NotificationPolicy(
            notification_type="test.event",
            channels=[Channel.SLACK],
            preview_override=ModeOverride(channels=[Channel.WEBSOCKET]),
            shadow_override=ModeOverride(channels=[Channel.WEBSOCKET, Channel.SLACK]),
            live_override=ModeOverride(
                channels=[Channel.SLACK, Channel.PAGERDUTY], require_ack=True
            ),
        )
        assert policy.preview_override is not None
        assert policy.preview_override.channels == [Channel.WEBSOCKET]


class TestPolicyChannelResolution:
    """Tests for get_channels_for_mode method."""

    def test_preview_mode_override_applies(self) -> None:
        """PREVIEW mode override should take precedence."""
        policy = NotificationPolicy(
            notification_type="test.event",
            channels=[Channel.SLACK, Channel.EMAIL],
            preview_override=ModeOverride(channels=[Channel.WEBSOCKET]),
        )
        channels = policy.get_channels_for_mode(
            AutonomyMode.PREVIEW, NotificationIntent.OPERATIONAL
        )
        assert channels == [Channel.WEBSOCKET]

    def test_shadow_mode_override_applies(self) -> None:
        """SHADOW mode override should take precedence."""
        policy = NotificationPolicy(
            notification_type="test.event",
            channels=[Channel.SLACK],
            shadow_override=ModeOverride(channels=[Channel.WEBSOCKET, Channel.SLACK]),
        )
        channels = policy.get_channels_for_mode(
            AutonomyMode.SHADOW, NotificationIntent.GOVERNANCE
        )
        assert channels == [Channel.WEBSOCKET, Channel.SLACK]

    def test_live_mode_override_applies(self) -> None:
        """LIVE mode override should take precedence."""
        policy = NotificationPolicy(
            notification_type="test.event",
            channels=[Channel.WEBSOCKET],
            live_override=ModeOverride(
                channels=[Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY]
            ),
        )
        channels = policy.get_channels_for_mode(
            AutonomyMode.LIVE, NotificationIntent.SAFETY
        )
        assert channels == [Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY]

    def test_fallback_to_base_channels(self) -> None:
        """Should use base channels when no mode override."""
        policy = NotificationPolicy(
            notification_type="test.event",
            channels=[Channel.SLACK, Channel.EMAIL],
        )
        # No LIVE override, should use base channels
        channels = policy.get_channels_for_mode(
            AutonomyMode.LIVE, NotificationIntent.OPERATIONAL
        )
        assert channels == [Channel.SLACK, Channel.EMAIL]

    def test_fallback_to_sdk_defaults(self) -> None:
        """Should use SDK defaults when no policy channels defined."""
        policy = NotificationPolicy(notification_type="test.event")
        # No channels defined, should use SDK defaults
        channels = policy.get_channels_for_mode(
            AutonomyMode.LIVE, NotificationIntent.SAFETY
        )
        # SDK default for LIVE + SAFETY is [SLACK, WEBSOCKET]
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]


class TestPolicyAckResolution:
    """Tests for get_require_ack_for_mode method."""

    def test_mode_override_ack_takes_precedence(self) -> None:
        """Mode override require_ack should take precedence."""
        policy = NotificationPolicy(
            notification_type="test.event",
            require_ack=False,
            live_override=ModeOverride(require_ack=True),
        )
        assert (
            policy.get_require_ack_for_mode(
                AutonomyMode.LIVE, NotificationIntent.OPERATIONAL
            )
            is True
        )

    def test_base_require_ack_used(self) -> None:
        """Base require_ack used when no mode override."""
        policy = NotificationPolicy(
            notification_type="test.event",
            require_ack=True,
        )
        assert (
            policy.get_require_ack_for_mode(
                AutonomyMode.PREVIEW, NotificationIntent.INFORMATIONAL
            )
            is True
        )

    def test_fallback_to_sdk_default_for_ack(self) -> None:
        """SDK default: SAFETY + LIVE = require_ack True."""
        policy = NotificationPolicy(notification_type="test.event")
        # SDK default: SAFETY + LIVE = True
        assert (
            policy.get_require_ack_for_mode(
                AutonomyMode.LIVE, NotificationIntent.SAFETY
            )
            is True
        )
        # SDK default: SAFETY + PREVIEW = False
        assert (
            policy.get_require_ack_for_mode(
                AutonomyMode.PREVIEW, NotificationIntent.SAFETY
            )
            is False
        )

    def test_override_can_disable_ack(self) -> None:
        """Override can explicitly disable ack requirement."""
        policy = NotificationPolicy(
            notification_type="test.event",
            require_ack=True,
            live_override=ModeOverride(require_ack=False),
        )
        assert (
            policy.get_require_ack_for_mode(
                AutonomyMode.LIVE, NotificationIntent.SAFETY
            )
            is False
        )


class TestPolicyDeliveryModeResolution:
    """Tests for get_delivery_mode_for_mode method."""

    def test_mode_override_delivery_mode(self) -> None:
        """Mode override delivery_mode should take precedence."""
        policy = NotificationPolicy(
            notification_type="test.event",
            delivery_mode=DeliveryMode.BEST_EFFORT,
            live_override=ModeOverride(delivery_mode=DeliveryMode.GUARANTEED),
        )
        assert (
            policy.get_delivery_mode_for_mode(
                AutonomyMode.LIVE, NotificationIntent.INFORMATIONAL
            )
            == DeliveryMode.GUARANTEED
        )

    def test_base_delivery_mode_used(self) -> None:
        """Base delivery_mode used when no mode override."""
        policy = NotificationPolicy(
            notification_type="test.event",
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        assert (
            policy.get_delivery_mode_for_mode(
                AutonomyMode.PREVIEW, NotificationIntent.INFORMATIONAL
            )
            == DeliveryMode.GUARANTEED
        )

    def test_fallback_to_sdk_default_for_delivery_mode(self) -> None:
        """SDK default derivation based on intent."""
        policy = NotificationPolicy(notification_type="test.event")
        # SAFETY -> GUARANTEED
        assert (
            policy.get_delivery_mode_for_mode(
                AutonomyMode.LIVE, NotificationIntent.SAFETY
            )
            == DeliveryMode.GUARANTEED
        )
        # INFORMATIONAL -> BEST_EFFORT
        assert (
            policy.get_delivery_mode_for_mode(
                AutonomyMode.LIVE, NotificationIntent.INFORMATIONAL
            )
            == DeliveryMode.BEST_EFFORT
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
    """Tests for _get_default_channels SDK defaults."""

    def test_preview_mode_always_websocket(self) -> None:
        """PREVIEW mode should always return WebSocket only."""
        for intent in NotificationIntent:
            channels = _get_default_channels(AutonomyMode.PREVIEW, intent)
            assert channels == [Channel.WEBSOCKET], f"Failed for {intent}"

    def test_live_mode_safety(self) -> None:
        """LIVE + SAFETY -> Slack, WebSocket."""
        channels = _get_default_channels(AutonomyMode.LIVE, NotificationIntent.SAFETY)
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_live_mode_governance(self) -> None:
        """LIVE + GOVERNANCE -> Slack, WebSocket."""
        channels = _get_default_channels(
            AutonomyMode.LIVE, NotificationIntent.GOVERNANCE
        )
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_live_mode_operational(self) -> None:
        """LIVE + OPERATIONAL -> Slack."""
        channels = _get_default_channels(
            AutonomyMode.LIVE, NotificationIntent.OPERATIONAL
        )
        assert channels == [Channel.SLACK]

    def test_live_mode_informational(self) -> None:
        """LIVE + INFORMATIONAL -> WebSocket."""
        channels = _get_default_channels(
            AutonomyMode.LIVE, NotificationIntent.INFORMATIONAL
        )
        assert channels == [Channel.WEBSOCKET]

    def test_shadow_mode_operational(self) -> None:
        """SHADOW + OPERATIONAL -> WebSocket (override from LIVE)."""
        channels = _get_default_channels(
            AutonomyMode.SHADOW, NotificationIntent.OPERATIONAL
        )
        assert channels == [Channel.WEBSOCKET]

    def test_shadow_mode_governance(self) -> None:
        """SHADOW + GOVERNANCE -> Slack, WebSocket (explicit override)."""
        channels = _get_default_channels(
            AutonomyMode.SHADOW, NotificationIntent.GOVERNANCE
        )
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_shadow_mode_safety_follows_live(self) -> None:
        """SHADOW + SAFETY -> follows LIVE defaults."""
        channels = _get_default_channels(
            AutonomyMode.SHADOW, NotificationIntent.SAFETY
        )
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_live_mode_safety_irreversible_adds_pagerduty(self):
        """Test LIVE mode SAFETY with irreversible adds PagerDuty."""
        channels = get_default_channels(
            NotificationIntent.SAFETY, AutonomyMode.LIVE, irreversible=True
        )
        assert Channel.PAGERDUTY in channels


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
    """Tests for PolicyRegistry class."""

    @pytest.fixture
    def registry(self) -> PolicyRegistry:
        """Create a fresh registry for each test."""
        return PolicyRegistry()

    def test_empty_registry(self, registry: PolicyRegistry) -> None:
        """Empty registry should return None for lookups."""
        assert registry.get_sync("nonexistent") is None
        assert len(registry) == 0

    def test_register_policy(self, registry: PolicyRegistry) -> None:
        """Can register and retrieve a policy."""
        policy = NotificationPolicy(notification_type="test.event")
        registry.register(policy)
        assert registry.get_sync("test.event") == policy
        assert len(registry) == 1

    def test_register_many(self, registry: PolicyRegistry) -> None:
        """Can register multiple policies at once."""
        policies = [
            NotificationPolicy(notification_type="event.a"),
            NotificationPolicy(notification_type="event.b"),
            NotificationPolicy(notification_type="event.c"),
        ]
        registry.register_many(policies)
        assert len(registry) == 3
        assert registry.get_sync("event.a") is not None
        assert registry.get_sync("event.b") is not None
        assert registry.get_sync("event.c") is not None

    def test_unregister_policy(self, registry: PolicyRegistry) -> None:
        """Can remove a registered policy."""
        policy = NotificationPolicy(notification_type="test.event")
        registry.register(policy)
        assert registry.unregister("test.event") is True
        assert registry.get_sync("test.event") is None
        assert len(registry) == 0

    def test_unregister_nonexistent(self, registry: PolicyRegistry) -> None:
        """Unregistering nonexistent policy returns False."""
        assert registry.unregister("nonexistent") is False

    def test_has_policy(self, registry: PolicyRegistry) -> None:
        """has_policy returns correct boolean."""
        policy = NotificationPolicy(notification_type="test.event")
        assert registry.has_policy("test.event") is False
        registry.register(policy)
        assert registry.has_policy("test.event") is True

    def test_list_notification_types(self, registry: PolicyRegistry) -> None:
        """list_notification_types returns all registered types."""
        registry.register(NotificationPolicy(notification_type="a"))
        registry.register(NotificationPolicy(notification_type="b"))
        types = registry.list_notification_types()
        assert set(types) == {"a", "b"}

    def test_clear_registry(self, registry: PolicyRegistry) -> None:
        """clear removes all policies."""
        registry.register(NotificationPolicy(notification_type="a"))
        registry.register(NotificationPolicy(notification_type="b"))
        registry.clear()
        assert len(registry) == 0
        assert registry.list_notification_types() == []

    def test_overwrite_policy(self, registry: PolicyRegistry) -> None:
        """Registering same type overwrites existing policy."""
        policy1 = NotificationPolicy(
            notification_type="test.event", channels=[Channel.SLACK]
        )
        policy2 = NotificationPolicy(
            notification_type="test.event", channels=[Channel.EMAIL]
        )
        registry.register(policy1)
        registry.register(policy2)
        assert len(registry) == 1
        retrieved = registry.get_sync("test.event")
        assert retrieved is not None
        assert retrieved.channels == [Channel.EMAIL]

    def test_get_delivery_mode_from_policy(self, registry: PolicyRegistry):
        """Test policy overrides delivery mode."""
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                delivery_mode=DeliveryMode.GUARANTEED,
            )
        )

        mode = registry.get_delivery_mode("test.notification", NotificationIntent.OPERATIONAL)
        assert mode == DeliveryMode.GUARANTEED

    def test_get_delivery_mode_defaults_without_policy(self, registry: PolicyRegistry):
        """Test delivery mode falls back to default without policy."""
        mode = registry.get_delivery_mode("test.notification", NotificationIntent.SAFETY)
        assert mode == DeliveryMode.GUARANTEED

    def test_get_channels_from_policy(self, registry: PolicyRegistry):
        """Test policy overrides channels."""
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

    def test_get_channels_with_mode_override(self, registry: PolicyRegistry):
        """Test mode-specific channel override."""
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

    def test_get_require_ack_from_policy(self, registry: PolicyRegistry):
        """Test policy overrides require_ack."""
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

    def test_get_ack_timeout_from_policy(self, registry: PolicyRegistry):
        """Test policy overrides ack timeout."""
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                ack_timeout_minutes=5,
            )
        )

        timeout = registry.get_ack_timeout("test.notification", NotificationIntent.SAFETY)
        assert timeout == 5

    def test_get_dedup_window_from_policy(self, registry: PolicyRegistry):
        """Test policy overrides dedup window."""
        registry.register(
            NotificationPolicy(
                notification_type="test.notification",
                dedup_window_seconds=60,
            )
        )

        window = registry.get_dedup_window("test.notification")
        assert window == 60

    def test_get_dedup_window_default(self, registry: PolicyRegistry):
        """Test dedup window falls back to default."""
        window = registry.get_dedup_window("nonexistent")
        assert window == DEFAULT_DEDUP_WINDOW_SECONDS


class TestDefaultRegistry:
    """Tests for global default registry management."""

    def test_get_default_registry_singleton(self) -> None:
        """get_default_registry returns same instance."""
        reg1 = get_default_registry()
        reg2 = get_default_registry()
        assert reg1 is reg2

    def test_set_default_registry(self) -> None:
        """Can replace the default registry."""
        original = get_default_registry()
        new_registry = PolicyRegistry()
        set_default_registry(new_registry)
        assert get_default_registry() is new_registry
        # Restore original for other tests
        set_default_registry(original)


class TestGlobalPolicyRegistry:
    """Tests for the get_policy_registry and configure_policy_registry functions."""

    def test_get_policy_registry_singleton(self) -> None:
        """get_policy_registry returns same instance."""
        reg1 = get_policy_registry()
        reg2 = get_policy_registry()
        assert reg1 is reg2

    def test_configure_policy_registry(self) -> None:
        """Can configure the global policy registry."""
        new_registry = PolicyRegistry()
        result = configure_policy_registry(new_registry)
        assert result is new_registry
        assert get_policy_registry() is new_registry


class TestResolveChannels:
    """Tests for resolve_channels helper function."""

    @pytest.fixture
    def registry(self) -> PolicyRegistry:
        """Create a registry with test policies."""
        reg = PolicyRegistry()
        reg.register(
            NotificationPolicy(
                notification_type="custom.event",
                channels=[Channel.EMAIL],
                preview_override=ModeOverride(channels=[Channel.WEBSOCKET]),
            )
        )
        return reg

    def test_resolve_with_policy(self, registry: PolicyRegistry) -> None:
        """Uses policy channels when policy exists."""
        channels = resolve_channels(
            notification_type="custom.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.OPERATIONAL,
            registry=registry,
        )
        assert channels == [Channel.EMAIL]

    def test_resolve_with_policy_mode_override(self, registry: PolicyRegistry) -> None:
        """Uses policy mode override when applicable."""
        channels = resolve_channels(
            notification_type="custom.event",
            autonomy_mode=AutonomyMode.PREVIEW,
            intent=NotificationIntent.OPERATIONAL,
            registry=registry,
        )
        assert channels == [Channel.WEBSOCKET]

    def test_resolve_without_policy(self, registry: PolicyRegistry) -> None:
        """Falls back to SDK defaults when no policy."""
        channels = resolve_channels(
            notification_type="unknown.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.SAFETY,
            registry=registry,
        )
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_resolve_adds_pagerduty_for_irreversible_safety(
        self, registry: PolicyRegistry
    ) -> None:
        """Adds PagerDuty for irreversible SAFETY notifications."""
        channels = resolve_channels(
            notification_type="unknown.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.SAFETY,
            irreversible=True,
            registry=registry,
        )
        assert Channel.PAGERDUTY in channels
        assert Channel.SLACK in channels
        assert Channel.WEBSOCKET in channels

    def test_resolve_no_duplicate_pagerduty(self) -> None:
        """Doesn't add duplicate PagerDuty if already in channels."""
        reg = PolicyRegistry()
        reg.register(
            NotificationPolicy(
                notification_type="pager.event",
                channels=[Channel.SLACK, Channel.PAGERDUTY],
            )
        )
        channels = resolve_channels(
            notification_type="pager.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.SAFETY,
            irreversible=True,
            registry=reg,
        )
        assert channels.count(Channel.PAGERDUTY) == 1


class TestResolveRequireAck:
    """Tests for resolve_require_ack helper function."""

    @pytest.fixture
    def registry(self) -> PolicyRegistry:
        """Create a registry with test policies."""
        reg = PolicyRegistry()
        reg.register(
            NotificationPolicy(
                notification_type="ack.required",
                require_ack=True,
            )
        )
        reg.register(
            NotificationPolicy(
                notification_type="ack.mode.override",
                require_ack=False,
                live_override=ModeOverride(require_ack=True),
            )
        )
        return reg

    def test_resolve_with_policy_require_ack(self, registry: PolicyRegistry) -> None:
        """Uses policy require_ack when set."""
        result = resolve_require_ack(
            notification_type="ack.required",
            autonomy_mode=AutonomyMode.PREVIEW,
            intent=NotificationIntent.INFORMATIONAL,
            registry=registry,
        )
        assert result is True

    def test_resolve_with_mode_override(self, registry: PolicyRegistry) -> None:
        """Mode override takes precedence."""
        # Without mode override (PREVIEW uses base)
        result_preview = resolve_require_ack(
            notification_type="ack.mode.override",
            autonomy_mode=AutonomyMode.PREVIEW,
            intent=NotificationIntent.INFORMATIONAL,
            registry=registry,
        )
        assert result_preview is False

        # With mode override (LIVE)
        result_live = resolve_require_ack(
            notification_type="ack.mode.override",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.INFORMATIONAL,
            registry=registry,
        )
        assert result_live is True

    def test_resolve_sdk_default(self, registry: PolicyRegistry) -> None:
        """Falls back to SDK default when no policy."""
        # SAFETY + LIVE = True
        result = resolve_require_ack(
            notification_type="unknown.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.SAFETY,
            registry=registry,
        )
        assert result is True


class TestResolveDeliveryMode:
    """Tests for resolve_delivery_mode helper function."""

    @pytest.fixture
    def registry(self) -> PolicyRegistry:
        """Create a registry with test policies."""
        reg = PolicyRegistry()
        reg.register(
            NotificationPolicy(
                notification_type="guaranteed.event",
                delivery_mode=DeliveryMode.GUARANTEED,
            )
        )
        return reg

    def test_resolve_with_policy(self, registry: PolicyRegistry) -> None:
        """Uses policy delivery_mode when set."""
        result = resolve_delivery_mode(
            notification_type="guaranteed.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.INFORMATIONAL,
            registry=registry,
        )
        assert result == DeliveryMode.GUARANTEED

    def test_resolve_sdk_default(self, registry: PolicyRegistry) -> None:
        """Falls back to SDK default based on intent."""
        # SAFETY -> GUARANTEED
        result_safety = resolve_delivery_mode(
            notification_type="unknown.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.SAFETY,
            registry=registry,
        )
        assert result_safety == DeliveryMode.GUARANTEED

        # INFORMATIONAL -> BEST_EFFORT
        result_info = resolve_delivery_mode(
            notification_type="unknown.event",
            autonomy_mode=AutonomyMode.LIVE,
            intent=NotificationIntent.INFORMATIONAL,
            registry=registry,
        )
        assert result_info == DeliveryMode.BEST_EFFORT


class TestInvariantsFromPRD:
    """Tests that verify PRD invariants are enforced."""

    def test_safety_governance_elevated_delivery(self) -> None:
        """SAFETY and GOVERNANCE imply elevated delivery guarantees (SDK default)."""
        registry = PolicyRegistry()

        for intent in [NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE]:
            mode = resolve_delivery_mode(
                "any.type", AutonomyMode.LIVE, intent, registry
            )
            assert (
                mode == DeliveryMode.GUARANTEED
            ), f"{intent} should default to GUARANTEED"

    def test_operational_informational_best_effort(self) -> None:
        """OPERATIONAL and INFORMATIONAL default to BEST_EFFORT."""
        registry = PolicyRegistry()

        for intent in [
            NotificationIntent.OPERATIONAL,
            NotificationIntent.INFORMATIONAL,
        ]:
            mode = resolve_delivery_mode(
                "any.type", AutonomyMode.LIVE, intent, registry
            )
            assert (
                mode == DeliveryMode.BEST_EFFORT
            ), f"{intent} should default to BEST_EFFORT"

    def test_safety_live_requires_ack(self) -> None:
        """SAFETY + LIVE = require_ack True (SDK default)."""
        registry = PolicyRegistry()
        result = resolve_require_ack(
            "any.type", AutonomyMode.LIVE, NotificationIntent.SAFETY, registry
        )
        assert result is True

    def test_safety_non_live_no_ack(self) -> None:
        """SAFETY + non-LIVE = require_ack False (SDK default)."""
        registry = PolicyRegistry()
        for mode in [AutonomyMode.PREVIEW, AutonomyMode.SHADOW]:
            result = resolve_require_ack(
                "any.type", mode, NotificationIntent.SAFETY, registry
            )
            assert result is False, f"SAFETY + {mode} should not require ack by default"

    def test_policy_lookup_failure_uses_defaults(self) -> None:
        """When policy lookup returns None, SDK defaults are used."""
        registry = PolicyRegistry()

        # No policy registered for "missing.type"
        channels = resolve_channels(
            "missing.type",
            AutonomyMode.LIVE,
            NotificationIntent.SAFETY,
            registry=registry,
        )
        # Should get SDK default channels
        assert channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_mode_overrides_apply_deterministically(self) -> None:
        """Mode overrides should always produce the same result."""
        policy = NotificationPolicy(
            notification_type="deterministic.test",
            channels=[Channel.EMAIL],
            preview_override=ModeOverride(channels=[Channel.WEBSOCKET]),
            live_override=ModeOverride(channels=[Channel.SLACK, Channel.PAGERDUTY]),
        )

        # Same inputs should produce same outputs every time
        for _ in range(10):
            preview_channels = policy.get_channels_for_mode(
                AutonomyMode.PREVIEW, NotificationIntent.SAFETY
            )
            live_channels = policy.get_channels_for_mode(
                AutonomyMode.LIVE, NotificationIntent.SAFETY
            )
            shadow_channels = policy.get_channels_for_mode(
                AutonomyMode.SHADOW, NotificationIntent.SAFETY
            )

            assert preview_channels == [Channel.WEBSOCKET]
            assert live_channels == [Channel.SLACK, Channel.PAGERDUTY]
            assert shadow_channels == [Channel.EMAIL]  # No shadow override, uses base

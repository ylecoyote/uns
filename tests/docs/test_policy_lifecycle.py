"""Tests for policy-lifecycle.md documentation.

Tests cover:
- Document structure and completeness
- Code examples from documentation work correctly
- Policy resolution priority is accurate
- Fallback behavior documentation matches implementation
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)
from notification.policies import (
    DEFAULT_DEDUP_WINDOW_SECONDS,
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
    get_policy_registry,
    set_policy_registry,
)

# Path to the policy lifecycle documentation
POLICY_LIFECYCLE_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "sections" / "policy-lifecycle.md"
)


@pytest.fixture
def policy_lifecycle_doc() -> str:
    """Load the policy lifecycle documentation."""
    assert POLICY_LIFECYCLE_PATH.exists(), (
        f"policy-lifecycle.md not found at {POLICY_LIFECYCLE_PATH}"
    )
    return POLICY_LIFECYCLE_PATH.read_text()


@pytest.fixture
def clean_registry() -> PolicyRegistry:
    """Provide a clean registry for each test."""
    registry = PolicyRegistry()
    original = get_policy_registry()
    set_policy_registry(registry)
    yield registry
    set_policy_registry(original)


class TestPolicyLifecycleDocExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify policy-lifecycle.md exists."""
        assert POLICY_LIFECYCLE_PATH.exists()

    def test_file_not_empty(self, policy_lifecycle_doc: str) -> None:
        """Verify policy-lifecycle.md is not empty."""
        assert len(policy_lifecycle_doc) > 0

    def test_is_markdown(self, policy_lifecycle_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in policy_lifecycle_doc


class TestPolicyLifecycleDocStructure:
    """Test the structure of the policy lifecycle documentation."""

    def test_has_title(self, policy_lifecycle_doc: str) -> None:
        """Verify document has a title."""
        assert policy_lifecycle_doc.startswith("# Policy Lifecycle")

    def test_has_overview_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document has overview section."""
        assert "## Overview" in policy_lifecycle_doc

    def test_has_policy_states_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document describes policy states."""
        assert "## Policy States" in policy_lifecycle_doc
        assert "DRAFT" in policy_lifecycle_doc
        assert "PREVIEW" in policy_lifecycle_doc
        assert "ACTIVE" in policy_lifecycle_doc
        assert "RETIRED" in policy_lifecycle_doc

    def test_has_policy_loading_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document describes policy loading."""
        assert "## Policy Loading" in policy_lifecycle_doc

    def test_has_policy_versioning_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document describes policy versioning."""
        assert "## Policy Versioning" in policy_lifecycle_doc

    def test_has_policy_application_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document describes policy application."""
        assert "## Policy Application" in policy_lifecycle_doc

    def test_has_registry_unavailability_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document describes fallback behavior."""
        assert "## Registry Unavailability" in policy_lifecycle_doc
        assert "Safe Fallback" in policy_lifecycle_doc

    def test_has_api_reference_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document has API reference."""
        assert "## API Reference" in policy_lifecycle_doc


class TestPolicyStateRuntimeBoundary:
    """Test policy state documentation for implemented runtime boundaries.

    These tests verify that the documentation clearly distinguishes between
    direct registry compatibility and database-backed lifecycle loading.
    """

    def test_has_current_implementation_note(self, policy_lifecycle_doc: str) -> None:
        """Verify document has current implementation note section."""
        assert "### Current Implementation Note" in policy_lifecycle_doc

    def test_current_implementation_describes_active_behavior(
        self, policy_lifecycle_doc: str
    ) -> None:
        """Verify current implementation note explains runtime loading behavior."""
        assert "load_runtime_registry()" in policy_lifecycle_doc
        assert "loads only **ACTIVE** policies" in policy_lifecycle_doc
        assert "load_shadow_registry()" in policy_lifecycle_doc
        assert "loads only **PREVIEW** policies" in policy_lifecycle_doc

    def test_has_state_lifecycle_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document has implemented state lifecycle management section."""
        assert "### State Lifecycle Management" in policy_lifecycle_doc

    def test_state_lifecycle_section_describes_status_meanings(
        self, policy_lifecycle_doc: str
    ) -> None:
        """Verify state lifecycle section explains the persisted status meanings."""
        assert "ACTIVE policies are runtime-enforced" in policy_lifecycle_doc
        assert "PREVIEW policies are shadow-evaluated" in policy_lifecycle_doc
        assert "DRAFT policies are editable" in policy_lifecycle_doc
        assert "RETIRED policies are terminal audit history" in policy_lifecycle_doc

    def test_has_planned_version_management_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document has planned version management section."""
        assert "### Planned: Version Management" in policy_lifecycle_doc

    def test_planned_version_management_references_rationale(
        self, policy_lifecycle_doc: str
    ) -> None:
        """Verify planned version management section references the rationale."""
        # The section should reference the Policy States section for rationale
        assert "See [Policy States](#policy-states) for rationale" in policy_lifecycle_doc

    def test_has_planned_policy_hashing_section(self, policy_lifecycle_doc: str) -> None:
        """Verify document has planned policy content hashing section."""
        assert "### Planned: Policy Content Hashing" in policy_lifecycle_doc

    def test_distinguishes_planned_from_implemented(self, policy_lifecycle_doc: str) -> None:
        """Verify document clearly distinguishes planned from implemented features.

        The documentation should clearly label what is currently implemented
        versus what is planned for future implementation.
        """
        # Current behavior sections exist
        assert (
            "### Current Behavior" in policy_lifecycle_doc
            or "### Current Implementation Note" in policy_lifecycle_doc
        )

        # Planned sections are labeled with "Planned:"
        planned_sections = policy_lifecycle_doc.count("### Planned:")
        assert planned_sections >= 2, "Should have multiple planned sections"


class TestPolicyLifecycleDocContent:
    """Test the content completeness of the documentation."""

    def test_documents_resolution_priority(self, policy_lifecycle_doc: str) -> None:
        """Verify resolution priority is documented."""
        assert "Resolution Priority" in policy_lifecycle_doc
        assert "Explicit parameter override" in policy_lifecycle_doc
        assert "Policy value" in policy_lifecycle_doc
        assert "SDK default" in policy_lifecycle_doc

    def test_documents_channel_defaults(self, policy_lifecycle_doc: str) -> None:
        """Verify channel defaults by mode are documented."""
        assert "LIVE" in policy_lifecycle_doc
        assert "SHADOW" in policy_lifecycle_doc
        assert "PREVIEW" in policy_lifecycle_doc
        assert "WebSocket" in policy_lifecycle_doc
        assert "Slack" in policy_lifecycle_doc

    def test_documents_ack_defaults(self, policy_lifecycle_doc: str) -> None:
        """Verify acknowledgment defaults are documented."""
        assert "SAFETY" in policy_lifecycle_doc
        assert "require_ack" in policy_lifecycle_doc

    def test_documents_dedup_window(self, policy_lifecycle_doc: str) -> None:
        """Verify deduplication window is documented."""
        assert "Deduplication" in policy_lifecycle_doc
        assert "300" in policy_lifecycle_doc or "5 minute" in policy_lifecycle_doc

    def test_documents_fallback_behavior(self, policy_lifecycle_doc: str) -> None:
        """Verify fallback behavior is documented."""
        assert "No exception raised" in policy_lifecycle_doc
        assert "SDK defaults apply" in policy_lifecycle_doc

    def test_includes_code_examples(self, policy_lifecycle_doc: str) -> None:
        """Verify document includes code examples."""
        assert "```python" in policy_lifecycle_doc

    def test_includes_policy_registry_methods(self, policy_lifecycle_doc: str) -> None:
        """Verify PolicyRegistry methods are documented."""
        assert "register(" in policy_lifecycle_doc
        assert "get_sync(" in policy_lifecycle_doc
        assert "unregister(" in policy_lifecycle_doc


class TestPolicyRegistrationExample:
    """Test that policy registration examples from documentation work."""

    def test_register_individual_policy(self, clean_registry: PolicyRegistry) -> None:
        """Test example: registering individual policies."""
        # From documentation example
        policy = NotificationPolicy(
            notification_type="trading.order.filled",
            intent=NotificationIntent.OPERATIONAL,
            delivery_mode=DeliveryMode.BEST_EFFORT,
            channels=[Channel.SLACK],
        )
        clean_registry.register(policy)

        # Verify registration
        found = clean_registry.get_sync("trading.order.filled")
        assert found is not None
        assert found.delivery_mode == DeliveryMode.BEST_EFFORT
        assert found.channels == [Channel.SLACK]

    def test_configure_with_policy_list(self) -> None:
        """Test example: configuring with policy list."""
        # From documentation example
        registry = configure_policy_registry(
            policies=[
                {
                    "notification_type": "risk.breach.detected",
                    "delivery_mode": "GUARANTEED",
                    "require_ack": True,
                    "channels_by_mode": {
                        "LIVE": ["SLACK", "WEBSOCKET", "PAGERDUTY"],
                        "SHADOW": ["WEBSOCKET"],
                        "PREVIEW": ["WEBSOCKET"],
                    },
                },
            ]
        )

        # Verify configuration
        policy = registry.get_sync("risk.breach.detected")
        assert policy is not None
        assert policy.delivery_mode == DeliveryMode.GUARANTEED
        assert policy.require_ack is True

    def test_load_from_dict(self, clean_registry: PolicyRegistry) -> None:
        """Test loading policies from dictionary format."""
        policies_data = [
            {
                "notification_type": "test.policy.one",
                "delivery_mode": "BEST_EFFORT",
            },
            {
                "notification_type": "test.policy.two",
                "delivery_mode": "GUARANTEED",
                "require_ack": True,
            },
        ]
        clean_registry.load_from_dict(policies_data)

        assert clean_registry.has_policy("test.policy.one")
        assert clean_registry.has_policy("test.policy.two")


class TestPolicyVersioningExample:
    """Test policy versioning behavior from documentation."""

    def test_policy_is_immutable(self) -> None:
        """Test that policies are immutable (frozen)."""
        policy = NotificationPolicy(
            notification_type="test.event",
            delivery_mode=DeliveryMode.BEST_EFFORT,
        )

        # Attempting to modify should raise error
        with pytest.raises(ValidationError):
            policy.delivery_mode = DeliveryMode.GUARANTEED  # type: ignore[misc]

    def test_update_via_unregister_register(self, clean_registry: PolicyRegistry) -> None:
        """Test example: updating policy via unregister + register."""
        # Register original
        original = NotificationPolicy(
            notification_type="trading.order.filled",
            delivery_mode=DeliveryMode.BEST_EFFORT,
            channels=[Channel.SLACK],
        )
        clean_registry.register(original)

        # Unregister old version
        result = clean_registry.unregister("trading.order.filled")
        assert result is True

        # Register new version
        updated = NotificationPolicy(
            notification_type="trading.order.filled",
            delivery_mode=DeliveryMode.GUARANTEED,  # Changed
            channels=[Channel.SLACK, Channel.EMAIL],  # Changed
        )
        clean_registry.register(updated)

        # Verify update
        found = clean_registry.get_sync("trading.order.filled")
        assert found is not None
        assert found.delivery_mode == DeliveryMode.GUARANTEED
        assert found.channels == [Channel.SLACK, Channel.EMAIL]


class TestPolicyResolutionPriority:
    """Test that resolution priority matches documentation."""

    def test_mode_override_takes_precedence(self, clean_registry: PolicyRegistry) -> None:
        """Test that mode-specific override takes precedence over base."""
        policy = NotificationPolicy(
            notification_type="test.notification",
            channels=[Channel.SLACK, Channel.WEBSOCKET],  # Base
            preview_override=ModeOverride(
                channels=[Channel.WEBSOCKET],  # Override for PREVIEW
            ),
        )
        clean_registry.register(policy)

        # PREVIEW mode should use override
        preview_channels = policy.get_channels_for_mode(
            AutonomyMode.PREVIEW, NotificationIntent.OPERATIONAL
        )
        assert preview_channels == [Channel.WEBSOCKET]

        # SHADOW mode should use base
        shadow_channels = policy.get_channels_for_mode(
            AutonomyMode.SHADOW, NotificationIntent.OPERATIONAL
        )
        assert shadow_channels == [Channel.SLACK, Channel.WEBSOCKET]

    def test_policy_takes_precedence_over_sdk_default(self, clean_registry: PolicyRegistry) -> None:
        """Test that policy value takes precedence over SDK default."""
        # OPERATIONAL default is BEST_EFFORT
        sdk_default = get_default_delivery_mode(NotificationIntent.OPERATIONAL)
        assert sdk_default == DeliveryMode.BEST_EFFORT

        # Policy overrides to GUARANTEED
        policy = NotificationPolicy(
            notification_type="test.notification",
            delivery_mode=DeliveryMode.GUARANTEED,
        )
        clean_registry.register(policy)

        # Registry should return policy value
        delivery_mode = clean_registry.get_delivery_mode(
            "test.notification", NotificationIntent.OPERATIONAL
        )
        assert delivery_mode == DeliveryMode.GUARANTEED

    def test_sdk_default_used_when_no_policy(self, clean_registry: PolicyRegistry) -> None:
        """Test that SDK defaults are used when no policy exists."""
        # No policy registered
        policy = clean_registry.get_sync("unknown.notification.type")
        assert policy is None

        # SDK defaults should apply
        delivery_mode = clean_registry.get_delivery_mode(
            "unknown.notification.type", NotificationIntent.SAFETY
        )
        assert delivery_mode == DeliveryMode.GUARANTEED  # SDK default for SAFETY


class TestModeSpecificOverrideExample:
    """Test mode-specific override example from documentation."""

    def test_mode_override_channels(self) -> None:
        """Test example: mode-specific channel overrides."""
        # From documentation example
        policy = NotificationPolicy(
            notification_type="trading.position.opened",
            channels=[Channel.SLACK, Channel.WEBSOCKET],  # Base channels
            preview_override=ModeOverride(
                channels=[Channel.WEBSOCKET],  # PREVIEW: WebSocket only
            ),
            live_override=ModeOverride(
                channels=[Channel.SLACK, Channel.WEBSOCKET, Channel.EMAIL],  # LIVE: Add Email
            ),
        )

        # In PREVIEW mode: channels=[WEBSOCKET]
        preview_channels = policy.get_channels_for_mode(
            AutonomyMode.PREVIEW, NotificationIntent.OPERATIONAL
        )
        assert preview_channels == [Channel.WEBSOCKET]

        # In SHADOW mode: channels=[SLACK, WEBSOCKET] (base)
        shadow_channels = policy.get_channels_for_mode(
            AutonomyMode.SHADOW, NotificationIntent.OPERATIONAL
        )
        assert shadow_channels == [Channel.SLACK, Channel.WEBSOCKET]

        # In LIVE mode: channels=[SLACK, WEBSOCKET, EMAIL]
        live_channels = policy.get_channels_for_mode(
            AutonomyMode.LIVE, NotificationIntent.OPERATIONAL
        )
        assert live_channels == [Channel.SLACK, Channel.WEBSOCKET, Channel.EMAIL]


class TestRegistryUnavailabilityFallback:
    """Test fallback behavior documented for registry unavailability."""

    def test_get_sync_returns_none_for_missing(self, clean_registry: PolicyRegistry) -> None:
        """Test that get_sync returns None for missing policy."""
        policy = clean_registry.get_sync("unknown.notification.type")
        assert policy is None

    def test_no_exception_for_missing_policy(self, clean_registry: PolicyRegistry) -> None:
        """Test that no exception is raised for missing policy."""
        # This should not raise
        policy = clean_registry.get_sync("completely.unknown.type")
        assert policy is None

    def test_sdk_defaults_apply_for_missing(self, clean_registry: PolicyRegistry) -> None:
        """Test that SDK defaults apply when policy is missing."""
        # Use registry methods that fall back to defaults
        channels = clean_registry.get_channels_for_mode(
            "missing.policy", NotificationIntent.SAFETY, AutonomyMode.LIVE
        )

        # Should get SDK default for SAFETY + LIVE
        sdk_default = get_default_channels(NotificationIntent.SAFETY, AutonomyMode.LIVE)
        assert channels == sdk_default

    def test_require_ack_defaults_for_missing(self, clean_registry: PolicyRegistry) -> None:
        """Test that require_ack defaults apply when policy is missing."""
        require_ack = clean_registry.get_require_ack_for_mode(
            "missing.policy", NotificationIntent.SAFETY, AutonomyMode.LIVE
        )

        # SAFETY + LIVE should require ack by default
        assert require_ack is True

    def test_delivery_mode_defaults_for_missing(self, clean_registry: PolicyRegistry) -> None:
        """Test that delivery_mode defaults apply when policy is missing."""
        # SAFETY should default to GUARANTEED
        delivery_mode = clean_registry.get_delivery_mode(
            "missing.policy", NotificationIntent.SAFETY
        )
        assert delivery_mode == DeliveryMode.GUARANTEED

        # OPERATIONAL should default to BEST_EFFORT
        delivery_mode = clean_registry.get_delivery_mode(
            "missing.policy", NotificationIntent.OPERATIONAL
        )
        assert delivery_mode == DeliveryMode.BEST_EFFORT


class TestChannelDefaultsTable:
    """Test channel defaults documented in the table."""

    @pytest.mark.parametrize(
        "mode,intent,expected_channels",
        [
            # LIVE mode
            (AutonomyMode.LIVE, NotificationIntent.SAFETY, [Channel.SLACK, Channel.WEBSOCKET]),
            (AutonomyMode.LIVE, NotificationIntent.GOVERNANCE, [Channel.SLACK, Channel.WEBSOCKET]),
            (AutonomyMode.LIVE, NotificationIntent.OPERATIONAL, [Channel.SLACK]),
            (AutonomyMode.LIVE, NotificationIntent.INFORMATIONAL, [Channel.WEBSOCKET]),
            # PREVIEW mode - all WebSocket only
            (AutonomyMode.PREVIEW, NotificationIntent.SAFETY, [Channel.WEBSOCKET]),
            (AutonomyMode.PREVIEW, NotificationIntent.GOVERNANCE, [Channel.WEBSOCKET]),
            (AutonomyMode.PREVIEW, NotificationIntent.OPERATIONAL, [Channel.WEBSOCKET]),
            (AutonomyMode.PREVIEW, NotificationIntent.INFORMATIONAL, [Channel.WEBSOCKET]),
            # SHADOW mode
            (AutonomyMode.SHADOW, NotificationIntent.OPERATIONAL, [Channel.WEBSOCKET]),
            (
                AutonomyMode.SHADOW,
                NotificationIntent.GOVERNANCE,
                [Channel.SLACK, Channel.WEBSOCKET],
            ),
        ],
    )
    def test_channel_defaults_match_documentation(
        self,
        mode: AutonomyMode,
        intent: NotificationIntent,
        expected_channels: list[Channel],
    ) -> None:
        """Verify documented channel defaults match implementation."""
        channels = get_default_channels(intent, mode)
        assert channels == expected_channels


class TestAckResolutionDocumentation:
    """Test acknowledgment resolution matches documentation."""

    def test_safety_live_requires_ack(self) -> None:
        """Test that SAFETY + LIVE requires ack by default."""
        require_ack = get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.LIVE)
        assert require_ack is True

    def test_safety_non_live_no_ack(self) -> None:
        """Test that SAFETY in non-LIVE modes does not require ack."""
        assert get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.PREVIEW) is False
        assert get_default_require_ack(NotificationIntent.SAFETY, AutonomyMode.SHADOW) is False

    def test_other_intents_no_ack(self) -> None:
        """Test that non-SAFETY intents do not require ack by default."""
        for intent in [
            NotificationIntent.GOVERNANCE,
            NotificationIntent.OPERATIONAL,
            NotificationIntent.INFORMATIONAL,
        ]:
            for mode in AutonomyMode:
                assert get_default_require_ack(intent, mode) is False


class TestDedupWindowDocumentation:
    """Test deduplication window documentation."""

    def test_default_dedup_window(self) -> None:
        """Test default deduplication window is 300 seconds."""
        assert DEFAULT_DEDUP_WINDOW_SECONDS == 300

    def test_policy_can_override_dedup_window(self, clean_registry: PolicyRegistry) -> None:
        """Test that policy can override dedup window."""
        policy = NotificationPolicy(
            notification_type="test.notification",
            dedup_window_seconds=600,  # Override to 10 minutes
        )
        clean_registry.register(policy)

        window = clean_registry.get_dedup_window("test.notification")
        assert window == 600

    def test_missing_policy_uses_default_dedup_window(self, clean_registry: PolicyRegistry) -> None:
        """Test that missing policy uses default dedup window."""
        window = clean_registry.get_dedup_window("missing.policy")
        assert window == DEFAULT_DEDUP_WINDOW_SECONDS


class TestPolicyRegistryMethods:
    """Test all PolicyRegistry methods documented in API reference."""

    def test_register(self, clean_registry: PolicyRegistry) -> None:
        """Test register method."""
        policy = NotificationPolicy(notification_type="test.type")
        clean_registry.register(policy)
        assert clean_registry.has_policy("test.type")

    def test_register_many(self, clean_registry: PolicyRegistry) -> None:
        """Test register_many method."""
        policies = [
            NotificationPolicy(notification_type="test.one"),
            NotificationPolicy(notification_type="test.two"),
        ]
        clean_registry.register_many(policies)
        assert clean_registry.has_policy("test.one")
        assert clean_registry.has_policy("test.two")

    def test_unregister(self, clean_registry: PolicyRegistry) -> None:
        """Test unregister method."""
        policy = NotificationPolicy(notification_type="test.type")
        clean_registry.register(policy)
        result = clean_registry.unregister("test.type")
        assert result is True
        assert not clean_registry.has_policy("test.type")

    def test_unregister_missing(self, clean_registry: PolicyRegistry) -> None:
        """Test unregister returns False for missing policy."""
        result = clean_registry.unregister("missing.type")
        assert result is False

    def test_get_sync(self, clean_registry: PolicyRegistry) -> None:
        """Test get_sync method."""
        policy = NotificationPolicy(notification_type="test.type")
        clean_registry.register(policy)
        found = clean_registry.get_sync("test.type")
        assert found is policy

    def test_has_policy(self, clean_registry: PolicyRegistry) -> None:
        """Test has_policy method."""
        assert not clean_registry.has_policy("test.type")
        policy = NotificationPolicy(notification_type="test.type")
        clean_registry.register(policy)
        assert clean_registry.has_policy("test.type")

    def test_list_notification_types(self, clean_registry: PolicyRegistry) -> None:
        """Test list_notification_types method."""
        clean_registry.register(NotificationPolicy(notification_type="type.a"))
        clean_registry.register(NotificationPolicy(notification_type="type.b"))
        types = clean_registry.list_notification_types()
        assert set(types) == {"type.a", "type.b"}

    def test_get_all(self, clean_registry: PolicyRegistry) -> None:
        """Test get_all method."""
        policy_a = NotificationPolicy(notification_type="type.a")
        policy_b = NotificationPolicy(notification_type="type.b")
        clean_registry.register(policy_a)
        clean_registry.register(policy_b)
        all_policies = clean_registry.get_all()
        assert len(all_policies) == 2
        assert "type.a" in all_policies
        assert "type.b" in all_policies

    def test_clear(self, clean_registry: PolicyRegistry) -> None:
        """Test clear method."""
        clean_registry.register(NotificationPolicy(notification_type="type.a"))
        clean_registry.register(NotificationPolicy(notification_type="type.b"))
        assert len(clean_registry) == 2
        clean_registry.clear()
        assert len(clean_registry) == 0

    def test_len(self, clean_registry: PolicyRegistry) -> None:
        """Test __len__ method."""
        assert len(clean_registry) == 0
        clean_registry.register(NotificationPolicy(notification_type="type.a"))
        assert len(clean_registry) == 1


class TestNotificationPolicyFields:
    """Test NotificationPolicy fields documented in API reference."""

    def test_all_fields_documented(self) -> None:
        """Test that all documented fields can be set."""
        policy = NotificationPolicy(
            notification_type="full.policy.test",
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.SLACK, Channel.WEBSOCKET],
            require_ack=True,
            ack_timeout_minutes=15,
            dedup_window_seconds=300,
            preview_override=ModeOverride(channels=[Channel.WEBSOCKET]),
            shadow_override=ModeOverride(require_ack=False),
            live_override=ModeOverride(delivery_mode=DeliveryMode.GUARANTEED),
            mode_overrides={AutonomyMode.PREVIEW: ModeOverride(channels=[Channel.EMAIL])},
        )

        assert policy.notification_type == "full.policy.test"
        assert policy.intent == NotificationIntent.SAFETY
        assert policy.delivery_mode == DeliveryMode.GUARANTEED
        assert policy.channels == [Channel.SLACK, Channel.WEBSOCKET]
        assert policy.require_ack is True
        assert policy.ack_timeout_minutes == 15
        assert policy.dedup_window_seconds == 300
        assert policy.preview_override is not None
        assert policy.shadow_override is not None
        assert policy.live_override is not None
        assert policy.mode_overrides is not None


class TestModeOverrideFields:
    """Test ModeOverride fields documented in API reference."""

    def test_all_fields_documented(self) -> None:
        """Test that all documented fields can be set."""
        override = ModeOverride(
            channels=[Channel.SLACK, Channel.EMAIL],
            require_ack=True,
            delivery_mode=DeliveryMode.GUARANTEED,
        )

        assert override.channels == [Channel.SLACK, Channel.EMAIL]
        assert override.require_ack is True
        assert override.delivery_mode == DeliveryMode.GUARANTEED

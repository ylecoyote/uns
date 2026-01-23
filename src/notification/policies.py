"""Policy schema, loader, and registry for the Unified Notification Service.

This module defines the NotificationPolicy object and PolicyRegistry
for mode-aware routing decisions.

Key features:
- NotificationPolicy typed object with mode-specific overrides
- get_channels_for_mode(autonomy_mode) - deterministic channel resolution
- get_require_ack_for_mode(autonomy_mode) - ack requirement resolution
- PolicyRegistry with get_sync(notification_type) - policy lookup

Acceptance criteria:
- Policy lookup failure falls back to SDK defaults
- Mode overrides apply deterministically
"""


from pydantic import BaseModel, Field

from .models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
    get_default_ack_timeout_minutes,
    get_default_delivery_mode,
    get_default_require_ack,
)


class ModeOverride(BaseModel):
    """Mode-specific configuration overrides.

    Allows policies to specify different behavior for PREVIEW, SHADOW, and LIVE modes.
    """

    channels: list[Channel] | None = Field(
        default=None, description="Override channels for this mode"
    )
    require_ack: bool | None = Field(
        default=None, description="Override ack requirement for this mode"
    )
    delivery_mode: DeliveryMode | None = Field(
        default=None, description="Override delivery mode for this mode"
    )

    model_config = {"frozen": True}


class NotificationPolicy(BaseModel):
    """Policy definition for a notification type.

    Policies can specify base configuration and mode-specific overrides.
    The routing logic applies overrides deterministically based on the
    current autonomy mode.
    """

    notification_type: str = Field(..., description="Unique policy identifier")
    intent: NotificationIntent | None = Field(
        default=None, description="Default intent if not specified in notification"
    )
    delivery_mode: DeliveryMode | None = Field(
        default=None, description="Base delivery mode override"
    )
    channels: list[Channel] = Field(
        default_factory=list, description="Default channels"
    )
    require_ack: bool | None = Field(
        default=None, description="Base ack requirement"
    )
    ack_timeout_minutes: int | None = Field(
        default=None, description="Base ack timeout"
    )
    dedup_window_seconds: int | None = Field(
        default=None, description="Deduplication window"
    )

    # Mode-specific overrides
    preview_override: ModeOverride | None = Field(
        default=None, description="PREVIEW mode overrides"
    )
    shadow_override: ModeOverride | None = Field(
        default=None, description="SHADOW mode overrides"
    )
    live_override: ModeOverride | None = Field(
        default=None, description="LIVE mode overrides"
    )

    model_config = {"frozen": True}

    def _get_mode_override(self, autonomy_mode: AutonomyMode) -> ModeOverride | None:
        """Get the override for a specific mode."""
        if autonomy_mode == AutonomyMode.PREVIEW:
            return self.preview_override
        if autonomy_mode == AutonomyMode.SHADOW:
            return self.shadow_override
        if autonomy_mode == AutonomyMode.LIVE:
            return self.live_override
        return None

    def get_channels_for_mode(
        self, autonomy_mode: AutonomyMode, intent: NotificationIntent
    ) -> list[Channel]:
        """Get channels for a specific autonomy mode.

        Resolution order:
        1. Mode-specific override channels (if defined)
        2. Policy base channels (if defined)
        3. SDK defaults based on mode + intent

        Args:
            autonomy_mode: Current operating mode.
            intent: Notification intent for default derivation.

        Returns:
            List of channels to use for delivery.
        """
        # Check mode override first
        override = self._get_mode_override(autonomy_mode)
        if override and override.channels is not None:
            return override.channels

        # Fall back to policy base channels
        if self.channels:
            return self.channels

        # Fall back to SDK defaults
        return _get_default_channels(autonomy_mode, intent)

    def get_require_ack_for_mode(
        self, autonomy_mode: AutonomyMode, intent: NotificationIntent
    ) -> bool:
        """Get ack requirement for a specific autonomy mode.

        Resolution order:
        1. Mode-specific override require_ack (if defined)
        2. Policy base require_ack (if defined)
        3. SDK defaults based on mode + intent

        Args:
            autonomy_mode: Current operating mode.
            intent: Notification intent for default derivation.

        Returns:
            Whether acknowledgment is required.
        """
        # Check mode override first
        override = self._get_mode_override(autonomy_mode)
        if override and override.require_ack is not None:
            return override.require_ack

        # Fall back to policy base setting
        if self.require_ack is not None:
            return self.require_ack

        # Fall back to SDK defaults
        return get_default_require_ack(intent, autonomy_mode)

    def get_delivery_mode_for_mode(
        self, autonomy_mode: AutonomyMode, intent: NotificationIntent
    ) -> DeliveryMode:
        """Get delivery mode for a specific autonomy mode.

        Resolution order:
        1. Mode-specific override delivery_mode (if defined)
        2. Policy base delivery_mode (if defined)
        3. SDK defaults based on intent

        Args:
            autonomy_mode: Current operating mode.
            intent: Notification intent for default derivation.

        Returns:
            Delivery mode (GUARANTEED or BEST_EFFORT).
        """
        # Check mode override first
        override = self._get_mode_override(autonomy_mode)
        if override and override.delivery_mode is not None:
            return override.delivery_mode

        # Fall back to policy base setting
        if self.delivery_mode is not None:
            return self.delivery_mode

        # Fall back to SDK defaults
        return get_default_delivery_mode(intent)

    def get_ack_timeout_minutes_for_mode(
        self, autonomy_mode: AutonomyMode, intent: NotificationIntent
    ) -> int | None:
        """Get ack timeout for a specific autonomy mode.

        Args:
            autonomy_mode: Current operating mode (unused, for API consistency).
            intent: Notification intent for default derivation.

        Returns:
            Timeout in minutes, or None if no timeout.
        """
        # Policy timeout takes precedence
        if self.ack_timeout_minutes is not None:
            return self.ack_timeout_minutes

        # Fall back to SDK defaults
        return get_default_ack_timeout_minutes(intent)


def _get_default_channels(
    autonomy_mode: AutonomyMode, intent: NotificationIntent
) -> list[Channel]:
    """Get default channels based on autonomy mode and intent.

    Channel resolution rules from PRD:

    LIVE Mode Defaults:
    - SAFETY: Slack, WebSocket (+ PagerDuty if irreversible - handled elsewhere)
    - GOVERNANCE: Slack, WebSocket
    - OPERATIONAL: Slack
    - INFORMATIONAL: WebSocket

    PREVIEW Mode Override:
    - All intents -> WebSocket only

    SHADOW Mode Override:
    - OPERATIONAL -> WebSocket
    - GOVERNANCE -> Slack + WebSocket
    - Others follow LIVE defaults
    """
    if autonomy_mode == AutonomyMode.PREVIEW:
        # PREVIEW: All intents -> WebSocket only
        return [Channel.WEBSOCKET]

    if autonomy_mode == AutonomyMode.SHADOW:
        # SHADOW mode overrides
        if intent == NotificationIntent.OPERATIONAL:
            return [Channel.WEBSOCKET]
        if intent == NotificationIntent.GOVERNANCE:
            return [Channel.SLACK, Channel.WEBSOCKET]
        # Others follow LIVE defaults (fall through)

    # LIVE mode defaults (also used for SHADOW SAFETY/INFORMATIONAL)
    if intent == NotificationIntent.SAFETY:
        return [Channel.SLACK, Channel.WEBSOCKET]
    if intent == NotificationIntent.GOVERNANCE:
        return [Channel.SLACK, Channel.WEBSOCKET]
    if intent == NotificationIntent.OPERATIONAL:
        return [Channel.SLACK]
    if intent == NotificationIntent.INFORMATIONAL:
        return [Channel.WEBSOCKET]

    # Fallback (should not reach here with valid enum)
    return [Channel.WEBSOCKET]


class PolicyRegistry:
    """Registry for notification policies with synchronous lookup.

    The registry stores policies keyed by notification_type and provides
    fallback to SDK defaults when no policy is found.

    Thread-safety: This implementation uses a simple dict and is suitable
    for single-threaded use or read-heavy workloads after initial population.
    For concurrent writes, consider adding locking.
    """

    def __init__(self) -> None:
        self._policies: dict[str, NotificationPolicy] = {}

    def register(self, policy: NotificationPolicy) -> None:
        """Register a policy for a notification type.

        Args:
            policy: The policy to register.
        """
        self._policies[policy.notification_type] = policy

    def register_many(self, policies: list[NotificationPolicy]) -> None:
        """Register multiple policies.

        Args:
            policies: List of policies to register.
        """
        for policy in policies:
            self.register(policy)

    def unregister(self, notification_type: str) -> bool:
        """Remove a policy from the registry.

        Args:
            notification_type: The notification type to unregister.

        Returns:
            True if policy was removed, False if not found.
        """
        if notification_type in self._policies:
            del self._policies[notification_type]
            return True
        return False

    def get_sync(self, notification_type: str) -> NotificationPolicy | None:
        """Synchronously retrieve a policy by notification type.

        Args:
            notification_type: The notification type to look up.

        Returns:
            The registered policy, or None if not found.
            When None is returned, callers should use SDK defaults.
        """
        return self._policies.get(notification_type)

    def has_policy(self, notification_type: str) -> bool:
        """Check if a policy exists for a notification type.

        Args:
            notification_type: The notification type to check.

        Returns:
            True if a policy is registered.
        """
        return notification_type in self._policies

    def list_notification_types(self) -> list[str]:
        """List all registered notification types.

        Returns:
            List of registered notification type strings.
        """
        return list(self._policies.keys())

    def clear(self) -> None:
        """Remove all registered policies."""
        self._policies.clear()

    def __len__(self) -> int:
        """Return the number of registered policies."""
        return len(self._policies)


# Module-level default registry instance
_default_registry: PolicyRegistry | None = None


def get_default_registry() -> PolicyRegistry:
    """Get the default global policy registry.

    Creates a new registry on first call.

    Returns:
        The default PolicyRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = PolicyRegistry()
    return _default_registry


def set_default_registry(registry: PolicyRegistry) -> None:
    """Set the default global policy registry.

    Args:
        registry: The registry to use as default.
    """
    global _default_registry
    _default_registry = registry


def resolve_channels(
    notification_type: str,
    autonomy_mode: AutonomyMode,
    intent: NotificationIntent,
    irreversible: bool = False,
    registry: PolicyRegistry | None = None,
) -> list[Channel]:
    """Resolve channels for a notification using policy and defaults.

    This is the primary entry point for channel resolution in the routing layer.

    Args:
        notification_type: The notification type for policy lookup.
        autonomy_mode: Current operating mode.
        intent: Notification intent.
        irreversible: If True and SAFETY intent, adds PagerDuty.
        registry: Optional custom registry, uses default if None.

    Returns:
        List of channels for delivery.
    """
    reg = registry or get_default_registry()
    policy = reg.get_sync(notification_type)

    if policy:
        channels = policy.get_channels_for_mode(autonomy_mode, intent)
    else:
        channels = _get_default_channels(autonomy_mode, intent)

    # Add PagerDuty for irreversible SAFETY notifications
    if (
        irreversible
        and intent == NotificationIntent.SAFETY
        and Channel.PAGERDUTY not in channels
    ):
        channels = list(channels) + [Channel.PAGERDUTY]

    return channels


def resolve_require_ack(
    notification_type: str,
    autonomy_mode: AutonomyMode,
    intent: NotificationIntent,
    registry: PolicyRegistry | None = None,
) -> bool:
    """Resolve ack requirement for a notification using policy and defaults.

    Args:
        notification_type: The notification type for policy lookup.
        autonomy_mode: Current operating mode.
        intent: Notification intent.
        registry: Optional custom registry, uses default if None.

    Returns:
        Whether acknowledgment is required.
    """
    reg = registry or get_default_registry()
    policy = reg.get_sync(notification_type)

    if policy:
        return policy.get_require_ack_for_mode(autonomy_mode, intent)

    return get_default_require_ack(intent, autonomy_mode)


def resolve_delivery_mode(
    notification_type: str,
    autonomy_mode: AutonomyMode,
    intent: NotificationIntent,
    registry: PolicyRegistry | None = None,
) -> DeliveryMode:
    """Resolve delivery mode for a notification using policy and defaults.

    Args:
        notification_type: The notification type for policy lookup.
        autonomy_mode: Current operating mode.
        intent: Notification intent.
        registry: Optional custom registry, uses default if None.

    Returns:
        Delivery mode (GUARANTEED or BEST_EFFORT).
    """
    reg = registry or get_default_registry()
    policy = reg.get_sync(notification_type)

    if policy:
        return policy.get_delivery_mode_for_mode(autonomy_mode, intent)

    return get_default_delivery_mode(intent)

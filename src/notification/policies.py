"""Policy schema and registry for notification routing.

This module defines the policy system that controls:
- Delivery mode selection (GUARANTEED vs BEST_EFFORT)
- Channel routing based on intent and autonomy mode
- Acknowledgment requirements
- Deduplication windows

Policies can be registered per notification_type or fall back to
intent-based defaults as specified in the PRD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notification.models import AutonomyMode, DeliveryMode, NotificationIntent

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)


@dataclass(frozen=True)
class NotificationPolicy:
    """Policy configuration for a notification type.

    Policies can override default behavior for specific notification types.
    All fields are optional - if not specified, defaults are derived from
    the notification's intent and autonomy mode.
    """

    notification_type: str
    delivery_mode: DeliveryMode | None = None
    channels: list[Channel] | None = None
    require_ack: bool | None = None
    ack_timeout_minutes: int | None = None
    dedup_window_seconds: int | None = None
    mode_overrides: dict[AutonomyMode, ModeOverride] | None = None


@dataclass(frozen=True)
class ModeOverride:
    """Per-autonomy-mode overrides for a policy.

    Allows fine-grained control over routing behavior based on
    whether the system is in PREVIEW, SHADOW, or LIVE mode.
    """

    channels: list[Channel] | None = None
    require_ack: bool | None = None


# Default channel mappings per intent for LIVE mode
_DEFAULT_CHANNELS_LIVE: dict[NotificationIntent, list[Channel]] = {
    NotificationIntent.SAFETY: [Channel.SLACK, Channel.WEBSOCKET],
    NotificationIntent.GOVERNANCE: [Channel.SLACK, Channel.WEBSOCKET],
    NotificationIntent.OPERATIONAL: [Channel.SLACK],
    NotificationIntent.INFORMATIONAL: [Channel.WEBSOCKET],
}

# Default channel mappings for PREVIEW mode (all intents -> WebSocket only)
_DEFAULT_CHANNELS_PREVIEW: dict[NotificationIntent, list[Channel]] = {
    NotificationIntent.SAFETY: [Channel.WEBSOCKET],
    NotificationIntent.GOVERNANCE: [Channel.WEBSOCKET],
    NotificationIntent.OPERATIONAL: [Channel.WEBSOCKET],
    NotificationIntent.INFORMATIONAL: [Channel.WEBSOCKET],
}

# Default channel mappings for SHADOW mode
_DEFAULT_CHANNELS_SHADOW: dict[NotificationIntent, list[Channel]] = {
    NotificationIntent.SAFETY: [Channel.SLACK, Channel.WEBSOCKET],
    NotificationIntent.GOVERNANCE: [Channel.SLACK, Channel.WEBSOCKET],
    NotificationIntent.OPERATIONAL: [Channel.WEBSOCKET],
    NotificationIntent.INFORMATIONAL: [Channel.WEBSOCKET],
}

# Default ack timeout per intent (in minutes)
_DEFAULT_ACK_TIMEOUTS: dict[NotificationIntent, int] = {
    NotificationIntent.SAFETY: 15,
    NotificationIntent.GOVERNANCE: 30,
    NotificationIntent.OPERATIONAL: 60,
    NotificationIntent.INFORMATIONAL: 120,
}

# Default dedup window (in seconds)
DEFAULT_DEDUP_WINDOW_SECONDS = 300  # 5 minutes


def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode:
    """Get the default delivery mode for an intent.

    Per PRD:
    - SAFETY and GOVERNANCE -> GUARANTEED
    - OPERATIONAL and INFORMATIONAL -> BEST_EFFORT

    Args:
        intent: The notification intent

    Returns:
        The appropriate DeliveryMode
    """
    if intent in (NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE):
        return DeliveryMode.GUARANTEED
    return DeliveryMode.BEST_EFFORT


def get_default_channels(
    intent: NotificationIntent,
    autonomy_mode: AutonomyMode,
    irreversible: bool = False,
) -> list[Channel]:
    """Get the default channels for an intent and mode.

    Applies the PRD-specified routing rules:
    - PREVIEW mode: All intents -> WebSocket only
    - SHADOW mode: OPERATIONAL -> WebSocket, GOVERNANCE -> Slack + WebSocket
    - LIVE mode: Intent-based defaults
    - SAFETY with irreversible=True in LIVE mode adds PagerDuty

    Args:
        intent: The notification intent
        autonomy_mode: Current operating mode
        irreversible: Whether the action is irreversible

    Returns:
        List of channels for delivery
    """
    if autonomy_mode == AutonomyMode.PREVIEW:
        channels = _DEFAULT_CHANNELS_PREVIEW[intent].copy()
    elif autonomy_mode == AutonomyMode.SHADOW:
        channels = _DEFAULT_CHANNELS_SHADOW[intent].copy()
    else:  # LIVE
        channels = _DEFAULT_CHANNELS_LIVE[intent].copy()

    # Add PagerDuty for irreversible SAFETY notifications in LIVE mode
    if (
        intent == NotificationIntent.SAFETY
        and irreversible
        and autonomy_mode == AutonomyMode.LIVE
        and Channel.PAGERDUTY not in channels
    ):
        channels.append(Channel.PAGERDUTY)

    return channels


def get_default_require_ack(
    intent: NotificationIntent,
    autonomy_mode: AutonomyMode,
) -> bool:
    """Determine if acknowledgment is required by default.

    Per PRD:
    - SAFETY in LIVE mode -> true
    - All other cases -> false

    Args:
        intent: The notification intent
        autonomy_mode: Current operating mode

    Returns:
        Whether acknowledgment is required
    """
    return intent == NotificationIntent.SAFETY and autonomy_mode == AutonomyMode.LIVE


def get_default_ack_timeout(intent: NotificationIntent) -> int:
    """Get the default acknowledgment timeout for an intent.

    Args:
        intent: The notification intent

    Returns:
        Timeout in minutes
    """
    return _DEFAULT_ACK_TIMEOUTS.get(intent, 60)


@dataclass
class PolicyRegistry:
    """Registry for notification policies.

    Provides policy lookup by notification_type with fallback to
    defaults when no policy is registered.
    """

    _policies: dict[str, NotificationPolicy] = field(default_factory=dict)

    def register(self, policy: NotificationPolicy) -> None:
        """Register a policy for a notification type.

        Args:
            policy: The policy to register
        """
        self._policies[policy.notification_type] = policy

    def unregister(self, notification_type: str) -> None:
        """Remove a registered policy.

        Args:
            notification_type: The type to unregister

        Raises:
            KeyError: If type is not registered
        """
        del self._policies[notification_type]

    def get_sync(self, notification_type: str) -> NotificationPolicy | None:
        """Get a policy synchronously.

        Args:
            notification_type: The notification type to look up

        Returns:
            The registered policy, or None if not found
        """
        return self._policies.get(notification_type)

    def get_channels_for_mode(
        self,
        notification_type: str,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool = False,
    ) -> list[Channel]:
        """Get channels for a notification, considering policy overrides.

        Resolution order:
        1. Policy mode-specific override
        2. Policy default channels
        3. SDK default channels

        Args:
            notification_type: The notification type
            intent: The notification intent
            autonomy_mode: Current operating mode
            irreversible: Whether action is irreversible

        Returns:
            List of channels for delivery
        """
        policy = self.get_sync(notification_type)
        if policy is not None:
            # Check mode-specific override first
            if policy.mode_overrides and autonomy_mode in policy.mode_overrides:
                mode_override = policy.mode_overrides[autonomy_mode]
                if mode_override.channels is not None:
                    return mode_override.channels.copy()

            # Then check policy default channels
            if policy.channels is not None:
                return policy.channels.copy()

        # Fall back to SDK defaults
        return get_default_channels(intent, autonomy_mode, irreversible)

    def get_require_ack_for_mode(
        self,
        notification_type: str,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
    ) -> bool:
        """Determine if ack is required, considering policy overrides.

        Resolution order:
        1. Policy mode-specific override
        2. Policy default require_ack
        3. SDK default (SAFETY + LIVE only)

        Args:
            notification_type: The notification type
            intent: The notification intent
            autonomy_mode: Current operating mode

        Returns:
            Whether acknowledgment is required
        """
        policy = self.get_sync(notification_type)
        if policy is not None:
            # Check mode-specific override first
            if policy.mode_overrides and autonomy_mode in policy.mode_overrides:
                mode_override = policy.mode_overrides[autonomy_mode]
                if mode_override.require_ack is not None:
                    return mode_override.require_ack

            # Then check policy default
            if policy.require_ack is not None:
                return policy.require_ack

        # Fall back to SDK defaults
        return get_default_require_ack(intent, autonomy_mode)

    def get_delivery_mode(
        self,
        notification_type: str,
        intent: NotificationIntent,
    ) -> DeliveryMode:
        """Get delivery mode, considering policy override.

        Resolution order:
        1. Policy delivery_mode
        2. SDK default based on intent

        Args:
            notification_type: The notification type
            intent: The notification intent

        Returns:
            The delivery mode to use
        """
        policy = self.get_sync(notification_type)
        if policy is not None and policy.delivery_mode is not None:
            return policy.delivery_mode

        return get_default_delivery_mode(intent)

    def get_ack_timeout(
        self,
        notification_type: str,
        intent: NotificationIntent,
    ) -> int:
        """Get ack timeout in minutes, considering policy override.

        Args:
            notification_type: The notification type
            intent: The notification intent

        Returns:
            Ack timeout in minutes
        """
        policy = self.get_sync(notification_type)
        if policy is not None and policy.ack_timeout_minutes is not None:
            return policy.ack_timeout_minutes

        return get_default_ack_timeout(intent)

    def get_dedup_window(self, notification_type: str) -> int:
        """Get deduplication window in seconds.

        Args:
            notification_type: The notification type

        Returns:
            Dedup window in seconds
        """
        policy = self.get_sync(notification_type)
        if policy is not None and policy.dedup_window_seconds is not None:
            return policy.dedup_window_seconds

        return DEFAULT_DEDUP_WINDOW_SECONDS


# Global policy registry instance
_policy_registry: PolicyRegistry | None = None


def get_policy_registry() -> PolicyRegistry:
    """Get the global policy registry instance.

    Returns:
        The singleton PolicyRegistry instance
    """
    global _policy_registry
    if _policy_registry is None:
        _policy_registry = PolicyRegistry()
    return _policy_registry


def configure_policy_registry(registry: PolicyRegistry | None = None) -> PolicyRegistry:
    """Configure the global policy registry.

    Args:
        registry: Custom registry to use, or None to create new default

    Returns:
        The configured PolicyRegistry instance
    """
    global _policy_registry
    _policy_registry = registry if registry is not None else PolicyRegistry()
    return _policy_registry

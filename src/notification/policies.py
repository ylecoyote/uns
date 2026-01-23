"""Policy schema and registry for the Unified Notification Service.

This module defines notification policies that control routing behavior,
delivery mode, acknowledgment requirements, and channel selection based
on notification type and autonomy mode.

Policies provide mode-aware overrides that take precedence over SDK defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from notification.models import AutonomyMode, Channel, DeliveryMode, NotificationIntent


@dataclass(frozen=True)
class NotificationPolicy:
    """Policy configuration for a notification type.

    Policies define how notifications of a specific type should be handled,
    including delivery mode, acknowledgment requirements, and channel routing
    per autonomy mode.

    Attributes:
        notification_type: The notification type this policy applies to (e.g., "trading.order_placed")
        delivery_mode: Override for delivery mode (GUARANTEED or BEST_EFFORT)
        require_ack: Override for acknowledgment requirement
        channels_by_mode: Channel routing per autonomy mode
        ack_timeout_minutes: Override for acknowledgment timeout
        dedup_window_seconds: Deduplication window duration
        priority_override: Override for priority level
    """

    notification_type: str
    delivery_mode: DeliveryMode | None = None
    require_ack: bool | None = None
    channels_by_mode: dict[AutonomyMode, list[Channel]] = field(default_factory=dict)
    ack_timeout_minutes: int | None = None
    dedup_window_seconds: int | None = None
    priority_override: str | None = None

    def get_channels_for_mode(self, autonomy_mode: AutonomyMode) -> list[Channel] | None:
        """Get the channels configured for a specific autonomy mode.

        Args:
            autonomy_mode: The autonomy mode to get channels for

        Returns:
            List of channels if configured for this mode, None otherwise
        """
        return self.channels_by_mode.get(autonomy_mode)

    def get_require_ack_for_mode(self, autonomy_mode: AutonomyMode) -> bool | None:
        """Get the require_ack setting, considering mode.

        The policy's require_ack is a global override. Mode-specific
        logic is handled at the SDK level using this value.

        Args:
            autonomy_mode: The current autonomy mode

        Returns:
            The require_ack setting if defined, None otherwise
        """
        return self.require_ack


# Default channel routing by intent and mode (from PRD Section 6.2)
DEFAULT_CHANNELS_BY_MODE: dict[NotificationIntent, dict[AutonomyMode, list[Channel]]] = {
    NotificationIntent.SAFETY: {
        AutonomyMode.LIVE: [Channel.SLACK, Channel.WEBSOCKET],
        AutonomyMode.SHADOW: [Channel.SLACK, Channel.WEBSOCKET],
        AutonomyMode.PREVIEW: [Channel.WEBSOCKET],
    },
    NotificationIntent.GOVERNANCE: {
        AutonomyMode.LIVE: [Channel.SLACK, Channel.WEBSOCKET],
        AutonomyMode.SHADOW: [Channel.SLACK, Channel.WEBSOCKET],
        AutonomyMode.PREVIEW: [Channel.WEBSOCKET],
    },
    NotificationIntent.OPERATIONAL: {
        AutonomyMode.LIVE: [Channel.SLACK],
        AutonomyMode.SHADOW: [Channel.WEBSOCKET],
        AutonomyMode.PREVIEW: [Channel.WEBSOCKET],
    },
    NotificationIntent.INFORMATIONAL: {
        AutonomyMode.LIVE: [Channel.WEBSOCKET],
        AutonomyMode.SHADOW: [Channel.WEBSOCKET],
        AutonomyMode.PREVIEW: [Channel.WEBSOCKET],
    },
}

# Default ack timeout by intent (from PRD Section 7)
DEFAULT_ACK_TIMEOUTS: dict[NotificationIntent, int] = {
    NotificationIntent.SAFETY: 15,  # 15 minutes
    NotificationIntent.GOVERNANCE: 30,  # 30 minutes
}

# Default dedup window in seconds
DEFAULT_DEDUP_WINDOW_SECONDS = 300  # 5 minutes


def get_default_channels(
    intent: NotificationIntent,
    autonomy_mode: AutonomyMode,
    irreversible: bool = False,
) -> list[Channel]:
    """Get the default channels for an intent and mode.

    Args:
        intent: The notification intent
        autonomy_mode: The current autonomy mode
        irreversible: Whether the action is irreversible (adds PagerDuty for SAFETY)

    Returns:
        List of channels to use for delivery
    """
    channels = list(
        DEFAULT_CHANNELS_BY_MODE.get(intent, {}).get(autonomy_mode, [Channel.WEBSOCKET])
    )

    # Add PagerDuty for irreversible SAFETY notifications in LIVE mode
    if intent == NotificationIntent.SAFETY and irreversible and autonomy_mode == AutonomyMode.LIVE:
        if Channel.PAGERDUTY not in channels:
            channels.append(Channel.PAGERDUTY)

    return channels


def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode:
    """Get the default delivery mode for an intent.

    From PRD Section 3.2:
    - SAFETY → GUARANTEED
    - GOVERNANCE → GUARANTEED
    - OPERATIONAL → BEST_EFFORT
    - INFORMATIONAL → BEST_EFFORT

    Args:
        intent: The notification intent

    Returns:
        The default delivery mode for the intent
    """
    if intent in (NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE):
        return DeliveryMode.GUARANTEED
    return DeliveryMode.BEST_EFFORT


def get_default_require_ack(intent: NotificationIntent, autonomy_mode: AutonomyMode) -> bool:
    """Get the default require_ack setting for an intent and mode.

    From PRD Section 7:
    - If intent == SAFETY and autonomy_mode == LIVE → true
    - Otherwise → false

    Args:
        intent: The notification intent
        autonomy_mode: The current autonomy mode

    Returns:
        Whether acknowledgment is required by default
    """
    return intent == NotificationIntent.SAFETY and autonomy_mode == AutonomyMode.LIVE


def get_default_ack_timeout(intent: NotificationIntent) -> int | None:
    """Get the default acknowledgment timeout for an intent.

    Args:
        intent: The notification intent

    Returns:
        Timeout in minutes, or None if no timeout applies
    """
    return DEFAULT_ACK_TIMEOUTS.get(intent)


class PolicyRegistry:
    """Registry for notification policies.

    Provides lookup and management of notification policies. Policies are
    registered by notification_type and can be retrieved synchronously.

    When a policy is not found, SDK defaults are used (as specified in the PRD).
    """

    def __init__(self) -> None:
        """Initialize an empty policy registry."""
        self._policies: dict[str, NotificationPolicy] = {}

    def register(self, policy: NotificationPolicy) -> None:
        """Register a policy for a notification type.

        Args:
            policy: The policy to register
        """
        self._policies[policy.notification_type] = policy

    def unregister(self, notification_type: str) -> None:
        """Unregister a policy for a notification type.

        Args:
            notification_type: The notification type to unregister

        Raises:
            KeyError: If the notification type is not registered
        """
        del self._policies[notification_type]

    def get_sync(self, notification_type: str) -> NotificationPolicy | None:
        """Synchronously get a policy by notification type.

        Args:
            notification_type: The notification type to look up

        Returns:
            The policy if found, None otherwise (falls back to SDK defaults)
        """
        return self._policies.get(notification_type)

    def get_all(self) -> dict[str, NotificationPolicy]:
        """Get all registered policies.

        Returns:
            Dictionary mapping notification types to policies
        """
        return dict(self._policies)

    def clear(self) -> None:
        """Clear all registered policies."""
        self._policies.clear()

    def load_from_dict(self, policies_data: list[dict[str, Any]]) -> None:
        """Load policies from a list of dictionaries.

        Args:
            policies_data: List of policy configurations as dictionaries
        """
        for policy_data in policies_data:
            # Convert string keys to enums for channels_by_mode
            channels_by_mode = {}
            for mode_str, channels_list in policy_data.get("channels_by_mode", {}).items():
                mode = AutonomyMode(mode_str)
                channels = [Channel(c) for c in channels_list]
                channels_by_mode[mode] = channels

            delivery_mode = None
            if policy_data.get("delivery_mode"):
                delivery_mode = DeliveryMode(policy_data["delivery_mode"])

            policy = NotificationPolicy(
                notification_type=policy_data["notification_type"],
                delivery_mode=delivery_mode,
                require_ack=policy_data.get("require_ack"),
                channels_by_mode=channels_by_mode,
                ack_timeout_minutes=policy_data.get("ack_timeout_minutes"),
                dedup_window_seconds=policy_data.get("dedup_window_seconds"),
                priority_override=policy_data.get("priority_override"),
            )
            self.register(policy)


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


def configure_policy_registry(policies: list[dict[str, Any]] | None = None) -> PolicyRegistry:
    """Configure and return the global policy registry.

    Args:
        policies: Optional list of policy configurations to load

    Returns:
        The configured PolicyRegistry instance
    """
    global _policy_registry
    _policy_registry = PolicyRegistry()
    if policies:
        _policy_registry.load_from_dict(policies)
    return _policy_registry

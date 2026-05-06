"""Policy schema and registry for the Unified Notification Service.

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

This module also includes:
- Delivery mode selection (GUARANTEED vs BEST_EFFORT)
- Channel routing based on intent and autonomy mode
- Acknowledgment requirements
- Deduplication windows

Policies can be registered per notification_type or fall back to
intent-based defaults as specified in the PRD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)
from notification.models import (
    get_default_ack_timeout_minutes as _get_default_ack_timeout_minutes,
)
from notification.models import (
    get_default_delivery_mode as _get_default_delivery_mode_from_models,
)
from notification.models import (
    get_default_require_ack as _get_default_require_ack_from_models,
)

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

# Default dedup window (in seconds)
DEFAULT_DEDUP_WINDOW_SECONDS = 300  # 5 minutes


class PolicyStatus(str, Enum):
    """Lifecycle status for notification routing policies."""

    DRAFT = "DRAFT"
    PREVIEW = "PREVIEW"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


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
    version: str = Field(default="1.0.0", description="Policy version")
    status: PolicyStatus = Field(
        default=PolicyStatus.ACTIVE, description="Policy lifecycle status"
    )
    intent: NotificationIntent | None = Field(
        default=None, description="Default intent if not specified in notification"
    )
    delivery_mode: DeliveryMode | None = Field(
        default=None, description="Base delivery mode override"
    )
    channels: list[Channel] = Field(default_factory=list, description="Default channels")
    require_ack: bool | None = Field(default=None, description="Base ack requirement")
    ack_timeout_minutes: int | None = Field(default=None, description="Base ack timeout")
    dedup_window_seconds: int | None = Field(default=None, description="Deduplication window")

    # Mode-specific overrides
    preview_override: ModeOverride | None = Field(
        default=None, description="PREVIEW mode overrides"
    )
    shadow_override: ModeOverride | None = Field(
        default=None, description="SHADOW mode overrides"
    )
    live_override: ModeOverride | None = Field(default=None, description="LIVE mode overrides")

    # Alternative: dict-based mode overrides for compatibility
    mode_overrides: dict[AutonomyMode, ModeOverride] | None = Field(
        default=None, description="Mode overrides as dict (alternative to individual fields)"
    )

    # Additional fields for compatibility with feature branch
    channels_by_mode: dict[AutonomyMode, list[Channel]] | None = Field(
        default=None, description="Per-mode channel routing configuration"
    )
    priority_override: str | None = Field(default=None, description="Priority override")

    model_config = {"frozen": True}

    @property
    def is_runtime_enforced(self) -> bool:
        """Whether this policy is eligible for live runtime enforcement."""
        return self.status == PolicyStatus.ACTIVE

    @property
    def is_shadow_evaluated(self) -> bool:
        """Whether this policy is eligible for shadow/simulation evaluation."""
        return self.status == PolicyStatus.PREVIEW

    @property
    def is_editable(self) -> bool:
        """Whether this policy may represent an editable draft."""
        return self.status == PolicyStatus.DRAFT

    @property
    def is_terminal(self) -> bool:
        """Whether this policy has left the active lifecycle."""
        return self.status == PolicyStatus.RETIRED

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationPolicy:
        """Build a policy from the YAML/dict extraction contract.

        The MIP source uses maps keyed by autonomy mode for `channels`,
        `require_ack`, and sometimes `delivery_mode`. The standalone core keeps
        those as mode overrides so routing remains deterministic while avoiding
        MIP-specific persistence concerns.
        """
        if "notification_type" not in data:
            raise ValueError("notification_type is required")

        mode_overrides: dict[AutonomyMode, ModeOverride] = {}
        raw_channels = data.get("channels")
        raw_require_ack = data.get("require_ack")
        raw_delivery_mode_by_mode = data.get("delivery_mode_by_autonomy")

        if isinstance(raw_channels, dict):
            for mode_text, channel_values in raw_channels.items():
                mode = AutonomyMode(mode_text)
                override = mode_overrides.get(mode) or ModeOverride()
                mode_overrides[mode] = override.model_copy(
                    update={"channels": [Channel(channel) for channel in channel_values]}
                )

        if isinstance(raw_require_ack, dict):
            for mode_text, require_ack in raw_require_ack.items():
                mode = AutonomyMode(mode_text)
                override = mode_overrides.get(mode) or ModeOverride()
                mode_overrides[mode] = override.model_copy(
                    update={"require_ack": bool(require_ack)}
                )

        if isinstance(raw_delivery_mode_by_mode, dict):
            for mode_text, delivery_mode in raw_delivery_mode_by_mode.items():
                mode = AutonomyMode(mode_text)
                override = mode_overrides.get(mode) or ModeOverride()
                mode_overrides[mode] = override.model_copy(
                    update={"delivery_mode": DeliveryMode(delivery_mode)}
                )

        base_channels: list[Channel] = []
        if isinstance(raw_channels, list):
            base_channels = [Channel(channel) for channel in raw_channels]

        base_require_ack = raw_require_ack if isinstance(raw_require_ack, bool) else None

        delivery_mode = data.get("delivery_mode")
        intent = data.get("intent")

        return cls(
            notification_type=data["notification_type"],
            version=data.get("version", "1.0.0"),
            status=PolicyStatus(data.get("status", PolicyStatus.ACTIVE.value)),
            intent=NotificationIntent(intent) if intent else None,
            delivery_mode=DeliveryMode(delivery_mode) if delivery_mode else None,
            channels=base_channels,
            require_ack=base_require_ack,
            ack_timeout_minutes=data.get("ack_timeout_minutes"),
            dedup_window_seconds=data.get("dedup_window_seconds"),
            mode_overrides=mode_overrides or None,
            priority_override=data.get("priority_override"),
        )

    def _get_mode_override(self, autonomy_mode: AutonomyMode) -> ModeOverride | None:
        """Get the override for a specific mode."""
        # Check dict-based overrides first
        if self.mode_overrides and autonomy_mode in self.mode_overrides:
            return self.mode_overrides[autonomy_mode]
        # Then check individual fields
        if autonomy_mode == AutonomyMode.PREVIEW:
            return self.preview_override
        if autonomy_mode == AutonomyMode.SHADOW:
            return self.shadow_override
        if autonomy_mode == AutonomyMode.LIVE:
            return self.live_override
        return None

    def get_channels_for_mode(
        self, autonomy_mode: AutonomyMode, intent: NotificationIntent | None = None
    ) -> list[Channel] | None:
        """Get channels for a specific autonomy mode.

        Resolution order:
        1. Mode-specific override channels (if defined)
        2. channels_by_mode (for compatibility)
        3. Policy base channels (if defined)
        4. SDK defaults based on mode + intent (if intent provided)
        5. None (if no intent provided and no channels configured)

        Args:
            autonomy_mode: Current operating mode.
            intent: Notification intent for default derivation.

        Returns:
            List of channels to use for delivery, or None if not configured.
        """
        # Check mode override first
        override = self._get_mode_override(autonomy_mode)
        if override and override.channels is not None:
            return override.channels

        # Check channels_by_mode (compatibility with feature branch)
        if self.channels_by_mode and autonomy_mode in self.channels_by_mode:
            return self.channels_by_mode[autonomy_mode]

        # Fall back to policy base channels
        if self.channels:
            return self.channels

        # Fall back to SDK defaults if intent provided
        if intent is not None:
            return _get_default_channels(autonomy_mode, intent)

        return None

    def get_require_ack_for_mode(
        self, autonomy_mode: AutonomyMode, intent: NotificationIntent | None = None
    ) -> bool | None:
        """Get ack requirement for a specific autonomy mode.

        Resolution order:
        1. Mode-specific override require_ack (if defined)
        2. Policy base require_ack (if defined)
        3. SDK defaults based on mode + intent (if intent provided)
        4. None (if no intent provided)

        Args:
            autonomy_mode: Current operating mode.
            intent: Notification intent for default derivation.

        Returns:
            Whether acknowledgment is required, or None if not configured.
        """
        # Check mode override first
        override = self._get_mode_override(autonomy_mode)
        if override and override.require_ack is not None:
            return override.require_ack

        # Fall back to policy base setting
        if self.require_ack is not None:
            return self.require_ack

        # Fall back to SDK defaults if intent provided
        if intent is not None:
            return get_default_require_ack(intent, autonomy_mode)

        return None

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
        return _get_default_delivery_mode_from_models(intent)

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
        return _get_default_ack_timeout_minutes(intent)


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
    intent: NotificationIntent, autonomy_mode: AutonomyMode
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
    return _get_default_require_ack_from_models(intent, autonomy_mode)


def get_default_ack_timeout(intent: NotificationIntent) -> int | None:
    """Get the default acknowledgment timeout for an intent.

    Args:
        intent: The notification intent

    Returns:
        Timeout in minutes, or None if no timeout applies
    """
    return _get_default_ack_timeout_minutes(intent)


def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode:
    """Get the default delivery mode for an intent.

    Args:
        intent: The notification intent

    Returns:
        The appropriate DeliveryMode (GUARANTEED or BEST_EFFORT)
    """
    return _get_default_delivery_mode_from_models(intent)


@dataclass
class PolicyRegistry:
    """Registry for notification policies.

    Provides policy lookup by notification_type with fallback to
    defaults when no policy is registered.

    Thread-safety: This implementation uses a simple dict and is suitable
    for single-threaded use or read-heavy workloads after initial population.
    For concurrent writes, consider adding locking.
    """

    _policies: dict[str, NotificationPolicy] = field(default_factory=dict)

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

    def get(self, notification_type: str) -> NotificationPolicy | None:
        """Compatibility alias for callers using the MIP extraction API."""
        return self.get_sync(notification_type)

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

    def get_all(self) -> dict[str, NotificationPolicy]:
        """Get all registered policies.

        Returns:
            Dictionary mapping notification types to policies
        """
        return dict(self._policies)

    def clear(self) -> None:
        """Remove all registered policies."""
        self._policies.clear()

    def load_from_dict(self, policies_data: list[dict[str, Any]]) -> None:
        """Load policies from a list of dictionaries.

        Args:
            policies_data: List of policy configurations as dictionaries
        """
        for policy_data in policies_data:
            # Convert string keys to enums for channels_by_mode
            channels_by_mode: dict[AutonomyMode, list[Channel]] = {}
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
                channels_by_mode=channels_by_mode if channels_by_mode else None,
                ack_timeout_minutes=policy_data.get("ack_timeout_minutes"),
                dedup_window_seconds=policy_data.get("dedup_window_seconds"),
                priority_override=policy_data.get("priority_override"),
            )
            self.register(policy)

    def __len__(self) -> int:
        """Return the number of registered policies."""
        return len(self._policies)

    def get_channels_for_mode(
        self,
        notification_type: str,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool = False,
    ) -> list[Channel]:
        """Get channels for a notification, considering policy overrides.

        Resolution order:
        1. Policy mode-specific override (individual fields or dict)
        2. Policy channels_by_mode (compatibility)
        3. Policy default channels
        4. SDK default channels

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
            # Use the policy's get_channels_for_mode which handles all override types
            channels = policy.get_channels_for_mode(autonomy_mode, intent)
            if channels is not None:
                channels = list(channels)  # Make a copy
                # Add PagerDuty for irreversible SAFETY in LIVE mode
                if (
                    intent == NotificationIntent.SAFETY
                    and irreversible
                    and autonomy_mode == AutonomyMode.LIVE
                    and Channel.PAGERDUTY not in channels
                ):
                    channels.append(Channel.PAGERDUTY)
                return channels

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
        1. Policy mode-specific override (individual fields or dict)
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
            # Use the policy's get_require_ack_for_mode which handles all override types
            result = policy.get_require_ack_for_mode(autonomy_mode, intent)
            if result is not None:
                return result

        # Fall back to SDK defaults
        return _get_default_require_ack_from_models(intent, autonomy_mode)

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

        return _get_default_delivery_mode_from_models(intent)

    def get_ack_timeout(
        self,
        notification_type: str,
        intent: NotificationIntent,
    ) -> int | None:
        """Get ack timeout in minutes, considering policy override.

        Args:
            notification_type: The notification type
            intent: The notification intent

        Returns:
            Ack timeout in minutes, or None if no timeout
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
        The singleton PolicyRegistry instance.
    """
    global _policy_registry
    if _policy_registry is None:
        _policy_registry = PolicyRegistry()
    return _policy_registry


def set_policy_registry(registry: PolicyRegistry) -> None:
    """Set the global policy registry instance.

    Args:
        registry: The registry to use as global singleton.
    """
    global _policy_registry
    _policy_registry = registry

def configure_policy_registry(
    registry: PolicyRegistry | None = None,
    policies: list[dict[str, Any]] | None = None,
) -> PolicyRegistry:
    """Configure the global policy registry.

    Args:
        registry: Custom registry to use, or None to create new default
        policies: Optional list of policy configurations to load

    Returns:
        The configured PolicyRegistry instance
    """
    global _policy_registry
    _policy_registry = registry if registry is not None else PolicyRegistry()
    if policies:
        _policy_registry.load_from_dict(policies)
    return _policy_registry


# Aliases for backward compatibility
def get_default_registry() -> PolicyRegistry:
    """Alias for get_policy_registry() for backward compatibility."""
    return get_policy_registry()


def set_default_registry(registry: PolicyRegistry) -> None:
    """Alias for set_policy_registry() for backward compatibility."""
    set_policy_registry(registry)


# Top-level resolution functions for convenience
def resolve_channels(
    notification_type: str,
    autonomy_mode: AutonomyMode,
    intent: NotificationIntent,
    irreversible: bool = False,
    registry: PolicyRegistry | None = None,
) -> list[Channel]:
    """Resolve channels using specified or global registry.

    Args:
        notification_type: The notification type
        autonomy_mode: Current operating mode
        intent: The notification intent
        irreversible: Whether action is irreversible
        registry: Optional registry to use (defaults to global)

    Returns:
        List of channels for delivery
    """
    reg = registry if registry is not None else get_policy_registry()
    return reg.get_channels_for_mode(notification_type, intent, autonomy_mode, irreversible)


def resolve_require_ack(
    notification_type: str,
    autonomy_mode: AutonomyMode,
    intent: NotificationIntent,
    registry: PolicyRegistry | None = None,
) -> bool:
    """Resolve ack requirement using specified or global registry.

    Args:
        notification_type: The notification type
        autonomy_mode: Current operating mode
        intent: The notification intent
        registry: Optional registry to use (defaults to global)

    Returns:
        Whether acknowledgment is required
    """
    reg = registry if registry is not None else get_policy_registry()
    return reg.get_require_ack_for_mode(notification_type, intent, autonomy_mode)


def resolve_delivery_mode(
    notification_type: str,
    autonomy_mode: AutonomyMode,
    intent: NotificationIntent,
    registry: PolicyRegistry | None = None,
) -> DeliveryMode:
    """Resolve delivery mode using specified or global registry.

    Args:
        notification_type: The notification type
        autonomy_mode: Current operating mode
        intent: The notification intent
        registry: Optional registry to use (defaults to global)

    Returns:
        The delivery mode to use
    """
    reg = registry if registry is not None else get_policy_registry()
    return reg.get_delivery_mode(notification_type, intent)

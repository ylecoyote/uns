"""SDK (Producer Interface) for the Unified Notification Service.

This module provides the primary API for producers to send notifications.
It enforces validation guards, applies policy overrides, and derives
default values based on intent and autonomy mode.

Key Features:
- Hard validation for autonomy_context, autonomy_mode, and agent_id
- Policy lookup with override behavior
- Default channel derivation by mode + intent
- Convenience methods: send_safety, send_governance, send_operational, send_info
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from notification.interfaces import (
    AcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
)
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
from notification.policies import (
    NotificationPolicy,
    PolicyOverrideError,
    PolicyRegistry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
    get_policy_registry,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when notification validation fails."""

    pass


class NotificationSDK:
    """SDK for sending notifications through the Unified Notification Service.

    This class provides the producer interface for creating and sending
    notifications with proper validation, policy application, and routing.

    The SDK enforces hard guards:
    - autonomy_context is REQUIRED
    - autonomy_mode must be set in context
    - agent_id must be present in context

    Example:
        >>> sdk = NotificationSDK()
        >>> context = AutonomyContext(
        ...     autonomy_mode=AutonomyMode.LIVE,
        ...     agent_id=uuid4()
        ... )
        >>> result = sdk.send_safety(
        ...     notification_type="trading.risk_breach",
        ...     title="Risk Limit Exceeded",
        ...     message="Position size exceeds configured limits",
        ...     source="risk_engine",
        ...     autonomy_context=context,
        ... )
    """

    def __init__(
        self,
        policy_registry: PolicyRegistry | None = None,
        context_provider: NotificationContextProvider | None = None,
        ack_callback: AcknowledgmentCallback | None = None,
        delivery_handler: Callable[[Notification], NotificationResult] | None = None,
    ) -> None:
        """Initialize the NotificationSDK.

        Args:
            policy_registry: Optional policy registry for policy lookups.
                If None, uses the global registry.
            context_provider: Optional context provider for autonomy context.
                If provided, can be used to auto-populate context.
            ack_callback: Optional callback for acknowledgment events.
                If None, uses NoOpAcknowledgmentCallback.
            delivery_handler: Optional handler for delivering notifications.
                If None, notifications are validated but not delivered.
                This allows for testing and for integration with external
                delivery systems (e.g., RQ job queue).
        """
        self._policy_registry = (
            policy_registry if policy_registry is not None else get_policy_registry()
        )
        self._context_provider = context_provider
        self._ack_callback = ack_callback or NoOpAcknowledgmentCallback()
        self._delivery_handler = delivery_handler

    def send(
        self,
        notification_type: str,
        intent: NotificationIntent,
        title: str,
        message: str,
        source: str,
        autonomy_context: AutonomyContext | None = None,
        irreversible: bool = False,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        channels_override: list[Channel] | None = None,
        delivery_mode_override: DeliveryMode | None = None,
        require_ack_override: bool | None = None,
        priority_override: Priority | None = None,
        dedup_key: str | None = None,
    ) -> NotificationResult:
        """Send a notification through the UNS.

        This is the primary entry point for sending notifications. It:
        1. Validates the autonomy_context (hard guard)
        2. Looks up applicable policy
        3. Derives delivery_mode, channels, require_ack, priority from intent/mode/policy
        4. Creates the Notification object
        5. Enqueues for delivery (if delivery_handler is configured)

        Args:
            notification_type: Namespaced notification type (e.g., "trading.order_placed")
            intent: Notification classification (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
            title: Notification title (max 200 chars)
            message: Notification body (max 4000 chars)
            source: Producer identifier
            autonomy_context: REQUIRED. The autonomy context for this notification.
                If None and context_provider is configured, attempts to get current context.
            irreversible: Whether the action is irreversible (triggers PagerDuty for SAFETY)
            metadata: Additional JSON metadata
            correlation_id: Optional correlation ID for tracing
            channels_override: Override the derived channels
            delivery_mode_override: Override the derived delivery mode
            require_ack_override: Override the derived require_ack
            priority_override: Override the derived priority
            dedup_key: Custom deduplication key (auto-generated if not provided)

        Returns:
            NotificationResult with delivery outcome

        Raises:
            ValidationError: If autonomy_context is missing or invalid
        """
        # Resolve autonomy context
        context = self._resolve_context(autonomy_context)

        # Validate context (hard guards)
        self._validate_context(context)

        # Look up policy
        policy = self._policy_registry.get_sync(notification_type)

        # ACTIVE policy is authority, not a suggestion. Equal producer values
        # are harmless; differing values (including apparently stronger ones)
        # require a separate policy activation, never a payload self-grant.
        if policy is not None and policy.is_runtime_enforced:
            if policy.intent is not None and intent != policy.intent:
                raise PolicyOverrideError("intent differs from ACTIVE policy")
            expected = {
                "delivery_mode": self._resolve_delivery_mode(
                    intent, context.autonomy_mode, policy, None
                ),
                "channels": self._resolve_channels(
                    intent, context.autonomy_mode, irreversible, policy, None
                ),
                "require_ack": self._resolve_require_ack(
                    intent, context.autonomy_mode, policy, None
                ),
                "priority": self._resolve_priority(intent, policy, None),
            }
            supplied = {
                "delivery_mode": delivery_mode_override,
                "channels": channels_override,
                "require_ack": require_ack_override,
                "priority": priority_override,
            }
            for field, value in supplied.items():
                if value is not None and value != expected[field]:
                    raise PolicyOverrideError(f"{field} override differs from ACTIVE policy")

        # Derive values using policy overrides and defaults
        delivery_mode = self._resolve_delivery_mode(
            intent,
            context.autonomy_mode,
            policy,
            delivery_mode_override,
        )
        channels = self._resolve_channels(
            intent, context.autonomy_mode, irreversible, policy, channels_override
        )
        require_ack = self._resolve_require_ack(
            intent, context.autonomy_mode, policy, require_ack_override
        )
        priority = self._resolve_priority(intent, policy, priority_override)
        ack_timeout = self._resolve_ack_timeout(
            intent,
            context.autonomy_mode,
            require_ack,
            policy,
        )
        resolved_dedup_key = self._resolve_dedup_key(notification_type, context, dedup_key)

        # Create notification
        notification = Notification(
            notification_type=notification_type,
            intent=intent,
            delivery_mode=delivery_mode,
            policy_config_id=policy.config_id if policy is not None else None,
            policy_config_hash=policy.config_hash if policy is not None else None,
            policy_evaluation_id=(
                uuid4() if policy is not None and policy.config_hash is not None else None
            ),
            irreversible=irreversible,
            autonomy_context=context,
            require_ack=require_ack,
            ack_timeout_minutes=ack_timeout,
            priority=priority,
            title=title,
            message=message,
            metadata=metadata or {},
            channels=channels,
            dedup_key=resolved_dedup_key,
            source=source,
            correlation_id=correlation_id,
        )

        logger.info(
            "Sending notification: type=%s, intent=%s, mode=%s, channels=%s",
            notification_type,
            intent.value,
            context.autonomy_mode.value,
            [c.value for c in channels],
        )

        # Deliver if handler is configured
        if self._delivery_handler:
            return self._delivery_handler(notification)

        # Return a pending result if no delivery handler
        return NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.PENDING,
            channels_attempted=[],
            channels_succeeded=[],
            channels_failed=[],
        )

    def send_safety(
        self,
        notification_type: str,
        title: str,
        message: str,
        source: str,
        autonomy_context: AutonomyContext | None = None,
        irreversible: bool = False,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        channels_override: list[Channel] | None = None,
        require_ack_override: bool | None = None,
        dedup_key: str | None = None,
    ) -> NotificationResult:
        """Send a SAFETY intent notification.

        SAFETY notifications have GUARANTEED delivery and require acknowledgment
        in LIVE mode by default.

        Args:
            notification_type: Namespaced notification type
            title: Notification title
            message: Notification body
            source: Producer identifier
            autonomy_context: Required autonomy context
            irreversible: If True, adds PagerDuty to channels in LIVE mode
            metadata: Additional JSON metadata
            correlation_id: Optional correlation ID
            channels_override: Override derived channels
            require_ack_override: Override require_ack (default True in LIVE)
            dedup_key: Custom deduplication key

        Returns:
            NotificationResult with delivery outcome
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.SAFETY,
            title=title,
            message=message,
            source=source,
            autonomy_context=autonomy_context,
            irreversible=irreversible,
            metadata=metadata,
            correlation_id=correlation_id,
            channels_override=channels_override,
            require_ack_override=require_ack_override,
            dedup_key=dedup_key,
        )

    def send_governance(
        self,
        notification_type: str,
        title: str,
        message: str,
        source: str,
        autonomy_context: AutonomyContext | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        channels_override: list[Channel] | None = None,
        require_ack_override: bool | None = None,
        dedup_key: str | None = None,
    ) -> NotificationResult:
        """Send a GOVERNANCE intent notification.

        GOVERNANCE notifications have GUARANTEED delivery.

        Args:
            notification_type: Namespaced notification type
            title: Notification title
            message: Notification body
            source: Producer identifier
            autonomy_context: Required autonomy context
            metadata: Additional JSON metadata
            correlation_id: Optional correlation ID
            channels_override: Override derived channels
            require_ack_override: Override require_ack
            dedup_key: Custom deduplication key

        Returns:
            NotificationResult with delivery outcome
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.GOVERNANCE,
            title=title,
            message=message,
            source=source,
            autonomy_context=autonomy_context,
            metadata=metadata,
            correlation_id=correlation_id,
            channels_override=channels_override,
            require_ack_override=require_ack_override,
            dedup_key=dedup_key,
        )

    def send_operational(
        self,
        notification_type: str,
        title: str,
        message: str,
        source: str,
        autonomy_context: AutonomyContext | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        channels_override: list[Channel] | None = None,
        dedup_key: str | None = None,
    ) -> NotificationResult:
        """Send an OPERATIONAL intent notification.

        OPERATIONAL notifications have BEST_EFFORT delivery.

        Args:
            notification_type: Namespaced notification type
            title: Notification title
            message: Notification body
            source: Producer identifier
            autonomy_context: Required autonomy context
            metadata: Additional JSON metadata
            correlation_id: Optional correlation ID
            channels_override: Override derived channels
            dedup_key: Custom deduplication key

        Returns:
            NotificationResult with delivery outcome
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.OPERATIONAL,
            title=title,
            message=message,
            source=source,
            autonomy_context=autonomy_context,
            metadata=metadata,
            correlation_id=correlation_id,
            channels_override=channels_override,
            dedup_key=dedup_key,
        )

    def send_info(
        self,
        notification_type: str,
        title: str,
        message: str,
        source: str,
        autonomy_context: AutonomyContext | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        channels_override: list[Channel] | None = None,
        dedup_key: str | None = None,
    ) -> NotificationResult:
        """Send an INFORMATIONAL intent notification.

        INFORMATIONAL notifications have BEST_EFFORT delivery and are
        typically delivered via WebSocket only.

        Args:
            notification_type: Namespaced notification type
            title: Notification title
            message: Notification body
            source: Producer identifier
            autonomy_context: Required autonomy context
            metadata: Additional JSON metadata
            correlation_id: Optional correlation ID
            channels_override: Override derived channels
            dedup_key: Custom deduplication key

        Returns:
            NotificationResult with delivery outcome
        """
        return self.send(
            notification_type=notification_type,
            intent=NotificationIntent.INFORMATIONAL,
            title=title,
            message=message,
            source=source,
            autonomy_context=autonomy_context,
            metadata=metadata,
            correlation_id=correlation_id,
            channels_override=channels_override,
            dedup_key=dedup_key,
        )

    def _resolve_context(self, context: AutonomyContext | None) -> AutonomyContext:
        """Resolve autonomy context from argument or provider.

        Args:
            context: Explicit context, if provided

        Returns:
            Resolved AutonomyContext

        Raises:
            ValidationError: If no context can be resolved
        """
        if context is not None:
            return context

        if self._context_provider is not None:
            try:
                return self._context_provider.get_current_context()
            except RuntimeError as e:
                raise ValidationError(f"Failed to get autonomy context from provider: {e}") from e

        raise ValidationError(
            "autonomy_context is required. Either provide it explicitly "
            "or configure a context_provider."
        )

    def _validate_context(self, context: AutonomyContext) -> None:
        """Validate autonomy context (hard guards).

        Args:
            context: The context to validate

        Raises:
            ValidationError: If context is invalid
        """
        # Hard guard: autonomy_mode must be set
        if context.autonomy_mode is None:
            raise ValidationError("autonomy_context.autonomy_mode is required")

        # Hard guard: agent_id must be present
        if context.agent_id is None:
            raise ValidationError("autonomy_context.agent_id is required")

    def _resolve_delivery_mode(
        self,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        policy: NotificationPolicy | None,
        override: DeliveryMode | None,
    ) -> DeliveryMode:
        """Resolve delivery mode from override, policy, or intent default.

        Priority:
        1. Explicit override
        2. Policy mode-specific delivery_mode
        3. Policy delivery_mode
        4. Intent default (SAFETY/GOVERNANCE → GUARANTEED, else BEST_EFFORT)

        Args:
            intent: The notification intent
            autonomy_mode: Current operating mode
            policy: The applicable policy, if any
            override: Explicit override, if any

        Returns:
            Resolved DeliveryMode
        """
        if override is not None:
            return override
        if policy is not None:
            return policy.get_delivery_mode_for_mode(autonomy_mode, intent)
        return get_default_delivery_mode(intent)

    def _resolve_channels(
        self,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool,
        policy: NotificationPolicy | None,
        override: list[Channel] | None,
    ) -> list[Channel]:
        """Resolve channels from override, policy, or defaults.

        Priority:
        1. Explicit override
        2. Policy channels_by_mode for current mode
        3. Default channels for intent/mode

        Args:
            intent: The notification intent
            autonomy_mode: The current autonomy mode
            irreversible: Whether action is irreversible
            policy: The applicable policy, if any
            override: Explicit override, if any

        Returns:
            Resolved list of channels
        """
        if override is not None:
            return override

        if policy is not None:
            policy_channels = policy.get_channels_for_mode(autonomy_mode)
            if policy_channels is not None:
                return policy_channels

        return get_default_channels(intent, autonomy_mode, irreversible)

    def _resolve_require_ack(
        self,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        policy: NotificationPolicy | None,
        override: bool | None,
    ) -> bool:
        """Resolve require_ack from override, policy, or defaults.

        Priority:
        1. Explicit override
        2. Policy mode-specific/base require_ack
        3. Default (SAFETY + LIVE → True, else False)

        Args:
            intent: The notification intent
            autonomy_mode: The current autonomy mode
            policy: The applicable policy, if any
            override: Explicit override, if any

        Returns:
            Resolved require_ack value
        """
        if override is not None:
            return override

        if policy is not None:
            resolved = policy.get_require_ack_for_mode(autonomy_mode, intent)
            if resolved is not None:
                return resolved

        return get_default_require_ack(intent, autonomy_mode)

    def _resolve_priority(
        self,
        intent: NotificationIntent,
        policy: NotificationPolicy | None,
        override: Priority | None,
    ) -> Priority:
        """Resolve priority from override, policy, or intent.

        Args:
            intent: The notification intent
            policy: The applicable policy, if any
            override: Explicit override, if any

        Returns:
            Resolved Priority
        """
        if override is not None:
            return override

        if policy is not None and policy.priority_override is not None:
            return Priority(policy.priority_override)

        # Default priority by intent
        if intent == NotificationIntent.SAFETY:
            return Priority.HIGH
        if intent == NotificationIntent.GOVERNANCE:
            return Priority.HIGH
        if intent == NotificationIntent.OPERATIONAL:
            return Priority.NORMAL
        return Priority.LOW

    def _resolve_ack_timeout(
        self,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        require_ack: bool,
        policy: NotificationPolicy | None,
    ) -> int | None:
        """Resolve ack timeout from policy or defaults.

        Args:
            intent: The notification intent
            autonomy_mode: The current autonomy mode
            require_ack: Whether ack is required
            policy: The applicable policy, if any

        Returns:
            Timeout in minutes, or None if ack not required
        """
        if not require_ack:
            return None

        if policy is not None:
            return policy.get_ack_timeout_minutes_for_mode(autonomy_mode, intent)

        return get_default_ack_timeout(intent)

    def _resolve_dedup_key(
        self,
        notification_type: str,
        context: AutonomyContext,
        custom_key: str | None,
    ) -> str:
        """Resolve deduplication key.

        If not provided, generates a stable key from notification_type and agent_id.

        Args:
            notification_type: The notification type
            context: The autonomy context
            custom_key: Custom dedup key, if provided

        Returns:
            Deduplication key
        """
        if custom_key is not None:
            return custom_key

        # Generate stable key from type + agent_id
        key_source = f"{notification_type}:{context.agent_id}"
        return hashlib.sha256(key_source.encode()).hexdigest()[:16]


def create_sdk(
    policy_registry: PolicyRegistry | None = None,
    context_provider: NotificationContextProvider | None = None,
    ack_callback: AcknowledgmentCallback | None = None,
    delivery_handler: Callable[[Notification], NotificationResult] | None = None,
) -> NotificationSDK:
    """Factory function to create a configured NotificationSDK.

    Args:
        policy_registry: Optional policy registry
        context_provider: Optional context provider
        ack_callback: Optional acknowledgment callback
        delivery_handler: Optional delivery handler

    Returns:
        Configured NotificationSDK instance
    """
    return NotificationSDK(
        policy_registry=policy_registry,
        context_provider=context_provider,
        ack_callback=ack_callback,
        delivery_handler=delivery_handler,
    )


# Global SDK instance
_sdk: NotificationSDK | None = None


def get_sdk() -> NotificationSDK:
    """Get the global SDK instance.

    Returns:
        The singleton NotificationSDK instance
    """
    global _sdk
    if _sdk is None:
        _sdk = NotificationSDK()
    return _sdk


def configure_sdk(
    policy_registry: PolicyRegistry | None = None,
    context_provider: NotificationContextProvider | None = None,
    ack_callback: AcknowledgmentCallback | None = None,
    delivery_handler: Callable[[Notification], NotificationResult] | None = None,
) -> NotificationSDK:
    """Configure and return the global SDK instance.

    Args:
        policy_registry: Optional policy registry
        context_provider: Optional context provider
        ack_callback: Optional acknowledgment callback
        delivery_handler: Optional delivery handler

    Returns:
        The configured NotificationSDK instance
    """
    global _sdk
    _sdk = NotificationSDK(
        policy_registry=policy_registry,
        context_provider=context_provider,
        ack_callback=ack_callback,
        delivery_handler=delivery_handler,
    )
    return _sdk

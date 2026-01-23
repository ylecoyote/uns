"""Unified Notification Service (UNS).

Control-plane notification and acknowledgment service for autonomous agent systems.
"""

__version__ = "0.1.0"

from notification.interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
)
from notification.models import (
    AckEvent,
    AckStatus,
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
    PolicyRegistry,
    configure_policy_registry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
    get_policy_registry,
)
from notification.sdk import (
    NotificationSDK,
    ValidationError,
    configure_sdk,
    create_sdk,
    get_sdk,
)

__all__ = [
    # Enums
    "NotificationIntent",
    "DeliveryMode",
    "AutonomyMode",
    "AckStatus",
    "Channel",
    "Priority",
    "DeliveryStatus",
    # Models
    "AutonomyContext",
    "Notification",
    "NotificationResult",
    "AckEvent",
    # Interfaces (Protocols)
    "NotificationContextProvider",
    "AcknowledgmentCallback",
    # Default Implementations
    "DefaultContextProvider",
    "NoOpAcknowledgmentCallback",
    "LoggingAcknowledgmentCallback",
    "CompositeAcknowledgmentCallback",
    # Policies
    "NotificationPolicy",
    "PolicyRegistry",
    "get_policy_registry",
    "configure_policy_registry",
    "get_default_channels",
    "get_default_delivery_mode",
    "get_default_require_ack",
    "get_default_ack_timeout",
    # SDK
    "NotificationSDK",
    "ValidationError",
    "create_sdk",
    "get_sdk",
    "configure_sdk",
]

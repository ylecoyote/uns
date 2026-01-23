"""
Unified Notification Service (UNS) - Core Package

A control-plane notification and acknowledgment service that:
- MUST NOT block execution loops
- MUST NOT participate in order routing or trade timing

This package provides the core notification infrastructure including:
- Models and data contracts
- Delivery adapters (Slack, Email, WebSocket, PagerDuty)
- Policy registry and routing rules
- Deduplication and rate limiting
- Acknowledgment handling
- SDK for notification sending
"""

__version__ = "0.1.0"

from .acknowledgment import (
    AcknowledgmentEngine,
    AckState,
    AckStorageProtocol,
    EscalationHandler,
    InMemoryAckStorage,
    LoggingEscalationHandler,
)
from .interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
)
from .models import (
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
    get_default_ack_timeout_minutes,
    get_default_delivery_mode,
    get_default_priority,
    get_default_require_ack,
)
from .policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_registry,
    get_policy_registry,
    resolve_channels,
    resolve_delivery_mode,
    resolve_require_ack,
    set_default_registry,
)
from .sdk import (
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
    "AckStorageProtocol",
    "EscalationHandler",
    # Default Implementations
    "DefaultContextProvider",
    "NoOpAcknowledgmentCallback",
    "LoggingAcknowledgmentCallback",
    "CompositeAcknowledgmentCallback",
    # Acknowledgment Engine
    "AcknowledgmentEngine",
    "AckState",
    "InMemoryAckStorage",
    "LoggingEscalationHandler",
    # Helper functions from models
    "get_default_delivery_mode",
    "get_default_priority",
    "get_default_ack_timeout_minutes",
    "get_default_require_ack",
    # Policies
    "ModeOverride",
    "NotificationPolicy",
    "PolicyRegistry",
    "get_policy_registry",
    "configure_policy_registry",
    "get_default_registry",
    "set_default_registry",
    "get_default_channels",
    "get_default_ack_timeout",
    "resolve_channels",
    "resolve_require_ack",
    "resolve_delivery_mode",
    # SDK
    "NotificationSDK",
    "ValidationError",
    "create_sdk",
    "get_sdk",
    "configure_sdk",
]

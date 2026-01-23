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
"""

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

__version__ = "0.1.0"

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
    # Helper functions
    "get_default_delivery_mode",
    "get_default_priority",
    "get_default_ack_timeout_minutes",
    "get_default_require_ack",
]

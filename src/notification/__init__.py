"""Unified Notification Service (UNS) core package.

This package provides the core functionality for the notification service including:
- Models and data contracts
- Interfaces for integration
- Policy management
- Acknowledgment handling
- Delivery orchestration
"""

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

__all__ = [
    "AckEvent",
    "AckStatus",
    "AutonomyContext",
    "AutonomyMode",
    "Channel",
    "DeliveryMode",
    "DeliveryStatus",
    "Notification",
    "NotificationIntent",
    "NotificationResult",
    "Priority",
]

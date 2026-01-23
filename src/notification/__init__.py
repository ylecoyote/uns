"""Unified Notification Service (UNS) core package.

This package provides the notification delivery infrastructure including:
- Core data models and enums
- Channel adapters (Slack, Email, WebSocket, PagerDuty)
- Rate limiting
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

"""UNS-branded model aliases."""

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

GovernanceSignal = Notification
SignalIntent = NotificationIntent

__all__ = [
    "AckEvent",
    "AckStatus",
    "AutonomyContext",
    "AutonomyMode",
    "Channel",
    "DeliveryMode",
    "DeliveryStatus",
    "GovernanceSignal",
    "Notification",
    "NotificationIntent",
    "NotificationResult",
    "Priority",
    "SignalIntent",
]

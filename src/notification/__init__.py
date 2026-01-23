"""Unified Notification Service (UNS).

Control-plane notification and acknowledgment service for autonomous agent systems.
"""

__version__ = "0.1.0"

from notification.acknowledgment import (
    AcknowledgmentEngine,
    AckState,
    AckStorageProtocol,
    EscalationHandler,
    InMemoryAckStorage,
    LoggingEscalationHandler,
)
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
]

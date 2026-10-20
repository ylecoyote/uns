"""AGSignal-branded integration interface aliases."""

from notification.interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
)

SignalContextProvider = NotificationContextProvider

__all__ = [
    "AcknowledgmentCallback",
    "CompositeAcknowledgmentCallback",
    "DefaultContextProvider",
    "LoggingAcknowledgmentCallback",
    "NoOpAcknowledgmentCallback",
    "SignalContextProvider",
    "NotificationContextProvider",
]

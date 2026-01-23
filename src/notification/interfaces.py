"""Integration interfaces for the Unified Notification Service.

This module defines protocol-based interfaces that allow UNS to remain
ATP-agnostic (autonomous trading platform). External systems inject
implementations at runtime via dependency injection.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from notification.models import AckEvent, AckStatus, AutonomyContext, AutonomyMode


@runtime_checkable
class NotificationContextProvider(Protocol):
    """Protocol for providing autonomy context to notifications."""

    @abstractmethod
    def get_current_context(self) -> AutonomyContext:
        """Retrieve the current autonomy context."""
        ...

    @abstractmethod
    def get_context_for_agent(self, agent_id: UUID) -> AutonomyContext:
        """Retrieve autonomy context for a specific agent."""
        ...

    @abstractmethod
    def get_autonomy_mode(self) -> AutonomyMode:
        """Get the current autonomy mode."""
        ...


@runtime_checkable
class AcknowledgmentCallback(Protocol):
    """Protocol for handling acknowledgment events."""

    @abstractmethod
    def on_ack(self, event: AckEvent) -> None:
        """Called when a notification is acknowledged."""
        ...

    @abstractmethod
    def on_dismiss(self, event: AckEvent) -> None:
        """Called when a notification is dismissed."""
        ...

    @abstractmethod
    def on_timeout(self, event: AckEvent) -> None:
        """Called when a notification acknowledgment times out."""
        ...

    @abstractmethod
    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Called on any acknowledgment status transition."""
        ...


class NoOpAcknowledgmentCallback:
    """No-operation implementation of AcknowledgmentCallback."""

    def on_ack(self, event: AckEvent) -> None:
        pass

    def on_dismiss(self, event: AckEvent) -> None:
        pass

    def on_timeout(self, event: AckEvent) -> None:
        pass

    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        pass


class LoggingAcknowledgmentCallback:
    """Logging implementation of AcknowledgmentCallback."""

    def __init__(self, logger: Any | None = None) -> None:
        if logger is None:
            import logging

            self._logger = logging.getLogger(__name__)
        else:
            self._logger = logger

    def on_ack(self, event: AckEvent) -> None:
        self._logger.info(
            "Notification acknowledged: notification_id=%s, acked_by=%s",
            event.notification_id,
            event.acked_by,
        )

    def on_dismiss(self, event: AckEvent) -> None:
        self._logger.info(
            "Notification dismissed: notification_id=%s, dismissed_by=%s",
            event.notification_id,
            event.acked_by,
        )

    def on_timeout(self, event: AckEvent) -> None:
        self._logger.warning(
            "Notification timed out: notification_id=%s",
            event.notification_id,
        )

    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._logger.info(
            "Notification status changed: notification_id=%s, %s -> %s",
            notification_id,
            old_status,
            new_status,
        )

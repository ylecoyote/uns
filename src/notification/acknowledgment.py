"""Acknowledgment engine for notification ack transitions and timeouts.

This module handles:
- ACK transitions (PENDING -> ACKED, DISMISSED, TIMED_OUT)
- Idempotent acknowledgment (repeated ack is safe)
- Timeout handling with re-escalation for SAFETY notifications

Per PRD:
- Timeout updates state to TIMED_OUT
- SAFETY timeout triggers re-escalation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from notification.interfaces import AcknowledgmentCallback, NoOpAcknowledgmentCallback
from notification.models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Notification,
    NotificationIntent,
)

logger = logging.getLogger(__name__)


class AckStorageError(Exception):
    """Raised when ack storage operations fail."""

    pass


class NotificationNotFoundError(Exception):
    """Raised when notification is not found in storage."""

    def __init__(self, notification_id: UUID) -> None:
        super().__init__(f"Notification not found: {notification_id}")
        self.notification_id = notification_id


class InvalidAckTransitionError(Exception):
    """Raised when an invalid ack status transition is attempted."""

    def __init__(
        self,
        notification_id: UUID,
        current_status: AckStatus,
        requested_status: AckStatus,
    ) -> None:
        super().__init__(
            f"Invalid transition for notification {notification_id}: "
            f"{current_status.value} -> {requested_status.value}"
        )
        self.notification_id = notification_id
        self.current_status = current_status
        self.requested_status = requested_status


class AckStorage(Protocol):
    """Protocol for acknowledgment state storage.

    Implementations persist ack state and enable lookup.
    """

    def get_ack_status(self, notification_id: UUID) -> AckStatus | None:
        """Get current ack status for a notification."""
        ...

    def set_ack_status(
        self,
        notification_id: UUID,
        status: AckStatus,
        acked_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set ack status for a notification."""
        ...

    def get_notification(self, notification_id: UUID) -> Notification | None:
        """Get notification by ID."""
        ...

    def store_notification(self, notification: Notification) -> None:
        """Store a notification for later retrieval."""
        ...


@dataclass
class InMemoryAckStorage:
    """In-memory implementation of AckStorage for testing.

    Not suitable for production - use Redis or database-backed storage.
    """

    _statuses: dict[UUID, tuple[AckStatus, str | None, dict[str, Any] | None]] = field(
        default_factory=dict
    )
    _notifications: dict[UUID, Notification] = field(default_factory=dict)

    def get_ack_status(self, notification_id: UUID) -> AckStatus | None:
        if notification_id in self._statuses:
            return self._statuses[notification_id][0]
        return None

    def set_ack_status(
        self,
        notification_id: UUID,
        status: AckStatus,
        acked_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._statuses[notification_id] = (status, acked_by, metadata)

    def get_notification(self, notification_id: UUID) -> Notification | None:
        return self._notifications.get(notification_id)

    def store_notification(self, notification: Notification) -> None:
        self._notifications[notification.notification_id] = notification


class EscalationHandler(Protocol):
    """Protocol for handling ack timeout escalations."""

    def escalate(
        self,
        notification: Notification,
        reason: str,
    ) -> None:
        """Escalate a notification (e.g., to PagerDuty or DLQ)."""
        ...


@dataclass
class NoOpEscalationHandler:
    """No-operation escalation handler for testing."""

    def escalate(
        self,
        notification: Notification,
        reason: str,
    ) -> None:
        logger.debug(
            "Escalation triggered (no-op): notification_id=%s reason=%s",
            notification.notification_id,
            reason,
        )


# Valid ack status transitions
_VALID_TRANSITIONS: dict[AckStatus, set[AckStatus]] = {
    AckStatus.PENDING: {AckStatus.ACKED, AckStatus.DISMISSED, AckStatus.TIMED_OUT},
    AckStatus.ACKED: set(),  # Terminal state
    AckStatus.DISMISSED: set(),  # Terminal state
    AckStatus.TIMED_OUT: {AckStatus.ACKED},  # Can still ack after timeout
}


def _is_valid_transition(current: AckStatus, target: AckStatus) -> bool:
    """Check if a status transition is valid."""
    # Idempotent: same status is always valid
    if current == target:
        return True
    return target in _VALID_TRANSITIONS.get(current, set())


@dataclass
class AcknowledgmentEngine:
    """Engine for handling notification acknowledgments.

    Provides:
    - ack(): Acknowledge a notification
    - dismiss(): Dismiss a notification
    - check_ack_timeout(): Check and handle ack timeouts
    """

    storage: AckStorage
    callback: AcknowledgmentCallback = field(default_factory=NoOpAcknowledgmentCallback)
    escalation_handler: EscalationHandler = field(default_factory=NoOpEscalationHandler)

    def ack(
        self,
        notification_id: UUID,
        acked_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AckEvent:
        """Acknowledge a notification.

        Idempotent: repeated ack returns success without error.

        Args:
            notification_id: ID of the notification to acknowledge
            acked_by: Identifier of user/system acknowledging
            metadata: Optional additional ack metadata

        Returns:
            AckEvent with the acknowledgment details

        Raises:
            NotificationNotFoundError: If notification doesn't exist
            InvalidAckTransitionError: If transition is invalid
        """
        return self._transition(
            notification_id=notification_id,
            target_status=AckStatus.ACKED,
            acked_by=acked_by,
            metadata=metadata,
        )

    def dismiss(
        self,
        notification_id: UUID,
        dismissed_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AckEvent:
        """Dismiss a notification.

        Dismissal indicates the operator saw but chose not to formally
        acknowledge the notification.

        Args:
            notification_id: ID of the notification to dismiss
            dismissed_by: Identifier of user/system dismissing
            metadata: Optional additional metadata

        Returns:
            AckEvent with the dismissal details

        Raises:
            NotificationNotFoundError: If notification doesn't exist
            InvalidAckTransitionError: If transition is invalid
        """
        return self._transition(
            notification_id=notification_id,
            target_status=AckStatus.DISMISSED,
            acked_by=dismissed_by,
            metadata=metadata,
        )

    def check_ack_timeout(
        self,
        notification_id: UUID,
        intent: NotificationIntent,
        autonomy_context: AutonomyContext,
    ) -> AckEvent | None:
        """Check and handle ack timeout for a notification.

        Per PRD:
        - Timeout updates state to TIMED_OUT
        - SAFETY timeout triggers re-escalation

        Args:
            notification_id: ID of the notification to check
            intent: The notification's intent
            autonomy_context: The notification's autonomy context

        Returns:
            AckEvent if timeout occurred, None if already acked/dismissed
        """
        current_status = self.storage.get_ack_status(notification_id)

        # Only PENDING notifications can timeout
        if current_status != AckStatus.PENDING:
            logger.debug(
                "Notification not pending, skipping timeout: notification_id=%s status=%s",
                notification_id,
                current_status,
            )
            return None

        # Transition to TIMED_OUT
        event = self._transition(
            notification_id=notification_id,
            target_status=AckStatus.TIMED_OUT,
            acked_by="system:timeout",
            metadata={"reason": "ack_timeout"},
        )

        # SAFETY timeout in LIVE mode triggers re-escalation
        if (
            intent == NotificationIntent.SAFETY
            and autonomy_context.autonomy_mode == AutonomyMode.LIVE
        ):
            notification = self.storage.get_notification(notification_id)
            if notification:
                logger.warning(
                    "SAFETY notification timed out in LIVE mode, escalating: notification_id=%s",
                    notification_id,
                )
                self.escalation_handler.escalate(
                    notification,
                    reason="SAFETY ack timeout in LIVE mode",
                )

        return event

    def get_status(self, notification_id: UUID) -> AckStatus | None:
        """Get the current ack status for a notification.

        Args:
            notification_id: ID of the notification

        Returns:
            Current AckStatus or None if not found
        """
        return self.storage.get_ack_status(notification_id)

    def get_notification(self, notification_id: UUID) -> Notification | None:
        """Get a notification by ID.

        Args:
            notification_id: ID of the notification

        Returns:
            The Notification or None if not found
        """
        return self.storage.get_notification(notification_id)

    def register_notification(self, notification: Notification) -> None:
        """Register a notification for ack tracking.

        Sets initial status to PENDING if require_ack is True.

        Args:
            notification: The notification to register
        """
        self.storage.store_notification(notification)
        if notification.require_ack:
            self.storage.set_ack_status(
                notification.notification_id,
                AckStatus.PENDING,
            )

    def _transition(
        self,
        notification_id: UUID,
        target_status: AckStatus,
        acked_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AckEvent:
        """Internal method to handle status transitions.

        Args:
            notification_id: ID of the notification
            target_status: Target ack status
            acked_by: Identifier of user/system
            metadata: Optional additional metadata

        Returns:
            AckEvent with transition details

        Raises:
            NotificationNotFoundError: If notification doesn't exist
            InvalidAckTransitionError: If transition is invalid
        """
        current_status = self.storage.get_ack_status(notification_id)

        # If no status exists, check if notification exists
        if current_status is None:
            notification = self.storage.get_notification(notification_id)
            if notification is None:
                raise NotificationNotFoundError(notification_id)
            # Initialize to PENDING if notification exists but has no status
            current_status = AckStatus.PENDING
            self.storage.set_ack_status(notification_id, current_status)

        # Idempotent: return success if already in target state
        if current_status == target_status:
            logger.debug(
                "Idempotent ack: notification_id=%s already %s",
                notification_id,
                target_status.value,
            )
            return AckEvent(
                notification_id=notification_id,
                ack_status=target_status,
                acked_by=acked_by,
                acked_at=datetime.now(UTC),
                metadata=metadata or {},
            )

        # Validate transition
        if not _is_valid_transition(current_status, target_status):
            raise InvalidAckTransitionError(notification_id, current_status, target_status)

        # Perform transition
        self.storage.set_ack_status(notification_id, target_status, acked_by, metadata)

        event = AckEvent(
            notification_id=notification_id,
            ack_status=target_status,
            acked_by=acked_by,
            acked_at=datetime.now(UTC),
            metadata=metadata or {},
        )

        logger.info(
            "Ack status transition: notification_id=%s %s -> %s by=%s",
            notification_id,
            current_status.value,
            target_status.value,
            acked_by,
        )

        # Trigger callbacks
        self.callback.on_status_change(notification_id, current_status, target_status, metadata)

        if target_status == AckStatus.ACKED:
            self.callback.on_ack(event)
        elif target_status == AckStatus.DISMISSED:
            self.callback.on_dismiss(event)
        elif target_status == AckStatus.TIMED_OUT:
            self.callback.on_timeout(event)

        return event


# Global acknowledgment engine instance
_ack_engine: AcknowledgmentEngine | None = None


def get_ack_engine() -> AcknowledgmentEngine:
    """Get the global acknowledgment engine instance.

    Raises:
        RuntimeError: If engine hasn't been configured
    """
    global _ack_engine
    if _ack_engine is None:
        raise RuntimeError(
            "Acknowledgment engine not configured. Call configure_ack_engine() first."
        )
    return _ack_engine


def configure_ack_engine(
    storage: AckStorage | None = None,
    callback: AcknowledgmentCallback | None = None,
    escalation_handler: EscalationHandler | None = None,
) -> AcknowledgmentEngine:
    """Configure the global acknowledgment engine.

    Args:
        storage: Storage backend for ack state
        callback: Callback handler for ack events
        escalation_handler: Handler for timeout escalations

    Returns:
        The configured AcknowledgmentEngine instance
    """
    global _ack_engine
    _ack_engine = AcknowledgmentEngine(
        storage=storage or InMemoryAckStorage(),
        callback=callback or NoOpAcknowledgmentCallback(),
        escalation_handler=escalation_handler or NoOpEscalationHandler(),
    )
    return _ack_engine

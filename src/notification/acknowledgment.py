"""Acknowledgment Engine for the Unified Notification Service.

Handles acknowledgment state transitions, timeout checking, and escalation
logic for notifications that require operator acknowledgment.

Key features:
- ack(): Handle ACK/DISMISS transitions with idempotency
- check_ack_timeout(): Check and handle timed-out notifications
- SAFETY timeout triggers re-escalation via configured callback
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from notification.models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    NotificationIntent,
)

if TYPE_CHECKING:
    from notification.interfaces import AcknowledgmentCallback

logger = logging.getLogger(__name__)


# Custom exceptions for acknowledgment operations
class AckEngineError(Exception):
    """Base exception for acknowledgment engine errors."""

    pass


class NotificationNotFoundError(AckEngineError):
    """Raised when a notification is not found in ack storage."""

    pass


class InvalidAckTransitionError(AckEngineError):
    """Raised when an invalid ack status transition is attempted."""

    def __init__(
        self,
        message: str,
        current_status: AckStatus,
        requested_status: AckStatus,
    ) -> None:
        super().__init__(message)
        self.current_status = current_status
        self.requested_status = requested_status


# Default timeout values per intent (in minutes)
DEFAULT_ACK_TIMEOUTS = {
    NotificationIntent.SAFETY: 15,
    NotificationIntent.GOVERNANCE: 30,
}


class AckStorageProtocol(Protocol):
    """Protocol for acknowledgment state storage.

    Implementations should provide persistent storage (e.g., Redis, database)
    for acknowledgment state tracking.
    """

    def get_ack_state(self, notification_id: UUID) -> AckState | None:
        """Retrieve the current ack state for a notification.

        Args:
            notification_id: UUID of the notification

        Returns:
            AckState if found, None otherwise
        """
        ...

    def set_ack_state(self, state: AckState) -> None:
        """Store or update the ack state for a notification.

        Args:
            state: AckState to persist
        """
        ...

    def get_pending_notifications(
        self,
        before: datetime | None = None,
    ) -> list[AckState]:
        """Get all notifications with PENDING status.

        Args:
            before: Optional cutoff time - only return notifications
                    created before this time

        Returns:
            List of AckState for pending notifications
        """
        ...


class AckState:
    """Internal state tracking for acknowledgment lifecycle.

    Tracks the current status, metadata, and timing information
    for a notification's acknowledgment state.
    """

    def __init__(
        self,
        notification_id: UUID,
        status: AckStatus = AckStatus.PENDING,
        intent: NotificationIntent | None = None,
        autonomy_context: AutonomyContext | None = None,
        timeout_minutes: int | None = None,
        created_at: datetime | None = None,
        acked_by: str | None = None,
        acked_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.notification_id = notification_id
        self.status = status
        self.intent = intent
        self.autonomy_context = autonomy_context
        self.timeout_minutes = timeout_minutes
        self.created_at = created_at or datetime.now(UTC)
        self.acked_by = acked_by
        self.acked_at = acked_at
        self.metadata = metadata or {}

    @property
    def timeout_at(self) -> datetime | None:
        """Calculate when this notification times out.

        Returns:
            Datetime when timeout occurs, or None if no timeout configured
        """
        if self.timeout_minutes is None:
            return None
        return self.created_at + timedelta(minutes=self.timeout_minutes)

    def is_timed_out(self, now: datetime | None = None) -> bool:
        """Check if this notification has timed out.

        Args:
            now: Current time (defaults to UTC now)

        Returns:
            True if timed out, False otherwise
        """
        if self.timeout_at is None:
            return False
        now = now or datetime.now(UTC)
        return now >= self.timeout_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary for storage."""
        return {
            "notification_id": str(self.notification_id),
            "status": self.status.value,
            "intent": self.intent.value if self.intent else None,
            "autonomy_mode": (
                self.autonomy_context.autonomy_mode.value if self.autonomy_context else None
            ),
            "agent_id": (str(self.autonomy_context.agent_id) if self.autonomy_context else None),
            "timeout_minutes": self.timeout_minutes,
            "created_at": self.created_at.isoformat(),
            "acked_by": self.acked_by,
            "acked_at": self.acked_at.isoformat() if self.acked_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AckState:
        """Deserialize state from dictionary."""
        autonomy_context = None
        if data.get("autonomy_mode") and data.get("agent_id"):
            autonomy_context = AutonomyContext(
                autonomy_mode=AutonomyMode(data["autonomy_mode"]),
                agent_id=UUID(data["agent_id"]),
            )

        return cls(
            notification_id=UUID(data["notification_id"]),
            status=AckStatus(data["status"]),
            intent=NotificationIntent(data["intent"]) if data.get("intent") else None,
            autonomy_context=autonomy_context,
            timeout_minutes=data.get("timeout_minutes"),
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
            ),
            acked_by=data.get("acked_by"),
            acked_at=(datetime.fromisoformat(data["acked_at"]) if data.get("acked_at") else None),
            metadata=data.get("metadata", {}),
        )


class InMemoryAckStorage:
    """In-memory implementation of AckStorageProtocol.

    Suitable for testing and single-instance deployments.
    For production, use Redis or database-backed storage.
    """

    def __init__(self) -> None:
        self._states: dict[UUID, AckState] = {}

    def get_ack_state(self, notification_id: UUID) -> AckState | None:
        return self._states.get(notification_id)

    def set_ack_state(self, state: AckState) -> None:
        self._states[state.notification_id] = state

    def get_pending_notifications(
        self,
        before: datetime | None = None,
    ) -> list[AckState]:
        result = []
        for state in self._states.values():
            if state.status != AckStatus.PENDING:
                continue
            if before is not None and state.created_at >= before:
                continue
            result.append(state)
        return result

    def clear(self) -> None:
        """Clear all stored states (for testing)."""
        self._states.clear()


class AcknowledgmentEngine:
    """Engine for handling notification acknowledgments and timeouts.

    Manages the lifecycle of notification acknowledgments including:
    - Recording new notifications that require acknowledgment
    - Processing ack/dismiss actions from operators
    - Checking for and handling timeouts
    - Triggering escalation callbacks for SAFETY timeouts

    Thread-safety: transitions through this engine are serialized with a
    process-local lock. For multi-process deployments, use a storage backend
    with its own compare-and-set semantics.
    """

    def __init__(
        self,
        storage: AckStorageProtocol | None = None,
        callback: AcknowledgmentCallback | None = None,
        escalation_handler: EscalationHandler | None = None,
    ) -> None:
        """Initialize the acknowledgment engine.

        Args:
            storage: Storage backend for ack state. Defaults to in-memory.
            callback: Callback for ack events. Defaults to no-op.
            escalation_handler: Handler for escalations on SAFETY timeouts.
        """
        from notification.interfaces import NoOpAcknowledgmentCallback

        self._storage = storage or InMemoryAckStorage()
        self._callback = callback or NoOpAcknowledgmentCallback()
        self._escalation_handler = escalation_handler
        self._lock = RLock()

    def register_notification(
        self,
        notification_id: UUID,
        intent: NotificationIntent,
        autonomy_context: AutonomyContext,
        timeout_minutes: int | None = None,
        created_at: datetime | None = None,
    ) -> AckState:
        """Register a notification that requires acknowledgment.

        Should be called by the delivery engine when a notification
        with require_ack=True is delivered.

        Args:
            notification_id: UUID of the notification
            intent: NotificationIntent for timeout defaults
            autonomy_context: Context for escalation decisions
            timeout_minutes: Override timeout (uses intent default if None)
            created_at: Override creation time (uses now if None)

        Returns:
            AckState for the registered notification
        """
        with self._lock:
            # Use provided timeout or intent-based default
            if timeout_minutes is None:
                timeout_minutes = DEFAULT_ACK_TIMEOUTS.get(intent)

            state = AckState(
                notification_id=notification_id,
                status=AckStatus.PENDING,
                intent=intent,
                autonomy_context=autonomy_context,
                timeout_minutes=timeout_minutes,
                created_at=created_at,
            )

            self._storage.set_ack_state(state)

        logger.info(
            "Registered notification for ack tracking: notification_id=%s, intent=%s, timeout=%s",
            notification_id,
            intent.value,
            timeout_minutes,
        )

        return state

    def ack(
        self,
        notification_id: UUID,
        ack_status: AckStatus,
        acked_by: str | None = None,
        metadata: dict[str, Any] | None = None,
        before_commit: Callable[[AckStatus | None, AckEvent], None] | None = None,
    ) -> AckEvent:
        """Acknowledge a notification.

        Handles transitions to ACKED or DISMISSED status.
        Idempotent: repeated calls with same status are safe.

        Args:
            notification_id: UUID of the notification to acknowledge
            ack_status: Target status (ACKED or DISMISSED)
            acked_by: Identifier of the acknowledging user/system
            metadata: Additional context for the acknowledgment
            before_commit: Optional callback invoked with the old status and
                new event before the state transition is committed. Exceptions
                abort the state transition.

        Returns:
            AckEvent describing the acknowledgment

        Raises:
            ValueError: If ack_status is not ACKED or DISMISSED
            KeyError: If notification_id is not found
        """
        if ack_status not in (AckStatus.ACKED, AckStatus.DISMISSED):
            raise ValueError(f"Invalid ack_status for ack(): {ack_status}. Use ACKED or DISMISSED.")

        with self._lock:
            state = self._storage.get_ack_state(notification_id)
            if state is None:
                raise KeyError(f"Notification not found: {notification_id}")

            old_status = state.status
            now = datetime.now(UTC)

            # Idempotency: if already in target status, return existing event
            if state.status == ack_status:
                logger.debug(
                    "Idempotent ack: notification_id=%s already in status %s",
                    notification_id,
                    ack_status.value,
                )
                return AckEvent(
                    notification_id=notification_id,
                    ack_status=ack_status,
                    acked_by=state.acked_by,
                    acked_at=state.acked_at or now,
                    metadata=state.metadata,
                )

            # Cannot ack a timed-out notification
            if state.status == AckStatus.TIMED_OUT:
                logger.warning(
                    "Attempted to ack timed-out notification: notification_id=%s",
                    notification_id,
                )
                return AckEvent(
                    notification_id=notification_id,
                    ack_status=AckStatus.TIMED_OUT,
                    acked_by=acked_by,
                    acked_at=now,
                    metadata={"error": "Notification already timed out"},
                )

            # Cannot transition between ACKED and DISMISSED
            if state.status in (AckStatus.ACKED, AckStatus.DISMISSED) and state.status != ack_status:
                logger.warning(
                    "Invalid transition attempted: notification_id=%s from %s to %s",
                    notification_id,
                    state.status.value,
                    ack_status.value,
                )
                raise InvalidAckTransitionError(
                    f"Cannot transition from {state.status.value} to {ack_status.value}",
                    current_status=state.status,
                    requested_status=ack_status,
                )

            merged_metadata = dict(state.metadata)
            merged_metadata.update(metadata or {})

            event = AckEvent(
                notification_id=notification_id,
                ack_status=ack_status,
                acked_by=acked_by,
                acked_at=now,
                metadata=merged_metadata,
            )
            if before_commit is not None:
                before_commit(old_status, event)

            new_state = AckState(
                notification_id=state.notification_id,
                status=ack_status,
                intent=state.intent,
                autonomy_context=state.autonomy_context,
                timeout_minutes=state.timeout_minutes,
                created_at=state.created_at,
                acked_by=acked_by,
                acked_at=now,
                metadata=merged_metadata,
            )
            self._storage.set_ack_state(new_state)

        # Trigger callbacks
        if ack_status == AckStatus.ACKED:
            self._callback.on_ack(event)
        elif ack_status == AckStatus.DISMISSED:
            self._callback.on_dismiss(event)

        self._callback.on_status_change(
            notification_id=notification_id,
            old_status=old_status,
            new_status=ack_status,
            metadata=event.metadata,
        )

        logger.info(
            "Notification acknowledged: notification_id=%s, status=%s -> %s, acked_by=%s",
            notification_id,
            old_status.value,
            ack_status.value,
            acked_by,
        )

        return event

    def check_ack_timeout(
        self,
        notification_id: UUID,
        now: datetime | None = None,
    ) -> AckEvent | None:
        """Check if a notification has timed out and handle if so.

        Args:
            notification_id: UUID of the notification to check
            now: Current time (defaults to UTC now)

        Returns:
            AckEvent if timed out, None if still pending or already processed
        """
        state = self._storage.get_ack_state(notification_id)
        if state is None:
            logger.warning(
                "check_ack_timeout called for unknown notification: %s",
                notification_id,
            )
            return None

        # Already processed
        if state.status != AckStatus.PENDING:
            return None

        now = now or datetime.now(UTC)

        # Not yet timed out
        if not state.is_timed_out(now):
            return None

        return self._handle_timeout(state, now)

    def check_all_timeouts(self, now: datetime | None = None) -> list[AckEvent]:
        """Check all pending notifications for timeouts.

        This should be called periodically (e.g., by a scheduled job)
        to process any timed-out notifications.

        Args:
            now: Current time (defaults to UTC now)

        Returns:
            List of AckEvents for timed-out notifications
        """
        now = now or datetime.now(UTC)
        events = []

        pending = self._storage.get_pending_notifications()
        for state in pending:
            if state.is_timed_out(now):
                event = self._handle_timeout(state, now)
                if event:
                    events.append(event)

        if events:
            logger.info("Processed %d timed-out notifications", len(events))

        return events

    def _handle_timeout(self, state: AckState, now: datetime) -> AckEvent:
        """Handle a timed-out notification.

        Updates state to TIMED_OUT and triggers escalation for SAFETY
        notifications in LIVE mode.

        Args:
            state: AckState to process
            now: Current time

        Returns:
            AckEvent describing the timeout
        """
        old_status = state.status
        state.status = AckStatus.TIMED_OUT
        state.acked_at = now
        state.metadata["timed_out_at"] = now.isoformat()

        self._storage.set_ack_state(state)

        event = AckEvent(
            notification_id=state.notification_id,
            ack_status=AckStatus.TIMED_OUT,
            acked_by=None,
            acked_at=now,
            metadata=state.metadata,
        )

        # Trigger callbacks
        self._callback.on_timeout(event)
        self._callback.on_status_change(
            notification_id=state.notification_id,
            old_status=old_status,
            new_status=AckStatus.TIMED_OUT,
            metadata=state.metadata,
        )

        logger.warning(
            "Notification timed out: notification_id=%s, intent=%s, autonomy_mode=%s",
            state.notification_id,
            state.intent.value if state.intent else "unknown",
            state.autonomy_context.autonomy_mode.value if state.autonomy_context else "unknown",
        )

        # SAFETY timeout in LIVE mode triggers re-escalation
        if self._should_escalate(state):
            self._trigger_escalation(state, event)

        return event

    def _should_escalate(self, state: AckState) -> bool:
        """Determine if a timed-out notification should escalate.

        Per PRD: SAFETY timeout triggers re-escalation in LIVE mode.

        Args:
            state: AckState of the timed-out notification

        Returns:
            True if escalation should be triggered
        """
        if state.intent != NotificationIntent.SAFETY:
            return False

        if state.autonomy_context is None:
            return False

        return state.autonomy_context.autonomy_mode == AutonomyMode.LIVE

    def _trigger_escalation(self, state: AckState, event: AckEvent) -> None:
        """Trigger escalation for a timed-out SAFETY notification.

        Args:
            state: AckState of the notification
            event: AckEvent for the timeout
        """
        logger.error(
            "SAFETY notification timed out in LIVE mode - escalating: notification_id=%s",
            state.notification_id,
        )

        if self._escalation_handler:
            try:
                self._escalation_handler.escalate(
                    notification_id=state.notification_id,
                    intent=state.intent,
                    autonomy_context=state.autonomy_context,
                    reason="Acknowledgment timeout",
                    metadata=event.metadata,
                )
            except Exception:
                logger.exception(
                    "Escalation handler failed for notification: %s",
                    state.notification_id,
                )

    def get_status(self, notification_id: UUID) -> AckStatus | None:
        """Get the current acknowledgment status for a notification.

        Args:
            notification_id: UUID of the notification

        Returns:
            Current AckStatus, or None if not found
        """
        state = self._storage.get_ack_state(notification_id)
        return state.status if state else None

    def get_state(self, notification_id: UUID) -> AckState | None:
        """Get the full acknowledgment state for a notification.

        Args:
            notification_id: UUID of the notification

        Returns:
            AckState if found, None otherwise
        """
        return self._storage.get_ack_state(notification_id)


class EscalationHandler(Protocol):
    """Protocol for handling escalations on SAFETY timeouts."""

    def escalate(
        self,
        notification_id: UUID,
        intent: NotificationIntent | None,
        autonomy_context: AutonomyContext | None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Trigger escalation for a timed-out notification.

        Args:
            notification_id: UUID of the notification
            intent: NotificationIntent
            autonomy_context: Context for escalation decisions
            reason: Human-readable reason for escalation
            metadata: Additional context
        """
        ...


class LoggingEscalationHandler:
    """Escalation handler that logs escalations.

    Suitable for testing and development. Production should use
    a handler that integrates with PagerDuty or similar.
    """

    def __init__(self, logger_instance: logging.Logger | None = None) -> None:
        self._logger = logger_instance or logger

    def escalate(
        self,
        notification_id: UUID,
        intent: NotificationIntent | None,
        autonomy_context: AutonomyContext | None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._logger.critical(
            "ESCALATION TRIGGERED: notification_id=%s, intent=%s, reason=%s, metadata=%s",
            notification_id,
            intent.value if intent else "unknown",
            reason,
            metadata,
        )


# Global acknowledgment engine instance
_ack_engine: AcknowledgmentEngine | None = None


def get_ack_engine() -> AcknowledgmentEngine:
    """Get the global acknowledgment engine instance.

    Returns:
        The singleton AcknowledgmentEngine instance.

    Raises:
        RuntimeError: If the engine has not been configured.
    """
    global _ack_engine
    if _ack_engine is None:
        # Auto-configure with defaults for convenience
        _ack_engine = AcknowledgmentEngine()
    return _ack_engine


def configure_ack_engine(
    storage: AckStorageProtocol | None = None,
    callback: AcknowledgmentCallback | None = None,
    escalation_handler: EscalationHandler | None = None,
) -> AcknowledgmentEngine:
    """Configure the global acknowledgment engine.

    Args:
        storage: Storage backend for ack state.
        callback: Callback for ack events.
        escalation_handler: Handler for escalations on SAFETY timeouts.

    Returns:
        The configured AcknowledgmentEngine instance.
    """
    global _ack_engine
    _ack_engine = AcknowledgmentEngine(
        storage=storage,
        callback=callback,
        escalation_handler=escalation_handler,
    )
    return _ack_engine


def reset_ack_engine() -> None:
    """Reset the global acknowledgment engine (for testing).

    Clears the global engine instance, allowing reconfiguration.
    """
    global _ack_engine
    _ack_engine = None

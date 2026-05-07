"""Audit logging for notification delivery.

This module provides audit persistence for notification delivery outcomes.
It creates audit records for all delivery attempts (delivered, failed, deduplicated)
as required by the PRD.

Audit records capture:
- Notification metadata and state at time of delivery
- Delivery outcome (success, failure, deduplication)
- Channel-level results
- Timestamp information
- Autonomy context for traceability
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from notification.models import (
    AckEvent,
    AckStatus,
    Channel,
    DeliveryStatus,
    Notification,
    NotificationResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditRecord:
    """Immutable audit record for notification delivery.

    This represents a single audit entry capturing the complete state
    of a delivery attempt for compliance and debugging purposes.
    """

    # Core identifiers
    audit_id: UUID
    notification_id: UUID
    notification_type: str

    # Delivery outcome
    status: DeliveryStatus
    channels_attempted: tuple[Channel, ...]
    channels_succeeded: tuple[Channel, ...]
    channels_failed: tuple[Channel, ...]
    error_message: str | None

    # Context
    intent: str
    delivery_mode: str
    autonomy_mode: str
    agent_id: UUID

    # Optional context IDs
    plan_id: UUID | None
    decision_snapshot_id: UUID | None
    execution_snapshot_id: UUID | None
    skip_snapshot_id: UUID | None

    # Notification content
    title: str
    source: str
    correlation_id: str | None

    # Metadata
    metadata: dict[str, Any]
    audit_metadata: dict[str, Any]

    # Timestamps
    notification_created_at: datetime
    delivered_at: datetime
    audit_created_at: datetime

    # Policy evaluation identity
    policy_config_id: UUID | None = None
    policy_config_hash: str | None = None
    policy_evaluation_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert audit record to dictionary for serialization.

        Returns:
            Dictionary representation of the audit record
        """
        return {
            "audit_id": str(self.audit_id),
            "notification_id": str(self.notification_id),
            "notification_type": self.notification_type,
            "status": self.status.value,
            "channels_attempted": [c.value for c in self.channels_attempted],
            "channels_succeeded": [c.value for c in self.channels_succeeded],
            "channels_failed": [c.value for c in self.channels_failed],
            "error_message": self.error_message,
            "intent": self.intent,
            "delivery_mode": self.delivery_mode,
            "autonomy_mode": self.autonomy_mode,
            "agent_id": str(self.agent_id),
            "plan_id": str(self.plan_id) if self.plan_id else None,
            "decision_snapshot_id": (
                str(self.decision_snapshot_id) if self.decision_snapshot_id else None
            ),
            "execution_snapshot_id": (
                str(self.execution_snapshot_id) if self.execution_snapshot_id else None
            ),
            "skip_snapshot_id": (
                str(self.skip_snapshot_id) if self.skip_snapshot_id else None
            ),
            "policy_config_id": (
                str(self.policy_config_id) if self.policy_config_id else None
            ),
            "policy_config_hash": self.policy_config_hash,
            "policy_evaluation_id": (
                str(self.policy_evaluation_id) if self.policy_evaluation_id else None
            ),
            "title": self.title,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "audit_metadata": self.audit_metadata,
            "notification_created_at": self.notification_created_at.isoformat(),
            "delivered_at": self.delivered_at.isoformat(),
            "audit_created_at": self.audit_created_at.isoformat(),
        }


@dataclass(frozen=True)
class AckAuditRecord:
    """Audit record for acknowledgment events.

    Captures state changes for notification acknowledgments.
    """

    audit_id: UUID
    notification_id: UUID
    old_status: AckStatus | None
    new_status: AckStatus
    acked_by: str | None
    acked_at: datetime
    audit_created_at: datetime
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert ack audit record to dictionary."""
        return {
            "audit_id": str(self.audit_id),
            "notification_id": str(self.notification_id),
            "old_status": self.old_status.value if self.old_status else None,
            "new_status": self.new_status.value,
            "acked_by": self.acked_by,
            "acked_at": self.acked_at.isoformat(),
            "audit_created_at": self.audit_created_at.isoformat(),
            "metadata": self.metadata,
        }


class AuditStore(ABC):
    """Abstract interface for audit storage.

    Implementations provide the underlying storage mechanism for
    audit records. This allows for different backends (database,
    file-based, cloud storage) without changing the audit logic.
    """

    @abstractmethod
    def save_delivery_audit(self, record: AuditRecord) -> None:
        """Save a delivery audit record.

        Args:
            record: The audit record to persist

        Raises:
            AuditPersistenceError: If the record cannot be saved
        """
        ...

    @abstractmethod
    def save_ack_audit(self, record: AckAuditRecord) -> None:
        """Save an acknowledgment audit record.

        Args:
            record: The ack audit record to persist

        Raises:
            AuditPersistenceError: If the record cannot be saved
        """
        ...

    @abstractmethod
    def get_delivery_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AuditRecord]:
        """Retrieve all delivery audit records for a notification.

        Args:
            notification_id: The notification ID to query

        Returns:
            List of audit records, ordered by created_at descending
        """
        ...

    @abstractmethod
    def get_ack_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AckAuditRecord]:
        """Retrieve all ack audit records for a notification.

        Args:
            notification_id: The notification ID to query

        Returns:
            List of ack audit records, ordered by created_at descending
        """
        ...


class AuditPersistenceError(Exception):
    """Raised when audit persistence fails."""

    def __init__(
        self,
        message: str,
        record: AuditRecord | AckAuditRecord | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.record = record
        self.original_error = original_error


class InMemoryAuditStore(AuditStore):
    """In-memory audit store for testing and development.

    Stores audit records in memory. Not suitable for production use
    as data is lost on process restart.
    """

    def __init__(self) -> None:
        self._delivery_audits: list[AuditRecord] = []
        self._ack_audits: list[AckAuditRecord] = []

    def save_delivery_audit(self, record: AuditRecord) -> None:
        """Save delivery audit record to memory."""
        self._delivery_audits.append(record)
        logger.debug(
            "Saved delivery audit: audit_id=%s, notification_id=%s, status=%s",
            record.audit_id,
            record.notification_id,
            record.status.value,
        )

    def save_ack_audit(self, record: AckAuditRecord) -> None:
        """Save ack audit record to memory."""
        self._ack_audits.append(record)
        logger.debug(
            "Saved ack audit: audit_id=%s, notification_id=%s, new_status=%s",
            record.audit_id,
            record.notification_id,
            record.new_status.value,
        )

    def get_delivery_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AuditRecord]:
        """Get delivery audits for a notification."""
        return sorted(
            [r for r in self._delivery_audits if r.notification_id == notification_id],
            key=lambda r: r.audit_created_at,
            reverse=True,
        )

    def get_ack_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AckAuditRecord]:
        """Get ack audits for a notification."""
        return sorted(
            [r for r in self._ack_audits if r.notification_id == notification_id],
            key=lambda r: r.audit_created_at,
            reverse=True,
        )

    def clear(self) -> None:
        """Clear all audit records (for testing)."""
        self._delivery_audits.clear()
        self._ack_audits.clear()

    @property
    def delivery_audits(self) -> list[AuditRecord]:
        """Get all delivery audits (for testing)."""
        return list(self._delivery_audits)

    @property
    def ack_audits(self) -> list[AckAuditRecord]:
        """Get all ack audits (for testing)."""
        return list(self._ack_audits)


class FileAuditStore(AuditStore):
    """File-based audit store for simple deployments.

    Appends JSON-line formatted audit records to files.
    Suitable for environments without database infrastructure.
    """

    def __init__(
        self,
        delivery_audit_path: str = "/var/log/uns/delivery_audits.jsonl",
        ack_audit_path: str = "/var/log/uns/ack_audits.jsonl",
    ) -> None:
        """Initialize file-based audit store.

        Args:
            delivery_audit_path: Path for delivery audit records
            ack_audit_path: Path for ack audit records
        """
        self._delivery_path = delivery_audit_path
        self._ack_path = ack_audit_path

    def save_delivery_audit(self, record: AuditRecord) -> None:
        """Append delivery audit record to file."""
        try:
            with open(self._delivery_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            raise AuditPersistenceError(
                f"Failed to write delivery audit: {e}",
                record=record,
                original_error=e,
            ) from e

    def save_ack_audit(self, record: AckAuditRecord) -> None:
        """Append ack audit record to file."""
        try:
            with open(self._ack_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            raise AuditPersistenceError(
                f"Failed to write ack audit: {e}",
                record=record,
                original_error=e,
            ) from e

    def get_delivery_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AuditRecord]:
        """Read delivery audits from file (not implemented for file store)."""
        # File-based store is write-optimized; reading would require
        # scanning the entire file. For query capabilities, use a database.
        raise NotImplementedError(
            "FileAuditStore does not support querying. Use a database-backed store."
        )

    def get_ack_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AckAuditRecord]:
        """Read ack audits from file (not implemented for file store)."""
        raise NotImplementedError(
            "FileAuditStore does not support querying. Use a database-backed store."
        )


def create_audit_record(
    notification: Notification,
    result: NotificationResult,
    metadata: dict[str, Any] | None = None,
) -> AuditRecord:
    """Create an audit record from a notification and its delivery result.

    Args:
        notification: The notification that was delivered
        result: The delivery result
        metadata: Optional additional audit metadata

    Returns:
        A new AuditRecord instance
    """
    from uuid import uuid4

    delivery_mode = notification.delivery_mode
    if delivery_mode is None:
        from notification.policies import get_default_delivery_mode

        delivery_mode = get_default_delivery_mode(notification.intent)

    return AuditRecord(
        audit_id=uuid4(),
        notification_id=notification.notification_id,
        notification_type=notification.notification_type,
        status=result.status,
        channels_attempted=tuple(result.channels_attempted),
        channels_succeeded=tuple(result.channels_succeeded),
        channels_failed=tuple(result.channels_failed),
        error_message=result.error_message,
        intent=notification.intent.value,
        delivery_mode=delivery_mode.value,
        autonomy_mode=notification.autonomy_context.autonomy_mode.value,
        agent_id=notification.autonomy_context.agent_id,
        plan_id=notification.autonomy_context.plan_id,
        decision_snapshot_id=notification.autonomy_context.decision_snapshot_id,
        execution_snapshot_id=notification.autonomy_context.execution_snapshot_id,
        skip_snapshot_id=notification.autonomy_context.skip_snapshot_id,
        policy_config_id=notification.policy_config_id,
        policy_config_hash=notification.policy_config_hash,
        policy_evaluation_id=notification.policy_evaluation_id,
        title=notification.title,
        source=notification.source,
        correlation_id=notification.correlation_id,
        metadata=notification.metadata,
        audit_metadata=metadata or {},
        notification_created_at=notification.created_at,
        delivered_at=result.delivered_at,
        audit_created_at=datetime.now(UTC),
    )


def create_ack_audit_record(
    notification_id: UUID,
    old_status: AckStatus | None,
    new_status: AckStatus,
    acked_by: str | None = None,
    acked_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> AckAuditRecord:
    """Create an acknowledgment audit record.

    Args:
        notification_id: The notification ID
        old_status: Previous ack status (None for initial state)
        new_status: New ack status
        acked_by: User/system that triggered the change
        acked_at: Timestamp of the ack action
        metadata: Optional additional metadata

    Returns:
        A new AckAuditRecord instance
    """
    from uuid import uuid4

    return AckAuditRecord(
        audit_id=uuid4(),
        notification_id=notification_id,
        old_status=old_status,
        new_status=new_status,
        acked_by=acked_by,
        acked_at=acked_at or datetime.now(UTC),
        audit_created_at=datetime.now(UTC),
        metadata=metadata or {},
    )


@dataclass
class PersistentAuditLogger:
    """Audit logger that persists records to a configured store.

    This is the production implementation of the AuditLogger protocol
    from the service module. It creates and persists audit records
    for all delivery outcomes.
    """

    store: AuditStore = field(default_factory=InMemoryAuditStore)
    fail_silently: bool = False

    def log_delivery(
        self,
        notification: Notification,
        result: NotificationResult,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a delivery attempt to the audit store.

        Args:
            notification: The notification that was delivered
            result: The delivery result
            metadata: Optional additional audit metadata
        """
        try:
            record = create_audit_record(notification, result, metadata)
            self.store.save_delivery_audit(record)
            logger.info(
                "Audit recorded: notification_id=%s, status=%s, channels=%s",
                notification.notification_id,
                result.status.value,
                [c.value for c in result.channels_succeeded],
            )
        except AuditPersistenceError as e:
            if self.fail_silently:
                logger.error(
                    "Failed to persist audit record (fail_silently=True): %s", str(e)
                )
            else:
                raise
        except Exception as e:
            if self.fail_silently:
                logger.error(
                    "Unexpected error persisting audit record (fail_silently=True): %s",
                    str(e),
                )
            else:
                raise AuditPersistenceError(
                    f"Unexpected error: {e}", original_error=e
                ) from e

    def log_ack(
        self,
        notification_id: UUID,
        old_status: AckStatus | None,
        new_status: AckStatus,
        acked_by: str | None = None,
        acked_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an acknowledgment event to the audit store.

        Args:
            notification_id: The notification ID
            old_status: Previous ack status
            new_status: New ack status
            acked_by: User/system that triggered the change
            acked_at: Timestamp of the ack action
            metadata: Optional additional metadata
        """
        try:
            record = create_ack_audit_record(
                notification_id=notification_id,
                old_status=old_status,
                new_status=new_status,
                acked_by=acked_by,
                acked_at=acked_at,
                metadata=metadata,
            )
            self.store.save_ack_audit(record)
            logger.info(
                "Ack audit recorded: notification_id=%s, %s -> %s",
                notification_id,
                old_status.value if old_status else "None",
                new_status.value,
            )
        except AuditPersistenceError as e:
            if self.fail_silently:
                logger.error(
                    "Failed to persist ack audit record (fail_silently=True): %s",
                    str(e),
                )
            else:
                raise
        except Exception as e:
            if self.fail_silently:
                logger.error(
                    "Unexpected error persisting ack audit record "
                    "(fail_silently=True): %s",
                    str(e),
                )
            else:
                raise AuditPersistenceError(
                    f"Unexpected error: {e}", original_error=e
                ) from e


@dataclass
class PersistentAcknowledgmentAuditCallback:
    """Acknowledgment callback that persists ACK lifecycle state changes."""

    store: AuditStore = field(default_factory=InMemoryAuditStore)
    fail_silently: bool = False

    def on_ack(self, event: AckEvent) -> None:
        """ACK events are persisted from on_status_change to capture old status."""
        return None

    def on_dismiss(self, event: AckEvent) -> None:
        """Dismiss events are persisted from on_status_change to capture old status."""
        return None

    def on_timeout(self, event: AckEvent) -> None:
        """Timeout events are persisted from on_status_change to capture old status."""
        return None

    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist an acknowledgment status transition."""
        if old_status == new_status:
            return
        try:
            record = create_ack_audit_record(
                notification_id=notification_id,
                old_status=old_status,
                new_status=new_status,
                metadata=metadata,
            )
            self.store.save_ack_audit(record)
            logger.info(
                "Ack audit recorded from callback: notification_id=%s, %s -> %s",
                notification_id,
                old_status.value,
                new_status.value,
            )
        except AuditPersistenceError as e:
            if self.fail_silently:
                logger.error(
                    "Failed to persist ack audit callback record "
                    "(fail_silently=True): %s",
                    str(e),
                )
            else:
                raise
        except Exception as e:
            if self.fail_silently:
                logger.error(
                    "Unexpected error persisting ack audit callback record "
                    "(fail_silently=True): %s",
                    str(e),
                )
            else:
                raise AuditPersistenceError(
                    f"Unexpected error: {e}", original_error=e
                ) from e


# Global audit logger instance
_audit_logger: PersistentAuditLogger | None = None


def get_audit_logger() -> PersistentAuditLogger:
    """Get the global audit logger instance.

    Returns:
        The singleton PersistentAuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = PersistentAuditLogger()
    return _audit_logger


def configure_audit_logger(
    store: AuditStore | None = None,
    fail_silently: bool = False,
) -> PersistentAuditLogger:
    """Configure the global audit logger.

    Args:
        store: Custom audit store to use
        fail_silently: Whether to suppress persistence errors

    Returns:
        The configured PersistentAuditLogger instance
    """
    global _audit_logger
    _audit_logger = PersistentAuditLogger(
        store=store if store is not None else InMemoryAuditStore(),
        fail_silently=fail_silently,
    )
    return _audit_logger

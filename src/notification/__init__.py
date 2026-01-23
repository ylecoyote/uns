"""Unified Notification Service (UNS) - Core notification package.

This package provides the notification delivery system with support for
multiple channels, delivery guarantees, and acknowledgment workflows.
"""

# Audit module exports
from notification.audit import (
    AckAuditRecord,
    AuditPersistenceError,
    AuditRecord,
    AuditStore,
    FileAuditStore,
    InMemoryAuditStore,
    PersistentAuditLogger,
    configure_audit_logger,
    create_ack_audit_record,
    create_audit_record,
    get_audit_logger,
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
    # Models
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
    # Audit
    "AckAuditRecord",
    "AuditPersistenceError",
    "AuditRecord",
    "AuditStore",
    "FileAuditStore",
    "InMemoryAuditStore",
    "PersistentAuditLogger",
    "configure_audit_logger",
    "create_ack_audit_record",
    "create_audit_record",
    "get_audit_logger",
]

"""Database module for the Unified Notification Service.

Provides SQLAlchemy models and utilities for persisting
notification and audit data.
"""

from db.models import (
    AckAuditRecord,
    Base,
    NotificationAuditRecord,
    PersistedNotificationPolicy,
)

__all__ = [
    "AckAuditRecord",
    "Base",
    "NotificationAuditRecord",
    "PersistedNotificationPolicy",
]

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
from db.policy_store import SQLAlchemyPolicyStore, create_sqlalchemy_policy_store

__all__ = [
    "AckAuditRecord",
    "Base",
    "NotificationAuditRecord",
    "PersistedNotificationPolicy",
    "SQLAlchemyPolicyStore",
    "create_sqlalchemy_policy_store",
]

"""Database module for the Unified Notification Service.

Provides SQLAlchemy models and utilities for persisting
notification and audit data.
"""

from db.models import (
    AckAuditRecord,
    Base,
    NotificationAuditRecord,
    PersistedNotificationPolicy,
    WebSocketReplayRecord,
)
from db.policy_store import SQLAlchemyPolicyStore, create_sqlalchemy_policy_store
from db.websocket_replay_store import (
    SQLAlchemyWebSocketReplayStore,
    create_sqlalchemy_websocket_replay_store,
)

__all__ = [
    "AckAuditRecord",
    "Base",
    "NotificationAuditRecord",
    "PersistedNotificationPolicy",
    "SQLAlchemyPolicyStore",
    "SQLAlchemyWebSocketReplayStore",
    "WebSocketReplayRecord",
    "create_sqlalchemy_policy_store",
    "create_sqlalchemy_websocket_replay_store",
]

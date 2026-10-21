"""SQLAlchemy ORM models, organised by concern.

Re-exports preserve the historical ``from db.models import …`` import path.
For new code, prefer the focused submodules so the import graph reflects the
table's domain (audit vs policy vs learning vs websocket replay).
"""

from db.models._base import AckStatusDB, Base, DeliveryStatusDB
from db.models.audit import AckAuditRecord, NotificationAuditRecord
from db.models.policy import (
    NotificationPolicyRevision,
    NotificationPolicySnapshot,
    PersistedNotificationPolicy,
)
from db.models.policy_learning import (
    PersistedPolicyDelta,
    PersistedShadowEvaluationAggregate,
    PersistedShadowEvaluationResult,
)
from db.models.websocket import WebSocketReplayRecord

__all__ = [
    "AckAuditRecord",
    "AckStatusDB",
    "Base",
    "DeliveryStatusDB",
    "NotificationAuditRecord",
    "NotificationPolicyRevision",
    "NotificationPolicySnapshot",
    "PersistedNotificationPolicy",
    "PersistedPolicyDelta",
    "PersistedShadowEvaluationAggregate",
    "PersistedShadowEvaluationResult",
    "WebSocketReplayRecord",
]

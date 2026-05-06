"""Dead-letter queue support for visible AGSignal delivery failures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from notification.config import get_notification_config
from notification.models import Notification


class DLQEntry(BaseModel):
    """Serializable failed-notification record."""

    entry_id: UUID = Field(default_factory=uuid4)
    notification_id: UUID
    notification_type: str
    intent: str
    source: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, payload: str | bytes) -> DLQEntry:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return cls(**json.loads(payload))


class DLQService:
    """Redis-list compatible DLQ service."""

    def __init__(self, redis_client: Any, key: str | None = None) -> None:
        self._redis = redis_client
        self._key = key or get_notification_config().dlq_key

    @property
    def key(self) -> str:
        return self._key

    def enqueue(
        self,
        notification: Notification,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> DLQEntry:
        """Record a failed notification in the DLQ."""
        entry = DLQEntry(
            notification_id=notification.notification_id,
            notification_type=notification.notification_type,
            intent=notification.intent.value,
            source=notification.source,
            reason=reason,
            metadata=metadata or {},
        )
        self._redis.lpush(self._key, entry.to_json())
        return entry

    def list_entries(self, start: int = 0, end: int = -1) -> list[DLQEntry]:
        """List DLQ entries, newest first."""
        return [
            DLQEntry.from_json(payload)
            for payload in self._redis.lrange(self._key, start, end)
        ]

    def remove(self, entry_id: UUID) -> bool:
        """Remove a DLQ entry by id."""
        for entry_payload in self._redis.lrange(self._key, 0, -1):
            entry = DLQEntry.from_json(entry_payload)
            if entry.entry_id == entry_id:
                return bool(self._redis.lrem(self._key, 1, entry_payload))
        return False

    def depth(self) -> int:
        """Return current DLQ depth."""
        return int(self._redis.llen(self._key))

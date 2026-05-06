"""Producer idempotency for AGSignal notification creation.

Idempotency protects producer retry safety. It is intentionally separate from
deduplication, which protects human attention after a notification exists.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from notification.config import NotificationConfig, get_notification_config

logger = logging.getLogger(__name__)


class IdempotencyRecord(BaseModel):
    """Stored result for a previously processed producer request."""

    notification_id: UUID
    job_id: str
    source: str
    idempotency_key: str
    created_at: datetime


class IdempotencyService:
    """Redis-style idempotency service using `get`, `set`, and `delete`."""

    KEY_PREFIX = "uns:idem:"

    def __init__(
        self,
        redis_client: Any,
        config: NotificationConfig | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis = redis_client
        self._config = config or get_notification_config()
        self._ttl_seconds = ttl_seconds or self._config.idempotency_ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def _make_key(self, source: str, idempotency_key: str) -> str:
        safe_source = source.replace(":", "_")
        safe_key = idempotency_key.replace(":", "_")
        return f"{self.KEY_PREFIX}{safe_source}:{safe_key}"

    def get_existing(self, source: str, idempotency_key: str) -> IdempotencyRecord | None:
        """Return the original record for a repeated producer request."""
        key = self._make_key(source, idempotency_key)
        raw = self._redis.get(key)
        if raw is None:
            return None

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            data = json.loads(raw)
            return IdempotencyRecord(
                notification_id=UUID(data["notification_id"]),
                job_id=data["job_id"],
                source=data["source"],
                idempotency_key=data["idempotency_key"],
                created_at=datetime.fromisoformat(data["created_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring malformed idempotency record for %s: %s", key, exc)
            return None

    def mark_processed(
        self,
        source: str,
        idempotency_key: str,
        notification_id: UUID,
        job_id: str,
    ) -> bool:
        """Store a processed idempotency key using atomic set-if-absent semantics."""
        key = self._make_key(source, idempotency_key)
        record = IdempotencyRecord(
            notification_id=notification_id,
            job_id=job_id,
            source=source,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )
        payload = json.dumps(
            {
                "notification_id": str(record.notification_id),
                "job_id": record.job_id,
                "source": record.source,
                "idempotency_key": record.idempotency_key,
                "created_at": record.created_at.isoformat(),
            }
        )
        return bool(self._redis.set(key, payload, ex=self._ttl_seconds, nx=True))

    def clear(self, source: str, idempotency_key: str) -> bool:
        """Delete an idempotency record."""
        return bool(self._redis.delete(self._make_key(source, idempotency_key)))

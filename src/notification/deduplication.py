"""Deduplication engine for notification delivery.

This module provides at-most-once semantic delivery per dedup_key within
a configurable time window. It uses Redis SETNX + TTL for distributed
deduplication.

The deduplication check is the first step in the delivery pipeline,
preventing duplicate notifications from being processed.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from notification.models import Notification
from notification.policies import get_policy_registry

logger = logging.getLogger(__name__)


class DeduplicationStore(ABC):
    """Abstract interface for deduplication storage.

    Implementations provide the underlying storage mechanism for
    tracking seen dedup keys. This allows for different backends
    (Redis, in-memory, etc.) without changing the deduplication logic.
    """

    @abstractmethod
    def set_if_not_exists(self, key: str, ttl_seconds: int) -> bool:
        """Attempt to set a key if it doesn't exist.

        Args:
            key: The dedup key to set
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if key was set (not a duplicate), False if key exists (duplicate)
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists.

        Args:
            key: The dedup key to check

        Returns:
            True if key exists, False otherwise
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key.

        Args:
            key: The dedup key to delete

        Returns:
            True if key was deleted, False if it didn't exist
        """
        ...


class InMemoryDeduplicationStore(DeduplicationStore):
    """In-memory deduplication store for testing and development.

    Note: This implementation does not provide TTL expiration automatically.
    Keys persist until explicitly deleted or the process restarts.
    For production use, use RedisDeduplicationStore.
    """

    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._expiry: dict[str, float] = {}

    def set_if_not_exists(self, key: str, ttl_seconds: int) -> bool:
        """Set key if not exists. TTL is tracked but not auto-expired."""
        if key in self._keys:
            return False
        self._keys.add(key)
        # Track expiry for potential manual cleanup
        import time

        self._expiry[key] = time.time() + ttl_seconds
        return True

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return key in self._keys

    def delete(self, key: str) -> bool:
        """Delete a key."""
        if key in self._keys:
            self._keys.discard(key)
            self._expiry.pop(key, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all keys (for testing)."""
        self._keys.clear()
        self._expiry.clear()


class RedisDeduplicationStore(DeduplicationStore):
    """Redis-backed deduplication store for production use.

    Uses Redis SETNX with TTL for atomic set-if-not-exists with
    automatic expiration. This provides distributed deduplication
    across multiple service instances.
    """

    def __init__(
        self,
        redis_client: Any = None,
        key_prefix: str = "uns:dedup:",
    ) -> None:
        """Initialize with Redis client.

        Args:
            redis_client: Redis client instance. If None, attempts to create one.
            key_prefix: Prefix for all dedup keys in Redis
        """
        self._key_prefix = key_prefix
        if redis_client is None:
            try:
                import redis

                self._redis = redis.Redis(host="localhost", port=6379, db=0)
            except ImportError as err:
                raise ImportError(
                    "redis package required for RedisDeduplicationStore. "
                    "Install with: pip install redis"
                ) from err
        else:
            self._redis = redis_client

    def _make_key(self, key: str) -> str:
        """Create prefixed Redis key."""
        return f"{self._key_prefix}{key}"

    def set_if_not_exists(self, key: str, ttl_seconds: int) -> bool:
        """Use Redis SET NX with TTL for atomic set-if-not-exists."""
        redis_key = self._make_key(key)
        # SET key value NX EX ttl returns True if key was set
        result = self._redis.set(redis_key, "1", nx=True, ex=ttl_seconds)
        return result is True

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        redis_key = self._make_key(key)
        return bool(self._redis.exists(redis_key))

    def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        redis_key = self._make_key(key)
        return bool(self._redis.delete(redis_key))


def generate_dedup_key(notification: Notification) -> str:
    """Generate a stable dedup key for a notification.

    If the notification has an explicit dedup_key, use it.
    Otherwise, generate one from notification properties that
    should be stable across duplicate submissions.

    Args:
        notification: The notification to generate key for

    Returns:
        A stable dedup key string
    """
    if notification.dedup_key:
        return notification.dedup_key

    # Generate key from stable properties
    key_parts = [
        notification.notification_type,
        notification.intent.value,
        str(notification.autonomy_context.agent_id),
        notification.source,
        notification.title,
    ]

    # Add correlation_id if present
    if notification.correlation_id:
        key_parts.append(notification.correlation_id)

    # Create hash of combined parts
    key_string = ":".join(key_parts)
    key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:32]

    return f"{notification.notification_type}:{key_hash}"


@dataclass
class DeduplicationEngine:
    """Engine for checking and recording notification deduplication.

    This is the main interface for the delivery service to use
    for deduplication checks.
    """

    store: DeduplicationStore = field(default_factory=InMemoryDeduplicationStore)

    def should_deduplicate(self, notification: Notification) -> bool:
        """Check if notification should be deduplicated (is a duplicate).

        This method:
        1. Generates or uses the notification's dedup key
        2. Attempts to set the key in the store with appropriate TTL
        3. Returns True if the key already existed (duplicate)

        Args:
            notification: The notification to check

        Returns:
            True if notification is a duplicate and should be skipped,
            False if it's new and should be delivered
        """
        dedup_key = generate_dedup_key(notification)

        # Get TTL from policy or use default
        policy_registry = get_policy_registry()
        ttl_seconds = policy_registry.get_dedup_window(notification.notification_type)

        # Try to set the key - if it fails, key exists (duplicate)
        key_was_set = self.store.set_if_not_exists(dedup_key, ttl_seconds)

        if not key_was_set:
            logger.info(
                "Notification deduplicated: notification_id=%s, dedup_key=%s",
                notification.notification_id,
                dedup_key,
            )
            return True

        return False

    def is_duplicate(self, notification: Notification) -> bool:
        """Check if notification is a duplicate without recording it.

        This is a read-only check that doesn't modify the store.
        Useful for checking status without affecting deduplication.

        Args:
            notification: The notification to check

        Returns:
            True if notification would be deduplicated
        """
        dedup_key = generate_dedup_key(notification)
        return self.store.exists(dedup_key)

    def clear_dedup(self, notification: Notification) -> bool:
        """Clear deduplication record for a notification.

        This allows a previously deduplicated notification to be
        reprocessed. Use with caution.

        Args:
            notification: The notification to clear

        Returns:
            True if a record was cleared, False if none existed
        """
        dedup_key = generate_dedup_key(notification)
        return self.store.delete(dedup_key)


# Global deduplication engine instance
_dedup_engine: DeduplicationEngine | None = None


def get_deduplication_engine() -> DeduplicationEngine:
    """Get the global deduplication engine instance.

    Returns:
        The singleton DeduplicationEngine instance
    """
    global _dedup_engine
    if _dedup_engine is None:
        _dedup_engine = DeduplicationEngine()
    return _dedup_engine


def configure_deduplication_engine(
    store: DeduplicationStore | None = None,
) -> DeduplicationEngine:
    """Configure the global deduplication engine.

    Args:
        store: Custom store to use, or None to use in-memory default

    Returns:
        The configured DeduplicationEngine instance
    """
    global _dedup_engine
    _dedup_engine = DeduplicationEngine(
        store=store if store is not None else InMemoryDeduplicationStore()
    )
    return _dedup_engine


def should_deduplicate(notification: Notification) -> bool:
    """Check if notification should be deduplicated.

    This is the primary interface as specified in the PRD.

    Args:
        notification: The notification to check

    Returns:
        True if notification is a duplicate and should be skipped
    """
    return get_deduplication_engine().should_deduplicate(notification)

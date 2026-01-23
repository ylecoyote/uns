"""Deduplication Engine for the Unified Notification Service.

This module provides at-most-once semantic delivery per dedup key within a configurable window.
It uses Redis SETNX (SET if Not eXists) + TTL for efficient distributed deduplication.

The deduplication check is the first step in the delivery pipeline,
preventing duplicate notifications from being processed.

Per PRD Task 4:
- should_deduplicate(notification) -> bool
- Redis SETNX + TTL behavior
- Second notification with same key within TTL deduplicates
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, Any
import logging
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from notification.models import Notification

logger = logging.getLogger(__name__)

# Default deduplication window in seconds (5 minutes)
DEFAULT_DEDUP_WINDOW_SECONDS = 300

# Redis key prefix for deduplication
DEDUP_KEY_PREFIX = "uns:dedup:"


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


class RedisClientProtocol(Protocol):
    """Protocol for Redis client operations needed by DeduplicationEngine."""

    def set(
        self,
        name: str,
        value: str | bytes,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        ...

    def exists(self, *names: str) -> int:
        ...

    def delete(self, *names: str) -> int:
        ...

    def ttl(self, name: str) -> int:
        ...


class RedisDeduplicationStore(DeduplicationStore):
    """Redis-backed deduplication store for production use.

    Uses Redis SETNX with TTL for atomic set-if-not-exists with
    automatic expiration. This provides distributed deduplication
    across multiple service instances.
    """

    def __init__(self, redis_client: RedisClientProtocol, key_prefix: str = DEDUP_KEY_PREFIX):
        """Initialize store.

        Args:
            redis_client: Redis client
            key_prefix: string prefix for dedup keys
        """
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _make_redis_key(self, dedup_key: str) -> str:
        return f"{self._key_prefix}{dedup_key}"

    def set_if_not_exists(self, key: str, ttl_seconds: int) -> bool:
        redis_key = self._make_redis_key(key)
        result = self._redis.set(redis_key, "1", ex=ttl_seconds, nx=True)
        return result is True

    def exists(self, key: str) -> bool:
        redis_key = self._make_redis_key(key)
        return self._redis.exists(redis_key) > 0

    def delete(self, key: str) -> bool:
        redis_key = self._make_redis_key(key)
        return self._redis.delete(redis_key) > 0

    def ttl(self, key: str) -> int:
        redis_key = self._make_redis_key(key)
        return self._redis.ttl(redis_key)

class DeduplicationEngine:
    """
    Engine for checking and recording notification deduplication.

    This is the main interface for the delivery service to use
    for deduplication checks.
    """

    def __init__(
        self,
        strategy: "DeduplicationStrategy" = None,
        default_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
        store: "DeduplicationStrategy" = None,  # Alias for strategy
    ):
        """Initialize the deduplication engine.

        Args:
            strategy: The deduplication strategy to use
            default_window_seconds: Default deduplication window in seconds
            store: Alias for strategy (for compatibility)
        """
        self._strategy = strategy or store or InMemoryDeduplicationStrategy()
        self._default_window_seconds = default_window_seconds

    @property
    def store(self) -> "DeduplicationStrategy":
        """Return the strategy (alias for store compatibility)."""
        return self._strategy

    @staticmethod
    def generate_dedup_key(notification: "Notification") -> str:
        """Generate a stable deduplication key for a notification.

        If the notification has an explicit dedup_key, use it.
        Otherwise, generate one from notification properties that
        should be stable across duplicate submissions.

        Args:
            notification: The notification to generate a key for

        Returns:
            A stable deduplication key
        """
        if hasattr(notification, "dedup_key") and notification.dedup_key:
            return notification.dedup_key

        key_parts = [
            getattr(notification, "notification_type", ""),
            # Support for .intent as optional (may not be present in all heads)
            getattr(getattr(notification, "intent", None), "value", ""),
            str(getattr(getattr(notification, "autonomy_context", None), "agent_id", "")),
            getattr(notification, "source", ""),
            getattr(notification, "title", ""),
        ]
        # Optionally add .correlation_id if it exists
        correlation_id = getattr(notification, "correlation_id", None)
        if correlation_id:
            key_parts.append(correlation_id)

        # Remove empty fields for compatibility if optional fields were missing
        key_parts = [part for part in key_parts if part]
        key_string = "|".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:32]

        # Use notification_type as prefix if available, else "notification"
        prefix = getattr(notification, "notification_type", "notification")
        return f"{prefix}:{key_hash}"

    def should_deduplicate(
        self,
        notification: "Notification",
        window_seconds: int = None,
    ) -> bool:
        """Check if a notification should be deduplicated.

        This method performs an atomic check-and-mark operation:
        1. Generate the dedup key for the notification
        2. Try to mark it as seen (SETNX behavior)
        3. If marking fails (key exists), return True (deduplicate)
        4. If marking succeeds (key was new), return False (proceed)

        Args:
            notification: The notification to check
            window_seconds: Optional custom deduplication window

        Returns:
            True if the notification should be skipped (duplicate),
            False if it should be delivered (new)
        """
        window = window_seconds if window_seconds is not None else self._default_window_seconds
        dedup_key = self.generate_dedup_key(notification)

        was_new = self._strategy.mark_seen(dedup_key, window)

        if not was_new:
            logger.info(
                "Deduplicating notification",
                extra={
                    "notification_id": str(getattr(notification, "notification_id", "")),
                    "dedup_key": dedup_key,
                    "notification_type": getattr(notification, "notification_type", ""),
                },
            )
            return True

        logger.debug(
            "Notification passed deduplication check",
            extra={
                "notification_id": str(getattr(notification, "notification_id", "")),
                "dedup_key": dedup_key,
            },
        )
        return False

    def is_duplicate(
        self,
        notification: "Notification",
        window_seconds: int = None,
    ) -> bool:
        """Check if a notification is a duplicate WITHOUT marking it.

        Use this for read-only checks. For delivery flow, use should_deduplicate().

        Args:
            notification: The notification to check
            window_seconds: Deduplication window (unused, for interface consistency)

        Returns:
            True if the notification is a duplicate, False otherwise
        """
        window = window_seconds if window_seconds is not None else self._default_window_seconds
        dedup_key = self.generate_dedup_key(notification)
        return self._strategy.is_duplicate(dedup_key, window)

    def clear_dedup_key(self, notification: "Notification") -> bool:
        """Clear the deduplication key for a notification.

        Useful for testing or administrative purposes.

        Args:
            notification: The notification whose dedup key should be cleared

        Returns:
            True if the key was cleared, False if it didn't exist
        """
        dedup_key = self.generate_dedup_key(notification)
        return self._strategy.clear(dedup_key)

    # Alias for compatibility
    def clear_dedup(self, notification: "Notification") -> bool:
        """Alias for clear_dedup_key for compatibility."""
        return self.clear_dedup_key(notification)

    @property
    def default_window_seconds(self) -> int:
        """Get the default deduplication window in seconds."""
        return self._default_window_seconds


def create_redis_deduplication_engine(
    redis_client: "RedisClientProtocol",
    default_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
    key_prefix: str = DEDUP_KEY_PREFIX,
) -> DeduplicationEngine:
    """Factory function to create a Redis-backed deduplication engine.

    Args:
        redis_client: A Redis client
        default_window_seconds: Default deduplication window in seconds
        key_prefix: Prefix for Redis keys

    Returns:
        A configured DeduplicationEngine with Redis strategy
    """
    strategy = RedisDeduplicationStrategy(redis_client, key_prefix)
    return DeduplicationEngine(strategy, default_window_seconds)


def create_inmemory_deduplication_engine(
    default_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
) -> DeduplicationEngine:
    """Factory function to create an in-memory deduplication engine.

    WARNING: Only use for testing or single-instance deployments.

    Args:
        default_window_seconds: Default deduplication window in seconds

    Returns:
        A configured DeduplicationEngine with in-memory strategy
    """
    strategy = InMemoryDeduplicationStrategy()
    return DeduplicationEngine(strategy, default_window_seconds)


# Module-level function as specified in PRD
def generate_dedup_key(notification: "Notification") -> str:
    """Generate a stable dedup key for a notification.

    This is the module-level function as specified in the PRD.
    Delegates to DeduplicationEngine.generate_dedup_key for DRYness.

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

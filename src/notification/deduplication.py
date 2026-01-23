"""Deduplication Engine for the Unified Notification Service.

This module provides at-most-once semantic delivery per dedup key within a configurable window.
Uses Redis SETNX (SET if Not eXists) + TTL for efficient distributed deduplication.

Per PRD Task 4:
- should_deduplicate(notification) -> bool
- Redis SETNX + TTL behavior
- Second notification with same key within TTL deduplicates
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from notification.models import Notification

logger = logging.getLogger(__name__)

# Default deduplication window in seconds (5 minutes)
DEFAULT_DEDUP_WINDOW_SECONDS = 300

# Redis key prefix for deduplication
DEDUP_KEY_PREFIX = "uns:dedup:"


class RedisClientProtocol(Protocol):
    """Protocol for Redis client operations needed by DeduplicationEngine."""

    def set(
        self,
        name: str,
        value: str | bytes,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        """Set key to value with optional expiry and NX flag.

        Args:
            name: The key name
            value: The value to set
            ex: Expire time in seconds
            nx: Only set if key does not exist (SETNX behavior)

        Returns:
            True if the key was set, None if NX was specified and key exists
        """
        ...

    def exists(self, *names: str) -> int:
        """Check if key(s) exist.

        Args:
            names: Key names to check

        Returns:
            Number of keys that exist
        """
        ...

    def delete(self, *names: str) -> int:
        """Delete key(s).

        Args:
            names: Key names to delete

        Returns:
            Number of keys deleted
        """
        ...

    def ttl(self, name: str) -> int:
        """Get the time to live for a key.

        Args:
            name: The key name

        Returns:
            TTL in seconds, -1 if no TTL, -2 if key doesn't exist
        """
        ...


class DeduplicationStrategy(ABC):
    """Abstract base class for deduplication strategies."""

    @abstractmethod
    def is_duplicate(self, dedup_key: str, window_seconds: int) -> bool:
        """Check if a notification with the given key is a duplicate.

        Args:
            dedup_key: The deduplication key
            window_seconds: The deduplication window in seconds

        Returns:
            True if this is a duplicate (should be deduplicated), False otherwise
        """
        ...

    @abstractmethod
    def mark_seen(self, dedup_key: str, window_seconds: int) -> bool:
        """Mark a deduplication key as seen.

        Args:
            dedup_key: The deduplication key
            window_seconds: The TTL for the deduplication record

        Returns:
            True if successfully marked, False if already exists
        """
        ...

    @abstractmethod
    def clear(self, dedup_key: str) -> bool:
        """Clear a deduplication key (for testing or administrative purposes).

        Args:
            dedup_key: The deduplication key to clear

        Returns:
            True if the key was cleared, False if it didn't exist
        """
        ...


# Alias for compatibility with Task 7 code
DeduplicationStore = DeduplicationStrategy


class RedisDeduplicationStrategy(DeduplicationStrategy):
    """Redis-backed deduplication using SETNX + TTL.

    This strategy uses Redis's atomic SETNX (SET if Not eXists) operation
    combined with TTL to provide distributed deduplication with automatic
    expiration of deduplication records.
    """

    def __init__(self, redis_client: RedisClientProtocol, key_prefix: str = DEDUP_KEY_PREFIX):
        """Initialize the Redis deduplication strategy.

        Args:
            redis_client: A Redis client implementing RedisClientProtocol
            key_prefix: Prefix for all deduplication keys in Redis
        """
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _make_redis_key(self, dedup_key: str) -> str:
        """Create the full Redis key from a dedup key."""
        return f"{self._key_prefix}{dedup_key}"

    def is_duplicate(self, dedup_key: str, window_seconds: int) -> bool:
        """Check if a notification with the given key is a duplicate.

        Uses Redis EXISTS to check if the key already exists.

        Args:
            dedup_key: The deduplication key
            window_seconds: The deduplication window (unused for EXISTS check)

        Returns:
            True if this is a duplicate (key exists), False otherwise
        """
        redis_key = self._make_redis_key(dedup_key)
        return self._redis.exists(redis_key) > 0

    def mark_seen(self, dedup_key: str, window_seconds: int) -> bool:
        """Mark a deduplication key as seen using SETNX + TTL.

        This is an atomic operation - the key is only set if it doesn't exist,
        and the TTL is set in the same operation.

        Args:
            dedup_key: The deduplication key
            window_seconds: The TTL for the deduplication record

        Returns:
            True if successfully marked (key was new), False if already exists
        """
        redis_key = self._make_redis_key(dedup_key)
        # Use SET with NX (SETNX) and EX (expire) for atomic operation
        result = self._redis.set(redis_key, "1", ex=window_seconds, nx=True)
        return result is True

    def clear(self, dedup_key: str) -> bool:
        """Clear a deduplication key.

        Args:
            dedup_key: The deduplication key to clear

        Returns:
            True if the key was cleared, False if it didn't exist
        """
        redis_key = self._make_redis_key(dedup_key)
        return self._redis.delete(redis_key) > 0

    def get_ttl(self, dedup_key: str) -> int:
        """Get the remaining TTL for a deduplication key.

        Args:
            dedup_key: The deduplication key

        Returns:
            TTL in seconds, -1 if no TTL, -2 if key doesn't exist
        """
        redis_key = self._make_redis_key(dedup_key)
        return self._redis.ttl(redis_key)

    # Compatibility methods for DeduplicationStore interface
    def set_if_not_exists(self, key: str, ttl_seconds: int) -> bool:
        """Alias for mark_seen for Store interface compatibility."""
        return self.mark_seen(key, ttl_seconds)

    def exists(self, key: str) -> bool:
        """Check if key exists (Store interface compatibility)."""
        return self.is_duplicate(key, 0)

    def delete(self, key: str) -> bool:
        """Delete a key (Store interface compatibility)."""
        return self.clear(key)


class InMemoryDeduplicationStrategy(DeduplicationStrategy):
    """In-memory deduplication for testing and single-instance deployments.

    WARNING: This strategy is NOT suitable for distributed deployments.
    Use RedisDeduplicationStrategy for production multi-instance deployments.
    """

    def __init__(self) -> None:
        """Initialize the in-memory deduplication strategy."""
        self._seen: dict[str, float] = {}  # key -> expiry timestamp

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        import time

        now = time.time()
        expired = [k for k, v in self._seen.items() if v <= now]
        for k in expired:
            del self._seen[k]

    def is_duplicate(self, dedup_key: str, window_seconds: int) -> bool:
        """Check if a notification with the given key is a duplicate."""
        import time

        self._cleanup_expired()
        if dedup_key in self._seen:
            return self._seen[dedup_key] > time.time()
        return False

    def mark_seen(self, dedup_key: str, window_seconds: int) -> bool:
        """Mark a deduplication key as seen."""
        import time

        self._cleanup_expired()
        if dedup_key in self._seen and self._seen[dedup_key] > time.time():
            return False
        self._seen[dedup_key] = time.time() + window_seconds
        return True

    def clear(self, dedup_key: str) -> bool:
        """Clear a deduplication key."""
        if dedup_key in self._seen:
            del self._seen[dedup_key]
            return True
        return False

    # Compatibility methods for DeduplicationStore interface
    def set_if_not_exists(self, key: str, ttl_seconds: int) -> bool:
        """Alias for mark_seen for Store interface compatibility."""
        return self.mark_seen(key, ttl_seconds)

    def exists(self, key: str) -> bool:
        """Check if key exists (Store interface compatibility)."""
        return self.is_duplicate(key, 0)

    def delete(self, key: str) -> bool:
        """Delete a key (Store interface compatibility)."""
        return self.clear(key)


# Aliases for compatibility with Task 7 code
InMemoryDeduplicationStore = InMemoryDeduplicationStrategy
RedisDeduplicationStore = RedisDeduplicationStrategy


class DeduplicationEngine:
    """Main deduplication engine for the Unified Notification Service.

    Provides at-most-once delivery semantics per dedup key within a configurable window.

    Usage:
        # With Redis
        redis_client = redis.Redis(...)
        engine = DeduplicationEngine(RedisDeduplicationStrategy(redis_client))

        # Check and mark in one atomic operation
        if engine.should_deduplicate(notification):
            # Skip delivery - this is a duplicate
            return
        # Proceed with delivery
    """

    def __init__(
        self,
        strategy: DeduplicationStrategy | None = None,
        default_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
        store: DeduplicationStrategy | None = None,  # Alias for strategy
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
    def store(self) -> DeduplicationStrategy:
        """Return the strategy (alias for store compatibility)."""
        return self._strategy

    @staticmethod
    def generate_dedup_key(notification: Notification) -> str:
        """Generate a stable deduplication key for a notification.

        If the notification has an explicit dedup_key, use that.
        Otherwise, generate one from notification_type + source + agent_id + title.

        Args:
            notification: The notification to generate a key for

        Returns:
            A stable deduplication key
        """
        # Use explicit dedup_key if provided
        if notification.dedup_key:
            return notification.dedup_key

        # Generate key from stable fields
        key_parts = [
            notification.notification_type,
            notification.source,
            str(notification.autonomy_context.agent_id),
            notification.title,
        ]
        key_string = "|".join(key_parts)

        # Hash for consistent length and to handle special characters
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    def should_deduplicate(
        self,
        notification: Notification,
        window_seconds: int | None = None,
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

        # Try to mark as seen - if it fails, this is a duplicate
        was_new = self._strategy.mark_seen(dedup_key, window)

        if not was_new:
            logger.info(
                "Deduplicating notification",
                extra={
                    "notification_id": str(notification.notification_id),
                    "dedup_key": dedup_key,
                    "notification_type": notification.notification_type,
                },
            )
            return True

        logger.debug(
            "Notification passed deduplication check",
            extra={
                "notification_id": str(notification.notification_id),
                "dedup_key": dedup_key,
            },
        )
        return False

    def is_duplicate(
        self,
        notification: Notification,
        window_seconds: int | None = None,
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

    def clear_dedup_key(self, notification: Notification) -> bool:
        """Clear the deduplication key for a notification.

        Useful for testing or administrative purposes.

        Args:
            notification: The notification whose dedup key should be cleared

        Returns:
            True if the key was cleared, False if it didn't exist
        """
        dedup_key = self.generate_dedup_key(notification)
        return self._strategy.clear(dedup_key)

    # Alias for compatibility with Task 7 code
    def clear_dedup(self, notification: Notification) -> bool:
        """Alias for clear_dedup_key for compatibility."""
        return self.clear_dedup_key(notification)

    @property
    def default_window_seconds(self) -> int:
        """Get the default deduplication window in seconds."""
        return self._default_window_seconds


def create_redis_deduplication_engine(
    redis_client: RedisClientProtocol,
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
def generate_dedup_key(notification: Notification) -> str:
    """Generate a stable dedup key for a notification.

    This is the module-level function as specified in the PRD.

    Args:
        notification: The notification to generate key for

    Returns:
        A stable dedup key string
    """
    return DeduplicationEngine.generate_dedup_key(notification)


# Global deduplication engine instance for convenience
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
    store: DeduplicationStrategy | None = None,
) -> DeduplicationEngine:
    """Configure the global deduplication engine.

    Args:
        store: Custom strategy to use, or None to use in-memory default

    Returns:
        The configured DeduplicationEngine instance
    """
    global _dedup_engine
    _dedup_engine = DeduplicationEngine(
        strategy=store if store is not None else InMemoryDeduplicationStrategy()
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

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
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol

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
        # Check if key exists and is not expired
        if key in self._keys:
            if key in self._expiry and time.time() < self._expiry[key]:
                return False
            # Key expired, remove it
            self._keys.discard(key)
            self._expiry.pop(key, None)

        self._keys.add(key)
        self._expiry[key] = time.time() + ttl_seconds
        return True

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        if key not in self._keys:
            return False
        if key in self._expiry and time.time() >= self._expiry[key]:
            # Key expired
            self._keys.discard(key)
            self._expiry.pop(key, None)
            return False
        return True

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


class DeduplicationStrategy(ABC):
    """Abstract strategy interface for deduplication.

    This is an alternative interface to DeduplicationStore that uses
    mark_seen/is_duplicate semantics instead of set_if_not_exists/exists.
    """

    @abstractmethod
    def mark_seen(self, key: str, ttl_seconds: int) -> bool:
        """Mark a key as seen.

        Args:
            key: The dedup key
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if key was new (not a duplicate), False if already seen
        """
        ...

    @abstractmethod
    def is_duplicate(self, key: str, ttl_seconds: int) -> bool:
        """Check if a key is a duplicate without marking it.

        Args:
            key: The dedup key
            ttl_seconds: TTL for consistency (may not be used)

        Returns:
            True if key exists (duplicate), False if not seen
        """
        ...

    @abstractmethod
    def clear(self, key: str) -> bool:
        """Clear a key from the store.

        Args:
            key: The dedup key

        Returns:
            True if key was cleared, False if not found
        """
        ...


class InMemoryDeduplicationStrategy(DeduplicationStrategy):
    """In-memory deduplication strategy for testing.

    Wraps InMemoryDeduplicationStore with the strategy interface.
    """

    def __init__(self) -> None:
        self._store = InMemoryDeduplicationStore()

    def mark_seen(self, key: str, ttl_seconds: int) -> bool:
        return self._store.set_if_not_exists(key, ttl_seconds)

    def is_duplicate(self, key: str, ttl_seconds: int) -> bool:
        return self._store.exists(key)

    def clear(self, key: str) -> bool:
        return self._store.delete(key)

    def clear_all(self) -> None:
        """Clear all keys (for testing)."""
        self._store.clear()


class RedisDeduplicationStrategy(DeduplicationStrategy):
    """Redis-backed deduplication strategy for production.

    Wraps RedisDeduplicationStore with the strategy interface.
    """

    def __init__(
        self,
        redis_client: RedisClientProtocol,
        key_prefix: str = DEDUP_KEY_PREFIX,
    ):
        self._store = RedisDeduplicationStore(redis_client, key_prefix)

    def mark_seen(self, key: str, ttl_seconds: int) -> bool:
        return self._store.set_if_not_exists(key, ttl_seconds)

    def is_duplicate(self, key: str, ttl_seconds: int) -> bool:
        return self._store.exists(key)

    def clear(self, key: str) -> bool:
        return self._store.delete(key)

    def _make_redis_key(self, dedup_key: str) -> str:
        """Expose internal key construction for testing."""
        return self._store._make_redis_key(dedup_key)

    def get_ttl(self, key: str) -> int:
        """Get TTL for a key."""
        return self._store.ttl(key)


class DeduplicationEngine:
    """Engine for checking and recording notification deduplication.

    This is the main interface for the delivery service to use
    for deduplication checks.
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

        If the notification has an explicit dedup_key, use it.
        Otherwise, generate one from notification properties that
        should be stable across duplicate submissions.

        Key is generated from:
        - notification_type
        - agent_id (from autonomy_context)
        - source
        - title

        Note: intent is NOT included because the same notification content
        should deduplicate regardless of intent classification.

        Args:
            notification: The notification to generate a key for

        Returns:
            A stable deduplication key (32-char hash)
        """
        if hasattr(notification, "dedup_key") and notification.dedup_key:
            return notification.dedup_key

        key_parts = [
            getattr(notification, "notification_type", ""),
            str(getattr(getattr(notification, "autonomy_context", None), "agent_id", "")),
            getattr(notification, "source", ""),
            getattr(notification, "title", ""),
        ]
        correlation_id = getattr(notification, "correlation_id", None)
        if correlation_id:
            key_parts.append(correlation_id)

        key_parts = [part for part in key_parts if part]
        key_string = "|".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:32]

        return key_hash

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


def generate_dedup_key(notification: Notification) -> str:
    """Generate a stable dedup key for a notification.

    This is the module-level function as specified in the PRD.
    Delegates to DeduplicationEngine.generate_dedup_key for DRYness.

    Args:
        notification: The notification to generate key for

    Returns:
        A stable dedup key string
    """
    return DeduplicationEngine.generate_dedup_key(notification)


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


class StoreToStrategyAdapter(DeduplicationStrategy):
    """Adapter to use a DeduplicationStore as a DeduplicationStrategy."""

    def __init__(self, store: DeduplicationStore):
        self._store = store

    def mark_seen(self, key: str, ttl_seconds: int) -> bool:
        return self._store.set_if_not_exists(key, ttl_seconds)

    def is_duplicate(self, key: str, ttl_seconds: int) -> bool:
        return self._store.exists(key)

    def clear(self, key: str) -> bool:
        return self._store.delete(key)


def configure_deduplication_engine(
    store: DeduplicationStore | DeduplicationStrategy | None = None,
    strategy: DeduplicationStrategy | None = None,
    default_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
) -> DeduplicationEngine:
    """Configure the global deduplication engine.

    Args:
        store: Custom store or strategy to use (alias for strategy)
        strategy: Custom strategy to use
        default_window_seconds: Default deduplication window

    Returns:
        The configured DeduplicationEngine instance
    """
    global _dedup_engine

    # Determine the strategy to use
    effective_strategy: DeduplicationStrategy
    if strategy is not None:
        effective_strategy = strategy
    elif store is not None:
        # Check if it's already a strategy
        if isinstance(store, DeduplicationStrategy):
            effective_strategy = store
        else:
            # Wrap the store in an adapter
            effective_strategy = StoreToStrategyAdapter(store)
    else:
        effective_strategy = InMemoryDeduplicationStrategy()

    _dedup_engine = DeduplicationEngine(
        strategy=effective_strategy,
        default_window_seconds=default_window_seconds,
    )
    return _dedup_engine


def reset_deduplication_engine() -> None:
    """Reset the global deduplication engine (for testing)."""
    global _dedup_engine
    _dedup_engine = None


def should_deduplicate(
    notification: Notification,
    window_seconds: int | None = None,
) -> bool:
    """Check if notification should be deduplicated.

    This is the primary interface as specified in the PRD.

    Args:
        notification: The notification to check
        window_seconds: Optional custom deduplication window

    Returns:
        True if notification is a duplicate and should be skipped
    """
    return get_deduplication_engine().should_deduplicate(notification, window_seconds)

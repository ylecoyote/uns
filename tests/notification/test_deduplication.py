"""Unit tests for the Deduplication Engine.

Tests cover:
- Redis SETNX + TTL behavior
- Second notification with same key within TTL deduplicates
- Dedup key generation (explicit vs generated)
- In-memory strategy for testing
- Edge cases and invariants
"""

import time
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.notification.deduplication import (
    DEDUP_KEY_PREFIX,
    DEFAULT_DEDUP_WINDOW_SECONDS,
    DeduplicationEngine,
    InMemoryDeduplicationStrategy,
    RedisDeduplicationStrategy,
    create_inmemory_deduplication_engine,
    create_redis_deduplication_engine,
)
from src.notification.models import (
    AutonomyContext,
    AutonomyMode,
    Notification,
    NotificationIntent,
)


# Test fixtures
@pytest.fixture
def autonomy_context() -> AutonomyContext:
    """Create a test autonomy context."""
    return AutonomyContext(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id=uuid4(),
    )


@pytest.fixture
def sample_notification(autonomy_context: AutonomyContext) -> Notification:
    """Create a sample notification for testing."""
    return Notification(
        notification_type="test.notification",
        intent=NotificationIntent.OPERATIONAL,
        autonomy_context=autonomy_context,
        title="Test Notification",
        message="This is a test notification message.",
        source="test-suite",
    )


@pytest.fixture
def notification_with_dedup_key(autonomy_context: AutonomyContext) -> Notification:
    """Create a notification with an explicit dedup_key."""
    return Notification(
        notification_type="test.notification",
        intent=NotificationIntent.OPERATIONAL,
        autonomy_context=autonomy_context,
        title="Test Notification",
        message="This is a test notification message.",
        source="test-suite",
        dedup_key="explicit-dedup-key-123",
    )


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.set.return_value = True
    client.exists.return_value = 0
    client.delete.return_value = 1
    client.ttl.return_value = 300
    return client


@pytest.fixture
def inmemory_engine() -> DeduplicationEngine:
    """Create an in-memory deduplication engine for testing."""
    return create_inmemory_deduplication_engine()


class TestRedisDeduplicationStrategy:
    """Tests for Redis-backed deduplication strategy."""

    def test_make_redis_key(self, mock_redis_client):
        """Test Redis key generation includes prefix."""
        strategy = RedisDeduplicationStrategy(mock_redis_client)
        key = strategy._make_redis_key("test-key")
        assert key == f"{DEDUP_KEY_PREFIX}test-key"

    def test_make_redis_key_custom_prefix(self, mock_redis_client):
        """Test Redis key generation with custom prefix."""
        strategy = RedisDeduplicationStrategy(mock_redis_client, key_prefix="custom:")
        key = strategy._make_redis_key("test-key")
        assert key == "custom:test-key"

    def test_mark_seen_uses_setnx_with_ttl(self, mock_redis_client):
        """Test that mark_seen uses SET with NX and EX flags."""
        strategy = RedisDeduplicationStrategy(mock_redis_client)
        strategy.mark_seen("test-key", 300)

        mock_redis_client.set.assert_called_once_with(
            f"{DEDUP_KEY_PREFIX}test-key",
            "1",
            ex=300,
            nx=True,
        )

    def test_mark_seen_returns_true_when_new(self, mock_redis_client):
        """Test mark_seen returns True when key is new."""
        mock_redis_client.set.return_value = True
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.mark_seen("new-key", 300)
        assert result is True

    def test_mark_seen_returns_false_when_exists(self, mock_redis_client):
        """Test mark_seen returns False when key already exists."""
        mock_redis_client.set.return_value = None  # Redis returns None when NX fails
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.mark_seen("existing-key", 300)
        assert result is False

    def test_is_duplicate_checks_existence(self, mock_redis_client):
        """Test is_duplicate uses EXISTS command."""
        mock_redis_client.exists.return_value = 1
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.is_duplicate("test-key", 300)

        mock_redis_client.exists.assert_called_once_with(f"{DEDUP_KEY_PREFIX}test-key")
        assert result is True

    def test_is_duplicate_returns_false_when_not_exists(self, mock_redis_client):
        """Test is_duplicate returns False when key doesn't exist."""
        mock_redis_client.exists.return_value = 0
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.is_duplicate("test-key", 300)
        assert result is False

    def test_clear_deletes_key(self, mock_redis_client):
        """Test clear uses DELETE command."""
        mock_redis_client.delete.return_value = 1
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.clear("test-key")

        mock_redis_client.delete.assert_called_once_with(f"{DEDUP_KEY_PREFIX}test-key")
        assert result is True

    def test_clear_returns_false_when_not_exists(self, mock_redis_client):
        """Test clear returns False when key doesn't exist."""
        mock_redis_client.delete.return_value = 0
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.clear("nonexistent-key")
        assert result is False

    def test_get_ttl(self, mock_redis_client):
        """Test get_ttl retrieves TTL from Redis."""
        mock_redis_client.ttl.return_value = 250
        strategy = RedisDeduplicationStrategy(mock_redis_client)

        result = strategy.get_ttl("test-key")

        mock_redis_client.ttl.assert_called_once_with(f"{DEDUP_KEY_PREFIX}test-key")
        assert result == 250


class TestInMemoryDeduplicationStrategy:
    """Tests for in-memory deduplication strategy."""

    def test_mark_seen_new_key(self):
        """Test marking a new key as seen."""
        strategy = InMemoryDeduplicationStrategy()

        result = strategy.mark_seen("new-key", 300)
        assert result is True

    def test_mark_seen_existing_key(self):
        """Test marking an existing key as seen returns False."""
        strategy = InMemoryDeduplicationStrategy()
        strategy.mark_seen("existing-key", 300)

        result = strategy.mark_seen("existing-key", 300)
        assert result is False

    def test_is_duplicate_new_key(self):
        """Test is_duplicate returns False for new keys."""
        strategy = InMemoryDeduplicationStrategy()

        result = strategy.is_duplicate("new-key", 300)
        assert result is False

    def test_is_duplicate_existing_key(self):
        """Test is_duplicate returns True for existing keys."""
        strategy = InMemoryDeduplicationStrategy()
        strategy.mark_seen("existing-key", 300)

        result = strategy.is_duplicate("existing-key", 300)
        assert result is True

    def test_clear_existing_key(self):
        """Test clearing an existing key."""
        strategy = InMemoryDeduplicationStrategy()
        strategy.mark_seen("key-to-clear", 300)

        result = strategy.clear("key-to-clear")
        assert result is True
        assert strategy.is_duplicate("key-to-clear", 300) is False

    def test_clear_nonexistent_key(self):
        """Test clearing a nonexistent key returns False."""
        strategy = InMemoryDeduplicationStrategy()

        result = strategy.clear("nonexistent-key")
        assert result is False

    def test_expiry_cleanup(self):
        """Test that expired entries are cleaned up."""
        strategy = InMemoryDeduplicationStrategy()
        # Mark with very short TTL
        strategy.mark_seen("short-lived", 1)

        # Wait for expiry
        time.sleep(1.1)

        # Should be expired now
        assert strategy.is_duplicate("short-lived", 300) is False
        # Should be able to mark again
        assert strategy.mark_seen("short-lived", 300) is True


class TestDeduplicationEngine:
    """Tests for the main DeduplicationEngine."""

    def test_generate_dedup_key_uses_explicit_key(self, notification_with_dedup_key: Notification):
        """Test that explicit dedup_key is used when provided."""
        key = DeduplicationEngine.generate_dedup_key(notification_with_dedup_key)
        assert key == "explicit-dedup-key-123"

    def test_generate_dedup_key_generates_hash(self, sample_notification: Notification):
        """Test that a hash is generated when no explicit key."""
        key = DeduplicationEngine.generate_dedup_key(sample_notification)

        # Should be 32 character hex string (SHA256 truncated)
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    def test_generate_dedup_key_is_stable(self, autonomy_context: AutonomyContext):
        """Test that the same notification generates the same key."""
        notification1 = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title="Test Notification",
            message="Message content",
            source="test-suite",
        )
        notification2 = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title="Test Notification",
            message="Different message content",  # Different message
            source="test-suite",
        )

        key1 = DeduplicationEngine.generate_dedup_key(notification1)
        key2 = DeduplicationEngine.generate_dedup_key(notification2)

        # Same type, source, agent_id, title = same key
        assert key1 == key2

    def test_generate_dedup_key_different_for_different_titles(
        self, autonomy_context: AutonomyContext
    ):
        """Test that different titles generate different keys."""
        notification1 = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title="Title A",
            message="Message content",
            source="test-suite",
        )
        notification2 = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title="Title B",
            message="Message content",
            source="test-suite",
        )

        key1 = DeduplicationEngine.generate_dedup_key(notification1)
        key2 = DeduplicationEngine.generate_dedup_key(notification2)

        assert key1 != key2

    def test_should_deduplicate_first_notification(
        self, inmemory_engine: DeduplicationEngine, sample_notification: Notification
    ):
        """Test that first notification is NOT deduplicated."""
        result = inmemory_engine.should_deduplicate(sample_notification)
        assert result is False

    def test_should_deduplicate_second_notification(
        self, inmemory_engine: DeduplicationEngine, sample_notification: Notification
    ):
        """Test that second notification with same key IS deduplicated."""
        # First notification - should pass
        assert inmemory_engine.should_deduplicate(sample_notification) is False

        # Second notification - should be deduplicated
        assert inmemory_engine.should_deduplicate(sample_notification) is True

    def test_should_deduplicate_respects_window(self, autonomy_context: AutonomyContext):
        """Test that notifications are NOT deduplicated after window expires."""
        engine = create_inmemory_deduplication_engine(default_window_seconds=1)

        notification = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title="Test Notification",
            message="Message content",
            source="test-suite",
        )

        # First notification - should pass
        assert engine.should_deduplicate(notification) is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should NOT be deduplicated anymore
        assert engine.should_deduplicate(notification) is False

    def test_should_deduplicate_custom_window(
        self, inmemory_engine: DeduplicationEngine, sample_notification: Notification
    ):
        """Test using a custom window."""
        # Mark first with short window
        assert inmemory_engine.should_deduplicate(sample_notification, window_seconds=1) is False

        # Immediate second call should deduplicate
        assert inmemory_engine.should_deduplicate(sample_notification, window_seconds=1) is True

        # Wait and try again
        time.sleep(1.1)
        assert inmemory_engine.should_deduplicate(sample_notification, window_seconds=1) is False

    def test_is_duplicate_does_not_mark(
        self, inmemory_engine: DeduplicationEngine, sample_notification: Notification
    ):
        """Test that is_duplicate is read-only."""
        # Check - should be False (new)
        assert inmemory_engine.is_duplicate(sample_notification) is False

        # Check again - still False because we didn't mark
        assert inmemory_engine.is_duplicate(sample_notification) is False

        # Now mark it
        assert inmemory_engine.should_deduplicate(sample_notification) is False

        # Now is_duplicate should return True
        assert inmemory_engine.is_duplicate(sample_notification) is True

    def test_clear_dedup_key(
        self, inmemory_engine: DeduplicationEngine, sample_notification: Notification
    ):
        """Test clearing a deduplication key."""
        # Mark the notification
        assert inmemory_engine.should_deduplicate(sample_notification) is False

        # Should be a duplicate now
        assert inmemory_engine.is_duplicate(sample_notification) is True

        # Clear the key
        assert inmemory_engine.clear_dedup_key(sample_notification) is True

        # Should no longer be a duplicate
        assert inmemory_engine.is_duplicate(sample_notification) is False

    def test_default_window_seconds_property(self, inmemory_engine: DeduplicationEngine):
        """Test that default window seconds is accessible."""
        assert inmemory_engine.default_window_seconds == DEFAULT_DEDUP_WINDOW_SECONDS


class TestDeduplicationEngineWithMockRedis:
    """Tests for DeduplicationEngine with mock Redis."""

    def test_should_deduplicate_new_notification(
        self, mock_redis_client, sample_notification: Notification
    ):
        """Test deduplication with Redis for new notification."""
        mock_redis_client.set.return_value = True  # SETNX succeeds
        engine = create_redis_deduplication_engine(mock_redis_client)

        result = engine.should_deduplicate(sample_notification)

        assert result is False  # Not a duplicate
        mock_redis_client.set.assert_called_once()

    def test_should_deduplicate_existing_notification(
        self, mock_redis_client, sample_notification: Notification
    ):
        """Test deduplication with Redis for existing notification."""
        mock_redis_client.set.return_value = None  # SETNX fails (key exists)
        engine = create_redis_deduplication_engine(mock_redis_client)

        result = engine.should_deduplicate(sample_notification)

        assert result is True  # Is a duplicate

    def test_custom_window_passed_to_redis(
        self, mock_redis_client, sample_notification: Notification
    ):
        """Test that custom window is passed to Redis SET command."""
        mock_redis_client.set.return_value = True
        engine = create_redis_deduplication_engine(mock_redis_client)

        engine.should_deduplicate(sample_notification, window_seconds=600)

        # Verify TTL of 600 was passed
        call_args = mock_redis_client.set.call_args
        assert call_args.kwargs["ex"] == 600


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_inmemory_deduplication_engine(self):
        """Test in-memory engine factory."""
        engine = create_inmemory_deduplication_engine(default_window_seconds=120)

        assert isinstance(engine, DeduplicationEngine)
        assert engine.default_window_seconds == 120

    def test_create_redis_deduplication_engine(self, mock_redis_client):
        """Test Redis engine factory."""
        engine = create_redis_deduplication_engine(
            mock_redis_client, default_window_seconds=180, key_prefix="test:"
        )

        assert isinstance(engine, DeduplicationEngine)
        assert engine.default_window_seconds == 180


class TestDeduplicationInvariants:
    """Tests for PRD invariants and edge cases."""

    def test_dedup_key_consistency_across_sessions(self, autonomy_context: AutonomyContext):
        """Test that dedup keys are consistent across engine instances."""
        notification = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=autonomy_context,
            title="Test Notification",
            message="Message content",
            source="test-suite",
        )

        engine1 = create_inmemory_deduplication_engine()
        engine2 = create_inmemory_deduplication_engine()

        key1 = engine1.generate_dedup_key(notification)
        key2 = engine2.generate_dedup_key(notification)

        assert key1 == key2

    def test_different_intents_same_title_same_key(self, autonomy_context: AutonomyContext):
        """Test that intent doesn't affect dedup key (only type, source, agent, title)."""
        notification_safety = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.SAFETY,
            autonomy_context=autonomy_context,
            title="Same Title",
            message="Message content",
            source="test-suite",
        )
        notification_info = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_context=autonomy_context,
            title="Same Title",
            message="Message content",
            source="test-suite",
        )

        key_safety = DeduplicationEngine.generate_dedup_key(notification_safety)
        key_info = DeduplicationEngine.generate_dedup_key(notification_info)

        # Same key because type, source, agent_id, and title are the same
        assert key_safety == key_info

    def test_different_agents_different_keys(self):
        """Test that different agents generate different dedup keys."""
        context1 = AutonomyContext(autonomy_mode=AutonomyMode.LIVE, agent_id=uuid4())
        context2 = AutonomyContext(autonomy_mode=AutonomyMode.LIVE, agent_id=uuid4())

        notification1 = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=context1,
            title="Same Title",
            message="Message content",
            source="test-suite",
        )
        notification2 = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.OPERATIONAL,
            autonomy_context=context2,
            title="Same Title",
            message="Message content",
            source="test-suite",
        )

        key1 = DeduplicationEngine.generate_dedup_key(notification1)
        key2 = DeduplicationEngine.generate_dedup_key(notification2)

        assert key1 != key2

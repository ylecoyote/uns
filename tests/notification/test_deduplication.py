"""Unit tests for the deduplication module."""

from uuid import uuid4

import pytest

from notification.deduplication import (
    DeduplicationEngine,
    InMemoryDeduplicationStore,
    configure_deduplication_engine,
    generate_dedup_key,
    should_deduplicate,
)
from notification.models import (
    AutonomyContext,
    AutonomyMode,
    Notification,
    NotificationIntent,
)
from notification.policies import PolicyRegistry, configure_policy_registry


@pytest.fixture
def notification() -> Notification:
    """Create a test notification."""
    return Notification(
        notification_type="test.notification",
        intent=NotificationIntent.OPERATIONAL,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
        title="Test Notification",
        message="Test message",
        source="test-source",
    )


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test."""
    configure_deduplication_engine(InMemoryDeduplicationStore())
    configure_policy_registry(PolicyRegistry())


class TestInMemoryDeduplicationStore:
    """Tests for InMemoryDeduplicationStore."""

    def test_set_if_not_exists_new_key(self):
        """Test setting a new key succeeds."""
        store = InMemoryDeduplicationStore()
        result = store.set_if_not_exists("key1", ttl_seconds=300)
        assert result is True

    def test_set_if_not_exists_existing_key(self):
        """Test setting an existing key fails."""
        store = InMemoryDeduplicationStore()
        store.set_if_not_exists("key1", ttl_seconds=300)
        result = store.set_if_not_exists("key1", ttl_seconds=300)
        assert result is False

    def test_exists(self):
        """Test exists returns correct value."""
        store = InMemoryDeduplicationStore()
        assert store.exists("key1") is False
        store.set_if_not_exists("key1", ttl_seconds=300)
        assert store.exists("key1") is True

    def test_delete(self):
        """Test delete removes key."""
        store = InMemoryDeduplicationStore()
        store.set_if_not_exists("key1", ttl_seconds=300)
        assert store.delete("key1") is True
        assert store.exists("key1") is False

    def test_delete_nonexistent(self):
        """Test delete nonexistent key returns False."""
        store = InMemoryDeduplicationStore()
        assert store.delete("nonexistent") is False

    def test_clear(self):
        """Test clear removes all keys."""
        store = InMemoryDeduplicationStore()
        store.set_if_not_exists("key1", ttl_seconds=300)
        store.set_if_not_exists("key2", ttl_seconds=300)
        store.clear()
        assert store.exists("key1") is False
        assert store.exists("key2") is False


class TestGenerateDedupKey:
    """Tests for dedup key generation."""

    def test_explicit_dedup_key_used(self, notification: Notification):
        """Test explicit dedup_key is used if provided."""
        notification.dedup_key = "my-custom-key"
        key = generate_dedup_key(notification)
        assert key == "my-custom-key"

    def test_generated_key_is_stable(self, notification: Notification):
        """Test generated key is deterministic for same notification properties."""
        notification.dedup_key = None
        key1 = generate_dedup_key(notification)
        key2 = generate_dedup_key(notification)
        assert key1 == key2

    def test_different_properties_different_key(self, notification: Notification):
        """Test different notification properties produce different keys."""
        notification.dedup_key = None
        key1 = generate_dedup_key(notification)

        notification.title = "Different Title"
        key2 = generate_dedup_key(notification)

        assert key1 != key2

    def test_key_includes_notification_type(self, notification: Notification):
        """Test generated key includes notification type prefix."""
        notification.dedup_key = None
        key = generate_dedup_key(notification)
        assert key.startswith(notification.notification_type)

    def test_correlation_id_affects_key(self, notification: Notification):
        """Test correlation_id affects generated key."""
        notification.dedup_key = None
        notification.correlation_id = None
        key1 = generate_dedup_key(notification)

        notification.correlation_id = "corr-123"
        key2 = generate_dedup_key(notification)

        assert key1 != key2


class TestDeduplicationEngine:
    """Tests for DeduplicationEngine."""

    def test_should_deduplicate_first_time_false(self, notification: Notification):
        """Test first notification is not deduplicated."""
        engine = DeduplicationEngine()
        notification.dedup_key = "engine-test-key"

        result = engine.should_deduplicate(notification)
        assert result is False

    def test_should_deduplicate_second_time_true(self, notification: Notification):
        """Test second notification with same key is deduplicated."""
        engine = DeduplicationEngine()
        notification.dedup_key = "engine-test-key-2"

        engine.should_deduplicate(notification)
        result = engine.should_deduplicate(notification)
        assert result is True

    def test_is_duplicate_read_only(self, notification: Notification):
        """Test is_duplicate is read-only."""
        engine = DeduplicationEngine()
        notification.dedup_key = "read-only-test"

        # Check first - should be False
        assert engine.is_duplicate(notification) is False

        # should_deduplicate records the key
        engine.should_deduplicate(notification)

        # Now is_duplicate should be True
        assert engine.is_duplicate(notification) is True

    def test_clear_dedup(self, notification: Notification):
        """Test clearing dedup record."""
        engine = DeduplicationEngine()
        notification.dedup_key = "clear-test"

        # Record the notification
        engine.should_deduplicate(notification)
        assert engine.is_duplicate(notification) is True

        # Clear it
        result = engine.clear_dedup(notification)
        assert result is True
        assert engine.is_duplicate(notification) is False

    def test_clear_nonexistent(self, notification: Notification):
        """Test clearing nonexistent record."""
        engine = DeduplicationEngine()
        notification.dedup_key = "nonexistent-clear"

        result = engine.clear_dedup(notification)
        assert result is False


class TestGlobalFunctions:
    """Tests for global deduplication functions."""

    def test_should_deduplicate_global(self, notification: Notification):
        """Test global should_deduplicate function."""
        notification.dedup_key = "global-test"

        # First call should not deduplicate
        assert should_deduplicate(notification) is False

        # Second call should deduplicate
        assert should_deduplicate(notification) is True

    def test_configure_deduplication_engine(self, notification: Notification):
        """Test configuring global engine with custom store."""
        store = InMemoryDeduplicationStore()
        configure_deduplication_engine(store)

        notification.dedup_key = "configure-test"

        # Record via global function
        should_deduplicate(notification)

        # Verify key is in custom store
        assert store.exists(notification.dedup_key)

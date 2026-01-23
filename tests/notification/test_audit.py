"""Unit tests for the audit logging module.

Tests cover:
- AuditRecord creation and serialization
- AckAuditRecord creation and serialization
- InMemoryAuditStore operations
- PersistentAuditLogger behavior
- Error handling for audit persistence
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.audit import (
    AuditPersistenceError,
    InMemoryAuditStore,
    PersistentAuditLogger,
    create_ack_audit_record,
    create_audit_record,
)
from notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
)


@pytest.fixture
def sample_autonomy_context() -> AutonomyContext:
    """Create a sample autonomy context for testing."""
    return AutonomyContext(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id=uuid4(),
        plan_id=uuid4(),
        decision_snapshot_id=uuid4(),
    )


@pytest.fixture
def sample_notification(sample_autonomy_context: AutonomyContext) -> Notification:
    """Create a sample notification for testing."""
    return Notification(
        notification_type="test.notification",
        intent=NotificationIntent.SAFETY,
        delivery_mode=DeliveryMode.GUARANTEED,
        autonomy_context=sample_autonomy_context,
        title="Test Notification",
        message="This is a test notification message.",
        source="test-suite",
        correlation_id="corr-123",
        metadata={"key": "value"},
    )


@pytest.fixture
def sample_result(sample_notification: Notification) -> NotificationResult:
    """Create a sample notification result for testing."""
    return NotificationResult(
        notification_id=sample_notification.notification_id,
        status=DeliveryStatus.SUCCESS,
        channels_attempted=[Channel.SLACK, Channel.WEBSOCKET],
        channels_succeeded=[Channel.SLACK],
        channels_failed=[Channel.WEBSOCKET],
        error_message="WebSocket: Connection failed",
    )


class TestAuditRecord:
    """Tests for AuditRecord creation and serialization."""

    def test_create_audit_record(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test creating an audit record from notification and result."""
        record = create_audit_record(sample_notification, sample_result)

        assert record.notification_id == sample_notification.notification_id
        assert record.notification_type == sample_notification.notification_type
        assert record.status == sample_result.status
        assert record.channels_attempted == tuple(sample_result.channels_attempted)
        assert record.channels_succeeded == tuple(sample_result.channels_succeeded)
        assert record.channels_failed == tuple(sample_result.channels_failed)
        assert record.error_message == sample_result.error_message
        assert record.intent == sample_notification.intent.value
        assert record.delivery_mode == sample_notification.delivery_mode.value
        assert record.autonomy_mode == sample_notification.autonomy_context.autonomy_mode.value
        assert record.agent_id == sample_notification.autonomy_context.agent_id
        assert record.title == sample_notification.title
        assert record.source == sample_notification.source
        assert record.correlation_id == sample_notification.correlation_id
        assert record.metadata == sample_notification.metadata

    def test_create_audit_record_with_metadata(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test creating an audit record with additional metadata."""
        audit_metadata = {"reason": "deduplicated", "dedup_key": "test-key"}
        record = create_audit_record(sample_notification, sample_result, audit_metadata)

        assert record.audit_metadata == audit_metadata

    def test_create_audit_record_derives_delivery_mode(
        self,
        sample_autonomy_context: AutonomyContext,
    ) -> None:
        """Test that delivery mode is derived when not set on notification."""
        notification = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.SAFETY,
            delivery_mode=None,  # Not set
            autonomy_context=sample_autonomy_context,
            title="Test",
            message="Test message",
            source="test",
        )
        result = NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.SUCCESS,
        )

        record = create_audit_record(notification, result)

        # SAFETY intent should derive GUARANTEED delivery mode
        assert record.delivery_mode == DeliveryMode.GUARANTEED.value

    def test_audit_record_to_dict(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test converting audit record to dictionary."""
        record = create_audit_record(sample_notification, sample_result)
        record_dict = record.to_dict()

        assert record_dict["notification_id"] == str(record.notification_id)
        assert record_dict["status"] == record.status.value
        assert record_dict["channels_attempted"] == [c.value for c in record.channels_attempted]
        assert record_dict["channels_succeeded"] == [c.value for c in record.channels_succeeded]
        assert record_dict["channels_failed"] == [c.value for c in record.channels_failed]
        assert record_dict["intent"] == record.intent
        assert record_dict["delivery_mode"] == record.delivery_mode
        assert record_dict["autonomy_mode"] == record.autonomy_mode
        assert record_dict["agent_id"] == str(record.agent_id)

    def test_audit_record_is_immutable(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that audit records are immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        record = create_audit_record(sample_notification, sample_result)

        with pytest.raises(FrozenInstanceError):
            record.status = DeliveryStatus.FAILED  # type: ignore


class TestAckAuditRecord:
    """Tests for AckAuditRecord creation and serialization."""

    def test_create_ack_audit_record(self) -> None:
        """Test creating an ack audit record."""
        notification_id = uuid4()
        record = create_ack_audit_record(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
            acked_by="user@example.com",
            metadata={"comment": "Acknowledged"},
        )

        assert record.notification_id == notification_id
        assert record.old_status == AckStatus.PENDING
        assert record.new_status == AckStatus.ACKED
        assert record.acked_by == "user@example.com"
        assert record.metadata == {"comment": "Acknowledged"}
        assert record.acked_at is not None
        assert record.audit_created_at is not None

    def test_create_ack_audit_record_without_old_status(self) -> None:
        """Test creating an ack audit record for initial state."""
        notification_id = uuid4()
        record = create_ack_audit_record(
            notification_id=notification_id,
            old_status=None,  # Initial state
            new_status=AckStatus.PENDING,
        )

        assert record.old_status is None
        assert record.new_status == AckStatus.PENDING

    def test_ack_audit_record_to_dict(self) -> None:
        """Test converting ack audit record to dictionary."""
        notification_id = uuid4()
        record = create_ack_audit_record(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.TIMED_OUT,
        )
        record_dict = record.to_dict()

        assert record_dict["notification_id"] == str(notification_id)
        assert record_dict["old_status"] == AckStatus.PENDING.value
        assert record_dict["new_status"] == AckStatus.TIMED_OUT.value


class TestInMemoryAuditStore:
    """Tests for InMemoryAuditStore operations."""

    def test_save_and_retrieve_delivery_audit(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test saving and retrieving delivery audit records."""
        store = InMemoryAuditStore()
        record = create_audit_record(sample_notification, sample_result)

        store.save_delivery_audit(record)

        retrieved = store.get_delivery_audits_for_notification(
            sample_notification.notification_id
        )
        assert len(retrieved) == 1
        assert retrieved[0].audit_id == record.audit_id

    def test_save_and_retrieve_ack_audit(self) -> None:
        """Test saving and retrieving ack audit records."""
        store = InMemoryAuditStore()
        notification_id = uuid4()
        record = create_ack_audit_record(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )

        store.save_ack_audit(record)

        retrieved = store.get_ack_audits_for_notification(notification_id)
        assert len(retrieved) == 1
        assert retrieved[0].audit_id == record.audit_id

    def test_multiple_audits_ordered_by_created_at(
        self,
        sample_notification: Notification,
    ) -> None:
        """Test that multiple audits are returned in descending order."""
        store = InMemoryAuditStore()

        # Create multiple records
        for status in [DeliveryStatus.FAILED, DeliveryStatus.SUCCESS]:
            result = NotificationResult(
                notification_id=sample_notification.notification_id,
                status=status,
            )
            record = create_audit_record(sample_notification, result)
            store.save_delivery_audit(record)

        retrieved = store.get_delivery_audits_for_notification(
            sample_notification.notification_id
        )
        assert len(retrieved) == 2
        # Most recent should be first
        assert retrieved[0].audit_created_at >= retrieved[1].audit_created_at

    def test_clear_removes_all_records(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that clear removes all records."""
        store = InMemoryAuditStore()
        record = create_audit_record(sample_notification, sample_result)
        store.save_delivery_audit(record)

        store.clear()

        assert len(store.delivery_audits) == 0
        assert len(store.ack_audits) == 0

    def test_get_audits_for_nonexistent_notification(self) -> None:
        """Test retrieving audits for a notification that doesn't exist."""
        store = InMemoryAuditStore()
        random_id = uuid4()

        delivery_audits = store.get_delivery_audits_for_notification(random_id)
        ack_audits = store.get_ack_audits_for_notification(random_id)

        assert delivery_audits == []
        assert ack_audits == []


class TestPersistentAuditLogger:
    """Tests for PersistentAuditLogger behavior."""

    def test_log_delivery_saves_to_store(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that log_delivery saves record to the store."""
        store = InMemoryAuditStore()
        logger = PersistentAuditLogger(store=store)

        logger.log_delivery(sample_notification, sample_result)

        audits = store.get_delivery_audits_for_notification(
            sample_notification.notification_id
        )
        assert len(audits) == 1
        assert audits[0].status == sample_result.status

    def test_log_delivery_with_metadata(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that log_delivery includes additional metadata."""
        store = InMemoryAuditStore()
        logger = PersistentAuditLogger(store=store)
        metadata = {"reason": "test"}

        logger.log_delivery(sample_notification, sample_result, metadata)

        audits = store.get_delivery_audits_for_notification(
            sample_notification.notification_id
        )
        assert audits[0].audit_metadata == metadata

    def test_log_ack_saves_to_store(self) -> None:
        """Test that log_ack saves record to the store."""
        store = InMemoryAuditStore()
        logger = PersistentAuditLogger(store=store)
        notification_id = uuid4()

        logger.log_ack(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
            acked_by="user@test.com",
        )

        audits = store.get_ack_audits_for_notification(notification_id)
        assert len(audits) == 1
        assert audits[0].new_status == AckStatus.ACKED
        assert audits[0].acked_by == "user@test.com"

    def test_fail_silently_suppresses_persistence_error(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that fail_silently=True suppresses persistence errors."""
        failing_store = MagicMock()
        failing_store.save_delivery_audit.side_effect = AuditPersistenceError("Test error")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=True)

        # Should not raise
        logger.log_delivery(sample_notification, sample_result)

    def test_fail_silently_false_raises_persistence_error(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that fail_silently=False raises persistence errors."""
        failing_store = MagicMock()
        failing_store.save_delivery_audit.side_effect = AuditPersistenceError("Test error")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=False)

        with pytest.raises(AuditPersistenceError):
            logger.log_delivery(sample_notification, sample_result)

    def test_unexpected_error_wrapped_in_persistence_error(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that unexpected errors are wrapped in AuditPersistenceError."""
        failing_store = MagicMock()
        failing_store.save_delivery_audit.side_effect = RuntimeError("Unexpected")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=False)

        with pytest.raises(AuditPersistenceError) as exc_info:
            logger.log_delivery(sample_notification, sample_result)

        assert exc_info.value.original_error is not None


class TestAuditRecordOutcomes:
    """Tests for audit records with different delivery outcomes."""

    def test_successful_delivery_audit(
        self,
        sample_notification: Notification,
    ) -> None:
        """Test audit record for successful delivery."""
        result = NotificationResult(
            notification_id=sample_notification.notification_id,
            status=DeliveryStatus.SUCCESS,
            channels_attempted=[Channel.SLACK],
            channels_succeeded=[Channel.SLACK],
        )

        record = create_audit_record(sample_notification, result)

        assert record.status == DeliveryStatus.SUCCESS
        assert Channel.SLACK in record.channels_succeeded
        assert len(record.channels_failed) == 0

    def test_failed_delivery_audit(
        self,
        sample_notification: Notification,
    ) -> None:
        """Test audit record for failed delivery."""
        result = NotificationResult(
            notification_id=sample_notification.notification_id,
            status=DeliveryStatus.FAILED,
            channels_attempted=[Channel.SLACK, Channel.EMAIL],
            channels_failed=[Channel.SLACK, Channel.EMAIL],
            error_message="All channels failed",
        )

        record = create_audit_record(sample_notification, result)

        assert record.status == DeliveryStatus.FAILED
        assert len(record.channels_succeeded) == 0
        assert Channel.SLACK in record.channels_failed
        assert record.error_message == "All channels failed"

    def test_deduplicated_delivery_audit(
        self,
        sample_notification: Notification,
    ) -> None:
        """Test audit record for deduplicated delivery."""
        result = NotificationResult(
            notification_id=sample_notification.notification_id,
            status=DeliveryStatus.DEDUPLICATED,
        )

        record = create_audit_record(
            sample_notification,
            result,
            metadata={"reason": "deduplicated", "dedup_key": "test-key"},
        )

        assert record.status == DeliveryStatus.DEDUPLICATED
        assert record.audit_metadata["reason"] == "deduplicated"

    def test_rate_limited_delivery_audit(
        self,
        sample_notification: Notification,
    ) -> None:
        """Test audit record for rate-limited delivery."""
        result = NotificationResult(
            notification_id=sample_notification.notification_id,
            status=DeliveryStatus.RATE_LIMITED,
            channels_attempted=[Channel.SLACK],
            channels_failed=[Channel.SLACK],
            error_message="Rate limit exceeded",
        )

        record = create_audit_record(sample_notification, result)

        assert record.status == DeliveryStatus.RATE_LIMITED


class TestFileAuditStore:
    """Tests for FileAuditStore operations."""

    def test_save_delivery_audit_writes_to_file(
        self,
        tmp_path,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that delivery audit is written to file."""
        from notification.audit import FileAuditStore

        delivery_path = tmp_path / "delivery_audits.jsonl"
        ack_path = tmp_path / "ack_audits.jsonl"

        store = FileAuditStore(
            delivery_audit_path=str(delivery_path),
            ack_audit_path=str(ack_path),
        )
        record = create_audit_record(sample_notification, sample_result)

        store.save_delivery_audit(record)

        assert delivery_path.exists()
        content = delivery_path.read_text()
        assert str(record.notification_id) in content

    def test_save_ack_audit_writes_to_file(self, tmp_path) -> None:
        """Test that ack audit is written to file."""
        from notification.audit import FileAuditStore

        delivery_path = tmp_path / "delivery_audits.jsonl"
        ack_path = tmp_path / "ack_audits.jsonl"

        store = FileAuditStore(
            delivery_audit_path=str(delivery_path),
            ack_audit_path=str(ack_path),
        )
        notification_id = uuid4()
        record = create_ack_audit_record(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )

        store.save_ack_audit(record)

        assert ack_path.exists()
        content = ack_path.read_text()
        assert str(notification_id) in content

    def test_save_delivery_audit_raises_on_write_error(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that OS errors raise AuditPersistenceError."""
        from notification.audit import FileAuditStore

        # Use an invalid path
        store = FileAuditStore(
            delivery_audit_path="/nonexistent/path/audits.jsonl",
            ack_audit_path="/nonexistent/path/ack_audits.jsonl",
        )
        record = create_audit_record(sample_notification, sample_result)

        with pytest.raises(AuditPersistenceError):
            store.save_delivery_audit(record)

    def test_save_ack_audit_raises_on_write_error(self) -> None:
        """Test that OS errors raise AuditPersistenceError for ack audits."""
        from notification.audit import FileAuditStore

        store = FileAuditStore(
            delivery_audit_path="/nonexistent/path/audits.jsonl",
            ack_audit_path="/nonexistent/path/ack_audits.jsonl",
        )
        notification_id = uuid4()
        record = create_ack_audit_record(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )

        with pytest.raises(AuditPersistenceError):
            store.save_ack_audit(record)

    def test_get_delivery_audits_not_implemented(self) -> None:
        """Test that querying is not implemented for file store."""
        from notification.audit import FileAuditStore

        store = FileAuditStore()

        with pytest.raises(NotImplementedError):
            store.get_delivery_audits_for_notification(uuid4())

    def test_get_ack_audits_not_implemented(self) -> None:
        """Test that querying ack audits is not implemented for file store."""
        from notification.audit import FileAuditStore

        store = FileAuditStore()

        with pytest.raises(NotImplementedError):
            store.get_ack_audits_for_notification(uuid4())


class TestPersistentAuditLoggerAck:
    """Tests for PersistentAuditLogger ack logging error handling."""

    def test_log_ack_fail_silently_suppresses_error(self) -> None:
        """Test that fail_silently=True suppresses ack persistence errors."""
        failing_store = MagicMock()
        failing_store.save_ack_audit.side_effect = AuditPersistenceError("Test error")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=True)

        # Should not raise
        logger.log_ack(
            notification_id=uuid4(),
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )

    def test_log_ack_fail_silently_false_raises_error(self) -> None:
        """Test that fail_silently=False raises ack persistence errors."""
        failing_store = MagicMock()
        failing_store.save_ack_audit.side_effect = AuditPersistenceError("Test error")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=False)

        with pytest.raises(AuditPersistenceError):
            logger.log_ack(
                notification_id=uuid4(),
                old_status=AckStatus.PENDING,
                new_status=AckStatus.ACKED,
            )

    def test_log_ack_unexpected_error_wrapped(self) -> None:
        """Test that unexpected errors in log_ack are wrapped."""
        failing_store = MagicMock()
        failing_store.save_ack_audit.side_effect = RuntimeError("Unexpected")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=False)

        with pytest.raises(AuditPersistenceError) as exc_info:
            logger.log_ack(
                notification_id=uuid4(),
                old_status=AckStatus.PENDING,
                new_status=AckStatus.ACKED,
            )

        assert exc_info.value.original_error is not None

    def test_log_ack_unexpected_error_fail_silently(self) -> None:
        """Test that unexpected errors are suppressed when fail_silently=True."""
        failing_store = MagicMock()
        failing_store.save_ack_audit.side_effect = RuntimeError("Unexpected")

        logger = PersistentAuditLogger(store=failing_store, fail_silently=True)

        # Should not raise
        logger.log_ack(
            notification_id=uuid4(),
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )


class TestGlobalAuditLogger:
    """Tests for global audit logger functions."""

    def test_get_audit_logger_returns_singleton(self) -> None:
        """Test that get_audit_logger returns a singleton."""
        # Reset the global logger
        import notification.audit as audit_module
        from notification.audit import get_audit_logger
        audit_module._audit_logger = None

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2

    def test_configure_audit_logger_replaces_global(self) -> None:
        """Test that configure_audit_logger replaces the global instance."""
        from notification.audit import configure_audit_logger, get_audit_logger

        store = InMemoryAuditStore()
        configured = configure_audit_logger(store=store, fail_silently=True)

        current = get_audit_logger()

        assert current is configured
        assert current.store is store
        assert current.fail_silently is True


class TestAuditRecordIntegrityInvariants:
    """Tests for audit record integrity and invariants."""

    def test_audit_record_preserves_autonomy_context(
        self,
        sample_autonomy_context: AutonomyContext,
    ) -> None:
        """Test that audit record preserves all autonomy context fields."""
        notification = Notification(
            notification_type="test.notification",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_context=sample_autonomy_context,
            title="Test",
            message="Test message",
            source="test",
        )
        result = NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.SUCCESS,
        )

        record = create_audit_record(notification, result)

        # Verify all context fields are preserved
        assert record.agent_id == sample_autonomy_context.agent_id
        assert record.autonomy_mode == sample_autonomy_context.autonomy_mode.value
        assert record.plan_id == sample_autonomy_context.plan_id
        assert record.decision_snapshot_id == sample_autonomy_context.decision_snapshot_id

    def test_audit_record_has_unique_id(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that each audit record gets a unique ID."""
        record1 = create_audit_record(sample_notification, sample_result)
        record2 = create_audit_record(sample_notification, sample_result)

        assert record1.audit_id != record2.audit_id

    def test_audit_record_timestamps_are_set(
        self,
        sample_notification: Notification,
        sample_result: NotificationResult,
    ) -> None:
        """Test that audit record timestamps are properly set."""
        before = datetime.now(UTC)
        record = create_audit_record(sample_notification, sample_result)
        after = datetime.now(UTC)

        assert record.notification_created_at == sample_notification.created_at
        assert record.delivered_at == sample_result.delivered_at
        assert before <= record.audit_created_at <= after

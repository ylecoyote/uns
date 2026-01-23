"""Tests for SQLAlchemy audit store implementation.

Tests cover:
- Creating audit store with factory function
- Saving delivery audit records
- Saving acknowledgment audit records
- Querying audit records by notification ID
- Error handling for persistence failures
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.audit_store import (
    SQLAlchemyAuditStore,
    create_sqlalchemy_audit_store,
)
from db.models import Base
from notification.audit import AckAuditRecord, AuditRecord
from notification.models import AckStatus, Channel, DeliveryStatus


@pytest.fixture
def session_factory():
    """Create an in-memory SQLite database with tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def audit_store(session_factory) -> SQLAlchemyAuditStore:
    """Create a test audit store."""
    return SQLAlchemyAuditStore(session_factory=session_factory)


@pytest.fixture
def sample_audit_record() -> AuditRecord:
    """Create a sample delivery audit record."""
    return AuditRecord(
        audit_id=uuid4(),
        notification_id=uuid4(),
        notification_type="test.notification",
        status=DeliveryStatus.SUCCESS,
        channels_attempted=(Channel.SLACK, Channel.EMAIL),
        channels_succeeded=(Channel.SLACK,),
        channels_failed=(Channel.EMAIL,),
        error_message="Email delivery failed",
        intent="OPERATIONAL",
        delivery_mode="BEST_EFFORT",
        autonomy_mode="LIVE",
        agent_id=uuid4(),
        plan_id=uuid4(),
        decision_snapshot_id=uuid4(),
        execution_snapshot_id=uuid4(),
        skip_snapshot_id=None,
        title="Test Notification",
        source="test_suite",
        correlation_id="corr-123",
        metadata={"key": "value"},
        audit_metadata={"reason": "test"},
        notification_created_at=datetime.now(UTC),
        delivered_at=datetime.now(UTC),
        audit_created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_ack_audit_record() -> AckAuditRecord:
    """Create a sample ack audit record."""
    return AckAuditRecord(
        audit_id=uuid4(),
        notification_id=uuid4(),
        old_status=AckStatus.PENDING,
        new_status=AckStatus.ACKED,
        acked_by="test_user",
        acked_at=datetime.now(UTC),
        audit_created_at=datetime.now(UTC),
        metadata={"reason": "reviewed"},
    )


class TestSQLAlchemyAuditStore:
    """Tests for SQLAlchemyAuditStore."""

    def test_save_and_retrieve_delivery_audit(
        self,
        audit_store: SQLAlchemyAuditStore,
        sample_audit_record: AuditRecord,
    ):
        """Test saving and retrieving a delivery audit record."""
        # Save the record
        audit_store.save_delivery_audit(sample_audit_record)

        # Retrieve it
        records = audit_store.get_delivery_audits_for_notification(
            sample_audit_record.notification_id
        )

        assert len(records) == 1
        record = records[0]
        assert record.audit_id == sample_audit_record.audit_id
        assert record.notification_id == sample_audit_record.notification_id
        assert record.notification_type == sample_audit_record.notification_type
        assert record.status == sample_audit_record.status
        assert set(record.channels_attempted) == set(sample_audit_record.channels_attempted)
        assert set(record.channels_succeeded) == set(sample_audit_record.channels_succeeded)
        assert set(record.channels_failed) == set(sample_audit_record.channels_failed)
        assert record.error_message == sample_audit_record.error_message
        assert record.title == sample_audit_record.title
        assert record.source == sample_audit_record.source

    def test_save_and_retrieve_ack_audit(
        self,
        audit_store: SQLAlchemyAuditStore,
        sample_ack_audit_record: AckAuditRecord,
    ):
        """Test saving and retrieving an ack audit record."""
        # Save the record
        audit_store.save_ack_audit(sample_ack_audit_record)

        # Retrieve it
        records = audit_store.get_ack_audits_for_notification(
            sample_ack_audit_record.notification_id
        )

        assert len(records) == 1
        record = records[0]
        assert record.audit_id == sample_ack_audit_record.audit_id
        assert record.notification_id == sample_ack_audit_record.notification_id
        assert record.old_status == sample_ack_audit_record.old_status
        assert record.new_status == sample_ack_audit_record.new_status
        assert record.acked_by == sample_ack_audit_record.acked_by

    def test_multiple_delivery_audits_for_notification(
        self,
        audit_store: SQLAlchemyAuditStore,
    ):
        """Test retrieving multiple delivery audits for the same notification."""
        notification_id = uuid4()

        # Create and save multiple audit records
        records_to_save = []
        for i in range(3):
            record = AuditRecord(
                audit_id=uuid4(),
                notification_id=notification_id,
                notification_type="test.notification",
                status=DeliveryStatus.SUCCESS if i < 2 else DeliveryStatus.FAILED,
                channels_attempted=(Channel.SLACK,),
                channels_succeeded=(Channel.SLACK,) if i < 2 else (),
                channels_failed=() if i < 2 else (Channel.SLACK,),
                error_message=None if i < 2 else "Retried and failed",
                intent="OPERATIONAL",
                delivery_mode="BEST_EFFORT",
                autonomy_mode="LIVE",
                agent_id=uuid4(),
                plan_id=None,
                decision_snapshot_id=None,
                execution_snapshot_id=None,
                skip_snapshot_id=None,
                correlation_id=None,
                metadata={},
                audit_metadata={},
                title=f"Notification {i}",
                source="test_suite",
                notification_created_at=datetime.now(UTC),
                delivered_at=datetime.now(UTC),
                audit_created_at=datetime.now(UTC),
            )
            records_to_save.append(record)
            audit_store.save_delivery_audit(record)

        # Retrieve all records
        retrieved = audit_store.get_delivery_audits_for_notification(notification_id)

        assert len(retrieved) == 3

    def test_multiple_ack_audits_for_notification(
        self,
        audit_store: SQLAlchemyAuditStore,
    ):
        """Test retrieving multiple ack audits for the same notification."""
        notification_id = uuid4()

        # Create and save ack audit records for state transitions
        statuses = [
            (None, AckStatus.PENDING),
            (AckStatus.PENDING, AckStatus.ACKED),
        ]

        for old_status, new_status in statuses:
            record = AckAuditRecord(
                audit_id=uuid4(),
                notification_id=notification_id,
                old_status=old_status,
                new_status=new_status,
                acked_by="test_user" if new_status == AckStatus.ACKED else None,
                acked_at=datetime.now(UTC),
                audit_created_at=datetime.now(UTC),
                metadata={},
            )
            audit_store.save_ack_audit(record)

        # Retrieve all records
        retrieved = audit_store.get_ack_audits_for_notification(notification_id)

        assert len(retrieved) == 2

    def test_no_audits_for_unknown_notification(
        self,
        audit_store: SQLAlchemyAuditStore,
    ):
        """Test that querying unknown notification returns empty list."""
        unknown_id = uuid4()

        delivery_audits = audit_store.get_delivery_audits_for_notification(unknown_id)
        ack_audits = audit_store.get_ack_audits_for_notification(unknown_id)

        assert delivery_audits == []
        assert ack_audits == []


class TestCreateSQLAlchemyAuditStore:
    """Tests for the factory function."""

    def test_create_with_sqlite_in_memory(self, tmp_path):
        """Test creating audit store with SQLite in-memory database."""
        store = create_sqlalchemy_audit_store(
            database_url="sqlite:///:memory:",
            create_tables=True,
        )

        assert isinstance(store, SQLAlchemyAuditStore)

        # Verify we can save and retrieve records
        record = AuditRecord(
            audit_id=uuid4(),
            notification_id=uuid4(),
            notification_type="test.notification",
            status=DeliveryStatus.SUCCESS,
            channels_attempted=(Channel.SLACK,),
            channels_succeeded=(Channel.SLACK,),
            channels_failed=(),
            error_message=None,
            intent="OPERATIONAL",
            delivery_mode="BEST_EFFORT",
            autonomy_mode="LIVE",
            agent_id=uuid4(),
            plan_id=None,
            decision_snapshot_id=None,
            execution_snapshot_id=None,
            skip_snapshot_id=None,
            correlation_id=None,
            metadata={},
            audit_metadata={},
            title="Test",
            source="test",
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
            audit_created_at=datetime.now(UTC),
        )

        store.save_delivery_audit(record)
        retrieved = store.get_delivery_audits_for_notification(record.notification_id)

        assert len(retrieved) == 1

    def test_create_with_file_database(self, tmp_path):
        """Test creating audit store with SQLite file database."""
        db_path = tmp_path / "test.db"
        store = create_sqlalchemy_audit_store(
            database_url=f"sqlite:///{db_path}",
            create_tables=True,
        )

        assert isinstance(store, SQLAlchemyAuditStore)
        assert db_path.exists()

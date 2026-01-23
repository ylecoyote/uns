"""Tests for database models.

Tests cover:
- NotificationAuditRecord model creation
- AckAuditRecord model creation
- PersistedNotificationPolicy model creation
- Model repr methods
- Default values and timestamps
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import (
    AckAuditRecord,
    AckStatusDB,
    Base,
    DeliveryStatusDB,
    NotificationAuditRecord,
    PersistedNotificationPolicy,
)


@pytest.fixture
def session():
    """Create an in-memory SQLite database with tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_session = session_factory()
    yield db_session
    db_session.close()


class TestDeliveryStatusDB:
    """Tests for DeliveryStatusDB enum."""

    def test_enum_values(self):
        """Test that enum has expected values."""
        assert DeliveryStatusDB.SUCCESS.value == "SUCCESS"
        assert DeliveryStatusDB.FAILED.value == "FAILED"
        assert DeliveryStatusDB.DEDUPLICATED.value == "DEDUPLICATED"
        assert DeliveryStatusDB.RATE_LIMITED.value == "RATE_LIMITED"


class TestAckStatusDB:
    """Tests for AckStatusDB enum."""

    def test_enum_values(self):
        """Test that enum has expected values."""
        assert AckStatusDB.PENDING.value == "PENDING"
        assert AckStatusDB.ACKED.value == "ACKED"
        assert AckStatusDB.DISMISSED.value == "DISMISSED"
        assert AckStatusDB.TIMED_OUT.value == "TIMED_OUT"


class TestNotificationAuditRecord:
    """Tests for NotificationAuditRecord model."""

    def test_create_record(self, session):
        """Test creating a notification audit record."""
        record = NotificationAuditRecord(
            id=uuid4(),
            notification_id=uuid4(),
            notification_type="test.notification",
            status="SUCCESS",
            channels_attempted=["SLACK", "EMAIL"],
            channels_succeeded=["SLACK"],
            channels_failed=["EMAIL"],
            error_message="Email failed",
            intent="OPERATIONAL",
            delivery_mode="BEST_EFFORT",
            autonomy_mode="LIVE",
            agent_id=uuid4(),
            title="Test Notification",
            source="test_suite",
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
        )

        session.add(record)
        session.commit()

        # Verify it was saved
        retrieved = session.query(NotificationAuditRecord).first()
        assert retrieved is not None
        assert retrieved.notification_type == "test.notification"
        assert retrieved.status == "SUCCESS"
        assert retrieved.channels_attempted == ["SLACK", "EMAIL"]
        assert retrieved.title == "Test Notification"

    def test_optional_fields(self, session):
        """Test that optional fields can be None."""
        record = NotificationAuditRecord(
            id=uuid4(),
            notification_id=uuid4(),
            notification_type="test.notification",
            status="SUCCESS",
            channels_attempted=[],
            channels_succeeded=[],
            channels_failed=[],
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
            title="Test",
            source="test",
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
        )

        session.add(record)
        session.commit()

        retrieved = session.query(NotificationAuditRecord).first()
        assert retrieved.plan_id is None
        assert retrieved.correlation_id is None

    def test_repr(self, session):
        """Test the __repr__ method."""
        record_id = uuid4()
        notification_id = uuid4()
        record = NotificationAuditRecord(
            id=record_id,
            notification_id=notification_id,
            notification_type="test.notification",
            status="SUCCESS",
            channels_attempted=[],
            channels_succeeded=[],
            channels_failed=[],
            intent="OPERATIONAL",
            delivery_mode="BEST_EFFORT",
            autonomy_mode="LIVE",
            agent_id=uuid4(),
            title="Test",
            source="test",
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
        )

        repr_str = repr(record)
        assert str(record_id) in repr_str
        assert str(notification_id) in repr_str
        assert "SUCCESS" in repr_str

    def test_default_values(self, session):
        """Test that default values are applied."""
        record = NotificationAuditRecord(
            notification_id=uuid4(),
            notification_type="test.notification",
            status="SUCCESS",
            intent="OPERATIONAL",
            delivery_mode="BEST_EFFORT",
            autonomy_mode="LIVE",
            agent_id=uuid4(),
            title="Test",
            source="test",
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
        )

        session.add(record)
        session.commit()

        retrieved = session.query(NotificationAuditRecord).first()
        # ID should be auto-generated
        assert retrieved.id is not None
        # created_at should be auto-set
        assert retrieved.created_at is not None
        # Default empty lists for JSON fields
        assert retrieved.notification_metadata == {}
        assert retrieved.audit_metadata == {}


class TestAckAuditRecord:
    """Tests for AckAuditRecord model."""

    def test_create_record(self, session):
        """Test creating an ack audit record."""
        record = AckAuditRecord(
            id=uuid4(),
            notification_id=uuid4(),
            old_status="PENDING",
            new_status="ACKED",
            acked_by="test_user",
            acked_at=datetime.now(UTC),
            ack_metadata={"reason": "reviewed"},
        )

        session.add(record)
        session.commit()

        retrieved = session.query(AckAuditRecord).first()
        assert retrieved is not None
        assert retrieved.old_status == "PENDING"
        assert retrieved.new_status == "ACKED"
        assert retrieved.acked_by == "test_user"
        assert retrieved.ack_metadata == {"reason": "reviewed"}

    def test_optional_old_status(self, session):
        """Test that old_status can be None (for initial state)."""
        record = AckAuditRecord(
            id=uuid4(),
            notification_id=uuid4(),
            old_status=None,
            new_status="PENDING",
            acked_by=None,
            acked_at=datetime.now(UTC),
            ack_metadata={},
        )

        session.add(record)
        session.commit()

        retrieved = session.query(AckAuditRecord).first()
        assert retrieved.old_status is None

    def test_repr(self, session):
        """Test the __repr__ method."""
        record_id = uuid4()
        notification_id = uuid4()
        record = AckAuditRecord(
            id=record_id,
            notification_id=notification_id,
            new_status="ACKED",
            acked_at=datetime.now(UTC),
        )

        repr_str = repr(record)
        assert str(record_id) in repr_str
        assert str(notification_id) in repr_str
        assert "ACKED" in repr_str


class TestPersistedNotificationPolicy:
    """Tests for PersistedNotificationPolicy model."""

    def test_create_policy(self, session):
        """Test creating a persisted notification policy."""
        policy = PersistedNotificationPolicy(
            notification_type="test.notification",
            delivery_mode="GUARANTEED",
            channels=["SLACK", "EMAIL"],
            require_ack=True,
            ack_timeout_minutes=15,
            dedup_window_seconds=300,
            description="Test policy",
            is_active=True,
        )

        session.add(policy)
        session.commit()

        retrieved = session.query(PersistedNotificationPolicy).first()
        assert retrieved is not None
        assert retrieved.notification_type == "test.notification"
        assert retrieved.delivery_mode == "GUARANTEED"
        assert retrieved.channels == ["SLACK", "EMAIL"]
        assert retrieved.require_ack is True
        assert retrieved.ack_timeout_minutes == 15

    def test_optional_fields(self, session):
        """Test that optional policy fields can be None."""
        policy = PersistedNotificationPolicy(
            notification_type="minimal.policy",
            delivery_mode=None,
            channels=None,
            require_ack=None,
            ack_timeout_minutes=None,
            dedup_window_seconds=None,
            mode_overrides=None,
            description=None,
            is_active=True,
        )

        session.add(policy)
        session.commit()

        retrieved = session.query(PersistedNotificationPolicy).first()
        assert retrieved.delivery_mode is None
        assert retrieved.channels is None
        assert retrieved.require_ack is None

    def test_mode_overrides_json(self, session):
        """Test storing complex mode overrides as JSON."""
        policy = PersistedNotificationPolicy(
            notification_type="complex.policy",
            mode_overrides={
                "PREVIEW": {
                    "channels": ["WEBSOCKET"],
                    "require_ack": False,
                },
                "SHADOW": {
                    "channels": ["WEBSOCKET", "SLACK"],
                    "require_ack": False,
                },
                "LIVE": {
                    "channels": ["SLACK", "EMAIL", "PAGERDUTY"],
                    "require_ack": True,
                    "ack_timeout_minutes": 15,
                },
            },
            is_active=True,
        )

        session.add(policy)
        session.commit()

        retrieved = session.query(PersistedNotificationPolicy).first()
        assert retrieved.mode_overrides is not None
        assert "PREVIEW" in retrieved.mode_overrides
        assert "SHADOW" in retrieved.mode_overrides
        assert "LIVE" in retrieved.mode_overrides
        assert retrieved.mode_overrides["LIVE"]["ack_timeout_minutes"] == 15

    def test_repr(self, session):
        """Test the __repr__ method."""
        policy = PersistedNotificationPolicy(
            notification_type="repr.test.policy",
            is_active=True,
        )

        repr_str = repr(policy)
        assert "repr.test.policy" in repr_str

    def test_default_is_active(self, session):
        """Test that is_active defaults to True."""
        policy = PersistedNotificationPolicy(
            notification_type="default.active.policy",
        )

        session.add(policy)
        session.commit()

        retrieved = session.query(PersistedNotificationPolicy).first()
        assert retrieved.is_active is True

    def test_timestamps_auto_set(self, session):
        """Test that timestamps are automatically set."""
        policy = PersistedNotificationPolicy(
            notification_type="timestamp.test.policy",
            is_active=True,
        )

        session.add(policy)
        session.commit()

        retrieved = session.query(PersistedNotificationPolicy).first()
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

"""Tests for read model adapters.

Tests the read model adapters that connect UI endpoints to persistence:
- InMemoryReadModelAdapter
- SQLAlchemyReadModelAdapter (with SQLite)
- Filter criteria and pagination
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mcp_server.read_models import (
    AuditEventFilter,
    DeliveryFilter,
    DeliverySummary,
    DeliveryTimeline,
    InMemoryReadModelAdapter,
    PaginatedResult,
    configure_read_model_adapter,
    create_in_memory_adapter,
    create_sqlalchemy_adapter,
    get_read_model_adapter,
)
from notification.audit import AckAuditRecord, AuditRecord, InMemoryAuditStore
from notification.models import (
    AckStatus,
    AutonomyMode,
    Channel,
    DeliveryStatus,
    NotificationIntent,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def create_test_audit_record(
    notification_id=None,
    notification_type="test.notification",
    status=DeliveryStatus.DELIVERED,
    channels_attempted=(Channel.SLACK,),
    channels_succeeded=(Channel.SLACK,),
    channels_failed=(),
    intent="OPERATIONAL",
    delivery_mode="BEST_EFFORT",
    autonomy_mode="LIVE",
    agent_id=None,
    correlation_id=None,
    created_offset_hours=0,
) -> AuditRecord:
    """Create a test audit record with customizable fields."""
    now = datetime.now(UTC)
    return AuditRecord(
        audit_id=uuid4(),
        notification_id=notification_id or uuid4(),
        notification_type=notification_type,
        status=status,
        channels_attempted=channels_attempted,
        channels_succeeded=channels_succeeded,
        channels_failed=channels_failed,
        error_message=None if status == DeliveryStatus.DELIVERED else "Test error",
        intent=intent,
        delivery_mode=delivery_mode,
        autonomy_mode=autonomy_mode,
        agent_id=agent_id or uuid4(),
        plan_id=None,
        decision_snapshot_id=None,
        execution_snapshot_id=None,
        skip_snapshot_id=None,
        title="Test Notification",
        source="test-source",
        correlation_id=correlation_id,
        metadata={},
        audit_metadata={},
        notification_created_at=now - timedelta(hours=created_offset_hours),
        delivered_at=now - timedelta(hours=created_offset_hours),
        audit_created_at=now - timedelta(hours=created_offset_hours),
    )


def create_test_ack_audit_record(
    notification_id=None,
    old_status=None,
    new_status=AckStatus.ACKED,
    acked_by="test-user",
    created_offset_hours=0,
) -> AckAuditRecord:
    """Create a test ack audit record with customizable fields."""
    now = datetime.now(UTC)
    return AckAuditRecord(
        audit_id=uuid4(),
        notification_id=notification_id or uuid4(),
        old_status=old_status,
        new_status=new_status,
        acked_by=acked_by,
        acked_at=now - timedelta(hours=created_offset_hours),
        audit_created_at=now - timedelta(hours=created_offset_hours),
        metadata={},
    )


@pytest.fixture
def audit_store() -> InMemoryAuditStore:
    """Create a fresh in-memory audit store."""
    return InMemoryAuditStore()


@pytest.fixture
def adapter(audit_store: InMemoryAuditStore) -> InMemoryReadModelAdapter:
    """Create an in-memory adapter with the test store."""
    return InMemoryReadModelAdapter(audit_store=audit_store)


@pytest.fixture
def populated_adapter(audit_store: InMemoryAuditStore) -> InMemoryReadModelAdapter:
    """Create an adapter with test data."""
    # Add various records for testing
    agent1 = uuid4()
    agent2 = uuid4()

    # Delivery records
    records = [
        create_test_audit_record(
            notification_type="app.alert",
            status=DeliveryStatus.DELIVERED,
            intent="SAFETY",
            autonomy_mode="LIVE",
            agent_id=agent1,
            created_offset_hours=0,
        ),
        create_test_audit_record(
            notification_type="app.alert",
            status=DeliveryStatus.FAILED,
            intent="SAFETY",
            autonomy_mode="LIVE",
            agent_id=agent1,
            channels_succeeded=(),
            channels_failed=(Channel.SLACK,),
            created_offset_hours=1,
        ),
        create_test_audit_record(
            notification_type="system.info",
            status=DeliveryStatus.DELIVERED,
            intent="INFORMATIONAL",
            autonomy_mode="PREVIEW",
            agent_id=agent2,
            created_offset_hours=2,
        ),
        create_test_audit_record(
            notification_type="trading.order",
            status=DeliveryStatus.DEDUPLICATED,
            intent="GOVERNANCE",
            autonomy_mode="SHADOW",
            agent_id=agent2,
            created_offset_hours=3,
        ),
    ]

    for record in records:
        audit_store.save_delivery_audit(record)

    # Ack records
    ack_records = [
        create_test_ack_audit_record(
            new_status=AckStatus.PENDING,
            old_status=None,
            created_offset_hours=0,
        ),
        create_test_ack_audit_record(
            new_status=AckStatus.ACKED,
            old_status=AckStatus.PENDING,
            created_offset_hours=0,
        ),
    ]

    for record in ack_records:
        audit_store.save_ack_audit(record)

    return InMemoryReadModelAdapter(audit_store=audit_store)


# =============================================================================
# InMemoryReadModelAdapter Tests
# =============================================================================


class TestInMemoryAdapterDeliveries:
    """Tests for delivery queries on in-memory adapter."""

    def test_get_deliveries_empty(self, adapter: InMemoryReadModelAdapter):
        """Test getting deliveries from empty store."""
        result = adapter.get_deliveries(DeliveryFilter(), limit=10)

        assert isinstance(result, PaginatedResult)
        assert result.items == []
        assert result.total_count == 0
        assert result.has_more is False
        assert result.next_cursor is None

    def test_get_deliveries_basic(self, audit_store: InMemoryAuditStore):
        """Test getting deliveries returns stored records."""
        record = create_test_audit_record()
        audit_store.save_delivery_audit(record)

        adapter = InMemoryReadModelAdapter(audit_store=audit_store)
        result = adapter.get_deliveries(DeliveryFilter(), limit=10)

        assert result.total_count == 1
        assert len(result.items) == 1

        item = result.items[0]
        assert isinstance(item, DeliverySummary)
        assert item.notification_id == record.notification_id
        assert item.notification_type == "test.notification"
        assert item.status == DeliveryStatus.DELIVERED

    def test_get_deliveries_filter_by_status(self, populated_adapter: InMemoryReadModelAdapter):
        """Test filtering deliveries by status."""
        result = populated_adapter.get_deliveries(
            DeliveryFilter(status=DeliveryStatus.DELIVERED),
            limit=10,
        )

        assert result.total_count == 2
        for item in result.items:
            assert item.status == DeliveryStatus.DELIVERED

    def test_get_deliveries_filter_by_intent(self, populated_adapter: InMemoryReadModelAdapter):
        """Test filtering deliveries by intent."""
        result = populated_adapter.get_deliveries(
            DeliveryFilter(intent=NotificationIntent.SAFETY),
            limit=10,
        )

        assert result.total_count == 2
        for item in result.items:
            assert item.intent == NotificationIntent.SAFETY

    def test_get_deliveries_filter_by_autonomy_mode(
        self, populated_adapter: InMemoryReadModelAdapter
    ):
        """Test filtering deliveries by autonomy mode."""
        result = populated_adapter.get_deliveries(
            DeliveryFilter(autonomy_mode=AutonomyMode.LIVE),
            limit=10,
        )

        assert result.total_count == 2
        for item in result.items:
            assert item.autonomy_mode == AutonomyMode.LIVE

    def test_get_deliveries_filter_by_notification_type(
        self, populated_adapter: InMemoryReadModelAdapter
    ):
        """Test filtering deliveries by notification type."""
        result = populated_adapter.get_deliveries(
            DeliveryFilter(notification_type="app.alert"),
            limit=10,
        )

        assert result.total_count == 2
        for item in result.items:
            assert item.notification_type == "app.alert"

    def test_get_deliveries_filter_by_time_range(self, populated_adapter: InMemoryReadModelAdapter):
        """Test filtering deliveries by time range."""
        now = datetime.now(UTC)

        # Get only records from the last hour
        result = populated_adapter.get_deliveries(
            DeliveryFilter(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
            ),
            limit=10,
        )

        # Should only get the most recent record
        assert result.total_count == 1

    def test_get_deliveries_pagination(self, populated_adapter: InMemoryReadModelAdapter):
        """Test pagination of deliveries."""
        # Get first page
        result1 = populated_adapter.get_deliveries(DeliveryFilter(), limit=2)

        assert len(result1.items) == 2
        assert result1.has_more is True
        assert result1.next_cursor is not None

        # Get second page
        result2 = populated_adapter.get_deliveries(
            DeliveryFilter(),
            cursor=result1.next_cursor,
            limit=2,
        )

        assert len(result2.items) == 2
        assert result2.has_more is False

    def test_get_deliveries_sorted_by_created_at_desc(
        self, populated_adapter: InMemoryReadModelAdapter
    ):
        """Test deliveries are sorted by created_at descending."""
        result = populated_adapter.get_deliveries(DeliveryFilter(), limit=10)

        for i in range(len(result.items) - 1):
            assert result.items[i].created_at >= result.items[i + 1].created_at


class TestInMemoryAdapterDeliveryTimeline:
    """Tests for single delivery timeline queries."""

    def test_get_delivery_timeline_not_found(self, adapter: InMemoryReadModelAdapter):
        """Test getting non-existent delivery returns None."""
        result = adapter.get_delivery_timeline(uuid4())
        assert result is None

    def test_get_delivery_timeline_found(self, audit_store: InMemoryAuditStore):
        """Test getting existing delivery timeline."""
        record = create_test_audit_record(
            channels_attempted=(Channel.SLACK, Channel.EMAIL),
            channels_succeeded=(Channel.SLACK,),
            channels_failed=(Channel.EMAIL,),
        )
        audit_store.save_delivery_audit(record)

        adapter = InMemoryReadModelAdapter(audit_store=audit_store)
        result = adapter.get_delivery_timeline(record.notification_id)

        assert result is not None
        assert isinstance(result, DeliveryTimeline)
        assert result.notification_id == record.notification_id
        assert result.notification_type == "test.notification"
        assert len(result.attempts) == 2
        assert Channel.SLACK in result.channels_attempted
        assert Channel.EMAIL in result.channels_attempted
        assert Channel.SLACK in result.channels_succeeded
        assert Channel.EMAIL in result.channels_failed


class TestInMemoryAdapterAuditEvents:
    """Tests for audit event queries on in-memory adapter."""

    def test_get_audit_events_empty(self, adapter: InMemoryReadModelAdapter):
        """Test getting audit events from empty store."""
        result = adapter.get_audit_events(AuditEventFilter(), limit=10)

        assert isinstance(result, PaginatedResult)
        assert result.items == []
        assert result.total_count == 0

    def test_get_audit_events_includes_delivery_and_ack(
        self, populated_adapter: InMemoryReadModelAdapter
    ):
        """Test audit events include both delivery and ack records."""
        result = populated_adapter.get_audit_events(AuditEventFilter(), limit=20)

        event_types = {e.event_type for e in result.items}
        # Should have delivery events
        assert any(et.startswith("delivery.") for et in event_types)
        # Should have ack events
        assert any(et.startswith("ack.") for et in event_types)

    def test_get_audit_events_filter_by_event_type(
        self, populated_adapter: InMemoryReadModelAdapter
    ):
        """Test filtering audit events by event type."""
        result = populated_adapter.get_audit_events(
            AuditEventFilter(event_type="delivery.succeeded"),
            limit=10,
        )

        for event in result.items:
            assert event.event_type == "delivery.succeeded"

    def test_get_audit_events_filter_by_notification_id(self, audit_store: InMemoryAuditStore):
        """Test filtering audit events by notification ID."""
        target_id = uuid4()
        record1 = create_test_audit_record(notification_id=target_id)
        record2 = create_test_audit_record()  # Different ID

        audit_store.save_delivery_audit(record1)
        audit_store.save_delivery_audit(record2)

        adapter = InMemoryReadModelAdapter(audit_store=audit_store)
        result = adapter.get_audit_events(
            AuditEventFilter(notification_id=target_id),
            limit=10,
        )

        assert result.total_count == 1
        assert result.items[0].notification_id == target_id

    def test_get_audit_events_sorted_by_time_desc(
        self, populated_adapter: InMemoryReadModelAdapter
    ):
        """Test audit events are sorted by event_time descending."""
        result = populated_adapter.get_audit_events(AuditEventFilter(), limit=20)

        for i in range(len(result.items) - 1):
            assert result.items[i].event_time >= result.items[i + 1].event_time


class TestInMemoryAdapterEventTypes:
    """Tests for correct event type derivation."""

    def test_delivery_status_to_event_type(self, audit_store: InMemoryAuditStore):
        """Test delivery status maps to correct event type."""
        status_event_map = {
            DeliveryStatus.DELIVERED: "delivery.succeeded",
            DeliveryStatus.FAILED: "delivery.failed",
            DeliveryStatus.DEDUPLICATED: "delivery.deduplicated",
            DeliveryStatus.RATE_LIMITED: "delivery.rate_limited",
        }

        for status, expected_event_type in status_event_map.items():
            audit_store.clear()
            record = create_test_audit_record(status=status)
            audit_store.save_delivery_audit(record)

            adapter = InMemoryReadModelAdapter(audit_store=audit_store)
            result = adapter.get_audit_events(AuditEventFilter(), limit=10)

            assert len(result.items) == 1
            assert result.items[0].event_type == expected_event_type

    def test_ack_status_to_event_type(self, audit_store: InMemoryAuditStore):
        """Test ack status maps to correct event type."""
        status_event_map = {
            AckStatus.PENDING: "ack.pending",
            AckStatus.ACKED: "ack.received",
            AckStatus.DISMISSED: "ack.dismissed",
            AckStatus.TIMED_OUT: "ack.timed_out",
        }

        for new_status, expected_event_type in status_event_map.items():
            audit_store.clear()
            record = create_test_ack_audit_record(new_status=new_status)
            audit_store.save_ack_audit(record)

            adapter = InMemoryReadModelAdapter(audit_store=audit_store)
            result = adapter.get_audit_events(AuditEventFilter(), limit=10)

            assert len(result.items) == 1
            assert result.items[0].event_type == expected_event_type


# =============================================================================
# Global Configuration Tests
# =============================================================================


class TestGlobalConfiguration:
    """Tests for global adapter configuration."""

    def test_get_read_model_adapter_default(self):
        """Test default adapter is InMemoryReadModelAdapter."""
        # Reset global state
        import mcp_server.read_models as rm

        rm._read_model_adapter = None

        adapter = get_read_model_adapter()
        assert isinstance(adapter, InMemoryReadModelAdapter)

    def test_configure_read_model_adapter(self, adapter: InMemoryReadModelAdapter):
        """Test configuring custom adapter."""
        configured = configure_read_model_adapter(adapter)

        assert configured is adapter
        assert get_read_model_adapter() is adapter

    def test_create_in_memory_adapter_factory(self):
        """Test in-memory adapter factory function."""
        adapter = create_in_memory_adapter()
        assert isinstance(adapter, InMemoryReadModelAdapter)

    def test_create_in_memory_adapter_with_store(self, audit_store: InMemoryAuditStore):
        """Test in-memory adapter factory with custom store."""
        adapter = create_in_memory_adapter(audit_store=audit_store)
        assert adapter.audit_store is audit_store


# =============================================================================
# Cursor Encoding Tests
# =============================================================================


class TestCursorEncoding:
    """Tests for cursor encoding/decoding."""

    def test_cursor_round_trip(self, adapter: InMemoryReadModelAdapter):
        """Test cursor encodes and decodes correctly."""
        original_offset = 42
        cursor = adapter._encode_cursor(original_offset)
        decoded_offset = adapter._decode_cursor(cursor)

        assert decoded_offset == original_offset

    def test_invalid_cursor_returns_zero(self, adapter: InMemoryReadModelAdapter):
        """Test invalid cursor returns zero offset."""
        assert adapter._decode_cursor("invalid-cursor") == 0
        assert adapter._decode_cursor("") == 0
        assert adapter._decode_cursor(None) == 0


# =============================================================================
# Integration Tests with UI Endpoints
# =============================================================================


class TestUIEndpointIntegration:
    """Tests for read model adapter integration with UI endpoints."""

    def test_deliveries_endpoint_uses_adapter(self, audit_store: InMemoryAuditStore):
        """Test /ui/deliveries endpoint uses configured adapter."""
        from fastapi.testclient import TestClient

        from mcp_server.app import create_app

        # Add test data
        record = create_test_audit_record()
        audit_store.save_delivery_audit(record)

        # Configure adapter
        adapter = InMemoryReadModelAdapter(audit_store=audit_store)
        configure_read_model_adapter(adapter)

        # Create app without auto-configuration to use our manually configured adapter
        app = create_app(skip_persistence_config=True)
        client = TestClient(app)

        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["notification_id"] == str(record.notification_id)

    def test_delivery_timeline_endpoint_uses_adapter(self, audit_store: InMemoryAuditStore):
        """Test /ui/deliveries/{id} endpoint uses configured adapter."""
        from fastapi.testclient import TestClient

        from mcp_server.app import create_app

        # Add test data
        record = create_test_audit_record()
        audit_store.save_delivery_audit(record)

        # Configure adapter
        adapter = InMemoryReadModelAdapter(audit_store=audit_store)
        configure_read_model_adapter(adapter)

        # Create app without auto-configuration to use our manually configured adapter
        app = create_app(skip_persistence_config=True)
        client = TestClient(app)

        response = client.get(f"/ui/deliveries/{record.notification_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["notification_id"] == str(record.notification_id)
        assert "attempts" in data
        assert "autonomy_context" in data

        # Test endpoint - not found
        response = client.get(f"/ui/deliveries/{uuid4()}")
        assert response.status_code == 404

    def test_audit_endpoint_uses_adapter(self, audit_store: InMemoryAuditStore):
        """Test /ui/audit endpoint uses configured adapter."""
        from fastapi.testclient import TestClient

        from mcp_server.app import create_app

        # Add test data
        record = create_test_audit_record()
        audit_store.save_delivery_audit(record)

        # Configure adapter
        adapter = InMemoryReadModelAdapter(audit_store=audit_store)
        configure_read_model_adapter(adapter)

        # Create app without auto-configuration to use our manually configured adapter
        app = create_app(skip_persistence_config=True)
        client = TestClient(app)

        response = client.get("/ui/audit")
        assert response.status_code == 200

        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["event_type"] == "delivery.succeeded"


# =============================================================================
# SQLAlchemy Adapter Tests (using SQLite)
# =============================================================================


class TestSQLAlchemyAdapter:
    """Tests for SQLAlchemy-backed adapter using SQLite."""

    @pytest.fixture
    def db_adapter(self, tmp_path):
        """Create SQLAlchemy adapter with temp SQLite database."""
        db_path = tmp_path / "test.db"
        adapter = create_sqlalchemy_adapter(
            f"sqlite:///{db_path}",
            create_tables=True,
        )
        return adapter

    @pytest.fixture
    def db_with_data(self, db_adapter, tmp_path):
        """Create database with test data."""
        from datetime import UTC, datetime

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from db.models import NotificationAuditRecord

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        session_maker = sessionmaker(bind=engine)

        session = session_maker()
        try:
            # Add delivery audit record
            record = NotificationAuditRecord(
                id=uuid4(),
                notification_id=uuid4(),
                notification_type="test.notification",
                status="DELIVERED",
                channels_attempted=["SLACK"],
                channels_succeeded=["SLACK"],
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
                title="Test",
                source="test",
                correlation_id=None,
                notification_metadata={},
                audit_metadata={},
                notification_created_at=datetime.now(UTC),
                delivered_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.commit()
        finally:
            session.close()

        return db_adapter

    def test_get_deliveries_empty(self, db_adapter):
        """Test getting deliveries from empty database."""
        result = db_adapter.get_deliveries(DeliveryFilter(), limit=10)

        assert result.items == []
        assert result.total_count == 0

    def test_get_deliveries_with_data(self, db_with_data):
        """Test getting deliveries from populated database."""
        result = db_with_data.get_deliveries(DeliveryFilter(), limit=10)

        assert result.total_count == 1
        assert len(result.items) == 1
        assert result.items[0].notification_type == "test.notification"

    def test_get_delivery_timeline_not_found(self, db_adapter):
        """Test getting non-existent delivery returns None."""
        result = db_adapter.get_delivery_timeline(uuid4())
        assert result is None

    def test_get_audit_events_empty(self, db_adapter):
        """Test getting audit events from empty database."""
        result = db_adapter.get_audit_events(AuditEventFilter(), limit=10)

        assert result.items == []
        assert result.total_count == 0

"""Tests for UI API client filters."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from ui_client.filters import (
    AuditFilters,
    DeliveryFilters,
    InvariantFilters,
    PaginationParams,
)
from ui_client.types import (
    AuditEventType,
    EnforcementType,
    InvariantSeverity,
    InvariantStatus,
)


class TestDeliveryFilters:
    """Tests for DeliveryFilters."""

    def test_empty_filters(self):
        """Test empty filters produce empty params."""
        filters = DeliveryFilters()
        params = filters.to_query_params()
        assert params == {}

    def test_all_filters(self):
        """Test all filters are converted to params."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)
        agent_id = uuid4()

        filters = DeliveryFilters(
            start_time=start,
            end_time=end,
            status=DeliveryStatus.DELIVERED,
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            agent_id=agent_id,
            autonomy_mode=AutonomyMode.LIVE,
            notification_type="trading.risk_breach",
            channel=Channel.SLACK,
        )

        params = filters.to_query_params()

        assert params["start_time"] == start.isoformat()
        assert params["end_time"] == end.isoformat()
        assert params["status"] == "DELIVERED"
        assert params["intent"] == "SAFETY"
        assert params["delivery_mode"] == "GUARANTEED"
        assert params["agent_id"] == str(agent_id)
        assert params["autonomy_mode"] == "LIVE"
        assert params["notification_type"] == "trading.risk_breach"
        assert params["channel"] == "SLACK"

    def test_partial_filters(self):
        """Test partial filters only include set values."""
        filters = DeliveryFilters(
            status=DeliveryStatus.FAILED,
            intent=NotificationIntent.GOVERNANCE,
        )

        params = filters.to_query_params()

        assert params == {
            "status": "FAILED",
            "intent": "GOVERNANCE",
        }
        assert "start_time" not in params
        assert "agent_id" not in params

    def test_filters_are_frozen(self):
        """Test filters are immutable (frozen dataclass)."""
        filters = DeliveryFilters(status=DeliveryStatus.PENDING)
        with pytest.raises(AttributeError):
            filters.status = DeliveryStatus.DELIVERED


class TestAuditFilters:
    """Tests for AuditFilters."""

    def test_empty_filters(self):
        """Test empty filters produce empty params."""
        filters = AuditFilters()
        params = filters.to_query_params()
        assert params == {}

    def test_all_filters(self):
        """Test all filters are converted to params."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)
        agent_id = uuid4()
        notification_id = uuid4()

        filters = AuditFilters(
            start_time=start,
            end_time=end,
            event_type=AuditEventType.DELIVERY_SUCCEEDED,
            notification_id=notification_id,
            agent_id=agent_id,
            autonomy_mode=AutonomyMode.SHADOW,
            correlation_id="corr-123",
        )

        params = filters.to_query_params()

        assert params["start_time"] == start.isoformat()
        assert params["end_time"] == end.isoformat()
        assert params["event_type"] == "delivery.succeeded"
        assert params["notification_id"] == str(notification_id)
        assert params["agent_id"] == str(agent_id)
        assert params["autonomy_mode"] == "SHADOW"
        assert params["correlation_id"] == "corr-123"

    def test_event_type_values(self):
        """Test different event types are properly serialized."""
        filters_delivery = AuditFilters(event_type=AuditEventType.DELIVERY_FAILED)
        assert filters_delivery.to_query_params()["event_type"] == "delivery.failed"

        filters_ack = AuditFilters(event_type=AuditEventType.ACK_RECEIVED)
        assert filters_ack.to_query_params()["event_type"] == "ack.received"


class TestInvariantFilters:
    """Tests for InvariantFilters."""

    def test_empty_filters(self):
        """Test empty filters produce empty params."""
        filters = InvariantFilters()
        params = filters.to_query_params()
        assert params == {}

    def test_all_filters(self):
        """Test all filters are converted to params."""
        filters = InvariantFilters(
            severity=InvariantSeverity.HIGH,
            enforcement_type=EnforcementType.GUARD,
            status=InvariantStatus.ACTIVE,
            search="acknowledgment",
        )

        params = filters.to_query_params()

        assert params["severity"] == "HIGH"
        assert params["enforcement_type"] == "guard"
        assert params["status"] == "active"
        assert params["search"] == "acknowledgment"

    def test_severity_values(self):
        """Test different severity levels."""
        for severity in InvariantSeverity:
            filters = InvariantFilters(severity=severity)
            params = filters.to_query_params()
            assert params["severity"] == severity.value

    def test_enforcement_values(self):
        """Test different enforcement types."""
        for enforcement in EnforcementType:
            filters = InvariantFilters(enforcement_type=enforcement)
            params = filters.to_query_params()
            assert params["enforcement_type"] == enforcement.value


class TestPaginationParams:
    """Tests for PaginationParams."""

    def test_default_values(self):
        """Test default pagination values."""
        pagination = PaginationParams()
        params = pagination.to_query_params()

        assert params["limit"] == 25
        assert "cursor" not in params

    def test_custom_values(self):
        """Test custom pagination values."""
        pagination = PaginationParams(cursor="abc123", limit=50)
        params = pagination.to_query_params()

        assert params["limit"] == 50
        assert params["cursor"] == "abc123"

    def test_limit_validation_min(self):
        """Test limit validation for minimum value."""
        with pytest.raises(ValueError, match="limit must be between 1 and 100"):
            PaginationParams(limit=0)

    def test_limit_validation_max(self):
        """Test limit validation for maximum value."""
        with pytest.raises(ValueError, match="limit must be between 1 and 100"):
            PaginationParams(limit=101)

    def test_limit_boundaries(self):
        """Test limit at valid boundaries."""
        min_pagination = PaginationParams(limit=1)
        assert min_pagination.limit == 1

        max_pagination = PaginationParams(limit=100)
        assert max_pagination.limit == 100

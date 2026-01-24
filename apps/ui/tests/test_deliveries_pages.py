"""Tests for Deliveries Explorer API endpoints.

Tests for the deliveries list and detail endpoints including:
- JSON response structure
- Filter functionality
- Pagination
- Detail endpoint data
- Error handling (404 for missing notification)

Note: These endpoints now return JSON for the React frontend.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.ui.app import create_ui_app
from mcp_server.read_models import (
    InMemoryReadModelAdapter,
    configure_read_model_adapter,
)
from notification.audit import (
    AuditRecord,
    InMemoryAuditStore,
)
from notification.models import (
    Channel,
    DeliveryStatus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audit_store() -> InMemoryAuditStore:
    """Create a fresh in-memory audit store."""
    return InMemoryAuditStore()


@pytest.fixture
def adapter(audit_store: InMemoryAuditStore) -> InMemoryReadModelAdapter:
    """Create a fresh adapter with the audit store."""
    adapter = InMemoryReadModelAdapter(audit_store=audit_store)
    configure_read_model_adapter(adapter)
    return adapter


@pytest.fixture
def client(adapter: InMemoryReadModelAdapter) -> TestClient:
    """Create a test client for the UI app."""
    app = create_ui_app()
    return TestClient(app)


def create_audit_record(
    notification_id=None,
    notification_type: str = "test.notification",
    status: DeliveryStatus = DeliveryStatus.DELIVERED,
    intent: str = "SAFETY",
    delivery_mode: str = "GUARANTEED",
    autonomy_mode: str = "LIVE",
    agent_id=None,
    channels_attempted: tuple[Channel, ...] = (Channel.SLACK,),
    channels_succeeded: tuple[Channel, ...] = (Channel.SLACK,),
    channels_failed: tuple[Channel, ...] = (),
    error_message: str | None = None,
    notification_created_at: datetime | None = None,
    delivered_at: datetime | None = None,
    correlation_id: str | None = None,
    plan_id=None,
    decision_snapshot_id=None,
    execution_snapshot_id=None,
    skip_snapshot_id=None,
) -> AuditRecord:
    """Factory function to create audit records for testing."""
    now = datetime.now(UTC)
    return AuditRecord(
        audit_id=uuid4(),
        notification_id=notification_id or uuid4(),
        notification_type=notification_type,
        status=status,
        channels_attempted=channels_attempted,
        channels_succeeded=channels_succeeded,
        channels_failed=channels_failed,
        error_message=error_message,
        intent=intent,
        delivery_mode=delivery_mode,
        autonomy_mode=autonomy_mode,
        agent_id=agent_id or uuid4(),
        plan_id=plan_id,
        decision_snapshot_id=decision_snapshot_id,
        execution_snapshot_id=execution_snapshot_id,
        skip_snapshot_id=skip_snapshot_id,
        title="Test Notification",
        source="test",
        correlation_id=correlation_id,
        metadata={},
        audit_metadata={},
        notification_created_at=notification_created_at or now,
        delivered_at=delivered_at or now,
        audit_created_at=now,
    )


# =============================================================================
# Test: Deliveries List Endpoint
# =============================================================================


class TestDeliveriesListEndpoint:
    """Tests for the deliveries list endpoint."""

    def test_list_endpoint_returns_json(self, client: TestClient):
        """Test list endpoint returns JSON successfully."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_list_endpoint_structure(self, client: TestClient):
        """Test list endpoint returns expected structure."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data
        assert "filters" in data
        assert "filter_options" in data
        assert isinstance(data["items"], list)

    def test_list_endpoint_filter_options(self, client: TestClient):
        """Test list endpoint includes filter options."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        filter_options = data["filter_options"]
        assert "status_options" in filter_options
        assert "intent_options" in filter_options
        assert "delivery_mode_options" in filter_options
        assert "autonomy_mode_options" in filter_options
        assert "channel_options" in filter_options
        # Verify some expected values
        assert "DELIVERED" in filter_options["status_options"]
        assert "SAFETY" in filter_options["intent_options"]

    def test_list_endpoint_empty_items(self, client: TestClient):
        """Test list endpoint returns empty items when no data."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["total_count"] == 0

    def test_list_endpoint_with_data(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test list endpoint returns delivery items."""
        # Create test data
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                notification_type="order.placed",
                status=DeliveryStatus.DELIVERED,
            )
        )

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["notification_type"] == "order.placed"
        assert item["status"] == "DELIVERED"

    def test_list_endpoint_multiple_items(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test list endpoint returns multiple delivery items."""
        for i in range(3):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_type=f"test.type_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3

    def test_list_endpoint_item_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test list endpoint item structure."""
        notif_id = uuid4()
        agent_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                notification_type="order.placed",
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                delivery_mode="GUARANTEED",
                autonomy_mode="LIVE",
                agent_id=agent_id,
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(Channel.SLACK,),
            )
        )

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert item["notification_id"] == str(notif_id)
        assert item["notification_type"] == "order.placed"
        assert item["intent"] == "SAFETY"
        assert item["delivery_mode"] == "GUARANTEED"
        assert item["status"] == "DELIVERED"
        assert item["autonomy_mode"] == "LIVE"
        assert item["agent_id"] == str(agent_id)
        assert "SLACK" in item["channels_attempted"]
        assert "EMAIL" in item["channels_attempted"]
        assert "SLACK" in item["channels_succeeded"]


class TestDeliveriesListFiltering:
    """Tests for filtering on the deliveries list endpoint."""

    def test_filter_by_status(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by status."""
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.FAILED))

        # Filter for DELIVERED
        response = client.get("/pages/deliveries/", params={"status": "DELIVERED"})
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert data["items"][0]["status"] == "DELIVERED"
        assert data["filters"]["status"] == "DELIVERED"

    def test_filter_by_intent(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by intent."""
        audit_store.save_delivery_audit(create_audit_record(intent="SAFETY"))
        audit_store.save_delivery_audit(create_audit_record(intent="INFORMATIONAL"))

        response = client.get("/pages/deliveries/", params={"intent": "SAFETY"})
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert data["items"][0]["intent"] == "SAFETY"

    def test_filter_by_autonomy_mode(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by autonomy mode."""
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="LIVE"))
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="PREVIEW"))

        response = client.get("/pages/deliveries/", params={"autonomy_mode": "LIVE"})
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert data["items"][0]["autonomy_mode"] == "LIVE"

    def test_filter_by_notification_type(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering by notification type."""
        audit_store.save_delivery_audit(create_audit_record(notification_type="order.placed"))
        audit_store.save_delivery_audit(create_audit_record(notification_type="payment.received"))

        response = client.get(
            "/pages/deliveries/",
            params={"notification_type": "order.placed"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert data["items"][0]["notification_type"] == "order.placed"

    def test_combined_filters(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test applying multiple filters."""
        # Create matching record
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                autonomy_mode="LIVE",
            )
        )
        # Create non-matching records
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.FAILED,
                intent="SAFETY",
                autonomy_mode="LIVE",
            )
        )
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                intent="INFORMATIONAL",
                autonomy_mode="PREVIEW",
            )
        )

        response = client.get(
            "/pages/deliveries/",
            params={
                "status": "DELIVERED",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_count"] == 1


class TestDeliveriesListPagination:
    """Tests for pagination on the deliveries list endpoint."""

    def test_pagination_total_count(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test pagination includes total count."""
        for i in range(5):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i)
                )
            )

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_count"] == 5

    def test_pagination_respects_limit(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test pagination respects limit parameter."""
        for i in range(10):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_type=f"type_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        response = client.get("/pages/deliveries/", params={"limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["pagination"]["has_more"] is True
        assert data["next_page_url"] is not None

    def test_pagination_cursor(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test pagination cursor works correctly."""
        for i in range(10):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i)
                )
            )

        response = client.get("/pages/deliveries/", params={"limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["next_cursor"] is not None


# =============================================================================
# Test: Deliveries Detail Endpoint
# =============================================================================


class TestDeliveriesDetailEndpoint:
    """Tests for the deliveries detail endpoint."""

    def test_detail_endpoint_returns_json(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns JSON successfully."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_detail_endpoint_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns expected structure."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert "notification_id" in data
        assert "notification_type" in data
        assert "intent" in data
        assert "delivery_mode" in data
        assert "status" in data
        assert "created_at" in data
        assert "attempts" in data
        assert "channels_attempted" in data
        assert "channels_succeeded" in data
        assert "channels_failed" in data
        assert "autonomy_context" in data

    def test_detail_endpoint_notification_id(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns correct notification ID."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["notification_id"] == str(notif_id)

    def test_detail_endpoint_notification_type(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns correct notification type."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                notification_type="order.shipped",
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["notification_type"] == "order.shipped"

    def test_detail_endpoint_status(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns correct status."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.DELIVERED,
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DELIVERED"

    def test_detail_endpoint_intent(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns correct intent."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                intent="GOVERNANCE",
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "GOVERNANCE"

    def test_detail_endpoint_autonomy_context(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns autonomy context."""
        notif_id = uuid4()
        agent_id = uuid4()
        plan_id = uuid4()

        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                autonomy_mode="LIVE",
                agent_id=agent_id,
                plan_id=plan_id,
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        ctx = data["autonomy_context"]
        assert ctx["autonomy_mode"] == "LIVE"
        assert ctx["agent_id"] == str(agent_id)
        assert ctx["plan_id"] == str(plan_id)

    def test_detail_endpoint_channel_results(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns channel results."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(Channel.SLACK,),
                channels_failed=(Channel.EMAIL,),
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert "SLACK" in data["channels_attempted"]
        assert "EMAIL" in data["channels_attempted"]
        assert "SLACK" in data["channels_succeeded"]
        assert "EMAIL" in data["channels_failed"]

    def test_detail_endpoint_delivery_attempts(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail endpoint returns delivery attempts."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(Channel.SLACK,),
                channels_failed=(Channel.EMAIL,),
                error_message="Email delivery failed",
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["attempts"], list)


class TestDeliveriesDetailErrors:
    """Tests for error handling on detail endpoint."""

    def test_detail_endpoint_404_for_missing_notification(self, client: TestClient):
        """Test detail endpoint returns 404 for non-existent notification."""
        fake_id = uuid4()
        response = client.get(f"/pages/deliveries/{fake_id}")
        assert response.status_code == 404

    def test_detail_endpoint_422_for_invalid_uuid(self, client: TestClient):
        """Test detail endpoint returns 422 for invalid UUID."""
        response = client.get("/pages/deliveries/not-a-valid-uuid")
        assert response.status_code == 422


# =============================================================================
# Test: Static Files
# =============================================================================


class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_file_served(self, client: TestClient):
        """Test CSS file is served correctly."""
        response = client.get("/static/css/main.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]


# =============================================================================
# Test: Navigation
# =============================================================================


class TestNavigation:
    """Tests for navigation endpoints."""

    def test_index_redirects_to_deliveries(self, client: TestClient):
        """Test index page redirects to deliveries."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert "/pages/deliveries/" in response.headers["location"]


# =============================================================================
# Test: API Client
# =============================================================================


class TestAPIClient:
    """Tests for the typed API client."""

    def test_client_import(self):
        """Test API client can be imported."""
        from apps.ui.src.api import UNSUIClient

        assert UNSUIClient is not None

    def test_types_import(self):
        """Test API types can be imported."""
        from apps.ui.src.api import (
            AutonomyContextResponse,
            DeliveryAttempt,
            DeliveryTimelineListResponse,
            DeliveryTimelineResponse,
            DeliveryTimelineSummary,
            ErrorResponse,
            PaginationInfo,
        )

        assert DeliveryTimelineListResponse is not None
        assert DeliveryTimelineResponse is not None
        assert DeliveryTimelineSummary is not None
        assert DeliveryAttempt is not None
        assert AutonomyContextResponse is not None
        assert PaginationInfo is not None
        assert ErrorResponse is not None

    def test_filter_params_to_query(self):
        """Test DeliveryFilterParams converts to query params."""
        from apps.ui.src.api.types import DeliveryFilterParams
        from notification.models import DeliveryStatus, NotificationIntent

        params = DeliveryFilterParams(
            status=DeliveryStatus.DELIVERED,
            intent=NotificationIntent.SAFETY,
            limit=10,
        )
        query = params.to_query_params()

        assert query["status"] == "DELIVERED"
        assert query["intent"] == "SAFETY"
        assert query["limit"] == "10"

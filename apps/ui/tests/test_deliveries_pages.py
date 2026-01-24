"""Tests for Deliveries Explorer UI pages.

Tests for the deliveries list and detail pages including:
- Page rendering with populated data
- Filter functionality
- Pagination
- Detail page display
- Error handling (404 for missing notification)
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
# Test: Deliveries List Page
# =============================================================================


class TestDeliveriesListPage:
    """Tests for the deliveries list page."""

    def test_list_page_renders(self, client: TestClient):
        """Test list page renders successfully."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_list_page_contains_title(self, client: TestClient):
        """Test list page contains expected title."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "Deliveries Explorer" in response.text

    def test_list_page_shows_empty_state(self, client: TestClient):
        """Test list page shows empty state when no data."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "No deliveries found" in response.text

    def test_list_page_shows_delivery_items(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test list page displays delivery items."""
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
        assert "order.placed" in response.text
        assert "DELIVERED" in response.text

    def test_list_page_shows_multiple_items(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test list page displays multiple delivery items."""
        for i in range(3):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_type=f"test.type_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "test.type_0" in response.text
        assert "test.type_1" in response.text
        assert "test.type_2" in response.text

    def test_list_page_contains_filter_form(self, client: TestClient):
        """Test list page contains filter form elements."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        # Check for filter dropdowns
        assert 'name="status"' in response.text
        assert 'name="intent"' in response.text
        assert 'name="delivery_mode"' in response.text
        assert 'name="autonomy_mode"' in response.text
        assert 'name="channel"' in response.text
        assert 'name="notification_type"' in response.text

    def test_list_page_links_to_detail(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test list page contains links to detail pages."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        # Should contain link to detail page
        assert f"/pages/deliveries/{notif_id}" in response.text


class TestDeliveriesListFiltering:
    """Tests for filtering on the deliveries list page."""

    def test_filter_by_status(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by status."""
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.FAILED))

        # Filter for DELIVERED
        response = client.get("/pages/deliveries/", params={"status": "DELIVERED"})
        assert response.status_code == 200
        # Should show DELIVERED status
        assert "DELIVERED" in response.text
        # Should show only 1 result (the DELIVERED one)
        assert "1 total result" in response.text

    def test_filter_by_intent(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by intent."""
        audit_store.save_delivery_audit(create_audit_record(intent="SAFETY"))
        audit_store.save_delivery_audit(create_audit_record(intent="INFORMATIONAL"))

        response = client.get("/pages/deliveries/", params={"intent": "SAFETY"})
        assert response.status_code == 200
        # Should show SAFETY notifications
        assert "SAFETY" in response.text

    def test_filter_by_autonomy_mode(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by autonomy mode."""
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="LIVE"))
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="PREVIEW"))

        response = client.get("/pages/deliveries/", params={"autonomy_mode": "LIVE"})
        assert response.status_code == 200
        assert "LIVE" in response.text

    def test_filter_by_notification_type(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering by notification type."""
        audit_store.save_delivery_audit(create_audit_record(notification_type="order.placed"))
        audit_store.save_delivery_audit(create_audit_record(notification_type="payment.received"))

        response = client.get(
            "/pages/deliveries/",
            params={"notification_type": "order.placed"},
        )
        assert response.status_code == 200
        assert "order.placed" in response.text

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
        # Should show only the matching record
        assert "1 total result" in response.text


class TestDeliveriesListPagination:
    """Tests for pagination on the deliveries list page."""

    def test_pagination_shows_total_count(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test pagination displays total count."""
        for i in range(5):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i)
                )
            )

        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "5 total results" in response.text

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
        # Should show next page link
        assert "Next Page" in response.text

    def test_pagination_next_page_link(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test next page link contains correct parameters."""
        for i in range(10):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i)
                )
            )

        response = client.get("/pages/deliveries/", params={"limit": 3})
        assert response.status_code == 200
        # Should contain cursor parameter in next page link
        assert "cursor=" in response.text


# =============================================================================
# Test: Deliveries Detail Page
# =============================================================================


class TestDeliveriesDetailPage:
    """Tests for the deliveries detail page."""

    def test_detail_page_renders(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test detail page renders successfully."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_detail_page_shows_notification_id(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail page displays notification ID."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert str(notif_id) in response.text

    def test_detail_page_shows_notification_type(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail page displays notification type."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                notification_type="order.shipped",
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert "order.shipped" in response.text

    def test_detail_page_shows_status(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test detail page displays status with badge."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.DELIVERED,
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert "DELIVERED" in response.text

    def test_detail_page_shows_intent(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test detail page displays intent."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                intent="GOVERNANCE",
            )
        )

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert "GOVERNANCE" in response.text

    def test_detail_page_shows_autonomy_context(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail page displays autonomy context."""
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
        assert "LIVE" in response.text
        assert str(agent_id) in response.text
        assert str(plan_id) in response.text

    def test_detail_page_shows_channel_results(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail page displays channel results."""
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
        assert "SLACK" in response.text
        assert "EMAIL" in response.text

    def test_detail_page_shows_delivery_attempts(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test detail page displays delivery attempts table."""
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
        assert "Delivery Attempts" in response.text
        # Should show attempt details
        assert "SUCCESS" in response.text
        assert "FAILED" in response.text

    def test_detail_page_shows_back_link(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test detail page has link back to list."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))

        response = client.get(f"/pages/deliveries/{notif_id}")
        assert response.status_code == 200
        assert "Back to List" in response.text
        assert "/pages/deliveries/" in response.text


class TestDeliveriesDetailErrors:
    """Tests for error handling on detail page."""

    def test_detail_page_404_for_missing_notification(self, client: TestClient):
        """Test detail page returns 404 for non-existent notification."""
        fake_id = uuid4()
        response = client.get(f"/pages/deliveries/{fake_id}")
        assert response.status_code == 404

    def test_detail_page_422_for_invalid_uuid(self, client: TestClient):
        """Test detail page returns 422 for invalid UUID."""
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
    """Tests for navigation elements."""

    def test_navbar_present(self, client: TestClient):
        """Test navbar is present on pages."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "UNS Dashboard" in response.text

    def test_navbar_links(self, client: TestClient):
        """Test navbar contains expected navigation links."""
        response = client.get("/pages/deliveries/")
        assert response.status_code == 200
        assert "/pages/deliveries/" in response.text

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

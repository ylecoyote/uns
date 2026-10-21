"""Tests for UI API routes.

Tests the read-only UI endpoints per ui-data-contracts.md:
- GET /ui/deliveries - List delivery timelines
- GET /ui/deliveries/{id} - Get single delivery timeline
- GET /ui/policies/effective - Get effective policy resolution
- GET /ui/invariants - List system invariants
- GET /ui/invariants/summary - Get invariant summary
- GET /ui/audit - List audit events

All endpoints are READ-ONLY.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agsignal.app import create_app
from notification.models import (
    Channel,
    DeliveryMode,
)
from notification.policies import (
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
)


@pytest.fixture
def client() -> TestClient:
    """Create a test client with fresh read model adapter."""
    # Reset the global read model adapter to ensure clean state
    from agsignal.api.read_models import InMemoryReadModelAdapter, configure_read_model_adapter
    from notification.audit import InMemoryAuditStore

    fresh_store = InMemoryAuditStore()
    fresh_adapter = InMemoryReadModelAdapter(audit_store=fresh_store)
    configure_read_model_adapter(fresh_adapter)

    app = create_app(skip_persistence_config=True)  # Explicit legacy read-model fixture
    app.state.agsignal_api_key = "test-key"
    return TestClient(app, headers={"Authorization": "Bearer test-key"})


@pytest.fixture
def policy_registry() -> PolicyRegistry:
    """Create a fresh policy registry for each test."""
    return configure_policy_registry()


class TestListDeliveries:
    """Tests for GET /ui/deliveries"""

    def test_list_deliveries_empty(self, client: TestClient):
        """Test listing deliveries returns empty list (stub)."""
        response = client.get("/ui/deliveries")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["has_more"] is False
        assert data["pagination"]["total_count"] == 0

    def test_list_deliveries_with_filters(self, client: TestClient):
        """Test listing deliveries with various filters."""
        response = client.get(
            "/ui/deliveries",
            params={
                "limit": 10,
                "status": "DELIVERED",
                "intent": "SAFETY",
                "delivery_mode": "GUARANTEED",
                "autonomy_mode": "LIVE",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data

    def test_list_deliveries_pagination_params(self, client: TestClient):
        """Test pagination parameters are accepted."""
        response = client.get(
            "/ui/deliveries",
            params={"cursor": "some-cursor", "limit": 50},
        )

        assert response.status_code == 200

    def test_list_deliveries_limit_bounds(self, client: TestClient):
        """Test limit parameter bounds."""
        # Min limit
        response = client.get("/ui/deliveries", params={"limit": 1})
        assert response.status_code == 200

        # Max limit
        response = client.get("/ui/deliveries", params={"limit": 100})
        assert response.status_code == 200

        # Over max
        response = client.get("/ui/deliveries", params={"limit": 101})
        assert response.status_code == 422  # Validation error

        # Under min
        response = client.get("/ui/deliveries", params={"limit": 0})
        assert response.status_code == 422


class TestGetDeliveryTimeline:
    """Tests for GET /ui/deliveries/{id}"""

    def test_get_delivery_not_found(self, client: TestClient):
        """Test getting non-existent delivery returns 404."""
        fake_id = uuid4()

        response = client.get(f"/ui/deliveries/{fake_id}")

        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["error"]["code"] == "not_found"

    def test_get_delivery_invalid_uuid(self, client: TestClient):
        """Test getting delivery with invalid UUID returns 422."""
        response = client.get("/ui/deliveries/not-a-uuid")

        assert response.status_code == 422


class TestGetEffectivePolicy:
    """Tests for GET /ui/policies/effective"""

    def test_get_effective_policy_no_policy(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test effective policy when no policy is registered."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check effective values use SDK defaults
        assert data["notification_type"] == "test.notification"
        assert data["effective"]["delivery_mode"] == "GUARANTEED"  # SAFETY -> GUARANTEED
        assert "SLACK" in data["effective"]["channels"]
        assert data["effective"]["require_ack"] is True  # SAFETY + LIVE -> True

        # Check resolution context
        assert data["resolution_context"]["policy_found"] is False
        assert data["resolution_context"]["intent"] == "SAFETY"
        assert data["resolution_context"]["autonomy_mode"] == "LIVE"

    def test_get_effective_policy_with_policy(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test effective policy when a policy is registered."""
        # Register a policy
        policy = NotificationPolicy(
            notification_type="trading.order_placed",
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.EMAIL, Channel.SLACK],
            require_ack=True,
            ack_timeout_minutes=10,
        )
        policy_registry.register(policy)

        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "trading.order_placed",
                "intent": "GOVERNANCE",
                "autonomy_mode": "LIVE",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check policy values are used
        assert data["resolution_context"]["policy_found"] is True
        assert data["effective"]["delivery_mode"] == "GUARANTEED"
        assert "EMAIL" in data["effective"]["channels"]
        assert "SLACK" in data["effective"]["channels"]

    def test_get_effective_policy_required_params(self, client: TestClient):
        """Test that required parameters are enforced."""
        # Missing notification_type
        response = client.get(
            "/ui/policies/effective",
            params={"intent": "SAFETY", "autonomy_mode": "LIVE"},
        )
        assert response.status_code == 422

        # Missing intent
        response = client.get(
            "/ui/policies/effective",
            params={"notification_type": "test", "autonomy_mode": "LIVE"},
        )
        assert response.status_code == 422

        # Missing autonomy_mode
        response = client.get(
            "/ui/policies/effective",
            params={"notification_type": "test", "intent": "SAFETY"},
        )
        assert response.status_code == 422

    def test_get_effective_policy_irreversible_adds_pagerduty(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test that irreversible=True adds PagerDuty for SAFETY in LIVE mode."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
                "irreversible": True,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # PagerDuty should be in channels for irreversible SAFETY in LIVE
        assert "PAGERDUTY" in data["effective"]["channels"]

    def test_get_effective_policy_preview_mode(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test effective policy in PREVIEW mode uses WebSocket only."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "PREVIEW",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # PREVIEW mode -> WebSocket only
        assert data["effective"]["channels"] == ["WEBSOCKET"]
        # SAFETY in PREVIEW -> require_ack is False (only True in LIVE)
        assert data["effective"]["require_ack"] is False


class TestListInvariants:
    """Tests for GET /ui/invariants"""

    def test_list_invariants_success(self, client: TestClient):
        """Test listing invariants returns data from YAML."""
        response = client.get("/ui/invariants")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data

        # Should have at least some invariants from the YAML
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "statement" in item
            assert "severity" in item
            assert "enforcement" in item

    def test_list_invariants_with_severity_filter(self, client: TestClient):
        """Test filtering invariants by severity."""
        response = client.get(
            "/ui/invariants",
            params={"severity": "HIGH"},
        )

        assert response.status_code == 200
        data = response.json()

        # All returned items should have HIGH severity
        for item in data["items"]:
            assert item["severity"] == "HIGH"

    def test_list_invariants_with_enforcement_filter(self, client: TestClient):
        """Test filtering invariants by enforcement type."""
        response = client.get(
            "/ui/invariants",
            params={"enforcement_type": "guard"},
        )

        assert response.status_code == 200
        data = response.json()

        # All returned items should have guard enforcement
        for item in data["items"]:
            assert item["enforcement"]["type"] == "guard"

    def test_list_invariants_with_status_filter(self, client: TestClient):
        """Test filtering invariants by status."""
        response = client.get(
            "/ui/invariants",
            params={"status": "active"},
        )

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["status"] == "active"

    def test_list_invariants_with_search(self, client: TestClient):
        """Test searching invariants by statement text."""
        response = client.get(
            "/ui/invariants",
            params={"search": "acknowledgment"},
        )

        assert response.status_code == 200
        data = response.json()

        # All returned items should contain "acknowledgment" in statement
        for item in data["items"]:
            assert "acknowledgment" in item["statement"].lower()

    def test_list_invariants_pagination(self, client: TestClient):
        """Test pagination parameters for invariants."""
        response = client.get(
            "/ui/invariants",
            params={"limit": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2


class TestInvariantsSummary:
    """Tests for GET /ui/invariants/summary"""

    def test_invariants_summary(self, client: TestClient):
        """Test invariants summary returns statistics."""
        response = client.get("/ui/invariants/summary")

        assert response.status_code == 200
        data = response.json()

        assert "total_count" in data
        assert "by_severity" in data
        assert "by_enforcement_type" in data
        assert "by_status" in data
        assert "exceptions_requiring_review" in data
        assert "last_updated" in data

        # Check structure of breakdowns
        assert "HIGH" in data["by_severity"]
        assert "MEDIUM" in data["by_severity"]
        assert "LOW" in data["by_severity"]

        assert "guard" in data["by_enforcement_type"]
        assert "isolation" in data["by_enforcement_type"]
        assert "test" in data["by_enforcement_type"]
        assert "exception" in data["by_enforcement_type"]

        assert "active" in data["by_status"]
        assert "inactive" in data["by_status"]


class TestListAuditEvents:
    """Tests for GET /ui/audit"""

    def test_list_audit_events_empty(self, client: TestClient):
        """Test listing audit events returns empty list (stub)."""
        response = client.get("/ui/audit")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["has_more"] is False

    def test_list_audit_events_with_filters(self, client: TestClient):
        """Test listing audit events with various filters."""
        response = client.get(
            "/ui/audit",
            params={
                "limit": 10,
                "event_type": "notification.created",
                "autonomy_mode": "LIVE",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data

    def test_list_audit_events_pagination(self, client: TestClient):
        """Test pagination parameters for audit events."""
        response = client.get(
            "/ui/audit",
            params={"cursor": "some-cursor", "limit": 50},
        )

        assert response.status_code == 200


class TestUIEndpointsAreReadOnly:
    """Tests to verify all UI endpoints are read-only."""

    def test_deliveries_no_post(self, client: TestClient):
        """Verify POST is not allowed on deliveries."""
        response = client.post("/ui/deliveries", json={})
        assert response.status_code == 405

    def test_deliveries_no_put(self, client: TestClient):
        """Verify PUT is not allowed on deliveries."""
        response = client.put(f"/ui/deliveries/{uuid4()}", json={})
        assert response.status_code == 405

    def test_deliveries_no_delete(self, client: TestClient):
        """Verify DELETE is not allowed on deliveries."""
        response = client.delete(f"/ui/deliveries/{uuid4()}")
        assert response.status_code == 405

    def test_policies_no_post(self, client: TestClient):
        """Verify POST is not allowed on policies endpoint."""
        response = client.post("/ui/policies/effective", json={})
        assert response.status_code == 405

    def test_invariants_no_post(self, client: TestClient):
        """Verify POST is not allowed on invariants."""
        response = client.post("/ui/invariants", json={})
        assert response.status_code == 405

    def test_audit_no_post(self, client: TestClient):
        """Verify POST is not allowed on audit."""
        response = client.post("/ui/audit", json={})
        assert response.status_code == 405

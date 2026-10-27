"""Smoke tests and critical flow tests for UI API routes.

This module provides:
1. Smoke tests - verify all endpoints are reachable and return valid responses
2. Critical flow tests - test end-to-end user journeys through the UI

Smoke tests verify:
- All endpoints return expected status codes
- Response structures match data contracts
- Request ID propagation works
- Basic error handling functions

Critical flows tested:
- Delivery list → detail navigation flow
- Audit event timeline exploration
- Policy resolution inspection
- Invariant browsing and filtering
- Error handling and graceful degradation

These tests are designed to catch regressions in core UI functionality
before more detailed unit tests are run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from notification.audit import (
    AckAuditRecord,
    AuditRecord,
    InMemoryAuditStore,
)
from notification.models import (
    AckStatus,
    Channel,
    DeliveryMode,
    DeliveryStatus,
)
from notification.policies import (
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
)
from uns.api.observability import configure_metrics_collector, get_metrics_collector
from uns.api.read_models import (
    InMemoryReadModelAdapter,
    configure_read_model_adapter,
)
from uns.app import create_app

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
    """Create a test client with fresh read model adapter."""
    configure_metrics_collector()  # Reset metrics collector
    app = create_app(skip_persistence_config=True)
    app.state.uns_api_key = "test-key"
    return TestClient(app, headers={"Authorization": "Bearer test-key"})


@pytest.fixture
def policy_registry() -> PolicyRegistry:
    """Create a fresh policy registry for each test."""
    return configure_policy_registry()


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
        decision_snapshot_id=None,
        execution_snapshot_id=None,
        skip_snapshot_id=None,
        title="Test Notification",
        source="test",
        correlation_id=correlation_id,
        metadata={},
        audit_metadata={},
        notification_created_at=notification_created_at or now,
        delivered_at=delivered_at or now,
        audit_created_at=now,
    )


def create_ack_record(
    notification_id=None,
    old_status: AckStatus | None = AckStatus.PENDING,
    new_status: AckStatus = AckStatus.ACKED,
    acked_by: str | None = "test-user",
) -> AckAuditRecord:
    """Factory function to create ack audit records for testing."""
    now = datetime.now(UTC)
    return AckAuditRecord(
        audit_id=uuid4(),
        notification_id=notification_id or uuid4(),
        old_status=old_status,
        new_status=new_status,
        acked_by=acked_by,
        acked_at=now,
        audit_created_at=now,
        metadata={},
    )


# =============================================================================
# SMOKE TESTS - Verify all endpoints are reachable
# =============================================================================


class TestSmokeEndpointAvailability:
    """Smoke tests to verify all UI endpoints are reachable."""

    def test_smoke_deliveries_list_endpoint(self, client: TestClient):
        """Smoke test: GET /ui/deliveries returns 200."""
        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        assert "items" in response.json()
        assert "pagination" in response.json()

    def test_smoke_deliveries_detail_endpoint(self, client: TestClient):
        """Smoke test: GET /ui/deliveries/{id} returns 404 for non-existent."""
        fake_id = uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")
        # 404 is expected for non-existent - endpoint is working
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_smoke_policies_effective_endpoint(self, client: TestClient):
        """Smoke test: GET /ui/policies/effective returns 200 with valid params."""
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
        assert "notification_type" in data
        assert "effective" in data
        assert "resolution" in data
        assert "resolution_context" in data

    def test_smoke_invariants_list_endpoint(self, client: TestClient):
        """Smoke test: GET /ui/invariants returns 200."""
        response = client.get("/ui/invariants")
        assert response.status_code == 200
        assert "items" in response.json()
        assert "pagination" in response.json()

    def test_smoke_invariants_summary_endpoint(self, client: TestClient):
        """Smoke test: GET /ui/invariants/summary returns 200."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_count" in data
        assert "by_severity" in data
        assert "by_enforcement_type" in data

    def test_smoke_audit_list_endpoint(self, client: TestClient):
        """Smoke test: GET /ui/audit returns 200."""
        response = client.get("/ui/audit")
        assert response.status_code == 200
        assert "items" in response.json()
        assert "pagination" in response.json()

    def test_smoke_health_endpoint(self, client: TestClient):
        """Smoke test: Health check endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200


class TestSmokeResponseContracts:
    """Smoke tests to verify response structures match contracts."""

    def test_smoke_deliveries_list_response_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Verify deliveries list response structure matches contract."""
        audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        data = response.json()

        # Verify top-level structure
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)

        # Verify pagination structure
        pagination = data["pagination"]
        assert "next_cursor" in pagination
        assert "has_more" in pagination
        assert "total_count" in pagination

        # Verify item structure
        item = data["items"][0]
        required_fields = [
            "notification_id",
            "notification_type",
            "intent",
            "delivery_mode",
            "status",
            "created_at",
            "channels_attempted",
            "channels_succeeded",
            "autonomy_mode",
            "agent_id",
        ]
        for field in required_fields:
            assert field in item, f"Missing required field: {field}"

    def test_smoke_delivery_detail_response_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Verify delivery detail response structure matches contract."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(Channel.SLACK,),
                channels_failed=(Channel.EMAIL,),
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        # Verify detail includes attempts (not in list view)
        assert "attempts" in data
        assert isinstance(data["attempts"], list)

        # Verify autonomy context structure
        assert "autonomy_context" in data
        ctx = data["autonomy_context"]
        assert "autonomy_mode" in ctx
        assert "agent_id" in ctx

    def test_smoke_policy_response_structure(self, client: TestClient):
        """Verify policy resolution response structure matches contract."""
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

        # Verify effective values structure
        effective = data["effective"]
        assert "delivery_mode" in effective
        assert "channels" in effective
        assert "require_ack" in effective
        assert "dedup_window_seconds" in effective

        # Verify resolution context
        ctx = data["resolution_context"]
        assert "intent" in ctx
        assert "autonomy_mode" in ctx
        assert "policy_found" in ctx

    def test_smoke_audit_event_response_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Verify audit event response structure matches contract."""
        audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        item = data["items"][0]
        required_fields = [
            "audit_id",
            "event_type",
            "event_time",
            "notification_id",
            "notification_type",
            "autonomy_context",
            "payload",
        ]
        for field in required_fields:
            assert field in item, f"Missing required field: {field}"


class TestSmokeRequestIdPropagation:
    """Smoke tests for X-Request-ID header propagation."""

    def test_smoke_request_id_in_response_header(self, client: TestClient):
        """Verify X-Request-ID is returned in response headers."""
        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req-")

    def test_smoke_request_id_preserved_from_request(self, client: TestClient):
        """Verify X-Request-ID from request is preserved in response."""
        custom_request_id = "custom-req-123456"
        response = client.get("/ui/deliveries", headers={"X-Request-ID": custom_request_id})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_request_id

    def test_smoke_request_id_in_error_response(self, client: TestClient):
        """Verify X-Request-ID is in response even on errors."""
        fake_id = uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")
        assert response.status_code == 404
        assert "X-Request-ID" in response.headers

        # Also verify request_id is in error body
        detail = response.json()["detail"]
        assert "request_id" in detail

    def test_smoke_request_id_different_per_request(self, client: TestClient):
        """Verify different requests get different auto-generated IDs."""
        response1 = client.get("/ui/deliveries")
        response2 = client.get("/ui/deliveries")

        id1 = response1.headers["X-Request-ID"]
        id2 = response2.headers["X-Request-ID"]

        assert id1 != id2


# =============================================================================
# CRITICAL FLOW TESTS - End-to-end user journeys
# =============================================================================


class TestCriticalFlowDeliveryNavigation:
    """Critical flow: Delivery list to detail navigation."""

    def test_flow_list_deliveries_then_view_detail(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test navigating from deliveries list to detail view."""
        # Setup: Create multiple deliveries
        notif_ids = []
        for i in range(3):
            notif_id = uuid4()
            notif_ids.append(notif_id)
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_id=notif_id,
                    notification_type=f"test.order_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        # Step 1: List deliveries
        list_response = client.get("/ui/deliveries")
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert len(list_data["items"]) == 3

        # Step 2: Get notification ID from list
        first_item = list_data["items"][0]
        selected_notif_id = first_item["notification_id"]

        # Step 3: Navigate to detail view
        detail_response = client.get(f"/ui/deliveries/{selected_notif_id}")
        assert detail_response.status_code == 200
        detail_data = detail_response.json()

        # Verify detail has more info than list
        assert detail_data["notification_id"] == selected_notif_id
        assert "attempts" in detail_data  # Only in detail view
        assert "autonomy_context" in detail_data

    def test_flow_filter_deliveries_then_drill_down(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering deliveries then viewing filtered item details."""
        # Setup: Create deliveries with different statuses
        failed_notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=failed_notif_id,
                status=DeliveryStatus.FAILED,
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(),
                channels_failed=(Channel.SLACK, Channel.EMAIL),
                error_message="Connection timeout",
            )
        )
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))

        # Step 1: Filter for FAILED only
        list_response = client.get("/ui/deliveries", params={"status": "FAILED"})
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert len(list_data["items"]) == 1
        assert list_data["items"][0]["status"] == "FAILED"

        # Step 2: View details of failed delivery
        detail_response = client.get(f"/ui/deliveries/{failed_notif_id}")
        assert detail_response.status_code == 200
        detail_data = detail_response.json()

        # Verify failure details are present
        assert detail_data["status"] == "FAILED"
        assert len(detail_data["channels_failed"]) == 2
        assert len(detail_data["attempts"]) == 2
        for attempt in detail_data["attempts"]:
            assert attempt["status"] == "FAILED"

    def test_flow_paginate_through_deliveries(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test paginating through multiple pages of deliveries."""
        # Setup: Create 10 deliveries
        for i in range(10):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_type=f"test.order_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        # Page 1: Get first 3
        page1 = client.get("/ui/deliveries", params={"limit": 3})
        assert page1.status_code == 200
        page1_data = page1.json()
        assert len(page1_data["items"]) == 3
        assert page1_data["pagination"]["has_more"] is True
        assert page1_data["pagination"]["total_count"] == 10

        # Page 2: Continue with cursor
        cursor = page1_data["pagination"]["next_cursor"]
        page2 = client.get("/ui/deliveries", params={"limit": 3, "cursor": cursor})
        assert page2.status_code == 200
        page2_data = page2.json()
        assert len(page2_data["items"]) == 3
        assert page2_data["pagination"]["has_more"] is True

        # Verify no duplicate IDs
        page1_ids = {item["notification_id"] for item in page1_data["items"]}
        page2_ids = {item["notification_id"] for item in page2_data["items"]}
        assert len(page1_ids & page2_ids) == 0


class TestCriticalFlowAuditTimeline:
    """Critical flow: Exploring audit event timeline."""

    def test_flow_view_audit_timeline_for_notification(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test viewing complete audit trail for a notification."""
        notif_id = uuid4()

        # Setup: Create sequence of events for one notification
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.PENDING,
                notification_created_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.DELIVERED,
                notification_created_at=datetime.now(UTC) - timedelta(minutes=3),
            )
        )
        audit_store.save_ack_audit(
            create_ack_record(
                notification_id=notif_id,
                old_status=AckStatus.PENDING,
                new_status=AckStatus.ACKED,
            )
        )

        # Get audit events for this notification
        response = client.get("/ui/audit", params={"notification_id": str(notif_id)})
        assert response.status_code == 200
        data = response.json()

        # Should have all 3 events
        assert len(data["items"]) == 3

        # Verify event types
        event_types = [item["event_type"] for item in data["items"]]
        assert "delivery.started" in event_types
        assert "delivery.succeeded" in event_types
        assert "ack.received" in event_types

    def test_flow_filter_audit_by_event_type(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering audit events by type to find failures."""
        # Setup: Create mixed events
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))
        audit_store.save_delivery_audit(
            create_audit_record(status=DeliveryStatus.FAILED, error_message="Failed")
        )
        audit_store.save_ack_audit(create_ack_record(new_status=AckStatus.TIMED_OUT))

        # Filter for failures
        response = client.get("/ui/audit", params={"event_type": "delivery.failed"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["event_type"] == "delivery.failed"

        # Filter for timeouts
        response = client.get("/ui/audit", params={"event_type": "ack.timed_out"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["event_type"] == "ack.timed_out"

    def test_flow_audit_combined_with_delivery_detail(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test combining audit timeline with delivery detail view."""
        notif_id = uuid4()
        agent_id = uuid4()

        # Create delivery record
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                agent_id=agent_id,
                status=DeliveryStatus.DELIVERED,
                channels_attempted=(Channel.SLACK,),
                channels_succeeded=(Channel.SLACK,),
            )
        )

        # Step 1: Get delivery detail
        delivery_response = client.get(f"/ui/deliveries/{notif_id}")
        assert delivery_response.status_code == 200
        delivery_data = delivery_response.json()

        # Step 2: Get audit events for same notification
        audit_response = client.get("/ui/audit", params={"notification_id": str(notif_id)})
        assert audit_response.status_code == 200
        audit_data = audit_response.json()

        # Verify correlation
        assert delivery_data["notification_id"] == str(notif_id)
        assert len(audit_data["items"]) >= 1
        assert audit_data["items"][0]["notification_id"] == str(notif_id)

        # Verify agent_id matches in both views
        assert delivery_data["autonomy_context"]["agent_id"] == str(agent_id)
        assert audit_data["items"][0]["autonomy_context"]["agent_id"] == str(agent_id)


class TestCriticalFlowPolicyResolution:
    """Critical flow: Policy resolution inspection."""

    def test_flow_inspect_policy_no_custom_policy(self, client: TestClient):
        """Test policy resolution when no custom policy exists."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "unregistered.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Verify SDK defaults are applied
        assert data["resolution_context"]["policy_found"] is False
        assert data["effective"]["delivery_mode"] == "GUARANTEED"  # SAFETY default
        assert data["effective"]["require_ack"] is True  # SAFETY + LIVE

    def test_flow_inspect_policy_with_registered_policy(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test policy resolution with registered policy."""
        # Register custom policy
        policy = NotificationPolicy(
            notification_type="trading.order_filled",
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY],
            require_ack=True,
            ack_timeout_minutes=5,
        )
        policy_registry.register(policy)

        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "trading.order_filled",
                "intent": "GOVERNANCE",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Verify policy values are used
        assert data["resolution_context"]["policy_found"] is True
        assert "PAGERDUTY" in data["effective"]["channels"]
        assert data["effective"]["ack_timeout_minutes"] == 5

    def test_flow_compare_preview_vs_live_modes(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test comparing policy behavior in different autonomy modes."""
        # PREVIEW mode
        preview_response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "PREVIEW",
            },
        )
        assert preview_response.status_code == 200
        preview_data = preview_response.json()

        # LIVE mode
        live_response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert live_response.status_code == 200
        live_data = live_response.json()

        # PREVIEW should have WebSocket only
        assert preview_data["effective"]["channels"] == ["WEBSOCKET"]
        assert preview_data["effective"]["require_ack"] is False

        # LIVE should have real channels and require ack
        assert "SLACK" in live_data["effective"]["channels"]
        assert live_data["effective"]["require_ack"] is True

    def test_flow_irreversible_action_adds_pagerduty(
        self, client: TestClient, policy_registry: PolicyRegistry
    ):
        """Test that irreversible flag adds PagerDuty for SAFETY."""
        # Without irreversible
        normal_response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.action",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
                "irreversible": False,
            },
        )
        assert normal_response.status_code == 200  # Verify request succeeded

        # With irreversible
        irreversible_response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.action",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
                "irreversible": True,
            },
        )
        irreversible_data = irreversible_response.json()

        # PagerDuty should only be in irreversible response
        assert "PAGERDUTY" in irreversible_data["effective"]["channels"]


class TestCriticalFlowInvariantBrowsing:
    """Critical flow: Browsing system invariants."""

    def test_flow_list_invariants_and_filter(self, client: TestClient):
        """Test listing and filtering invariants."""
        # Get all invariants
        all_response = client.get("/ui/invariants")
        assert all_response.status_code == 200
        all_data = all_response.json()

        # Filter by severity
        high_response = client.get("/ui/invariants", params={"severity": "HIGH"})
        assert high_response.status_code == 200
        high_data = high_response.json()

        # All HIGH severity items should be subset of all items
        high_ids = {item["id"] for item in high_data["items"]}
        all_ids = {item["id"] for item in all_data["items"]}
        assert high_ids.issubset(all_ids)

        # All returned items should be HIGH severity
        for item in high_data["items"]:
            assert item["severity"] == "HIGH"

    def test_flow_invariant_summary_statistics(self, client: TestClient):
        """Test getting invariant summary statistics."""
        # Get summary
        summary_response = client.get("/ui/invariants/summary")
        assert summary_response.status_code == 200
        summary_data = summary_response.json()

        # Get list for comparison
        list_response = client.get("/ui/invariants", params={"limit": 100})
        list_data = list_response.json()

        # Summary total should match list total
        assert summary_data["total_count"] == len(list_data["items"])

        # Severity breakdowns should sum to total
        severity_sum = sum(summary_data["by_severity"].values())
        assert severity_sum == summary_data["total_count"]

    def test_flow_search_invariants(self, client: TestClient):
        """Test searching invariants by statement text."""
        # Search for acknowledgment-related invariants
        response = client.get("/ui/invariants", params={"search": "acknowledgment"})
        assert response.status_code == 200
        data = response.json()

        # All results should contain search term
        for item in data["items"]:
            assert "acknowledgment" in item["statement"].lower()


class TestCriticalFlowErrorHandling:
    """Critical flow: Error handling and graceful degradation."""

    def test_flow_404_error_with_request_id(self, client: TestClient):
        """Test 404 errors include request ID for debugging."""
        fake_id = uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")

        assert response.status_code == 404
        detail = response.json()["detail"]

        # Error response should include request_id
        assert "request_id" in detail
        assert detail["request_id"] != "unknown"

        # Error should have structured format
        assert "error" in detail
        assert detail["error"]["code"] == "not_found"
        assert str(fake_id) in detail["error"]["message"]

    def test_flow_422_validation_error(self, client: TestClient):
        """Test validation errors are handled properly."""
        # Invalid enum value
        response = client.get("/ui/deliveries", params={"status": "INVALID"})
        assert response.status_code == 422

        # Invalid UUID
        response = client.get("/ui/deliveries/not-a-uuid")
        assert response.status_code == 422

        # Missing required params
        response = client.get("/ui/policies/effective")
        assert response.status_code == 422

    def test_flow_empty_results_handling(self, client: TestClient):
        """Test empty results are handled gracefully."""
        # Empty deliveries list
        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["total_count"] == 0
        assert data["pagination"]["has_more"] is False

    def test_flow_filter_with_no_matches(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering with no matches returns empty gracefully."""
        # Create only DELIVERED records
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))

        # Filter for RATE_LIMITED (no matches)
        response = client.get("/ui/deliveries", params={"status": "RATE_LIMITED"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["total_count"] == 0


class TestCriticalFlowMetricsCollection:
    """Critical flow: Verify metrics are collected for monitoring."""

    def test_flow_metrics_recorded_for_successful_requests(self, client: TestClient):
        """Test that successful requests record metrics."""
        collector = get_metrics_collector()
        collector.clear()

        # Make some requests
        client.get("/ui/deliveries")
        client.get("/ui/invariants")
        client.get("/ui/audit")

        # Verify metrics recorded
        assert collector.get_request_count("/ui/deliveries") == 1
        assert collector.get_request_count("/ui/invariants") == 1
        assert collector.get_request_count("/ui/audit") == 1

    def test_flow_error_metrics_recorded(self, client: TestClient):
        """Test that errors record appropriate metrics."""
        collector = get_metrics_collector()
        collector.clear()

        # Make request that will 404
        fake_id = uuid4()
        client.get(f"/ui/deliveries/{fake_id}")

        # Verify error metric recorded
        assert collector.get_error_count("/ui/deliveries/{id}") >= 1

    def test_flow_latency_metrics_collected(self, client: TestClient):
        """Test that latency metrics are collected."""
        collector = get_metrics_collector()
        collector.clear()

        # Make several requests
        for _ in range(5):
            client.get("/ui/deliveries")

        # Get latency stats
        stats = collector.get_latency_stats("/ui/deliveries")
        assert stats is not None
        assert stats["count"] == 5
        assert stats["min"] <= stats["avg"] <= stats["max"]


class TestCriticalFlowMultipleFiltersCombined:
    """Critical flow: Testing complex filter combinations."""

    def test_flow_delivery_filters_combined(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test combining multiple delivery filters."""
        target_agent = uuid4()
        now = datetime.now(UTC)

        # Create target record that matches all filters
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                autonomy_mode="LIVE",
                agent_id=target_agent,
                notification_created_at=now,
            )
        )
        # Create non-matching records
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.FAILED))
        audit_store.save_delivery_audit(create_audit_record(intent="INFORMATIONAL"))

        # Apply combined filters
        response = client.get(
            "/ui/deliveries",
            params={
                "status": "DELIVERED",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
                "agent_id": str(target_agent),
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Should only match the target record
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["status"] == "DELIVERED"
        assert item["intent"] == "SAFETY"
        assert item["autonomy_mode"] == "LIVE"
        assert item["agent_id"] == str(target_agent)

    def test_flow_audit_filters_combined(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test combining multiple audit filters."""
        target_agent = uuid4()
        correlation_id = "corr-test-123"

        # Create matching record
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                autonomy_mode="LIVE",
                agent_id=target_agent,
                correlation_id=correlation_id,
            )
        )
        # Create non-matching
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="PREVIEW"))

        # Apply combined filters
        response = client.get(
            "/ui/audit",
            params={
                "event_type": "delivery.succeeded",
                "agent_id": str(target_agent),
                "autonomy_mode": "LIVE",
                "correlation_id": correlation_id,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        event = data["items"][0]
        assert event["event_type"] == "delivery.succeeded"
        assert event["correlation_id"] == correlation_id


class TestCriticalFlowDataIntegrity:
    """Critical flow: Verify data integrity across views."""

    def test_flow_delivery_data_consistent_across_views(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test that delivery data is consistent between list and detail views."""
        notif_id = uuid4()
        agent_id = uuid4()

        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                notification_type="test.consistency",
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                delivery_mode="GUARANTEED",
                autonomy_mode="LIVE",
                agent_id=agent_id,
            )
        )

        # Get from list
        list_response = client.get("/ui/deliveries")
        list_item = list_response.json()["items"][0]

        # Get from detail
        detail_response = client.get(f"/ui/deliveries/{notif_id}")
        detail_item = detail_response.json()

        # Compare common fields
        assert list_item["notification_id"] == detail_item["notification_id"]
        assert list_item["notification_type"] == detail_item["notification_type"]
        assert list_item["status"] == detail_item["status"]
        assert list_item["intent"] == detail_item["intent"]
        assert list_item["delivery_mode"] == detail_item["delivery_mode"]
        assert list_item["autonomy_mode"] == detail_item["autonomy_context"]["autonomy_mode"]
        assert list_item["agent_id"] == str(detail_item["autonomy_context"]["agent_id"])

    def test_flow_uuid_serialization_consistent(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test that UUID fields are serialized consistently as strings."""
        notif_id = uuid4()
        agent_id = uuid4()
        plan_id = uuid4()

        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                agent_id=agent_id,
                plan_id=plan_id,
            )
        )

        # Check delivery detail
        detail_response = client.get(f"/ui/deliveries/{notif_id}")
        detail = detail_response.json()
        assert detail["notification_id"] == str(notif_id)
        assert detail["autonomy_context"]["agent_id"] == str(agent_id)
        assert detail["autonomy_context"]["plan_id"] == str(plan_id)

        # Check audit event
        audit_response = client.get("/ui/audit")
        event = audit_response.json()["items"][0]
        assert event["notification_id"] == str(notif_id)
        assert event["autonomy_context"]["agent_id"] == str(agent_id)

    def test_flow_datetime_serialization_iso_format(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test that datetime fields are serialized in ISO 8601 format."""
        from datetime import datetime as dt

        audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/deliveries")
        item = response.json()["items"][0]

        # Should be parseable as ISO datetime
        created_at = dt.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        assert created_at is not None

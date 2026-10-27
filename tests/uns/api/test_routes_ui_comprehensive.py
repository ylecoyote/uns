"""Comprehensive tests for UI API routes.

Tests filtering, pagination, authorization boundaries, and response shape mapping
for the read-only UI endpoints per ui-data-contracts.md.

Focus areas:
- Filtering and pagination with populated data
- Authorization boundaries (read-only enforcement)
- Correct mapping of delivery attempts/escalations to response shapes
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
    DeliveryStatus,
)
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
    # Skip automatic persistence configuration to use our manually configured adapter
    app = create_app(skip_persistence_config=True)
    app.state.uns_api_key = "test-key"
    return TestClient(app, headers={"Authorization": "Bearer test-key"})


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


def create_ack_audit_record(
    notification_id=None,
    old_status: AckStatus | None = AckStatus.PENDING,
    new_status: AckStatus = AckStatus.ACKED,
    acked_by: str | None = "test-user",
    acked_at: datetime | None = None,
) -> AckAuditRecord:
    """Factory function to create ack audit records for testing."""
    now = datetime.now(UTC)
    return AckAuditRecord(
        audit_id=uuid4(),
        notification_id=notification_id or uuid4(),
        old_status=old_status,
        new_status=new_status,
        acked_by=acked_by,
        acked_at=acked_at or now,
        audit_created_at=now,
        metadata={},
    )


# =============================================================================
# Test: Filtering for Deliveries
# =============================================================================


class TestDeliveryFiltering:
    """Tests for delivery filtering functionality."""

    def test_filter_by_status(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by status."""
        # Create records with different statuses
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.FAILED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))

        # Filter for DELIVERED only
        response = client.get("/ui/deliveries", params={"status": "DELIVERED"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["status"] == "DELIVERED"

        # Filter for FAILED only
        response = client.get("/ui/deliveries", params={"status": "FAILED"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "FAILED"

    def test_filter_by_intent(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by intent."""
        audit_store.save_delivery_audit(create_audit_record(intent="SAFETY"))
        audit_store.save_delivery_audit(create_audit_record(intent="GOVERNANCE"))
        audit_store.save_delivery_audit(create_audit_record(intent="INFORMATIONAL"))

        response = client.get("/ui/deliveries", params={"intent": "SAFETY"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["intent"] == "SAFETY"

    def test_filter_by_delivery_mode(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by delivery mode."""
        audit_store.save_delivery_audit(create_audit_record(delivery_mode="GUARANTEED"))
        audit_store.save_delivery_audit(create_audit_record(delivery_mode="BEST_EFFORT"))
        audit_store.save_delivery_audit(create_audit_record(delivery_mode="GUARANTEED"))

        response = client.get("/ui/deliveries", params={"delivery_mode": "BEST_EFFORT"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["delivery_mode"] == "BEST_EFFORT"

    def test_filter_by_autonomy_mode(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by autonomy mode."""
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="LIVE"))
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="PREVIEW"))
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="SHADOW"))

        response = client.get("/ui/deliveries", params={"autonomy_mode": "PREVIEW"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["autonomy_mode"] == "PREVIEW"

    def test_filter_by_agent_id(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by agent ID."""
        agent_1 = uuid4()
        agent_2 = uuid4()

        audit_store.save_delivery_audit(create_audit_record(agent_id=agent_1))
        audit_store.save_delivery_audit(create_audit_record(agent_id=agent_1))
        audit_store.save_delivery_audit(create_audit_record(agent_id=agent_2))

        response = client.get("/ui/deliveries", params={"agent_id": str(agent_1)})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["agent_id"] == str(agent_1)

    def test_filter_by_notification_type(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by notification type."""
        audit_store.save_delivery_audit(
            create_audit_record(notification_type="trading.order_placed")
        )
        audit_store.save_delivery_audit(
            create_audit_record(notification_type="trading.order_cancelled")
        )
        audit_store.save_delivery_audit(create_audit_record(notification_type="system.alert"))

        response = client.get(
            "/ui/deliveries", params={"notification_type": "trading.order_placed"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["notification_type"] == "trading.order_placed"

    def test_filter_by_channel(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by channel attempted."""
        audit_store.save_delivery_audit(create_audit_record(channels_attempted=(Channel.SLACK,)))
        audit_store.save_delivery_audit(create_audit_record(channels_attempted=(Channel.EMAIL,)))
        audit_store.save_delivery_audit(
            create_audit_record(channels_attempted=(Channel.SLACK, Channel.EMAIL))
        )

        response = client.get("/ui/deliveries", params={"channel": "EMAIL"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert "EMAIL" in item["channels_attempted"]

    def test_filter_by_time_range(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering deliveries by time range."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)
        three_days_ago = now - timedelta(days=3)

        audit_store.save_delivery_audit(create_audit_record(notification_created_at=now))
        audit_store.save_delivery_audit(create_audit_record(notification_created_at=yesterday))
        audit_store.save_delivery_audit(create_audit_record(notification_created_at=three_days_ago))

        # Filter: created in last 2 days
        response = client.get(
            "/ui/deliveries",
            params={
                "start_time": two_days_ago.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2  # now and yesterday

    def test_combined_filters(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test multiple filters combined."""
        agent_id = uuid4()

        # Target: DELIVERED + SAFETY + LIVE + specific agent
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                autonomy_mode="LIVE",
                agent_id=agent_id,
            )
        )
        # Non-match: wrong status
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.FAILED,
                intent="SAFETY",
                autonomy_mode="LIVE",
                agent_id=agent_id,
            )
        )
        # Non-match: wrong intent
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                intent="INFORMATIONAL",
                autonomy_mode="LIVE",
                agent_id=agent_id,
            )
        )
        # Non-match: wrong agent
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                autonomy_mode="LIVE",
                agent_id=uuid4(),
            )
        )

        response = client.get(
            "/ui/deliveries",
            params={
                "status": "DELIVERED",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
                "agent_id": str(agent_id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_filter_returns_empty_when_no_matches(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering returns empty list when no matches."""
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))

        response = client.get("/ui/deliveries", params={"status": "RATE_LIMITED"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["total_count"] == 0


# =============================================================================
# Test: Pagination for Deliveries
# =============================================================================


class TestDeliveryPagination:
    """Tests for delivery pagination functionality."""

    def test_pagination_basic(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test basic pagination with limit."""
        # Create 10 records
        for i in range(10):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i)
                )
            )

        # Request first page with limit 3
        response = client.get("/ui/deliveries", params={"limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["pagination"]["has_more"] is True
        assert data["pagination"]["total_count"] == 10
        assert data["pagination"]["next_cursor"] is not None

    def test_pagination_cursor_navigation(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test navigating through pages using cursors."""
        # Create 7 records with distinct times
        for i in range(7):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_type=f"type_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        # Page 1
        response = client.get("/ui/deliveries", params={"limit": 3})
        assert response.status_code == 200
        page1 = response.json()
        assert len(page1["items"]) == 3
        assert page1["pagination"]["has_more"] is True
        cursor1 = page1["pagination"]["next_cursor"]

        # Page 2
        response = client.get("/ui/deliveries", params={"limit": 3, "cursor": cursor1})
        assert response.status_code == 200
        page2 = response.json()
        assert len(page2["items"]) == 3
        assert page2["pagination"]["has_more"] is True
        cursor2 = page2["pagination"]["next_cursor"]

        # Page 3 (last page)
        response = client.get("/ui/deliveries", params={"limit": 3, "cursor": cursor2})
        assert response.status_code == 200
        page3 = response.json()
        assert len(page3["items"]) == 1  # Only 1 remaining
        assert page3["pagination"]["has_more"] is False
        assert page3["pagination"]["next_cursor"] is None

        # Verify no duplicates across pages
        all_ids = [item["notification_id"] for item in page1["items"]]
        all_ids += [item["notification_id"] for item in page2["items"]]
        all_ids += [item["notification_id"] for item in page3["items"]]
        assert len(all_ids) == len(set(all_ids))  # All unique

    def test_pagination_with_filters(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test pagination combined with filtering."""
        # Create mixed records
        for i in range(10):
            status = DeliveryStatus.DELIVERED if i % 2 == 0 else DeliveryStatus.FAILED
            audit_store.save_delivery_audit(
                create_audit_record(
                    status=status,
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        # Filter for DELIVERED only, paginate
        response = client.get("/ui/deliveries", params={"status": "DELIVERED", "limit": 2})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["pagination"]["total_count"] == 5  # 5 DELIVERED records
        assert data["pagination"]["has_more"] is True

        for item in data["items"]:
            assert item["status"] == "DELIVERED"

    def test_pagination_limit_validation(self, client: TestClient):
        """Test pagination limit bounds validation."""
        # Min limit (1)
        response = client.get("/ui/deliveries", params={"limit": 1})
        assert response.status_code == 200

        # Max limit (100)
        response = client.get("/ui/deliveries", params={"limit": 100})
        assert response.status_code == 200

        # Over max (101)
        response = client.get("/ui/deliveries", params={"limit": 101})
        assert response.status_code == 422

        # Under min (0)
        response = client.get("/ui/deliveries", params={"limit": 0})
        assert response.status_code == 422

        # Negative
        response = client.get("/ui/deliveries", params={"limit": -1})
        assert response.status_code == 422

    def test_pagination_invalid_cursor_handled_gracefully(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test that invalid cursors are handled gracefully."""
        audit_store.save_delivery_audit(create_audit_record())

        # Invalid cursor should not crash - adapter handles gracefully
        response = client.get("/ui/deliveries", params={"cursor": "not-a-valid-cursor"})
        assert response.status_code == 200

    def test_pagination_total_count_accuracy(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test total_count is accurate across pages."""
        for _ in range(15):
            audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/deliveries", params={"limit": 5})
        data = response.json()
        assert data["pagination"]["total_count"] == 15

        # Navigate to next page - total_count should be consistent
        cursor = data["pagination"]["next_cursor"]
        response = client.get("/ui/deliveries", params={"limit": 5, "cursor": cursor})
        data = response.json()
        assert data["pagination"]["total_count"] == 15


# =============================================================================
# Test: Audit Event Filtering and Pagination
# =============================================================================


class TestAuditEventFiltering:
    """Tests for audit event filtering functionality."""

    def test_filter_audit_by_event_type(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering audit events by event type."""
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DELIVERED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.FAILED))
        audit_store.save_delivery_audit(create_audit_record(status=DeliveryStatus.DEDUPLICATED))

        response = client.get("/ui/audit", params={"event_type": "delivery.succeeded"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["event_type"] == "delivery.succeeded"

    def test_filter_audit_by_notification_id(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering audit events by notification ID."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))
        audit_store.save_delivery_audit(create_audit_record())
        audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/audit", params={"notification_id": str(notif_id)})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["notification_id"] == str(notif_id)

    def test_filter_audit_by_autonomy_mode(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering audit events by autonomy mode."""
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="LIVE"))
        audit_store.save_delivery_audit(create_audit_record(autonomy_mode="PREVIEW"))

        response = client.get("/ui/audit", params={"autonomy_mode": "LIVE"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["autonomy_context"]["autonomy_mode"] == "LIVE"

    def test_filter_audit_by_correlation_id(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test filtering audit events by correlation ID."""
        corr_id = "corr-123-abc"
        audit_store.save_delivery_audit(create_audit_record(correlation_id=corr_id))
        audit_store.save_delivery_audit(create_audit_record(correlation_id="other-corr"))

        response = client.get("/ui/audit", params={"correlation_id": corr_id})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["correlation_id"] == corr_id

    def test_audit_includes_ack_events(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test audit endpoint includes ack events."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(create_audit_record(notification_id=notif_id))
        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notif_id,
                old_status=AckStatus.PENDING,
                new_status=AckStatus.ACKED,
            )
        )

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        event_types = [item["event_type"] for item in data["items"]]
        assert "delivery.succeeded" in event_types
        assert "ack.received" in event_types

    def test_filter_ack_events_by_type(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering for ack events specifically."""
        audit_store.save_delivery_audit(create_audit_record())
        audit_store.save_ack_audit(create_ack_audit_record(new_status=AckStatus.ACKED))
        audit_store.save_ack_audit(create_ack_audit_record(new_status=AckStatus.TIMED_OUT))

        response = client.get("/ui/audit", params={"event_type": "ack.timed_out"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["event_type"] == "ack.timed_out"

    def test_audit_pagination(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test audit event pagination."""
        for _ in range(10):
            audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/audit", params={"limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["pagination"]["has_more"] is True
        assert data["pagination"]["total_count"] == 10


# =============================================================================
# Test: Authorization Boundaries (Read-Only)
# =============================================================================


class TestAuthorizationBoundaries:
    """Tests for read-only authorization enforcement."""

    def test_deliveries_post_not_allowed(self, client: TestClient):
        """POST /ui/deliveries should return 405."""
        response = client.post("/ui/deliveries", json={"data": "test"})
        assert response.status_code == 405

    def test_deliveries_put_not_allowed(self, client: TestClient):
        """PUT /ui/deliveries/{id} should return 405."""
        response = client.put(f"/ui/deliveries/{uuid4()}", json={"data": "test"})
        assert response.status_code == 405

    def test_deliveries_delete_not_allowed(self, client: TestClient):
        """DELETE /ui/deliveries/{id} should return 405."""
        response = client.delete(f"/ui/deliveries/{uuid4()}")
        assert response.status_code == 405

    def test_deliveries_patch_not_allowed(self, client: TestClient):
        """PATCH /ui/deliveries/{id} should return 405."""
        response = client.patch(f"/ui/deliveries/{uuid4()}", json={"data": "test"})
        assert response.status_code == 405

    def test_policies_post_not_allowed(self, client: TestClient):
        """POST /ui/policies/effective should return 405."""
        response = client.post("/ui/policies/effective", json={})
        assert response.status_code == 405

    def test_policies_put_not_allowed(self, client: TestClient):
        """PUT /ui/policies/effective should return 405."""
        response = client.put("/ui/policies/effective", json={})
        assert response.status_code == 405

    def test_policies_delete_not_allowed(self, client: TestClient):
        """DELETE /ui/policies/effective should return 405."""
        response = client.delete("/ui/policies/effective")
        assert response.status_code == 405

    def test_invariants_post_not_allowed(self, client: TestClient):
        """POST /ui/invariants should return 405."""
        response = client.post("/ui/invariants", json={})
        assert response.status_code == 405

    def test_invariants_put_not_allowed(self, client: TestClient):
        """PUT /ui/invariants should return 405."""
        response = client.put("/ui/invariants", json={})
        assert response.status_code == 405

    def test_invariants_delete_not_allowed(self, client: TestClient):
        """DELETE /ui/invariants should return 405."""
        response = client.delete("/ui/invariants")
        assert response.status_code == 405

    def test_invariants_summary_post_not_allowed(self, client: TestClient):
        """POST /ui/invariants/summary should return 405."""
        response = client.post("/ui/invariants/summary", json={})
        assert response.status_code == 405

    def test_audit_post_not_allowed(self, client: TestClient):
        """POST /ui/audit should return 405."""
        response = client.post("/ui/audit", json={})
        assert response.status_code == 405

    def test_audit_put_not_allowed(self, client: TestClient):
        """PUT /ui/audit should return 405."""
        response = client.put("/ui/audit", json={})
        assert response.status_code == 405

    def test_audit_delete_not_allowed(self, client: TestClient):
        """DELETE /ui/audit should return 405."""
        response = client.delete("/ui/audit")
        assert response.status_code == 405

    def test_all_endpoints_allow_get(self, client: TestClient):
        """Verify all UI endpoints allow GET requests."""
        # deliveries
        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        # policies/effective (requires params)
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200

        # invariants
        response = client.get("/ui/invariants")
        assert response.status_code == 200

        # invariants/summary
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200

        # audit
        response = client.get("/ui/audit")
        assert response.status_code == 200


# =============================================================================
# Test: Response Shape Mapping (Delivery Attempts & Escalations)
# =============================================================================


class TestDeliveryAttemptResponseMapping:
    """Tests for correct mapping of delivery attempts to response shapes."""

    def test_delivery_timeline_attempts_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery timeline includes properly structured attempts."""
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

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        # Verify attempts list
        assert "attempts" in data
        assert len(data["attempts"]) == 2

        # Find slack attempt
        slack_attempt = next((a for a in data["attempts"] if a["channel"] == "SLACK"), None)
        assert slack_attempt is not None
        assert slack_attempt["status"] == "SUCCESS"
        assert "attempt_id" in slack_attempt
        assert "started_at" in slack_attempt
        assert "completed_at" in slack_attempt
        assert "duration_ms" in slack_attempt

        # Find email attempt
        email_attempt = next((a for a in data["attempts"] if a["channel"] == "EMAIL"), None)
        assert email_attempt is not None
        assert email_attempt["status"] == "FAILED"
        assert email_attempt["error_message"] == "Email delivery failed"

    def test_delivery_timeline_channels_lists(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery timeline includes correct channel lists."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                channels_attempted=(Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY),
                channels_succeeded=(Channel.SLACK, Channel.EMAIL),
                channels_failed=(Channel.PAGERDUTY,),
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        assert set(data["channels_attempted"]) == {"SLACK", "EMAIL", "PAGERDUTY"}
        assert set(data["channels_succeeded"]) == {"SLACK", "EMAIL"}
        assert data["channels_failed"] == ["PAGERDUTY"]

    def test_delivery_timeline_autonomy_context(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery timeline includes full autonomy context."""
        notif_id = uuid4()
        agent_id = uuid4()
        plan_id = uuid4()
        decision_id = uuid4()
        execution_id = uuid4()
        skip_id = uuid4()

        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                autonomy_mode="LIVE",
                agent_id=agent_id,
                plan_id=plan_id,
                decision_snapshot_id=decision_id,
                execution_snapshot_id=execution_id,
                skip_snapshot_id=skip_id,
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        ctx = data["autonomy_context"]
        assert ctx["autonomy_mode"] == "LIVE"
        assert ctx["agent_id"] == str(agent_id)
        assert ctx["plan_id"] == str(plan_id)
        assert ctx["decision_snapshot_id"] == str(decision_id)
        assert ctx["execution_snapshot_id"] == str(execution_id)
        assert ctx["skip_snapshot_id"] == str(skip_id)

    def test_delivery_summary_in_list_response(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery list returns correct summary shape."""
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_type="test.order",
                status=DeliveryStatus.DELIVERED,
                intent="SAFETY",
                delivery_mode="GUARANTEED",
                autonomy_mode="LIVE",
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(Channel.SLACK,),
            )
        )

        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        item = data["items"][0]

        # Verify summary fields
        assert "notification_id" in item
        assert item["notification_type"] == "test.order"
        assert item["status"] == "DELIVERED"
        assert item["intent"] == "SAFETY"
        assert item["delivery_mode"] == "GUARANTEED"
        assert item["autonomy_mode"] == "LIVE"
        assert "created_at" in item
        assert "channels_attempted" in item
        assert "channels_succeeded" in item
        assert "agent_id" in item

        # Summary should NOT include attempts (that's only in detail view)
        assert "attempts" not in item


class TestAuditEventResponseMapping:
    """Tests for correct mapping of audit events to response shapes."""

    def test_delivery_audit_event_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery audit event has correct structure."""
        notif_id = uuid4()
        agent_id = uuid4()
        plan_id = uuid4()

        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                notification_type="test.notification",
                status=DeliveryStatus.DELIVERED,
                autonomy_mode="LIVE",
                agent_id=agent_id,
                plan_id=plan_id,
                channels_attempted=(Channel.SLACK,),
                channels_succeeded=(Channel.SLACK,),
                correlation_id="corr-123",
            )
        )

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        event = data["items"][0]

        # Core fields
        assert "audit_id" in event
        assert event["event_type"] == "delivery.succeeded"
        assert "event_time" in event
        assert event["notification_id"] == str(notif_id)
        assert event["notification_type"] == "test.notification"
        assert event["correlation_id"] == "corr-123"

        # Autonomy context
        ctx = event["autonomy_context"]
        assert ctx["autonomy_mode"] == "LIVE"
        assert ctx["agent_id"] == str(agent_id)
        assert ctx["plan_id"] == str(plan_id)

        # Payload
        payload = event["payload"]
        assert payload["status"] == "DELIVERED"
        assert "channels_attempted" in payload
        assert "channels_succeeded" in payload

    def test_ack_audit_event_structure(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test ack audit event has correct structure."""
        notif_id = uuid4()
        ack_time = datetime.now(UTC)

        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notif_id,
                old_status=AckStatus.PENDING,
                new_status=AckStatus.ACKED,
                acked_by="user@example.com",
                acked_at=ack_time,
            )
        )

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        event = data["items"][0]

        assert "audit_id" in event
        assert event["event_type"] == "ack.received"
        assert "event_time" in event
        assert event["notification_id"] == str(notif_id)

        # Payload
        payload = event["payload"]
        assert payload["old_status"] == "PENDING"
        assert payload["new_status"] == "ACKED"
        assert payload["acked_by"] == "user@example.com"
        assert "acked_at" in payload

    def test_escalation_event_from_ack_timeout(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test ack timeout event (basis for escalation detection)."""
        notif_id = uuid4()

        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notif_id,
                old_status=AckStatus.PENDING,
                new_status=AckStatus.TIMED_OUT,
            )
        )

        response = client.get("/ui/audit", params={"event_type": "ack.timed_out"})
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        event = data["items"][0]
        assert event["event_type"] == "ack.timed_out"
        assert event["payload"]["new_status"] == "TIMED_OUT"

    def test_event_types_derived_correctly(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test all delivery status values map to correct event types."""
        status_event_mapping = [
            (DeliveryStatus.DELIVERED, "delivery.succeeded"),
            (DeliveryStatus.FAILED, "delivery.failed"),
            (DeliveryStatus.DEDUPLICATED, "delivery.deduplicated"),
            (DeliveryStatus.RATE_LIMITED, "delivery.rate_limited"),
            (DeliveryStatus.PENDING, "delivery.started"),
        ]

        for status, _ in status_event_mapping:
            audit_store.save_delivery_audit(create_audit_record(status=status))

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        event_types = [item["event_type"] for item in data["items"]]
        for _, expected_event in status_event_mapping:
            assert expected_event in event_types

    def test_ack_status_event_types(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test all ack status values map to correct event types."""
        ack_event_mapping = [
            (AckStatus.ACKED, "ack.received"),
            (AckStatus.DISMISSED, "ack.dismissed"),
            (AckStatus.TIMED_OUT, "ack.timed_out"),
            (AckStatus.PENDING, "ack.pending"),
        ]

        for status, _ in ack_event_mapping:
            audit_store.save_ack_audit(
                create_ack_audit_record(
                    old_status=None,
                    new_status=status,
                )
            )

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        event_types = [item["event_type"] for item in data["items"]]
        for _, expected_event in ack_event_mapping:
            assert expected_event in event_types


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and responses."""

    def test_delivery_not_found_returns_404(self, client: TestClient):
        """Test getting non-existent delivery returns proper 404."""
        fake_id = uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")

        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["error"]["code"] == "not_found"
        assert str(fake_id) in detail["error"]["message"]

    def test_invalid_uuid_returns_422(self, client: TestClient):
        """Test invalid UUID format returns 422 validation error."""
        response = client.get("/ui/deliveries/not-a-uuid")
        assert response.status_code == 422

    def test_invalid_enum_value_returns_422(self, client: TestClient):
        """Test invalid enum value returns 422 validation error."""
        response = client.get("/ui/deliveries", params={"status": "INVALID_STATUS"})
        assert response.status_code == 422

        response = client.get("/ui/deliveries", params={"intent": "INVALID_INTENT"})
        assert response.status_code == 422

    def test_missing_required_params_returns_422(self, client: TestClient):
        """Test missing required parameters returns 422."""
        # effective policy requires all params
        response = client.get("/ui/policies/effective")
        assert response.status_code == 422

        # Missing intent
        response = client.get(
            "/ui/policies/effective",
            params={"notification_type": "test", "autonomy_mode": "LIVE"},
        )
        assert response.status_code == 422


# =============================================================================
# Test: Response Structure Validation
# =============================================================================


# =============================================================================
# Test: Audit Event Filtering and Pagination (Additional)
# =============================================================================


class TestAuditEventFilteringAdditional:
    """Additional tests for audit event filtering functionality."""

    def test_filter_audit_by_agent_id(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering audit events by agent ID."""
        target_agent = uuid4()
        other_agent = uuid4()

        audit_store.save_delivery_audit(create_audit_record(agent_id=target_agent))
        audit_store.save_delivery_audit(create_audit_record(agent_id=target_agent))
        audit_store.save_delivery_audit(create_audit_record(agent_id=other_agent))

        response = client.get("/ui/audit", params={"agent_id": str(target_agent)})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["autonomy_context"]["agent_id"] == str(target_agent)

    def test_filter_audit_by_time_range(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test filtering audit events by time range."""
        # The audit time filter uses audit_created_at which is set internally
        # We need to test with distinct times that we control
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)

        # Create one record
        audit_store.save_delivery_audit(create_audit_record())

        # Filter: time range that includes the record
        response = client.get(
            "/ui/audit",
            params={
                "start_time": (now - timedelta(minutes=1)).isoformat(),
                "end_time": future.isoformat(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # Filter: time range in the future (should return nothing)
        response = client.get(
            "/ui/audit",
            params={
                "start_time": future.isoformat(),
                "end_time": (future + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_audit_pagination_cursor_navigation(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test navigating audit events using cursors."""
        # Create 7 records
        for i in range(7):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_type=f"type_{i}",
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i),
                )
            )

        # Page 1
        response = client.get("/ui/audit", params={"limit": 3})
        assert response.status_code == 200
        page1 = response.json()
        assert len(page1["items"]) == 3
        assert page1["pagination"]["has_more"] is True
        cursor1 = page1["pagination"]["next_cursor"]

        # Page 2
        response = client.get("/ui/audit", params={"limit": 3, "cursor": cursor1})
        assert response.status_code == 200
        page2 = response.json()
        assert len(page2["items"]) == 3
        assert page2["pagination"]["has_more"] is True
        cursor2 = page2["pagination"]["next_cursor"]

        # Page 3 (last page)
        response = client.get("/ui/audit", params={"limit": 3, "cursor": cursor2})
        assert response.status_code == 200
        page3 = response.json()
        assert len(page3["items"]) == 1
        assert page3["pagination"]["has_more"] is False
        assert page3["pagination"]["next_cursor"] is None

        # Verify no duplicates across pages
        all_ids = [item["audit_id"] for item in page1["items"]]
        all_ids += [item["audit_id"] for item in page2["items"]]
        all_ids += [item["audit_id"] for item in page3["items"]]
        assert len(all_ids) == len(set(all_ids))

    def test_filter_audit_combined_filters(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test combining multiple audit filters."""
        target_agent = uuid4()
        now = datetime.now(UTC)

        # Target record: matches all filters
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                agent_id=target_agent,
                autonomy_mode="LIVE",
                notification_created_at=now,
            )
        )
        # Non-match: wrong status
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.FAILED,
                agent_id=target_agent,
                autonomy_mode="LIVE",
                notification_created_at=now,
            )
        )
        # Non-match: wrong agent
        audit_store.save_delivery_audit(
            create_audit_record(
                status=DeliveryStatus.DELIVERED,
                agent_id=uuid4(),
                autonomy_mode="LIVE",
                notification_created_at=now,
            )
        )

        response = client.get(
            "/ui/audit",
            params={
                "event_type": "delivery.succeeded",
                "agent_id": str(target_agent),
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1


# =============================================================================
# Test: Authorization Boundaries (Additional)
# =============================================================================


class TestAuthorizationBoundariesAdditional:
    """Additional tests for read-only authorization enforcement."""

    def test_audit_patch_not_allowed(self, client: TestClient):
        """PATCH /ui/audit should return 405."""
        response = client.patch("/ui/audit", json={"data": "test"})
        assert response.status_code == 405

    def test_deliveries_detail_post_not_allowed(self, client: TestClient):
        """POST /ui/deliveries/{id} should return 405."""
        response = client.post(f"/ui/deliveries/{uuid4()}", json={"data": "test"})
        assert response.status_code == 405

    def test_invariants_summary_patch_not_allowed(self, client: TestClient):
        """PATCH /ui/invariants/summary should return 405."""
        response = client.patch("/ui/invariants/summary", json={})
        assert response.status_code == 405

    def test_invariants_summary_delete_not_allowed(self, client: TestClient):
        """DELETE /ui/invariants/summary should return 405."""
        response = client.delete("/ui/invariants/summary")
        assert response.status_code == 405

    def test_policies_patch_not_allowed(self, client: TestClient):
        """PATCH /ui/policies/effective should return 405."""
        response = client.patch("/ui/policies/effective", json={})
        assert response.status_code == 405

    def test_no_mutations_via_query_params(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Verify read endpoints don't accidentally mutate data via query params."""
        # Create initial record
        audit_store.save_delivery_audit(create_audit_record())
        initial_count = len(audit_store.delivery_audits)

        # Make various read requests with unusual params
        client.get("/ui/deliveries", params={"_method": "DELETE"})
        client.get("/ui/deliveries", params={"action": "delete"})
        client.get("/ui/audit", params={"_destroy": "true"})

        # Verify no mutations occurred
        assert len(audit_store.delivery_audits) == initial_count


# =============================================================================
# Test: Response Shape Mapping (Additional)
# =============================================================================


class TestDeliveryAttemptResponseMappingAdditional:
    """Additional tests for delivery attempts to response shapes."""

    def test_delivery_with_rate_limited_channel(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery with rate-limited channel in attempts."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.RATE_LIMITED,
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(),
                channels_failed=(),
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "RATE_LIMITED"
        assert len(data["attempts"]) == 2

    def test_delivery_with_deduplicated_status(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery with deduplicated status."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.DEDUPLICATED,
                channels_attempted=(),
                channels_succeeded=(),
                channels_failed=(),
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "DEDUPLICATED"
        assert data["attempts"] == []  # No attempts for deduplicated

    def test_delivery_timeline_null_optional_fields(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery timeline handles null optional fields correctly."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                plan_id=None,
                decision_snapshot_id=None,
                execution_snapshot_id=None,
                skip_snapshot_id=None,
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        ctx = data["autonomy_context"]
        assert ctx["plan_id"] is None
        assert ctx["decision_snapshot_id"] is None
        assert ctx["execution_snapshot_id"] is None
        assert ctx["skip_snapshot_id"] is None

    def test_delivery_with_all_channels_failed(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test delivery where all channels failed."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.FAILED,
                channels_attempted=(Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY),
                channels_succeeded=(),
                channels_failed=(Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY),
                error_message="All channels failed",
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "FAILED"
        assert len(data["channels_attempted"]) == 3
        assert len(data["channels_succeeded"]) == 0
        assert len(data["channels_failed"]) == 3
        assert len(data["attempts"]) == 3

        for attempt in data["attempts"]:
            assert attempt["status"] == "FAILED"
            assert attempt["error_message"] is not None


class TestAuditEventResponseMappingAdditional:
    """Additional tests for audit event response shapes."""

    def test_escalation_triggered_from_timeout(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test that ack timeouts can indicate escalation events."""
        notif_id = uuid4()

        # First, create a delivery for SAFETY intent (would require ack)
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                intent="SAFETY",
                status=DeliveryStatus.DELIVERED,
            )
        )

        # Then create ack timeout (escalation trigger)
        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notif_id,
                old_status=AckStatus.PENDING,
                new_status=AckStatus.TIMED_OUT,
            )
        )

        # Query for timeout events
        response = client.get("/ui/audit", params={"event_type": "ack.timed_out"})
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        event = data["items"][0]
        assert event["event_type"] == "ack.timed_out"
        assert event["notification_id"] == str(notif_id)
        assert event["payload"]["new_status"] == "TIMED_OUT"
        assert event["payload"]["old_status"] == "PENDING"

    def test_audit_event_payload_contains_channel_info(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test audit event payload includes channel information."""
        audit_store.save_delivery_audit(
            create_audit_record(
                channels_attempted=(Channel.SLACK, Channel.EMAIL),
                channels_succeeded=(Channel.SLACK,),
                channels_failed=(Channel.EMAIL,),
                error_message="Email gateway timeout",
            )
        )

        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        event = data["items"][0]
        payload = event["payload"]

        assert "channels_attempted" in payload
        assert "channels_succeeded" in payload
        assert "channels_failed" in payload
        assert "error_message" in payload
        assert set(payload["channels_attempted"]) == {"SLACK", "EMAIL"}
        assert payload["channels_succeeded"] == ["SLACK"]
        assert payload["channels_failed"] == ["EMAIL"]
        assert payload["error_message"] == "Email gateway timeout"

    def test_ack_dismissed_event_structure(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test dismissed acknowledgment event structure."""
        notif_id = uuid4()

        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notif_id,
                old_status=AckStatus.PENDING,
                new_status=AckStatus.DISMISSED,
                acked_by="admin@example.com",
            )
        )

        response = client.get("/ui/audit", params={"event_type": "ack.dismissed"})
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        event = data["items"][0]
        assert event["event_type"] == "ack.dismissed"
        assert event["payload"]["new_status"] == "DISMISSED"
        assert event["payload"]["acked_by"] == "admin@example.com"


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_channels_list(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test handling of empty channels list."""
        notif_id = uuid4()
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.DEDUPLICATED,
                channels_attempted=(),
                channels_succeeded=(),
                channels_failed=(),
            )
        )

        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["channels_attempted"] == []
        assert data["channels_succeeded"] == []
        assert data["channels_failed"] == []
        assert data["attempts"] == []

    def test_large_pagination_request(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test pagination with max limit."""
        # Create 100 records
        for i in range(100):
            audit_store.save_delivery_audit(
                create_audit_record(
                    notification_created_at=datetime.now(UTC) - timedelta(minutes=i)
                )
            )

        response = client.get("/ui/deliveries", params={"limit": 100})
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 100
        assert data["pagination"]["total_count"] == 100
        assert data["pagination"]["has_more"] is False

    def test_filter_with_no_data(self, client: TestClient):
        """Test filtering on empty database returns empty results."""
        response = client.get(
            "/ui/deliveries",
            params={
                "status": "DELIVERED",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["items"] == []
        assert data["pagination"]["total_count"] == 0
        assert data["pagination"]["has_more"] is False

    def test_multiple_records_same_notification_id(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test handling multiple audit records for same notification."""
        notif_id = uuid4()

        # Create multiple records for same notification (e.g., status changes)
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.PENDING,
                notification_created_at=datetime.now(UTC) - timedelta(minutes=2),
            )
        )
        audit_store.save_delivery_audit(
            create_audit_record(
                notification_id=notif_id,
                status=DeliveryStatus.DELIVERED,
                notification_created_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )

        # Get timeline should return the most recent
        response = client.get(f"/ui/deliveries/{notif_id}")
        assert response.status_code == 200
        data = response.json()

        # Should get most recent record (DELIVERED)
        assert data["status"] == "DELIVERED"

    def test_special_characters_in_notification_type(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test notification types with special characters."""
        special_type = "app.trading/order:created"
        audit_store.save_delivery_audit(create_audit_record(notification_type=special_type))

        response = client.get("/ui/deliveries", params={"notification_type": special_type})
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        assert data["items"][0]["notification_type"] == special_type


class TestResponseStructure:
    """Tests validating response structures match contracts."""

    def test_pagination_info_structure(self, client: TestClient, audit_store: InMemoryAuditStore):
        """Test pagination info matches expected structure."""
        for _ in range(5):
            audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/deliveries", params={"limit": 2})
        data = response.json()

        pagination = data["pagination"]
        assert "next_cursor" in pagination
        assert "has_more" in pagination
        assert "total_count" in pagination
        assert isinstance(pagination["has_more"], bool)
        assert isinstance(pagination["total_count"], int)

    def test_list_response_structure(self, client: TestClient):
        """Test list responses have items and pagination."""
        # Deliveries
        response = client.get("/ui/deliveries")
        data = response.json()
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)

        # Invariants
        response = client.get("/ui/invariants")
        data = response.json()
        assert "items" in data
        assert "pagination" in data

        # Audit
        response = client.get("/ui/audit")
        data = response.json()
        assert "items" in data
        assert "pagination" in data

    def test_datetime_fields_are_iso_format(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test datetime fields are returned in ISO 8601 format."""
        audit_store.save_delivery_audit(create_audit_record())

        response = client.get("/ui/deliveries")
        data = response.json()
        item = data["items"][0]

        # Should be parseable as ISO datetime
        from datetime import datetime as dt

        created_at = dt.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        assert created_at is not None

    def test_uuid_fields_are_string_format(
        self, client: TestClient, audit_store: InMemoryAuditStore
    ):
        """Test UUID fields are returned as string format."""
        notif_id = uuid4()
        agent_id = uuid4()

        audit_store.save_delivery_audit(
            create_audit_record(notification_id=notif_id, agent_id=agent_id)
        )

        response = client.get("/ui/deliveries")
        data = response.json()
        item = data["items"][0]

        # Should be string representation of UUID
        assert item["notification_id"] == str(notif_id)
        assert item["agent_id"] == str(agent_id)

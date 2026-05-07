"""Tests for notification API routes.

Tests the ack/status endpoints per PRD Task 10:
- POST /v1/notifications/{id}/ack
- POST /v1/notifications/{id}/dismiss
- GET /v1/notifications/{id}
- GET /v1/notifications/{id}/ack-status
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mcp_server.app import create_app
from notification.acknowledgment import (
    InMemoryAckStorage,
    configure_ack_engine,
)
from notification.audit import AckAuditRecord, AuditPersistenceError, AuditRecord, AuditStore
from notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Notification,
    NotificationIntent,
)


class FailingAckAuditStore(AuditStore):
    """Audit store that fails ack writes for rollback tests."""

    def save_delivery_audit(self, record: AuditRecord) -> None:
        return None

    def save_ack_audit(self, record: AckAuditRecord) -> None:
        raise AuditPersistenceError("ack audit failed", record=record)

    def get_delivery_audits_for_notification(self, notification_id):
        return []

    def get_ack_audits_for_notification(self, notification_id):
        return []


@pytest.fixture
def storage() -> InMemoryAckStorage:
    """Create a fresh in-memory storage for each test."""
    return InMemoryAckStorage()


@pytest.fixture
def engine(storage: InMemoryAckStorage):
    """Configure the ack engine with test storage."""
    return configure_ack_engine(storage=storage)


@pytest.fixture
def client(engine) -> TestClient:
    """Create a test client with configured engine."""
    app = create_app()
    app.state.agsignal_api_key = "test-key"
    app.state.agsignal_api_principal = "test_user"
    return TestClient(app, headers={"Authorization": "Bearer test-key"})


@pytest.fixture
def sample_notification() -> Notification:
    """Create a sample notification for testing."""
    return Notification(
        notification_type="test.notification",
        intent=NotificationIntent.SAFETY,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
        title="Test Notification",
        message="This is a test notification message.",
        source="test_suite",
        require_ack=True,
    )


def register_notification_with_engine(engine, notification: Notification) -> None:
    """Helper to register a notification with the ack engine."""
    engine.register_notification(
        notification_id=notification.notification_id,
        intent=notification.intent,
        autonomy_context=notification.autonomy_context,
        timeout_minutes=notification.ack_timeout_minutes,
    )


class TestAckEndpoint:
    """Tests for POST /v1/notifications/{id}/ack"""

    def test_ack_notification_success(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test successful notification acknowledgment."""
        register_notification_with_engine(engine, sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "test_user", "metadata": {"reason": "reviewed"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notification_id"] == str(sample_notification.notification_id)
        assert data["ack_status"] == "ACKED"
        assert data["acked_by"] == "test_user"
        assert data["metadata"]["reason"] == "reviewed"
        assert "acked_at" in data

    def test_ack_notification_without_body(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test ack without request body."""
        register_notification_with_engine(engine, sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ack_status"] == "ACKED"
        assert data["acked_by"] == "test_user"

    def test_ack_notification_idempotent(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test that ack is idempotent - repeated ack returns success."""
        register_notification_with_engine(engine, sample_notification)

        # First ack
        response1 = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "test_user"},
        )
        assert response1.status_code == 200

        # Second ack (idempotent)
        response2 = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "test_user"},
        )
        assert response2.status_code == 200
        assert response2.json()["ack_status"] == "ACKED"

    def test_ack_notification_not_found(
        self,
        client: TestClient,
        engine,
    ):
        """Test ack for non-existent notification returns 404."""
        fake_id = uuid4()

        response = client.post(
            f"/v1/notifications/{fake_id}/ack",
            json={"acked_by": "test_user"},
        )

        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["error"] == "not_found"
        assert str(fake_id) in detail["message"]

    def test_ack_dismissed_notification_fails(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test that acking a dismissed notification fails with 409."""
        register_notification_with_engine(engine, sample_notification)
        engine.ack(
            sample_notification.notification_id,
            ack_status=AckStatus.DISMISSED,
            acked_by="other_user"
        )

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "test_user"},
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error"] == "invalid_transition"
        assert detail["current_status"] == "DISMISSED"


class TestDismissEndpoint:
    """Tests for POST /v1/notifications/{id}/dismiss"""

    def test_dismiss_notification_success(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test successful notification dismissal."""
        register_notification_with_engine(engine, sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/dismiss",
            json={"dismissed_by": "test_user", "metadata": {"reason": "not relevant"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notification_id"] == str(sample_notification.notification_id)
        assert data["ack_status"] == "DISMISSED"
        assert data["acked_by"] == "test_user"

    def test_dismiss_notification_without_body(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test dismiss without request body."""
        register_notification_with_engine(engine, sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/dismiss",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ack_status"] == "DISMISSED"

    def test_ack_rejects_unauthenticated_request(
        self,
        engine,
        sample_notification: Notification,
    ):
        """Mutating ACK routes require a valid AGSignal API key."""
        app = create_app()
        app.state.agsignal_api_key = "test-key"
        app.state.agsignal_api_principal = "test_user"
        unauthenticated_client = TestClient(app)
        register_notification_with_engine(engine, sample_notification)

        response = unauthenticated_client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "test_user"},
        )

        assert response.status_code == 401

    def test_ack_rejects_principal_override(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Body identity cannot override the authenticated principal."""
        register_notification_with_engine(engine, sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "other_user"},
        )

        assert response.status_code == 403

    def test_ack_audit_failure_does_not_mutate_ack_state(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """ACK state should not commit when audit persistence fails."""
        client.app.state.audit_store = FailingAckAuditStore()
        register_notification_with_engine(engine, sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "test_user"},
        )

        assert response.status_code == 503
        assert engine.get_status(sample_notification.notification_id) == AckStatus.PENDING

    def test_dismiss_acked_notification_fails(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test that dismissing an acked notification fails with 409."""
        register_notification_with_engine(engine, sample_notification)
        engine.ack(
            sample_notification.notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="other_user"
        )

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/dismiss",
            json={"dismissed_by": "test_user"},
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error"] == "invalid_transition"
        assert detail["current_status"] == "ACKED"


class TestGetNotificationStatus:
    """Tests for GET /v1/notifications/{id}"""

    def test_get_status_found(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test getting status of existing notification."""
        register_notification_with_engine(engine, sample_notification)

        response = client.get(
            f"/v1/notifications/{sample_notification.notification_id}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["found"] is True
        assert data["notification_id"] == str(sample_notification.notification_id)
        assert data["ack_status"] == "PENDING"

    def test_get_status_after_ack(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test getting status after acknowledgment."""
        register_notification_with_engine(engine, sample_notification)
        engine.ack(
            sample_notification.notification_id,
            ack_status=AckStatus.ACKED,
        )

        response = client.get(
            f"/v1/notifications/{sample_notification.notification_id}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ack_status"] == "ACKED"

    def test_get_status_not_found(
        self,
        client: TestClient,
        engine,
    ):
        """Test getting status of non-existent notification."""
        fake_id = uuid4()

        response = client.get(f"/v1/notifications/{fake_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["found"] is False
        assert data["notification_id"] == str(fake_id)
        assert data["ack_status"] is None


class TestGetAckStatus:
    """Tests for GET /v1/notifications/{id}/ack-status"""

    def test_get_ack_status_pending(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test getting ack status when pending."""
        register_notification_with_engine(engine, sample_notification)

        response = client.get(
            f"/v1/notifications/{sample_notification.notification_id}/ack-status",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notification_id"] == str(sample_notification.notification_id)
        assert data["ack_status"] == "PENDING"

    def test_get_ack_status_acked(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test getting ack status when acked."""
        register_notification_with_engine(engine, sample_notification)
        engine.ack(
            sample_notification.notification_id,
            ack_status=AckStatus.ACKED,
        )

        response = client.get(
            f"/v1/notifications/{sample_notification.notification_id}/ack-status",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ack_status"] == "ACKED"

    def test_get_ack_status_not_tracked(
        self,
        client: TestClient,
        engine,
    ):
        """Test getting ack status for untracked notification."""
        fake_id = uuid4()

        response = client.get(f"/v1/notifications/{fake_id}/ack-status")

        assert response.status_code == 200
        data = response.json()
        assert data["notification_id"] == str(fake_id)
        assert data["ack_status"] is None


class TestHealthEndpoint:
    """Tests for GET /health"""

    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

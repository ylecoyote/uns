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
from notification.models import (
    AutonomyContext,
    AutonomyMode,
    Notification,
    NotificationIntent,
)


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
    return TestClient(app)


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


class TestAckEndpoint:
    """Tests for POST /v1/notifications/{id}/ack"""

    def test_ack_notification_success(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test successful notification acknowledgment."""
        engine.register_notification(sample_notification)

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
        engine.register_notification(sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ack_status"] == "ACKED"
        assert data["acked_by"] is None

    def test_ack_notification_idempotent(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test that ack is idempotent - repeated ack returns success."""
        engine.register_notification(sample_notification)

        # First ack
        response1 = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "user1"},
        )
        assert response1.status_code == 200

        # Second ack (idempotent)
        response2 = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/ack",
            json={"acked_by": "user2"},
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
        engine.register_notification(sample_notification)
        engine.dismiss(sample_notification.notification_id, dismissed_by="other_user")

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
        engine.register_notification(sample_notification)

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
        engine.register_notification(sample_notification)

        response = client.post(
            f"/v1/notifications/{sample_notification.notification_id}/dismiss",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ack_status"] == "DISMISSED"

    def test_dismiss_acked_notification_fails(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test that dismissing an acked notification fails with 409."""
        engine.register_notification(sample_notification)
        engine.ack(sample_notification.notification_id, acked_by="other_user")

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
        engine.register_notification(sample_notification)

        response = client.get(
            f"/v1/notifications/{sample_notification.notification_id}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["found"] is True
        assert data["notification_id"] == str(sample_notification.notification_id)
        assert data["notification_type"] == "test.notification"
        assert data["intent"] == "SAFETY"
        assert data["title"] == "Test Notification"
        assert data["ack_status"] == "PENDING"
        assert data["require_ack"] is True

    def test_get_status_after_ack(
        self,
        client: TestClient,
        engine,
        sample_notification: Notification,
    ):
        """Test getting status after acknowledgment."""
        engine.register_notification(sample_notification)
        engine.ack(sample_notification.notification_id)

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
        engine.register_notification(sample_notification)

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
        engine.register_notification(sample_notification)
        engine.ack(sample_notification.notification_id)

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

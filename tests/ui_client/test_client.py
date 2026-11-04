"""Tests for UI API client."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryStatus,
    NotificationIntent,
)
from ui_client.client import UIApiClient, create_ui_client
from ui_client.errors import (
    ConnectionError,
    InvalidCursorError,
    InvalidParameterError,
    NotFoundError,
    RateLimitedError,
    UIApiServerError,
)
from ui_client.filters import AuditFilters, DeliveryFilters, InvariantFilters
from ui_client.types import (
    AuditEventType,
    EnforcementType,
    InvariantSeverity,
    InvariantStatus,
)


class TestUIApiClientInit:
    """Tests for UIApiClient initialization."""

    def test_basic_init(self):
        """Test basic client initialization."""
        client = UIApiClient(base_url="http://localhost:8000")
        assert client._base_url == "http://localhost:8000"
        client.close()

    def test_init_strips_trailing_slash(self):
        """Test trailing slash is removed from base_url."""
        client = UIApiClient(base_url="http://localhost:8000/")
        assert client._base_url == "http://localhost:8000"
        client.close()

    def test_init_with_custom_timeout(self):
        """Test client with custom timeout."""
        client = UIApiClient(base_url="http://localhost:8000", timeout=60.0)
        assert client._timeout == 60.0
        client.close()

    def test_init_with_headers(self):
        """Test client with custom headers."""
        headers = {"Authorization": "Bearer token123"}
        client = UIApiClient(base_url="http://localhost:8000", headers=headers)
        assert client._default_headers == headers
        client.close()

    def test_init_with_http_client(self):
        """Test client with pre-configured httpx.Client."""
        http_client = httpx.Client(base_url="http://localhost:8000")
        client = UIApiClient(base_url="http://localhost:8000", http_client=http_client)
        assert client._owns_client is False
        client.close()
        # The passed client should not be closed
        assert not http_client.is_closed
        http_client.close()

    def test_context_manager(self):
        """Test client can be used as context manager."""
        with UIApiClient(base_url="http://localhost:8000") as client:
            assert client._base_url == "http://localhost:8000"
        # Client should be closed after exiting context
        assert client._client.is_closed


class TestCreateUiClient:
    """Tests for create_ui_client factory function."""

    def test_factory_creates_client(self):
        """Test factory function creates working client."""
        client = create_ui_client("http://localhost:8000")
        assert isinstance(client, UIApiClient)
        client.close()

    def test_factory_with_options(self):
        """Test factory function accepts all options."""
        client = create_ui_client(
            base_url="http://localhost:8000",
            timeout=45.0,
            connect_timeout=15.0,
            headers={"X-Custom": "value"},
        )
        assert client._timeout == 45.0
        assert client._connect_timeout == 15.0
        client.close()


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict | None = None,
        text: str = "",
        headers: dict | None = None,
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data


class TestListDeliveries:
    """Tests for list_deliveries endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_list_deliveries_basic(self, client):
        """Test basic list deliveries call."""
        now = datetime.now(UTC).isoformat()
        agent_id = str(uuid4())
        notification_id = str(uuid4())

        mock_response = MockResponse(
            json_data={
                "items": [
                    {
                        "notification_id": notification_id,
                        "notification_type": "test.notification",
                        "intent": "OPERATIONAL",
                        "delivery_mode": "BEST_EFFORT",
                        "status": "DELIVERED",
                        "created_at": now,
                        "delivered_at": now,
                        "channels_attempted": ["SLACK"],
                        "channels_succeeded": ["SLACK"],
                        "autonomy_mode": "LIVE",
                        "agent_id": agent_id,
                    }
                ],
                "pagination": {
                    "next_cursor": None,
                    "has_more": False,
                    "total_count": 1,
                },
            }
        )

        with patch.object(client._client, "request", return_value=mock_response):
            response = client.list_deliveries()

        assert len(response.items) == 1
        assert response.items[0].notification_type == "test.notification"
        assert response.pagination.has_more is False

    def test_list_deliveries_with_filters(self, client):
        """Test list deliveries with filters."""
        mock_response = MockResponse(
            json_data={
                "items": [],
                "pagination": {"next_cursor": None, "has_more": False},
            }
        )

        filters = DeliveryFilters(
            status=DeliveryStatus.DELIVERED,
            intent=NotificationIntent.SAFETY,
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            client.list_deliveries(filters=filters, limit=10)

        # Verify filters were passed as params
        call_args = mock_request.call_args
        params = call_args.kwargs["params"]
        assert params["status"] == "DELIVERED"
        assert params["intent"] == "SAFETY"
        assert params["limit"] == 10

    def test_list_deliveries_with_pagination(self, client):
        """Test list deliveries with cursor pagination."""
        mock_response = MockResponse(
            json_data={
                "items": [],
                "pagination": {"next_cursor": "page2", "has_more": True},
            }
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            client.list_deliveries(cursor="page1")

        call_args = mock_request.call_args
        params = call_args.kwargs["params"]
        assert params["cursor"] == "page1"


class TestGetDeliveryTimeline:
    """Tests for get_delivery_timeline endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_get_timeline_success(self, client):
        """Test successful timeline retrieval."""
        now = datetime.now(UTC).isoformat()
        agent_id = str(uuid4())
        notification_id = uuid4()

        mock_response = MockResponse(
            json_data={
                "notification_id": str(notification_id),
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "delivery_mode": "GUARANTEED",
                "status": "DELIVERED",
                "created_at": now,
                "delivered_at": now,
                "attempts": [
                    {
                        "attempt_id": str(uuid4()),
                        "channel": "SLACK",
                        "status": "SUCCESS",
                        "started_at": now,
                        "completed_at": now,
                        "duration_ms": 150,
                    }
                ],
                "channels_attempted": ["SLACK"],
                "channels_succeeded": ["SLACK"],
                "channels_failed": [],
                "autonomy_context": {
                    "autonomy_mode": "LIVE",
                    "agent_id": agent_id,
                },
            }
        )

        with patch.object(client._client, "request", return_value=mock_response):
            timeline = client.get_delivery_timeline(notification_id)

        assert timeline.notification_id == notification_id
        assert timeline.intent == NotificationIntent.SAFETY
        assert len(timeline.attempts) == 1

    def test_get_timeline_not_found(self, client):
        """Test timeline retrieval for non-existent notification."""
        notification_id = uuid4()
        mock_response = MockResponse(
            status_code=404,
            json_data={
                "detail": {
                    "error": {
                        "code": "not_found",
                        "message": f"Notification not found: {notification_id}",
                    },
                    "request_id": "req-123",
                }
            },
        )

        with (
            patch.object(client._client, "request", return_value=mock_response),
            pytest.raises(NotFoundError) as exc_info,
        ):
            client.get_delivery_timeline(notification_id)

        assert str(notification_id) in exc_info.value.message


class TestGetEffectivePolicy:
    """Tests for get_effective_policy endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_get_policy_success(self, client):
        """Test successful policy resolution."""
        mock_response = MockResponse(
            json_data={
                "notification_type": "trading.risk_breach",
                "effective": {
                    "delivery_mode": "GUARANTEED",
                    "channels": ["SLACK", "PAGERDUTY"],
                    "require_ack": True,
                    "ack_timeout_minutes": 15,
                    "dedup_window_seconds": 300,
                },
                "resolution": {
                    "delivery_mode": [
                        {
                            "source": "sdk_default",
                            "value": "GUARANTEED",
                            "applied": True,
                        }
                    ]
                },
                "resolution_context": {
                    "intent": "SAFETY",
                    "autonomy_mode": "LIVE",
                    "irreversible": False,
                    "policy_found": True,
                    "policy_notification_type": "trading.risk_breach",
                },
            }
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            policy = client.get_effective_policy(
                notification_type="trading.risk_breach",
                intent=NotificationIntent.SAFETY,
                autonomy_mode=AutonomyMode.LIVE,
                irreversible=False,
            )

        assert policy.notification_type == "trading.risk_breach"
        assert policy.effective.require_ack is True
        assert Channel.PAGERDUTY in policy.effective.channels

        # Verify params were passed correctly
        call_args = mock_request.call_args
        params = call_args.kwargs["params"]
        assert params["notification_type"] == "trading.risk_breach"
        assert params["intent"] == "SAFETY"
        assert params["autonomy_mode"] == "LIVE"


class TestListInvariants:
    """Tests for list_invariants endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_list_invariants_basic(self, client):
        """Test basic invariants listing."""
        mock_response = MockResponse(
            json_data={
                "items": [
                    {
                        "id": "INV-ACK-001",
                        "statement": "SAFETY notifications require acknowledgment",
                        "severity": "HIGH",
                        "status": "active",
                        "enforcement": {
                            "type": "guard",
                            "description": "Validated in SDK",
                        },
                        "evidence": [],
                        "owner": "platform-team",
                        "last_reviewed": "2024-01-15",
                    }
                ],
                "pagination": {"next_cursor": None, "has_more": False, "total_count": 1},
            }
        )

        with patch.object(client._client, "request", return_value=mock_response):
            response = client.list_invariants()

        assert len(response.items) == 1
        assert response.items[0].id == "INV-ACK-001"
        assert response.items[0].severity == InvariantSeverity.HIGH

    def test_list_invariants_with_filters(self, client):
        """Test invariants listing with filters."""
        mock_response = MockResponse(
            json_data={"items": [], "pagination": {"next_cursor": None, "has_more": False}}
        )

        filters = InvariantFilters(
            severity=InvariantSeverity.HIGH,
            enforcement_type=EnforcementType.GUARD,
            status=InvariantStatus.ACTIVE,
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            client.list_invariants(filters=filters)

        call_args = mock_request.call_args
        params = call_args.kwargs["params"]
        assert params["severity"] == "HIGH"
        assert params["enforcement_type"] == "guard"
        assert params["status"] == "active"


class TestGetInvariantsSummary:
    """Tests for get_invariants_summary endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_get_summary(self, client):
        """Test getting invariants summary."""
        mock_response = MockResponse(
            json_data={
                "total_count": 15,
                "by_severity": {"HIGH": 5, "MEDIUM": 8, "LOW": 2},
                "by_enforcement_type": {"guard": 7, "test": 6, "isolation": 2},
                "by_status": {"active": 14, "inactive": 1},
                "exceptions_requiring_review": 0,
                "last_updated": "2024-01-20T10:30:00Z",
            }
        )

        with patch.object(client._client, "request", return_value=mock_response):
            summary = client.get_invariants_summary()

        assert summary.total_count == 15
        assert summary.by_severity["HIGH"] == 5
        assert summary.exceptions_requiring_review == 0


class TestListAuditEvents:
    """Tests for list_audit_events endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_list_audit_events_basic(self, client):
        """Test basic audit events listing."""
        now = datetime.now(UTC).isoformat()
        agent_id = str(uuid4())
        notification_id = str(uuid4())
        audit_id = str(uuid4())

        mock_response = MockResponse(
            json_data={
                "items": [
                    {
                        "audit_id": audit_id,
                        "event_type": "delivery.succeeded",
                        "event_time": now,
                        "notification_id": notification_id,
                        "notification_type": "test.notification",
                        "autonomy_context": {
                            "autonomy_mode": "LIVE",
                            "agent_id": agent_id,
                        },
                        "payload": {},
                        "correlation_id": "corr-123",
                    }
                ],
                "pagination": {"next_cursor": None, "has_more": False, "total_count": 1},
            }
        )

        with patch.object(client._client, "request", return_value=mock_response):
            response = client.list_audit_events()

        assert len(response.items) == 1
        assert response.items[0].event_type == AuditEventType.DELIVERY_SUCCEEDED

    def test_list_audit_events_with_filters(self, client):
        """Test audit events listing with filters."""
        mock_response = MockResponse(
            json_data={"items": [], "pagination": {"next_cursor": None, "has_more": False}}
        )

        filters = AuditFilters(
            event_type=AuditEventType.DELIVERY_FAILED,
            autonomy_mode=AutonomyMode.LIVE,
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            client.list_audit_events(filters=filters)

        call_args = mock_request.call_args
        params = call_args.kwargs["params"]
        assert params["event_type"] == "delivery.failed"
        assert params["autonomy_mode"] == "LIVE"


class TestIterators:
    """Tests for iterator methods that handle pagination."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_iter_deliveries(self, client):
        """Test iterating through all deliveries."""
        now = datetime.now(UTC).isoformat()
        agent_id = str(uuid4())

        # Simulate 2 pages of results
        page1 = MockResponse(
            json_data={
                "items": [
                    {
                        "notification_id": str(uuid4()),
                        "notification_type": "test.1",
                        "intent": "OPERATIONAL",
                        "delivery_mode": "BEST_EFFORT",
                        "status": "DELIVERED",
                        "created_at": now,
                        "channels_attempted": [],
                        "channels_succeeded": [],
                        "autonomy_mode": "LIVE",
                        "agent_id": agent_id,
                    }
                ],
                "pagination": {"next_cursor": "page2", "has_more": True},
            }
        )

        page2 = MockResponse(
            json_data={
                "items": [
                    {
                        "notification_id": str(uuid4()),
                        "notification_type": "test.2",
                        "intent": "OPERATIONAL",
                        "delivery_mode": "BEST_EFFORT",
                        "status": "DELIVERED",
                        "created_at": now,
                        "channels_attempted": [],
                        "channels_succeeded": [],
                        "autonomy_mode": "LIVE",
                        "agent_id": agent_id,
                    }
                ],
                "pagination": {"next_cursor": None, "has_more": False},
            }
        )

        with patch.object(client._client, "request", side_effect=[page1, page2]):
            items = list(client.iter_deliveries())

        assert len(items) == 2
        assert items[0].notification_type == "test.1"
        assert items[1].notification_type == "test.2"

    def test_iter_invariants(self, client):
        """Test iterating through all invariants."""
        mock_response = MockResponse(
            json_data={
                "items": [
                    {
                        "id": "INV-001",
                        "statement": "Test invariant",
                        "severity": "MEDIUM",
                        "status": "active",
                        "enforcement": {"type": "test", "description": "desc"},
                        "evidence": [],
                        "owner": "team",
                        "last_reviewed": "2024-01-01",
                    }
                ],
                "pagination": {"next_cursor": None, "has_more": False},
            }
        )

        with patch.object(client._client, "request", return_value=mock_response):
            items = list(client.iter_invariants())

        assert len(items) == 1
        assert items[0].id == "INV-001"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_invalid_parameter_error(self, client):
        """Test handling of invalid parameter errors."""
        mock_response = MockResponse(
            status_code=400,
            json_data={
                "detail": {
                    "error": {
                        "code": "invalid_parameter",
                        "message": "Invalid status value: INVALID",
                    },
                    "request_id": "req-123",
                }
            },
        )

        with (
            patch.object(client._client, "request", return_value=mock_response),
            pytest.raises(InvalidParameterError) as exc_info,
        ):
            client.list_deliveries()

        assert exc_info.value.request_id == "req-123"

    def test_invalid_cursor_error(self, client):
        """Test handling of invalid cursor errors."""
        mock_response = MockResponse(
            status_code=400,
            json_data={
                "detail": {
                    "error": {
                        "code": "invalid_cursor",
                        "message": "Cursor expired",
                    },
                    "request_id": "req-456",
                }
            },
        )

        with (
            patch.object(client._client, "request", return_value=mock_response),
            pytest.raises(InvalidCursorError),
        ):
            client.list_deliveries(cursor="expired-cursor")

    def test_rate_limited_error(self, client):
        """Test handling of rate limit errors."""
        mock_response = MockResponse(
            status_code=429,
            json_data={
                "detail": {
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                    },
                    "request_id": "req-789",
                }
            },
            headers={"Retry-After": "30"},
        )

        with (
            patch.object(client._client, "request", return_value=mock_response),
            pytest.raises(RateLimitedError) as exc_info,
        ):
            client.list_deliveries()

        assert exc_info.value.retry_after == 30

    def test_server_error(self, client):
        """Test handling of server errors."""
        mock_response = MockResponse(
            status_code=500,
            json_data={
                "detail": {
                    "error": {
                        "code": "internal_error",
                        "message": "Internal server error",
                    },
                    "request_id": "req-abc",
                }
            },
        )

        with (
            patch.object(client._client, "request", return_value=mock_response),
            pytest.raises(UIApiServerError),
        ):
            client.list_deliveries()

    def test_connection_error(self, client):
        """Test handling of connection errors."""
        with (
            patch.object(
                client._client, "request", side_effect=httpx.ConnectError("Connection refused")
            ),
            pytest.raises(ConnectionError) as exc_info,
        ):
            client.list_deliveries()

        assert "Connection refused" in exc_info.value.message

    def test_timeout_error(self, client):
        """Test handling of timeout errors."""
        with (
            patch.object(client._client, "request", side_effect=httpx.TimeoutException("Timeout")),
            pytest.raises(ConnectionError) as exc_info,
        ):
            client.list_deliveries()

        assert "Timeout" in exc_info.value.message


class TestRequestIdPropagation:
    """Tests for request ID propagation."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked HTTP."""
        client = UIApiClient(base_url="http://localhost:8000")
        yield client
        client.close()

    def test_request_id_in_header(self, client):
        """Test request ID is passed in X-Request-ID header."""
        mock_response = MockResponse(
            json_data={"items": [], "pagination": {"next_cursor": None, "has_more": False}}
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            client.list_deliveries(request_id="my-request-123")

        call_args = mock_request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["X-Request-ID"] == "my-request-123"

    def test_no_request_id(self, client):
        """Test no X-Request-ID header when not provided."""
        mock_response = MockResponse(
            json_data={"items": [], "pagination": {"next_cursor": None, "has_more": False}}
        )

        with patch.object(client._client, "request", return_value=mock_response) as mock_request:
            client.list_deliveries()

        call_args = mock_request.call_args
        headers = call_args.kwargs["headers"]
        assert "X-Request-ID" not in headers

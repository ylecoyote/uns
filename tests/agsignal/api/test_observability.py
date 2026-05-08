"""Tests for UI observability instrumentation.

Tests the observability module for:
- Request ID generation and propagation
- Request metrics collection
- Error metrics tracking
- Structured logging with request context
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agsignal.api.observability import (
    MetricsCollector,
    StructuredLogger,
    configure_metrics_collector,
    generate_request_id,
    get_request_id,
    get_structured_logger,
    set_request_id,
)
from agsignal.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client with fresh metrics collector."""
    # Reset metrics collector for each test
    configure_metrics_collector(MetricsCollector())

    # Reset read model adapter
    from agsignal.api.read_models import InMemoryReadModelAdapter, configure_read_model_adapter
    from notification.audit import InMemoryAuditStore

    fresh_store = InMemoryAuditStore()
    fresh_adapter = InMemoryReadModelAdapter(audit_store=fresh_store)
    configure_read_model_adapter(fresh_adapter)

    app = create_app()
    return TestClient(app)


@pytest.fixture
def metrics_collector() -> MetricsCollector:
    """Create a fresh metrics collector for each test."""
    collector = MetricsCollector()
    configure_metrics_collector(collector)
    return collector


class TestRequestIdGeneration:
    """Tests for request ID generation."""

    def test_generate_request_id_format(self):
        """Test request ID has correct format."""
        request_id = generate_request_id()
        assert request_id.startswith("req-")
        assert len(request_id) == 16  # "req-" + 12 hex chars

    def test_generate_request_id_unique(self):
        """Test each generated ID is unique."""
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100

    def test_request_id_context_var(self):
        """Test request ID context variable operations."""
        # Initially None
        assert get_request_id() is None

        # Set and get
        set_request_id("test-id-123")
        assert get_request_id() == "test-id-123"

        # Clear
        set_request_id(None)
        assert get_request_id() is None


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_record_request(self, metrics_collector: MetricsCollector):
        """Test recording a request metric."""
        metrics_collector.record_request(
            endpoint="/ui/deliveries",
            method="GET",
            status_code=200,
            latency_ms=50.5,
        )

        assert metrics_collector.get_request_count("/ui/deliveries") == 1
        stats = metrics_collector.get_latency_stats("/ui/deliveries")
        assert stats is not None
        assert stats["avg"] == 50.5

    def test_record_multiple_requests(self, metrics_collector: MetricsCollector):
        """Test recording multiple requests."""
        for i in range(5):
            metrics_collector.record_request(
                endpoint="/ui/deliveries",
                method="GET",
                status_code=200,
                latency_ms=10.0 * (i + 1),
            )

        assert metrics_collector.get_request_count("/ui/deliveries") == 5
        stats = metrics_collector.get_latency_stats("/ui/deliveries")
        assert stats is not None
        assert stats["count"] == 5
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["avg"] == 30.0  # (10+20+30+40+50)/5

    def test_record_error(self, metrics_collector: MetricsCollector):
        """Test recording an error metric."""
        metrics_collector.record_error(
            endpoint="/ui/deliveries",
            method="GET",
            error_code="not_found",
            error_message="Delivery not found",
            status_code=404,
        )

        metrics = metrics_collector.get_all_metrics()
        error_metrics = [m for m in metrics if m.metric_type.value == "ui_request_error"]
        assert len(error_metrics) == 1
        assert error_metrics[0].labels["error_code"] == "not_found"

    def test_error_count_tracking(self, metrics_collector: MetricsCollector):
        """Test error count tracking."""
        # Record some successful requests
        for _ in range(3):
            metrics_collector.record_request(
                endpoint="/ui/deliveries",
                method="GET",
                status_code=200,
                latency_ms=50.0,
            )

        # Record some errors
        for _ in range(2):
            metrics_collector.record_request(
                endpoint="/ui/deliveries",
                method="GET",
                status_code=404,
                latency_ms=10.0,
            )

        assert metrics_collector.get_request_count("/ui/deliveries") == 5
        assert metrics_collector.get_error_count("/ui/deliveries") == 2
        assert metrics_collector.get_error_count("/ui/deliveries", status_code=404) == 2

    def test_clear_metrics(self, metrics_collector: MetricsCollector):
        """Test clearing all metrics."""
        metrics_collector.record_request(
            endpoint="/ui/deliveries",
            method="GET",
            status_code=200,
            latency_ms=50.0,
        )

        metrics_collector.clear()

        assert metrics_collector.get_request_count("/ui/deliveries") == 0
        assert metrics_collector.get_all_metrics() == []

    def test_latency_percentiles(self, metrics_collector: MetricsCollector):
        """Test latency percentile calculations."""
        # Record 100 requests with latencies 1-100
        for i in range(100):
            metrics_collector.record_request(
                endpoint="/ui/test",
                method="GET",
                status_code=200,
                latency_ms=float(i + 1),
            )

        stats = metrics_collector.get_latency_stats("/ui/test")
        assert stats is not None
        # Allow for off-by-one in percentile calculation
        assert 49.0 <= stats["p50"] <= 51.0
        assert 94.0 <= stats["p95"] <= 96.0
        assert 98.0 <= stats["p99"] <= 100.0


class TestStructuredLogger:
    """Tests for StructuredLogger."""

    def test_structured_logger_creation(self):
        """Test creating a structured logger."""
        logger = get_structured_logger("test.module")
        assert isinstance(logger, StructuredLogger)

    def test_logger_adds_request_id(self, caplog):
        """Test that logger adds request ID to messages."""
        logger = get_structured_logger("test.module")

        # Set request ID
        set_request_id("test-req-abc123")

        # Log a message
        import logging
        with caplog.at_level(logging.INFO):
            logger.info("Test message", extra={"key": "value"})

        # Check request ID is in the log
        assert "request_id=test-req-abc123" in caplog.text
        assert "key=value" in caplog.text

        # Clean up
        set_request_id(None)


class TestObservabilityMiddleware:
    """Tests for ObservabilityMiddleware integration."""

    def test_middleware_adds_request_id_header(self, client: TestClient):
        """Test that middleware adds X-Request-ID header to responses."""
        response = client.get("/ui/deliveries")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req-")

    def test_middleware_uses_provided_request_id(self, client: TestClient):
        """Test that middleware uses X-Request-ID from request if provided."""
        custom_id = "custom-req-12345"
        response = client.get(
            "/ui/deliveries",
            headers={"X-Request-ID": custom_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id

    def test_middleware_records_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test that middleware records request metrics."""
        # Make a request
        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        # Check metrics were recorded
        assert metrics_collector.get_request_count("/ui/deliveries") == 1
        stats = metrics_collector.get_latency_stats("/ui/deliveries")
        assert stats is not None
        assert stats["count"] == 1

    def test_middleware_records_error_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test that middleware records error metrics for 4xx responses."""
        # Make a request that will return 404
        fake_id = uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")
        assert response.status_code == 404

        # Check metrics were recorded
        # Endpoint is normalized to /ui/deliveries/{id}
        assert metrics_collector.get_request_count("/ui/deliveries/{id}") == 1
        assert metrics_collector.get_error_count("/ui/deliveries/{id}") == 1

    def test_middleware_skips_non_ui_endpoints(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test that middleware only instruments /ui/* endpoints."""
        # Make a request to /health
        response = client.get("/health")
        assert response.status_code == 200

        # Should not have X-Request-ID header
        assert "X-Request-ID" not in response.headers

        # Should not record metrics
        assert metrics_collector.get_request_count("/health") == 0


class TestUIEndpointsObservability:
    """Tests for observability in specific UI endpoints."""

    def test_list_deliveries_request_id_in_response(self, client: TestClient):
        """Test list deliveries includes request ID."""
        response = client.get("/ui/deliveries")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_get_delivery_404_includes_request_id(self, client: TestClient):
        """Test 404 error response includes request ID."""
        fake_id = uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")

        assert response.status_code == 404
        assert "X-Request-ID" in response.headers

        # Check error response has request_id field
        detail = response.json()["detail"]
        assert "request_id" in detail
        # Request ID should match header
        assert detail["request_id"] == response.headers["X-Request-ID"]

    def test_get_effective_policy_request_id(self, client: TestClient):
        """Test get effective policy includes request ID."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_list_invariants_request_id(self, client: TestClient):
        """Test list invariants includes request ID."""
        response = client.get("/ui/invariants")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_invariants_summary_request_id(self, client: TestClient):
        """Test invariants summary includes request ID."""
        response = client.get("/ui/invariants/summary")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_list_audit_events_request_id(self, client: TestClient):
        """Test list audit events includes request ID."""
        response = client.get("/ui/audit")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers


class TestMetricsForAllEndpoints:
    """Tests verifying metrics are collected for all UI endpoints."""

    def test_deliveries_list_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test metrics for GET /ui/deliveries."""
        client.get("/ui/deliveries")

        assert metrics_collector.get_request_count("/ui/deliveries") == 1

    def test_deliveries_get_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test metrics for GET /ui/deliveries/{id}."""
        fake_id = uuid4()
        client.get(f"/ui/deliveries/{fake_id}")

        assert metrics_collector.get_request_count("/ui/deliveries/{id}") == 1

    def test_policies_effective_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test metrics for GET /ui/policies/effective."""
        client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )

        assert metrics_collector.get_request_count("/ui/policies/effective") == 1

    def test_invariants_list_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test metrics for GET /ui/invariants."""
        client.get("/ui/invariants")

        assert metrics_collector.get_request_count("/ui/invariants") == 1

    def test_invariants_summary_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test metrics for GET /ui/invariants/summary."""
        client.get("/ui/invariants/summary")

        assert metrics_collector.get_request_count("/ui/invariants/summary") == 1

    def test_audit_list_metrics(self, client: TestClient, metrics_collector: MetricsCollector):
        """Test metrics for GET /ui/audit."""
        client.get("/ui/audit")

        assert metrics_collector.get_request_count("/ui/audit") == 1

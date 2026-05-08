"""Tests for application startup and persistence configuration.

Tests the automatic wiring of audit stores and read model adapters
that happens at application startup.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from agsignal.app import configure_persistence, create_app


class TestConfigurePersistence:
    """Tests for configure_persistence function."""

    def test_in_memory_mode_when_no_database_url(self):
        """Test in-memory mode is used when DATABASE_URL is not set."""
        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Ensure DATABASE_URL is not set
        with patch.dict(os.environ, {}, clear=True):
            configure_persistence()

        # Verify in-memory adapter is configured
        from mcp_server.read_models import InMemoryReadModelAdapter, get_read_model_adapter

        adapter = get_read_model_adapter()
        assert isinstance(adapter, InMemoryReadModelAdapter)

        # Verify audit logger is configured
        from notification.audit import InMemoryAuditStore, get_audit_logger

        audit_logger = get_audit_logger()
        assert isinstance(audit_logger.store, InMemoryAuditStore)

    def test_shared_store_in_memory_mode(self):
        """Test audit store is shared between reads and writes in in-memory mode."""
        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Configure with no DATABASE_URL
        with patch.dict(os.environ, {}, clear=True):
            configure_persistence()

        # Get configured components
        from mcp_server.read_models import get_read_model_adapter
        from notification.audit import get_audit_logger

        adapter = get_read_model_adapter()
        audit_logger = get_audit_logger()

        # Verify they share the same underlying store
        assert adapter.audit_store is audit_logger.store

    def test_data_flows_from_audit_to_read_model(self):
        """Test data written via audit logger is visible in read model adapter."""
        from datetime import UTC, datetime
        from uuid import uuid4

        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Configure with no DATABASE_URL
        with patch.dict(os.environ, {}, clear=True):
            configure_persistence()

        # Write an audit record
        from notification.audit import AuditRecord, get_audit_logger
        from notification.models import Channel, DeliveryStatus

        notification_id = uuid4()
        record = AuditRecord(
            audit_id=uuid4(),
            notification_id=notification_id,
            notification_type="test.notification",
            status=DeliveryStatus.DELIVERED,
            channels_attempted=(Channel.SLACK,),
            channels_succeeded=(Channel.SLACK,),
            channels_failed=(),
            error_message=None,
            intent="OPERATIONAL",
            delivery_mode="BEST_EFFORT",
            autonomy_mode="LIVE",
            agent_id=uuid4(),
            plan_id=None,
            decision_snapshot_id=None,
            execution_snapshot_id=None,
            skip_snapshot_id=None,
            title="Test Notification",
            source="test-source",
            correlation_id=None,
            metadata={},
            audit_metadata={},
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
            audit_created_at=datetime.now(UTC),
        )

        audit_logger = get_audit_logger()
        audit_logger.store.save_delivery_audit(record)

        # Read via read model adapter
        from mcp_server.read_models import DeliveryFilter, get_read_model_adapter

        adapter = get_read_model_adapter()
        result = adapter.get_deliveries(DeliveryFilter(), limit=10)

        # Verify the record is visible
        assert result.total_count == 1
        assert result.items[0].notification_id == notification_id

    def test_sqlalchemy_mode_when_database_url_set(self, tmp_path):
        """Test SQLAlchemy mode is used when DATABASE_URL is set."""
        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Set DATABASE_URL to a SQLite database
        db_path = tmp_path / "test.db"
        database_url = f"sqlite:///{db_path}"

        with patch.dict(os.environ, {"DATABASE_URL": database_url, "UNS_CREATE_TABLES": "true"}):
            configure_persistence()

        # Verify SQLAlchemy adapter is configured
        from mcp_server.read_models import SQLAlchemyReadModelAdapter, get_read_model_adapter

        adapter = get_read_model_adapter()
        assert isinstance(adapter, SQLAlchemyReadModelAdapter)

        # Verify SQLAlchemy audit store is configured
        from db.audit_store import SQLAlchemyAuditStore
        from notification.audit import get_audit_logger

        audit_logger = get_audit_logger()
        assert isinstance(audit_logger.store, SQLAlchemyAuditStore)

    def test_sqlalchemy_mode_hydrates_policy_registry(self, tmp_path):
        """Test SQLAlchemy mode loads persisted runtime policies."""
        from db.policy_store import create_sqlalchemy_policy_store
        from notification.policies import (
            NotificationPolicy,
            PolicyStatus,
            configure_policy_registry,
            get_policy_registry,
        )

        db_path = tmp_path / "policy.db"
        database_url = f"sqlite:///{db_path}"
        store = create_sqlalchemy_policy_store(database_url, create_tables=True)
        store.save_policy(
            NotificationPolicy.from_dict(
                {
                    "notification_type": "safety.kill_switch",
                    "version": "1.0.0",
                    "status": PolicyStatus.ACTIVE.value,
                    "channels": {"LIVE": ["SLACK", "WEBSOCKET"]},
                    "require_ack": {"LIVE": True},
                }
            )
        )
        configure_policy_registry()

        with patch.dict(os.environ, {"DATABASE_URL": database_url, "UNS_CREATE_TABLES": "true"}):
            configure_persistence()

        policy = get_policy_registry().get_sync("safety.kill_switch")
        assert policy is not None
        assert policy.version == "1.0.0"
        assert policy.status == PolicyStatus.ACTIVE

    def test_sqlalchemy_mode_excludes_preview_policies_from_runtime_registry(self, tmp_path):
        """Test SQLAlchemy startup does not runtime-enforce PREVIEW policies."""
        from db.policy_store import create_sqlalchemy_policy_store
        from notification.policies import (
            NotificationPolicy,
            PolicyStatus,
            configure_policy_registry,
            get_policy_registry,
        )

        db_path = tmp_path / "preview-policy.db"
        database_url = f"sqlite:///{db_path}"
        store = create_sqlalchemy_policy_store(database_url, create_tables=True)
        store.save_policy(
            NotificationPolicy.from_dict(
                {
                    "notification_type": "safety.preview_only",
                    "version": "0.9.0",
                    "status": PolicyStatus.PREVIEW.value,
                    "channels": {"PREVIEW": ["WEBSOCKET"]},
                    "require_ack": {"PREVIEW": False},
                }
            )
        )
        configure_policy_registry()

        with patch.dict(os.environ, {"DATABASE_URL": database_url, "UNS_CREATE_TABLES": "true"}):
            configure_persistence()

        assert get_policy_registry().get_sync("safety.preview_only") is None


class TestCreateApp:
    """Tests for create_app function."""

    def test_create_app_configures_persistence_by_default(self):
        """Test create_app calls configure_persistence by default."""
        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Create app (should configure persistence)
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()

        # Verify persistence was configured
        from mcp_server.read_models import InMemoryReadModelAdapter, get_read_model_adapter

        adapter = get_read_model_adapter()
        assert isinstance(adapter, InMemoryReadModelAdapter)

        assert app is not None
        assert app.title == "AGSignal"

    def test_create_app_skip_persistence_config(self):
        """Test create_app skips persistence config when requested."""
        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Create app with skip_persistence_config=True
        app = create_app(skip_persistence_config=True)

        # Verify persistence was NOT configured (adapter is None)
        assert rm._read_model_adapter is None

        assert app is not None
        assert app.title == "AGSignal"

    def test_create_app_includes_ui_routes(self):
        """Test create_app includes UI routes."""
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()

        # Check that UI routes are registered
        route_paths = [route.path for route in app.routes]
        assert "/ui/deliveries" in route_paths
        assert "/ui/deliveries/{notification_id}" in route_paths
        assert "/ui/audit" in route_paths
        assert "/ui/policies/effective" in route_paths
        assert "/ui/invariants" in route_paths

    def test_health_check_endpoint(self):
        """Test health check endpoint works."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
            client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "alive"
        assert body["service"] == "agsignal"
        assert "version" in body

    def test_healthz_returns_kubernetes_convention_payload(self):
        """`/healthz` is the Kubernetes-convention liveness probe."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

        response = client.get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "alive"
        assert body["service"] == "agsignal"
        assert "version" in body

    def test_ready_reports_persistence_dependencies(self):
        """`/ready` confirms the read-model adapter and audit logger are wired."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
            client = TestClient(app)

        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["service"] == "agsignal"
        assert "read_model_adapter" in body
        assert "audit_logger" in body

    def test_readyz_aliases_ready(self):
        """`/readyz` returns the same payload as `/ready`."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
            client = TestClient(app)

        ready_body = client.get("/ready").json()
        readyz_body = client.get("/readyz").json()
        assert readyz_body == ready_body

    def test_metrics_endpoint_exposes_prometheus_format(self):
        """`/metrics` returns Prometheus exposition format with expected metric names."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

        response = client.get("/metrics")
        assert response.status_code == 200
        content_type = response.headers["content-type"]
        # prometheus-client returns: text/plain; version=0.0.4; charset=utf-8
        assert content_type.startswith("text/plain")
        assert "version=" in content_type

        body = response.text
        # The four metric families AGSignal exposes must all appear in the
        # output, even if their counters are still at zero.
        for metric_name in (
            "agsignal_http_requests_total",
            "agsignal_http_request_duration_seconds",
            "agsignal_signals_received_total",
            "agsignal_deliveries_total",
        ):
            assert metric_name in body, f"missing metric {metric_name}"

    def test_metrics_records_http_requests(self):
        """Each non-/metrics request increments the http counter."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

        # Drive a request through a known route template.
        client.get("/healthz")
        body = client.get("/metrics").text

        # The healthz hit should appear with status_code="200".
        assert "agsignal_http_requests_total" in body
        # The /metrics endpoint itself is excluded from instrumentation.
        assert 'path_template="/metrics"' not in body

    def test_rate_limit_returns_429_after_threshold(self):
        """Hitting any non-exempt route past its limit returns 429 with Retry-After."""
        from fastapi.testclient import TestClient

        env = {"AGSIGNAL_RATE_LIMIT_DEFAULT": "3/minute"}
        with patch.dict(os.environ, env, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

            # Probes all key against the same TestClient remote IP.
            statuses = [client.get("/healthz").status_code for _ in range(4)]

        assert statuses[:3] == [200, 200, 200], statuses
        assert statuses[3] == 429, statuses

        # Confirm the 429 carries Retry-After (any positive integer string).
        with patch.dict(os.environ, env, clear=True):
            app2 = create_app(skip_persistence_config=True)
            client2 = TestClient(app2)
            for _ in range(3):
                client2.get("/healthz")
            response = client2.get("/healthz")

        assert response.status_code == 429
        retry_after = response.headers.get("retry-after") or response.headers.get(
            "Retry-After"
        )
        assert retry_after is not None and retry_after.isdigit()
        assert int(retry_after) >= 1

    def test_rate_limit_keys_independently_per_principal(self):
        """Different Bearer tokens get independent rate-limit counters."""
        from fastapi.testclient import TestClient

        env = {"AGSIGNAL_RATE_LIMIT_DEFAULT": "2/minute"}
        with patch.dict(os.environ, env, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

            headers_alice = {"Authorization": "Bearer alice-key"}
            headers_bob = {"Authorization": "Bearer bob-key"}

            # Alice hits her limit.
            assert client.get("/healthz", headers=headers_alice).status_code == 200
            assert client.get("/healthz", headers=headers_alice).status_code == 200
            assert client.get("/healthz", headers=headers_alice).status_code == 429

            # Bob is independent — first request still passes.
            assert client.get("/healthz", headers=headers_bob).status_code == 200

    def test_create_app_allows_console_cors_preflight(self):
        """Browser console origins can preflight read and write API headers."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

        response = client.options(
            "/ui/audit",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": (
                    "Authorization, X-AGSignal-API-Key, X-UNS-API-Key, X-Request-ID"
                ),
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        allowed_headers = response.headers["access-control-allow-headers"].lower()
        assert "authorization" in allowed_headers
        assert "x-agsignal-api-key" in allowed_headers
        assert "x-uns-api-key" in allowed_headers

    def test_create_app_disables_interactive_docs_by_default(self):
        """Console API does not expose /docs, /redoc, or /openapi.json by default."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

        for path in ("/docs", "/redoc", "/openapi.json"):
            response = client.get(path)
            assert response.status_code == 404, (
                f"{path} should be disabled by default; got {response.status_code}"
            )

    def test_create_app_exposes_interactive_docs_when_enabled(self):
        """Operators can opt in to interactive docs via AGSIGNAL_ENABLE_DOCS=true."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {"AGSIGNAL_ENABLE_DOCS": "true"}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

            response = client.get("/openapi.json")

        assert response.status_code == 200
        assert response.json()["info"]["title"] == "AGSignal"

    def test_create_app_rejects_unknown_cors_origin(self):
        """CORS stays closed by default for non-console origins."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {}, clear=True):
            app = create_app(skip_persistence_config=True)
            client = TestClient(app)

        response = client.options(
            "/ui/audit",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


class TestEndToEndIntegration:
    """End-to-end tests for the full data flow."""

    def test_notification_delivery_visible_in_ui(self):
        """Test a delivered notification is visible in UI endpoints."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from fastapi.testclient import TestClient

        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Create app with in-memory storage
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()

        # Simulate a notification delivery by writing to the audit store
        from notification.audit import AuditRecord, get_audit_logger
        from notification.models import Channel, DeliveryStatus

        notification_id = uuid4()
        record = AuditRecord(
            audit_id=uuid4(),
            notification_id=notification_id,
            notification_type="test.integration",
            status=DeliveryStatus.DELIVERED,
            channels_attempted=(Channel.SLACK,),
            channels_succeeded=(Channel.SLACK,),
            channels_failed=(),
            error_message=None,
            intent="OPERATIONAL",
            delivery_mode="BEST_EFFORT",
            autonomy_mode="LIVE",
            agent_id=uuid4(),
            plan_id=None,
            decision_snapshot_id=None,
            execution_snapshot_id=None,
            skip_snapshot_id=None,
            title="Integration Test",
            source="test",
            correlation_id=None,
            metadata={},
            audit_metadata={},
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
            audit_created_at=datetime.now(UTC),
        )
        get_audit_logger().store.save_delivery_audit(record)

        # Query via UI endpoint
        client = TestClient(app)
        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert data["items"][0]["notification_id"] == str(notification_id)
        assert data["items"][0]["notification_type"] == "test.integration"

    def test_audit_events_visible_in_ui(self):
        """Test audit events are visible in UI audit endpoint."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from fastapi.testclient import TestClient

        # Clear any existing configuration
        import mcp_server.read_models as rm
        import notification.audit as audit

        rm._read_model_adapter = None
        audit._audit_logger = None

        # Create app with in-memory storage
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()

        # Write an audit record
        from notification.audit import AuditRecord, get_audit_logger
        from notification.models import Channel, DeliveryStatus

        notification_id = uuid4()
        record = AuditRecord(
            audit_id=uuid4(),
            notification_id=notification_id,
            notification_type="test.audit",
            status=DeliveryStatus.FAILED,
            channels_attempted=(Channel.EMAIL,),
            channels_succeeded=(),
            channels_failed=(Channel.EMAIL,),
            error_message="SMTP connection failed",
            intent="SAFETY",
            delivery_mode="GUARANTEED",
            autonomy_mode="PREVIEW",
            agent_id=uuid4(),
            plan_id=None,
            decision_snapshot_id=None,
            execution_snapshot_id=None,
            skip_snapshot_id=None,
            title="Audit Test",
            source="test",
            correlation_id="corr-123",
            metadata={},
            audit_metadata={},
            notification_created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC),
            audit_created_at=datetime.now(UTC),
        )
        get_audit_logger().store.save_delivery_audit(record)

        # Query via UI audit endpoint
        client = TestClient(app)
        response = client.get("/ui/audit")
        assert response.status_code == 200

        data = response.json()
        assert data["pagination"]["total_count"] == 1
        assert data["items"][0]["event_type"] == "delivery.failed"
        assert data["items"][0]["notification_id"] == str(notification_id)

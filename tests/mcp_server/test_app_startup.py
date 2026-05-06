"""Tests for application startup and persistence configuration.

Tests the automatic wiring of audit stores and read model adapters
that happens at application startup.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from mcp_server.app import configure_persistence, create_app


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
        assert app.title == "Unified Notification Service"

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
        assert app.title == "Unified Notification Service"

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
        assert response.json() == {"status": "healthy"}


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

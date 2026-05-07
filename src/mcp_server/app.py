"""FastAPI application factory for the MCP Server.

This module provides the application factory and configuration for the
notification service HTTP API.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from mcp_server.observability import ObservabilityMiddleware
from mcp_server.routes_notification import router as notification_router
from mcp_server.routes_ui import router as ui_router

logger = logging.getLogger(__name__)


def configure_persistence() -> None:
    """Configure persistence layer for audit stores and read models.

    This function wires up the audit stores and read model adapters at startup.
    Configuration is determined by environment variables:

    - DATABASE_URL: If set, uses SQLAlchemy with the specified database.
      If not set, uses in-memory storage (suitable for local demo only).

    - UNS_CREATE_TABLES: If "true", creates database tables on startup.
      Default is "true" for local development convenience.

    For local demo/development:
        - Uses shared InMemoryAuditStore for both writes (audit logger) and reads
        - Data is NOT persisted across restarts
        - Suitable for testing and demos only

    For production:
        - Set DATABASE_URL to a PostgreSQL/MySQL connection string
        - Uses SQLAlchemy-backed stores with proper persistence
        - Tables are created on first run if UNS_CREATE_TABLES=true
    """
    from mcp_server.read_models import (
        InMemoryReadModelAdapter,
        configure_read_model_adapter,
        create_sqlalchemy_adapter,
    )
    from notification.audit import (
        InMemoryAuditStore,
        configure_audit_logger,
    )

    database_url = os.environ.get("DATABASE_URL")
    create_tables = os.environ.get("UNS_CREATE_TABLES", "true").lower() == "true"

    if database_url:
        # Production mode: use SQLAlchemy-backed storage
        logger.info(
            "Configuring SQLAlchemy persistence (DATABASE_URL set)",
            extra={"create_tables": create_tables},
        )

        # Configure read model adapter
        adapter = create_sqlalchemy_adapter(
            database_url=database_url,
            create_tables=create_tables,
        )
        configure_read_model_adapter(adapter)

        # Configure audit logger with SQLAlchemy store
        from db.audit_store import create_sqlalchemy_audit_store
        from db.policy_store import create_sqlalchemy_policy_store
        from notification.policies import configure_policy_registry

        audit_store = create_sqlalchemy_audit_store(
            database_url=database_url,
            create_tables=create_tables,
        )
        configure_audit_logger(store=audit_store)

        policy_store = create_sqlalchemy_policy_store(
            database_url=database_url,
            create_tables=create_tables,
        )
        configure_policy_registry(registry=policy_store.load_runtime_registry())

        logger.info("SQLAlchemy persistence configured successfully")
    else:
        # Demo/development mode: use shared in-memory storage
        logger.warning(
            "DATABASE_URL not set. Using in-memory storage. "
            "Data will NOT persist across restarts. "
            "Set DATABASE_URL for production use."
        )

        # Create shared audit store for both reads and writes
        shared_audit_store = InMemoryAuditStore()

        # Configure audit logger (writes)
        configure_audit_logger(store=shared_audit_store)

        # Configure read adapter (reads) - shares the same store
        adapter = InMemoryReadModelAdapter(audit_store=shared_audit_store)
        configure_read_model_adapter(adapter)

        logger.info("In-memory persistence configured (shared store for reads and writes)")


def create_app(skip_persistence_config: bool = False) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        skip_persistence_config: If True, skips automatic persistence configuration.
            Useful for testing when you want to configure adapters manually.

    Returns:
        Configured FastAPI application instance
    """
    # Configure persistence layer (audit stores, read model adapters)
    # This must happen before the app starts handling requests
    if not skip_persistence_config:
        configure_persistence()

    app = FastAPI(
        title="AGSignal Console API",
        description="Read-first console API for AGSignal governance signals",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add observability middleware for UI endpoints
    # This provides request ID generation, metrics, and structured logging
    app.add_middleware(ObservabilityMiddleware, ui_prefix="/ui")

    # Include notification routes
    app.include_router(notification_router)

    # Include UI routes (read-only endpoints)
    app.include_router(ui_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    logger.info("UNS API application created")
    return app


# Application instance for ASGI servers
app = create_app()

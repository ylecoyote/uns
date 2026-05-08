"""FastAPI application factory for the MCP Server.

This module provides the application factory and configuration for the
notification service HTTP API.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI

from mcp_server.auth import configure_cors
from mcp_server.observability import ObservabilityMiddleware
from mcp_server.routes_notification import router as notification_router
from mcp_server.routes_ui import router as ui_router

logger = logging.getLogger(__name__)


def _docs_url(suffix: str) -> str | None:
    """Return ``suffix`` only when interactive API docs are explicitly enabled.

    Disabled by default so production deployments do not leak the full API
    surface to anonymous callers. Set ``AGSIGNAL_ENABLE_DOCS=true`` to expose
    ``/docs``, ``/redoc``, and ``/openapi.json``.
    """
    enabled = os.environ.get("AGSIGNAL_ENABLE_DOCS", "false").strip().lower()
    return suffix if enabled in ("1", "true", "yes", "on") else None


def _policy_dir_from_env() -> Path | None:
    raw_path = os.environ.get("AGSIGNAL_POLICY_DIR") or os.environ.get("UNS_POLICY_DIR")
    return Path(raw_path) if raw_path else None


def configure_persistence() -> None:
    """Configure persistence layer for audit stores and read models.

    This function wires up the audit stores and read model adapters at startup.
    Configuration is determined by environment variables:

    - DATABASE_URL: If set, uses SQLAlchemy with the specified database.
      If not set, uses in-memory storage (suitable for local demo only).

    - AGSIGNAL_CREATE_TABLES: If "true", creates database tables on startup.
      UNS_CREATE_TABLES remains supported as a compatibility alias.
      Defaults to "false" so production deployments do not auto-mutate
      schema; set to "true" for local demos or first-run bootstrap.

    For local demo/development:
        - Uses shared InMemoryAuditStore for both writes (audit logger) and reads
        - Data is NOT persisted across restarts
        - Suitable for testing and demos only

    For production:
        - Set DATABASE_URL to a PostgreSQL/MySQL connection string
        - Uses SQLAlchemy-backed stores with proper persistence
        - Schema management is operator-driven; opt in with AGSIGNAL_CREATE_TABLES=true
          only on first-run bootstrap, then unset
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
    create_tables = (
        os.environ.get("AGSIGNAL_CREATE_TABLES")
        or os.environ.get("UNS_CREATE_TABLES")
        or "false"
    ).lower() == "true"

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

        policy_dir = _policy_dir_from_env()
        if policy_dir is not None:
            from notification.policies import configure_policy_registry
            from notification.policy_loader import load_runtime_registry_from_directory

            loaded_count, registry = load_runtime_registry_from_directory(policy_dir)
            configure_policy_registry(registry=registry)
            logger.info(
                "Loaded ACTIVE runtime policies from AGSIGNAL_POLICY_DIR",
                extra={"loaded_count": loaded_count, "policy_count": len(registry)},
            )


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
        docs_url=_docs_url("/docs"),
        redoc_url=_docs_url("/redoc"),
        openapi_url=_docs_url("/openapi.json"),
    )

    configure_cors(app)

    # Add observability middleware for UI endpoints
    # This provides request ID generation, metrics, and structured logging
    app.add_middleware(ObservabilityMiddleware, ui_prefix="/ui")

    # Add Prometheus instrumentation: /metrics endpoint + request middleware.
    from notification.metrics import install_metrics

    install_metrics(app)

    # Install API rate limiting (default 1000/minute per principal/IP).
    from notification.rate_limiter import install_rate_limiter

    install_rate_limiter(app)

    # Include notification routes
    app.include_router(notification_router)

    # Include UI routes (read-only endpoints)
    app.include_router(ui_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Liveness probe (legacy path). Returns 200 once the process is up."""
        return {"status": "healthy"}

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        """Liveness probe (Kubernetes convention)."""
        return {
            "status": "alive",
            "service": "agsignal-console",
            "version": "0.1.0",
        }

    @app.get("/ready", tags=["system"])
    async def ready() -> dict[str, object]:
        """Readiness probe — confirms persistence layer is reachable."""
        from mcp_server.read_models import get_read_model_adapter
        from notification.audit import get_audit_logger

        try:
            adapter = get_read_model_adapter()
            audit_logger = get_audit_logger()
        except Exception as exc:  # noqa: BLE001 - readiness probe needs to surface any failure
            return {
                "status": "not_ready",
                "service": "agsignal-console",
                "version": "0.1.0",
                "error": str(exc),
            }
        return {
            "status": "ready",
            "service": "agsignal-console",
            "version": "0.1.0",
            "read_model_adapter": type(adapter).__name__,
            "audit_logger": type(audit_logger).__name__,
        }

    @app.get("/readyz", tags=["system"])
    async def readyz() -> dict[str, object]:
        """Readiness probe (Kubernetes convention). Same payload as /ready."""
        return await ready()

    logger.info("UNS API application created")
    return app


# Application instance for ASGI servers
app = create_app()

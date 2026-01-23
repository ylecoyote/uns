"""FastAPI application factory for the MCP Server.

This module provides the application factory and configuration for the
notification service HTTP API.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from mcp_server.routes_notification import router as notification_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Unified Notification Service",
        description="Control-plane notification and acknowledgment service",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Include notification routes
    app.include_router(notification_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    logger.info("UNS API application created")
    return app


# Application instance for ASGI servers
app = create_app()

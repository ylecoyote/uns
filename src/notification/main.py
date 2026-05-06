"""Standalone FastAPI application for AGSignal Core."""

from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI

from mcp_server.routes_notification import router as acknowledgment_router
from notification import __version__
from notification.config import get_notification_config
from notification.routes import router as notification_router


def _channel_readiness() -> dict[str, bool]:
    config = get_notification_config()
    return {
        "slack": config.slack_webhook_url is not None,
        "pagerduty": config.pagerduty_routing_key is not None,
        "email": config.smtp_host is not None,
    }


def create_app() -> FastAPI:
    """Create the standalone AGSignal Core HTTP application."""
    app = FastAPI(
        title="AGSignal Core",
        description="Control-plane notification and acknowledgment service for autonomous agents.",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.include_router(notification_router)
    app.include_router(acknowledgment_router, prefix="/api")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "alive",
            "service": "agsignal-core",
            "version": __version__,
        }

    @app.get("/ready", tags=["system"])
    async def ready() -> dict[str, Any]:
        return {
            "status": "ready",
            "service": "agsignal-core",
            "version": __version__,
            "channels_configured": _channel_readiness(),
        }

    return app


app = create_app()


def main() -> None:
    """Run the standalone AGSignal Core HTTP server."""
    uvicorn.run("notification.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()

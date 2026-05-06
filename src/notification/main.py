"""Standalone FastAPI application for AGSignal Core."""

from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI

from mcp_server.routes_notification import router as acknowledgment_router
from notification import __version__
from notification.config import get_notification_config
from notification.dlq import DLQService
from notification.policies import get_policy_registry
from notification.routes import ops_router
from notification.routes import router as notification_router


class _InMemoryRedisList:
    """Minimal Redis-list compatible store for standalone local operation."""

    def __init__(self) -> None:
        self.values: list[str] = []

    def lpush(self, key: str, value: str) -> int:
        self.values.insert(0, value)
        return len(self.values)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        stop = None if end == -1 else end + 1
        return self.values[start:stop]

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        next_values = []
        for item in self.values:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            next_values.append(item)
        self.values = next_values
        return removed

    def llen(self, key: str) -> int:
        return len(self.values)


def _channel_readiness() -> dict[str, bool]:
    config = get_notification_config()
    return {
        "slack": config.slack_webhook_url is not None,
        "pagerduty": config.pagerduty_routing_key is not None,
        "email": config.smtp_host is not None,
    }


def create_app(dlq_service: DLQService | None = None) -> FastAPI:
    """Create the standalone AGSignal Core HTTP application."""
    app = FastAPI(
        title="AGSignal Core",
        description="Control-plane notification and acknowledgment service for autonomous agents.",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.dlq_service = dlq_service or DLQService(redis_client=_InMemoryRedisList())

    app.include_router(notification_router)
    app.include_router(ops_router)
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
            "policy_count": len(get_policy_registry()),
            "dlq_depth": app.state.dlq_service.depth(),
        }

    return app


app = create_app()


def main() -> None:
    """Run the standalone AGSignal Core HTTP server."""
    uvicorn.run("notification.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()

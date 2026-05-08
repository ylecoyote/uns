"""Standalone FastAPI application for AGSignal Core."""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI

from agsignal._in_memory import InMemoryRedisList
from db.policy_store import SQLAlchemyPolicyStore
from mcp_server.auth import configure_cors
from mcp_server.routes_notification import router as acknowledgment_router
from notification import __version__
from notification.audit import AuditStore, InMemoryAuditStore
from notification.channel_health import ChannelHealthTracker
from notification.config import get_notification_config
from notification.dlq import DLQService
from notification.policies import configure_policy_registry, get_policy_registry
from notification.policy_loader import load_runtime_registry_from_directory
from notification.routes import ops_router
from notification.routes import router as notification_router
from notification.websocket_runtime import (
    InMemoryWebSocketReplayStore,
    RedisWebSocketClient,
    RedisWebSocketFanout,
    RedisWebSocketSubscriber,
    WebSocketConnectionManager,
    WebSocketReplayStore,
    websocket_endpoint,
)


def _policy_dir_from_env() -> Path | None:
    raw_path = os.environ.get("AGSIGNAL_POLICY_DIR")
    if raw_path is None:
        legacy = os.environ.get("UNS_POLICY_DIR")
        if legacy is not None:
            warnings.warn(
                "UNS_POLICY_DIR is deprecated. Use AGSIGNAL_POLICY_DIR instead. "
                "UNS_* aliases will be removed in v1.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            raw_path = legacy
    return Path(raw_path) if raw_path else None


def _docs_url(suffix: str) -> str | None:
    """Return ``suffix`` only when interactive API docs are explicitly enabled.

    Disabled by default so production deployments do not leak the full API
    surface to anonymous callers. Set ``AGSIGNAL_ENABLE_DOCS=true`` to expose
    ``/docs``, ``/redoc``, and ``/openapi.json``.
    """
    enabled = os.environ.get("AGSIGNAL_ENABLE_DOCS", "false").strip().lower()
    return suffix if enabled in ("1", "true", "yes", "on") else None


def _channel_readiness() -> dict[str, bool]:
    config = get_notification_config()
    return {
        "slack": config.slack_webhook_url is not None,
        "pagerduty": config.pagerduty_routing_key is not None,
        "email": config.smtp_host is not None,
    }


def create_app(
    dlq_service: DLQService | None = None,
    policy_store: SQLAlchemyPolicyStore | None = None,
    channel_health_tracker: ChannelHealthTracker | None = None,
    audit_store: AuditStore | None = None,
    redis_client_factory: Callable[[str], RedisWebSocketClient] | None = None,
    websocket_replay_store: WebSocketReplayStore | None = None,
) -> FastAPI:
    """Create the standalone AGSignal Core HTTP application."""
    app = FastAPI(
        title="AGSignal Core",
        description="Control-plane notification and acknowledgment service for autonomous agents.",
        version=__version__,
        docs_url=_docs_url("/docs"),
        redoc_url=_docs_url("/redoc"),
        openapi_url=_docs_url("/openapi.json"),
    )
    configure_cors(app)

    # Prometheus instrumentation: /metrics endpoint + request middleware.
    from notification.metrics import install_metrics

    install_metrics(app)

    # Install API rate limiting (default 1000/minute per principal/IP).
    from notification.rate_limiter import install_rate_limiter

    install_rate_limiter(app)
    config = get_notification_config()
    app.state.dlq_service = dlq_service or DLQService(redis_client=InMemoryRedisList())
    app.state.policy_store = policy_store
    app.state.audit_store = audit_store or InMemoryAuditStore()
    tracker = channel_health_tracker or ChannelHealthTracker()
    app.state.channel_health_tracker = tracker
    app.state.http_idempotency_records = {}
    policy_dir = _policy_dir_from_env()
    if policy_dir is not None:
        _, runtime_registry = load_runtime_registry_from_directory(policy_dir)
        configure_policy_registry(registry=runtime_registry)
    websocket_manager = WebSocketConnectionManager()
    app.state.websocket_manager = websocket_manager
    app.state.websocket_replay_store = websocket_replay_store or InMemoryWebSocketReplayStore()
    app.state.websocket_fanout = None
    app.state.websocket_subscriber = None
    if config.websocket_redis_enabled:
        factory = redis_client_factory or _create_redis_client
        redis_client = factory(config.redis_url)
        websocket_fanout = RedisWebSocketFanout(
            redis_client=redis_client,
            channel_prefix=config.websocket_redis_channel,
            channel_health_tracker=tracker,
        )
        app.state.websocket_fanout = websocket_fanout
        websocket_subscriber = RedisWebSocketSubscriber(
            redis_client=redis_client,
            channel_prefix=config.websocket_redis_channel,
            manager=websocket_manager,
            origin_id=websocket_fanout.instance_id,
            channel_health_tracker=tracker,
        )
        websocket_manager.set_subscriber(websocket_subscriber)
        app.state.websocket_subscriber = websocket_subscriber

    app.include_router(notification_router)
    app.include_router(ops_router)
    app.include_router(acknowledgment_router, prefix="/api")
    app.websocket("/ws/agents/{agent_id}")(websocket_endpoint)

    @app.get("/health", tags=["system"])
    @app.get("/healthz", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "alive",
            "service": "agsignal-core",
            "version": __version__,
        }

    @app.get("/ready", tags=["system"])
    @app.get("/readyz", tags=["system"])
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

def main() -> None:
    """Run the standalone AGSignal Core HTTP server."""
    host = os.environ.get("AGSIGNAL_HOST", "127.0.0.1")
    port = int(os.environ.get("AGSIGNAL_PORT", "8000"))
    uvicorn.run("notification.main:app", host=host, port=port, reload=False)


def _create_redis_client(redis_url: str) -> RedisWebSocketClient:
    from redis import Redis

    return Redis.from_url(redis_url)


app = create_app()


if __name__ == "__main__":
    main()

"""Unified FastAPI factory for UNS.

This is the canonical entry point for the UNS HTTP service. It
combines what were previously two separate FastAPI apps (one for the
write/Core surface, one for the read/Console surface) into a single app
that exposes both surfaces.

The two predecessor factories (``notification.main:create_app`` and
``mcp_server.app:create_app``) were deleted in Task 6 of Phase 3.
UNS is pre-release, so there were no external consumers to
preserve compat for; internal consumers cascade-updated in the same
commit.

Mounted route surfaces:
    - ``/api/v1/notifications/*``   send, simulate, status   (write)
    - ``/api/v1/dlq``, ``/policies/*``, ``/ops/*``           (ops)
    - ``/api/v1/notifications/{id}/ack`` and ``/dismiss``    (ack/dismiss)
    - ``/ui/*``                     read-side console        (read)
    - ``/ws/agents/{agent_id}``     websocket fanout
    - ``/health``, ``/healthz``     liveness
    - ``/ready``, ``/readyz``       unified readiness
    - ``/metrics``                  Prometheus

Unified readiness semantics: ``/ready`` and ``/readyz`` check BOTH the
Core-side concerns (DLQ depth, channel-readiness summary, policy count)
AND the Console-side concerns (read-model adapter reachable, audit
logger configured). If any check fails, the probe returns
``status: not_ready`` with the failing component named. This is stricter
than either predecessor factory's readiness probe.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI

from db.policy_store import SQLAlchemyPolicyStore
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
from uns._in_memory import InMemoryRedisList
from uns.api.auth import (
    configure_cors,
    require_authenticated_observer,
)
from uns.api.observability import ObservabilityMiddleware
from uns.api.routes_notification import router as ack_router
from uns.api.routes_ui import router as ui_router
from uns.api.routes_webhooks import router as webhooks_router

logger = logging.getLogger(__name__)


def _docs_url(suffix: str) -> str | None:
    """Return ``suffix`` only when interactive API docs are explicitly enabled."""
    enabled = os.environ.get("UNS_ENABLE_DOCS", "false").strip().lower()
    return suffix if enabled in ("1", "true", "yes", "on") else None


def _policy_dir_from_env() -> Path | None:
    raw_path = os.environ.get("UNS_POLICY_DIR")
    return Path(raw_path) if raw_path else None


def _channel_readiness(runtime: Any = None) -> dict[str, bool]:
    config = get_notification_config()
    slack_ready = config.slack_webhook_url is not None or bool(os.environ.get("UNS_SLACK_BOT_TOKEN"))
    pagerduty_ready = config.pagerduty_routing_key is not None
    email_ready = config.smtp_host is not None
    if runtime is not None and hasattr(runtime, "adapters"):
        from notification.models import Channel

        slack_ready = slack_ready or runtime.adapters.get_adapter(Channel.SLACK) is not None
        pagerduty_ready = pagerduty_ready or runtime.adapters.get_adapter(Channel.PAGERDUTY) is not None
        email_ready = email_ready or runtime.adapters.get_adapter(Channel.EMAIL) is not None
    return {
        "slack": slack_ready,
        "pagerduty": pagerduty_ready,
        "email": email_ready,
    }


def _create_redis_client(redis_url: str) -> RedisWebSocketClient:
    from redis import Redis
    return Redis.from_url(redis_url)


def _configure_persistence() -> None:
    """Wire up audit stores and read-model adapters from environment.

    Behavior matches the Console-side ``configure_persistence`` from the
    pre-Phase-3 ``mcp_server.app`` factory: SQLAlchemy when DATABASE_URL
    is set, in-memory otherwise. ``UNS_CREATE_TABLES=true`` enables
    schema creation for first-run bootstrap.
    """
    from notification.audit import configure_audit_logger
    from uns.api.read_models import (
        InMemoryReadModelAdapter,
        configure_read_model_adapter,
        create_sqlalchemy_adapter,
    )
    from uns.config import value
    database_url = value("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    create_tables = os.environ.get("UNS_CREATE_TABLES", "false").lower() == "true"

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

        # Configure audit logger with SQLAlchemy store. The db.* imports stay
        # in-function so the optional `db` extra isn't pulled in at import time
        # for clients that only need the SDK surface.
        from db.audit_store import create_sqlalchemy_audit_store
        from db.policy_store import create_sqlalchemy_policy_store

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
        memory_adapter = InMemoryReadModelAdapter(audit_store=shared_audit_store)
        configure_read_model_adapter(memory_adapter)

        logger.info("In-memory persistence configured (shared store for reads and writes)")

    # NOTE: UNS_POLICY_DIR loading is handled UNCONDITIONALLY in
    # ``create_app`` after this function returns (see the precedence-rule
    # comment there). The pre-Phase-3 ``mcp_server.app.configure_persistence``
    # had its own in-memory-branch policy_dir load, but in the unified factory
    # that block would fire twice for the same env var, so it is intentionally
    # NOT carried over here.


# Public alias. Tests and external callers reach for this name; the
# underscore-prefixed ``_configure_persistence`` is the internal symbol.
configure_persistence = _configure_persistence


def create_app(
    dlq_service: DLQService | None = None,
    policy_store: SQLAlchemyPolicyStore | None = None,
    channel_health_tracker: ChannelHealthTracker | None = None,
    audit_store: AuditStore | None = None,
    redis_client_factory: Callable[[str], RedisWebSocketClient] | None = None,
    websocket_replay_store: WebSocketReplayStore | None = None,
    skip_persistence_config: bool = False,
    runtime: Any = None,
) -> FastAPI:
    """Create HTTP against one durable Runtime.

    ``skip_persistence_config`` without a runtime is explicit legacy fixture
    composition. Only that composition accepts an injected legacy policy store.
    """
    owns_runtime = runtime is None and not skip_persistence_config
    if runtime is None and not skip_persistence_config:
        from uns.config import build_runtime
        # This factory also serves direct ASGI/Uvicorn and container startup,
        # which do not pass through the CLI's validation in main().
        runtime = build_runtime(require_persistent=True)
    elif runtime is not None:
        from uns.config import configure_runtime_policies
        configure_runtime_policies(runtime)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(runtime.worker()) if runtime is not None else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if owns_runtime and runtime is not None:
                runtime.engine.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title="UNS",
        description=(
            "Control-plane governance signaling for autonomous agents. "
            "Unified Core (write) and Console (read) HTTP surfaces."
        ),
        version=__version__,
        docs_url=_docs_url("/docs"),
        redoc_url=_docs_url("/redoc"),
        openapi_url=_docs_url("/openapi.json"),
    )

    configure_cors(app)
    app.add_middleware(ObservabilityMiddleware, ui_prefix="/ui")

    from notification.metrics import install_metrics
    install_metrics(app)

    from notification.rate_limiter import install_rate_limiter
    install_rate_limiter(app)

    config = get_notification_config()
    app.state.dlq_service = dlq_service or DLQService(redis_client=InMemoryRedisList())
    app.state.policy_store = policy_store
    app.state.runtime = runtime
    app.state.audit_store = runtime.audit_store if runtime is not None else (audit_store or InMemoryAuditStore())
    app.state.read_model_adapter = None  # Explicit legacy fixture composition only.
    if runtime is not None:
        from uns.api.read_models import SQLAlchemyReadModelAdapter
        app.state.read_model_adapter = SQLAlchemyReadModelAdapter(runtime.sessions, runtime=runtime)
    tracker = channel_health_tracker or ChannelHealthTracker()
    app.state.channel_health_tracker = tracker
    app.state.http_idempotency_records = {}

    # Legacy fixture composition may use a process-local registry. Real HTTP,
    # MCP and SDK intake use the Runtime policy authority in the same database.
    policy_dir = _policy_dir_from_env()
    if runtime is None and policy_dir is not None:
        loaded_count, registry = load_runtime_registry_from_directory(policy_dir)
        configure_policy_registry(registry=registry)
        logger.info("Loaded legacy fixture policy directory", extra={"loaded_count": loaded_count})

    # Websocket runtime setup
    websocket_manager = WebSocketConnectionManager()
    app.state.websocket_manager = websocket_manager
    app.state.websocket_replay_store = websocket_replay_store or InMemoryWebSocketReplayStore()
    app.state.websocket_fanout = None
    app.state.websocket_subscriber = None
    app.state.policy_reload_broadcaster = None
    app.state.policy_reload_subscriber = None
    app.state.policy_postgres_listener = None
    redis_client: RedisWebSocketClient | None = None
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

    if runtime is not None:
        from uns.dlq import RuntimeDLQ
        app.state.dlq_service = RuntimeDLQ(runtime)
        from uns.routes import router as runtime_router
        from uns.websocket import WebSocketDeliveryAdapter
        app.include_router(runtime_router)
        from notification.models import Channel
        if runtime.adapters.get_adapter(Channel.WEBSOCKET) is None:
            runtime.adapters.register(WebSocketDeliveryAdapter(app))
        app.state.policy_store = runtime.policy_runtime.store
        app.state.learning_store = runtime.learning_store
        app.state.shadow_evaluator = runtime.shadow_evaluator
        if redis_client is not None:
            from uns.policy_runtime import (
                RedisPolicyReloadBroadcaster,
                RedisPolicyReloadSubscriber,
            )

            broadcaster = RedisPolicyReloadBroadcaster(redis_client)
            runtime.policy_runtime.set_broadcaster(broadcaster)
            app.state.policy_reload_broadcaster = broadcaster
            app.state.policy_reload_subscriber = RedisPolicyReloadSubscriber(
                runtime.policy_runtime,
                origin_id=broadcaster.instance_id,
            )
    # Mount routers
    app.include_router(notification_router)              # /api/v1/notifications/*
    app.include_router(ops_router)                       # /api/v1/dlq, /policies/*, /ops/*
    app.include_router(ack_router, prefix="/api")        # /api/v1/notifications/{id}/ack, /dismiss
    app.include_router(webhooks_router)                  # /api/v1/webhooks/slack, /pagerduty
    app.include_router(ui_router)                        # /ui/*

    # Websocket
    app.websocket("/ws/agents/{agent_id}")(websocket_endpoint)

    # Unified probes
    @app.get("/health", tags=["system"])
    @app.get("/healthz", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "alive",
            "service": "uns",
            "version": __version__,
        }

    @app.get("/ready", tags=["system"], dependencies=[Depends(require_authenticated_observer)])
    @app.get("/readyz", tags=["system"], dependencies=[Depends(require_authenticated_observer)])
    async def ready() -> dict[str, Any]:
        from notification.audit import get_audit_logger
        from uns.api.read_models import get_read_model_adapter
        try:
            if runtime is not None:
                from sqlalchemy import select
                with runtime.engine.connect() as connection:
                    connection.execute(select(1))
            if runtime is not None:
                read_model_adapter = type(app.state.read_model_adapter).__name__
                audit_logger_type = type(runtime.audit_store).__name__
                persistence_mode = runtime.persistence_mode
                operational_progress = runtime.operational_progress()
            else:
                read_model_adapter = type(get_read_model_adapter()).__name__
                audit_logger_type = type(get_audit_logger()).__name__
                persistence_mode = "in_memory"
                operational_progress = None
        except Exception as exc:  # noqa: BLE001 — readiness probe surfaces all failures
            return {
                "status": "not_ready",
                "service": "uns",
                "version": __version__,
                "error": str(exc),
            }
        payload: dict[str, Any] = {
            "status": "ready",
            "service": "uns",
            "version": __version__,
            "persistence_mode": persistence_mode,
            "channels_configured": _channel_readiness(runtime),
            "policy_count": len(runtime.policy_runtime.registry() if runtime is not None else get_policy_registry()),
            "dlq_depth": (
                operational_progress["unresolved_failure_count"]
                if operational_progress is not None
                else app.state.dlq_service.depth()
            ),
            "read_model_adapter": read_model_adapter,
            "audit_logger": audit_logger_type,
        }
        if operational_progress is not None:
            payload["operational_progress"] = operational_progress
        return payload

    return app


def main(argv: list[str] | None = None) -> None:
    """Run the unified UNS HTTP server."""
    import argparse

    from uns.config import ensure_daemon_persistence_configured, value
    parser = argparse.ArgumentParser(description="UNS notification and acknowledgment service")
    parser.add_argument("--host", default=value("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(value("PORT", "8000")))
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="Allow volatile in-memory SQLite storage for local demo or test runs",
    )
    args = parser.parse_args(argv)
    if args.in_memory:
        os.environ["UNS_ALLOW_IN_MEMORY"] = "true"
    try:
        ensure_daemon_persistence_configured(allow_in_memory=args.in_memory)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    host, port = args.host, args.port
    uvicorn.run("uns.app:app", host=host, port=port, reload=False)


# ASGI entrypoint lazily initializes its configured Runtime when ``app`` is accessed.
_default_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    global _default_app
    if name == "app":
        if _default_app is None:
            _default_app = create_app()
        return _default_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()

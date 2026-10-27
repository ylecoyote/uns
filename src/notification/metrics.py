"""Prometheus metrics for UNS.

Defines the metric objects exposed at ``/metrics`` on both UNS apps,
plus the FastAPI middleware that records HTTP request volume and latency
without entangling with the structured-logging :class:`ObservabilityMiddleware`.

Instrumentation is intentionally narrow:

- HTTP layer: every request is counted and timed by route template
  (the route's ``path`` attribute, not the raw URL — preventing cardinality
  explosion on path parameters like notification UUIDs).
- Domain layer: signals and deliveries are counted at their canonical entry
  points (see ``notification.routes`` and ``uns.signaling``).

The ``/metrics`` endpoint requires the configured API key. Prometheus scrapers
must send the same bearer credential as other authenticated HTTP clients.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware

from uns.api.auth import require_write_principal

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "uns_http_requests_total",
    "Total HTTP requests received by UNS",
    labelnames=("method", "path_template", "status_code"),
)

http_request_duration_seconds = Histogram(
    "uns_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "path_template"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

signals_received_total = Counter(
    "uns_signals_received_total",
    "Total governance signals received by UNS",
    labelnames=("intent", "autonomy_mode", "transport"),
)

deliveries_total = Counter(
    "uns_deliveries_total",
    "Total channel delivery attempts by status",
    labelnames=("channel", "status"),
)


# ---------------------------------------------------------------------------
# Recording helpers (called from domain entry points)
# ---------------------------------------------------------------------------


def record_signal_received(intent: str, autonomy_mode: str, transport: str) -> None:
    """Increment the signals counter. Safe to call from any code path."""
    signals_received_total.labels(
        intent=intent,
        autonomy_mode=autonomy_mode,
        transport=transport,
    ).inc()


def record_delivery(channel: str, status: str) -> None:
    """Increment the deliveries counter for a single channel attempt."""
    deliveries_total.labels(channel=channel, status=status).inc()


# ---------------------------------------------------------------------------
# HTTP middleware
# ---------------------------------------------------------------------------


def _resolve_path_template(request: Request) -> str:
    """Return the FastAPI route template (parameterized) when available.

    Falls back to the raw URL path. Using the route template prevents
    high-cardinality labels on path-parameter values (e.g. notification UUIDs).
    """
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return request.url.path


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record per-request count and latency. Excludes ``/metrics`` itself."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.monotonic()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration = time.monotonic() - start
            http_requests_total.labels(
                method=request.method,
                path_template=_resolve_path_template(request),
                status_code="500",
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                path_template=_resolve_path_template(request),
            ).observe(duration)
            raise

        duration = time.monotonic() - start
        path_template = _resolve_path_template(request)
        http_requests_total.labels(
            method=request.method,
            path_template=path_template,
            status_code=str(status_code),
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method,
            path_template=path_template,
        ).observe(duration)
        return response


# ---------------------------------------------------------------------------
# Route mounting
# ---------------------------------------------------------------------------


def install_metrics(app: FastAPI) -> None:
    """Wire Prometheus metrics into a FastAPI app.

    Adds the ``/metrics`` endpoint and the request-recording middleware.
    Idempotent — if called twice on the same app, the route is only mounted
    once. The middleware is added as-is; double-installation will double-count.
    """
    if not any(getattr(route, "path", None) == "/metrics" for route in app.routes):

        @app.get("/metrics", include_in_schema=False, dependencies=[Depends(require_write_principal)])
        async def metrics() -> Response:  # pragma: no cover - thin shim, exercised in tests
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.add_middleware(PrometheusMiddleware)

"""Observability instrumentation for UI endpoints.

This module provides:
- Request ID generation and propagation
- Request metrics collection (latency, status codes, error rates)
- Structured logging with request context
- Error metrics tracking

All UI endpoints emit observability data through this module.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ALLOWED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"})
_KNOWN_UI_ENDPOINTS = frozenset(
    {
        "/ui/session",
        "/ui/deliveries",
        "/ui/deliveries/{id}",
        "/ui/policies/effective",
        "/ui/policies/active",
        "/ui/policies/revisions",
        "/ui/policies/proposals",
        "/ui/policies/proposals/{id}",
        "/ui/invariants",
        "/ui/invariants/summary",
        "/ui/audit",
    }
)


def _normalize_http_method(method: str | None) -> str:
    if not isinstance(method, str):
        return "OTHER"
    upper = method.upper()
    return upper if upper in _ALLOWED_HTTP_METHODS else "OTHER"


# Context variable for request ID propagation
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Get the current request ID from context.

    Returns:
        The current request ID, or None if not in a request context.
    """
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context.

    Args:
        request_id: The request ID to set.
    """
    _request_id_var.set(request_id)


def generate_request_id() -> str:
    """Generate a new unique request ID.

    Returns:
        A UUID-based request ID string.
    """
    return f"req-{uuid.uuid4().hex[:12]}"


class MetricType(str, Enum):
    """Types of metrics collected."""

    REQUEST_TOTAL = "ui_request_total"
    REQUEST_LATENCY_MS = "ui_request_latency_ms"
    REQUEST_ERROR = "ui_request_error"
    REQUEST_IN_PROGRESS = "ui_request_in_progress"


@dataclass
class RequestMetric:
    """A single request metric data point."""

    metric_type: MetricType
    endpoint: str
    method: str
    status_code: int
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert metric to dictionary for logging/export."""
        return {
            "metric_type": self.metric_type.value,
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
        }


class MetricsCollector:
    """Collects and stores request metrics.

    This is an in-memory collector suitable for testing and development.
    For production, replace with Prometheus, StatsD, or similar.
    """

    def __init__(self, max_samples: int = 10_000, max_endpoints: int = 128) -> None:
        self._max_samples = max_samples
        self._max_endpoints = max_endpoints
        self._metrics: deque[RequestMetric] = deque(maxlen=max_samples)
        self._request_counts: dict[str, int] = {}
        self._error_counts: dict[str, int] = {}
        self._latency_samples: dict[str, deque[float]] = {}

    @property
    def _latencies(self) -> dict[str, deque[float]]:
        return self._latency_samples

    @property
    def _requests_by_endpoint(self) -> dict[str, int]:
        return self._request_counts

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        latency_ms: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a completed request.

        Args:
            endpoint: The endpoint path (e.g., "/ui/deliveries").
            method: HTTP method (e.g., "GET").
            status_code: HTTP response status code.
            latency_ms: Request latency in milliseconds.
            labels: Additional labels for the metric.
        """
        labels = labels or {}
        method = _normalize_http_method(method)

        # Record total request count (bounded cardinality)
        key = f"{method}:{endpoint}"
        if key not in self._latency_samples and len(self._latency_samples) >= self._max_endpoints:
            endpoint = "__unmatched__"
            key = f"{method}:__unmatched__"
        self._request_counts[key] = self._request_counts.get(key, 0) + 1

        # Record latency
        if key not in self._latency_samples:
            self._latency_samples[key] = deque(maxlen=self._max_samples)
        self._latency_samples[key].append(latency_ms)

        # Record error if applicable
        if status_code >= 400:
            error_key = f"{key}:{status_code}"
            self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1

        # Store metric
        metric = RequestMetric(
            metric_type=MetricType.REQUEST_TOTAL,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            value=1.0,
            labels=labels,
        )
        self._metrics.append(metric)

        latency_metric = RequestMetric(
            metric_type=MetricType.REQUEST_LATENCY_MS,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            value=latency_ms,
            labels=labels,
        )
        self._metrics.append(latency_metric)

    def record_error(
        self,
        endpoint: str,
        method: str,
        error_code: str,
        error_message: str,
        status_code: int,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record an error metric.

        Args:
            endpoint: The endpoint path.
            method: HTTP method.
            error_code: Machine-readable error code.
            error_message: Human-readable error message.
            status_code: HTTP response status code.
            labels: Additional labels for the metric.
        """
        labels = labels or {}
        labels["error_code"] = error_code
        labels["error_message"] = error_message[:100]  # Truncate long messages

        metric = RequestMetric(
            metric_type=MetricType.REQUEST_ERROR,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            value=1.0,
            labels=labels,
        )
        self._metrics.append(metric)

    def get_request_count(self, endpoint: str, method: str = "GET") -> int:
        """Get total request count for an endpoint."""
        return self._request_counts.get(f"{method}:{endpoint}", 0)

    def get_error_count(
        self, endpoint: str, method: str = "GET", status_code: int | None = None
    ) -> int:
        """Get error count for an endpoint."""
        if status_code:
            return self._error_counts.get(f"{method}:{endpoint}:{status_code}", 0)
        # Sum all errors for this endpoint
        prefix = f"{method}:{endpoint}:"
        return sum(v for k, v in self._error_counts.items() if k.startswith(prefix))

    def get_latency_stats(self, endpoint: str, method: str = "GET") -> dict[str, float] | None:
        """Get latency statistics for an endpoint.

        Returns:
            Dict with min, max, avg, p50, p95, p99 latencies, or None if no data.
        """
        key = f"{method}:{endpoint}"
        samples = self._latency_samples.get(key)
        if not samples:
            return None

        sorted_samples: list[float] = sorted(samples)
        count = len(sorted_samples)

        def percentile(p: float) -> float:
            idx = int(count * p / 100)
            return sorted_samples[min(idx, count - 1)]

        return {
            "min": min(samples),
            "max": max(samples),
            "avg": sum(samples) / count,
            "p50": percentile(50),
            "p95": percentile(95),
            "p99": percentile(99),
            "count": count,
        }

    def get_all_metrics(self) -> list[RequestMetric]:
        """Get all collected metrics."""
        return list(self._metrics)

    def clear(self) -> None:
        """Clear all collected metrics (for testing)."""
        self._metrics.clear()
        self._request_counts.clear()
        self._error_counts.clear()
        self._latency_samples.clear()


# Global metrics collector
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance.

    Returns:
        The singleton MetricsCollector instance.
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def configure_metrics_collector(collector: MetricsCollector | None = None) -> MetricsCollector:
    """Configure the global metrics collector.

    Args:
        collector: Custom collector to use, or None for default.

    Returns:
        The configured MetricsCollector instance.
    """
    global _metrics_collector
    _metrics_collector = collector if collector is not None else MetricsCollector()
    return _metrics_collector


class StructuredLogger:
    """Structured logger with request context.

    Wraps the standard logger to add request ID and other context
    to all log messages.
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _format_extra(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Add request context to extra data."""
        result: dict[str, Any] = {}
        request_id = get_request_id()
        if request_id:
            result["request_id"] = request_id
        if extra:
            result.update(extra)
        return result

    def _format_message(self, msg: str, extra: dict[str, Any]) -> str:
        """Format message with structured context for log output."""
        if not extra:
            return msg
        # Append structured context as key=value pairs
        context_str = " ".join(f"{k}={v}" for k, v in extra.items())
        return f"{msg} [{context_str}]"

    def info(self, msg: str, *args: Any, extra: dict[str, Any] | None = None) -> None:
        """Log info message with request context."""
        formatted_extra = self._format_extra(extra)
        formatted_msg = self._format_message(msg, formatted_extra)
        self._logger.info(formatted_msg, *args)

    def warning(self, msg: str, *args: Any, extra: dict[str, Any] | None = None) -> None:
        """Log warning message with request context."""
        formatted_extra = self._format_extra(extra)
        formatted_msg = self._format_message(msg, formatted_extra)
        self._logger.warning(formatted_msg, *args)

    def error(self, msg: str, *args: Any, extra: dict[str, Any] | None = None) -> None:
        """Log error message with request context."""
        formatted_extra = self._format_extra(extra)
        formatted_msg = self._format_message(msg, formatted_extra)
        self._logger.error(formatted_msg, *args)

    def debug(self, msg: str, *args: Any, extra: dict[str, Any] | None = None) -> None:
        """Log debug message with request context."""
        formatted_extra = self._format_extra(extra)
        formatted_msg = self._format_message(msg, formatted_extra)
        self._logger.debug(formatted_msg, *args)


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger for the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        A StructuredLogger instance.
    """
    return StructuredLogger(name)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for observability instrumentation.

    Provides:
    - Request ID generation and propagation
    - Request timing
    - Metrics collection
    - Structured logging

    Only applies to /ui/* endpoints.
    """

    def __init__(self, app: Any, ui_prefix: str = "/ui") -> None:
        super().__init__(app)
        self.ui_prefix = ui_prefix
        self.logger = get_structured_logger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with observability instrumentation."""
        # Only instrument UI endpoints
        if not request.url.path.startswith(self.ui_prefix):
            return await call_next(request)

        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id or not _REQUEST_ID_PATTERN.match(request_id):
            request_id = generate_request_id()
        set_request_id(request_id)

        # Extract endpoint pattern (normalize path parameters)
        endpoint = self._resolve_endpoint(request)
        method = _normalize_http_method(request.method)

        # Start timing
        start_time = time.perf_counter()

        # Log request start
        self.logger.info(
            "UI request started",
            extra={
                "endpoint": endpoint,
                "method": method,
                "path": request.url.path,
                "query": str(request.query_params),
            },
        )

        try:
            response = await call_next(request)
            endpoint = self._resolve_endpoint(request)

            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Record metrics
            collector = get_metrics_collector()
            collector.record_request(
                endpoint=endpoint,
                method=method,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )

            # Log request completion
            self.logger.info(
                "UI request completed",
                extra={
                    "endpoint": endpoint,
                    "method": method,
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                },
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            endpoint = self._resolve_endpoint(request)
            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Record error metrics
            collector = get_metrics_collector()
            collector.record_error(
                endpoint=endpoint,
                method=method,
                error_code="internal_error",
                error_message=str(e),
                status_code=500,
            )
            collector.record_request(
                endpoint=endpoint,
                method=method,
                status_code=500,
                latency_ms=latency_ms,
            )

            # Log error
            self.logger.error(
                "UI request failed with exception",
                extra={
                    "endpoint": endpoint,
                    "method": method,
                    "error": str(e),
                    "latency_ms": round(latency_ms, 2),
                },
            )

            raise

        finally:
            # Clear request context
            set_request_id(None)  # type: ignore[arg-type]

    def _resolve_endpoint(self, request: Request) -> str:
        """Resolve a bounded route template for the request, or ``__unmatched__``."""
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        if isinstance(template, str) and template:
            return re.sub(r"\{[^}]+\}", "{id}", template)
        app = request.scope.get("app")
        routes = getattr(app, "routes", None)
        if routes is not None:
            for candidate in routes:
                matches = getattr(candidate, "matches", None)
                if callable(matches):
                    try:
                        match, _ = matches(request.scope)
                    except Exception:  # nosec B112
                        continue
                    if match == Match.FULL:
                        cand_path = getattr(candidate, "path", None)
                        if isinstance(cand_path, str) and cand_path:
                            return re.sub(r"\{[^}]+\}", "{id}", cand_path)
            return "__unmatched__"
        return self._normalize_endpoint(request.url.path)

    def _normalize_endpoint(self, path: str) -> str:
        """Normalize path to endpoint pattern.

        Replaces UUID path parameters with placeholders for consistent metrics,
        mapping unknown paths to ``__unmatched__``.

        Args:
            path: The request path.

        Returns:
            Normalized endpoint pattern.
        """
        # Pattern: /ui/deliveries/{uuid} -> /ui/deliveries/{id}
        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        normalized = re.sub(uuid_pattern, "{id}", path, flags=re.IGNORECASE)
        return normalized if normalized in _KNOWN_UI_ENDPOINTS else "__unmatched__"


def create_error_response_with_request_id(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create an error response dict with request ID.

    Args:
        code: Machine-readable error code.
        message: Human-readable error message.
        details: Optional additional context.

    Returns:
        Error response dictionary with request_id.
    """
    request_id = get_request_id() or "unknown"
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "request_id": request_id,
    }


def log_endpoint_call(
    logger: StructuredLogger,
    endpoint_name: str,
    **params: Any,
) -> None:
    """Log an endpoint call with standardized format.

    Args:
        logger: The structured logger to use.
        endpoint_name: Name of the endpoint being called.
        **params: Parameters to log.
    """
    logger.info(
        f"{endpoint_name} called",
        extra=params,
    )


def record_endpoint_error(
    endpoint: str,
    error_code: str,
    error_message: str,
    status_code: int,
) -> None:
    """Record an endpoint error metric.

    Args:
        endpoint: The endpoint path.
        error_code: Machine-readable error code.
        error_message: Human-readable error message.
        status_code: HTTP status code.
    """
    collector = get_metrics_collector()
    collector.record_error(
        endpoint=endpoint,
        method="GET",  # UI endpoints are all GET
        error_code=error_code,
        error_message=error_message,
        status_code=status_code,
    )

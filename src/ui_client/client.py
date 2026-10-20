"""Typed UI API client implementation.

This module provides the main UIApiClient class that provides typed access
to all UI endpoints. It handles HTTP communication, error parsing, pagination,
and request ID propagation.

Features:
- Full type safety with typed responses
- Automatic error handling with typed exceptions
- Request ID propagation for correlation
- Configurable timeouts and retry behavior
- Support for both sync and async usage patterns

Example:
    >>> client = UIApiClient(base_url="http://localhost:8000")
    >>> # List deliveries with filters
    >>> deliveries = client.list_deliveries(
    ...     filters=DeliveryFilters(status=DeliveryStatus.DELIVERED),
    ...     limit=10
    ... )
    >>> # Iterate through all pages
    >>> for delivery in client.iter_deliveries():
    ...     print(delivery.notification_id)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any, TypeVar, cast
from uuid import UUID

import httpx

from notification.models import AutonomyMode, NotificationIntent
from ui_client.errors import ConnectionError, error_from_response
from ui_client.filters import AuditFilters, DeliveryFilters, InvariantFilters
from ui_client.types import (
    AuditEvent,
    AuditEventListResponse,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    InvariantEntry,
    InvariantListResponse,
    InvariantSummaryResponse,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default configuration
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_CONNECT_TIMEOUT = 10.0  # seconds
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


class UIApiClient:
    """Typed client for the UNS UI API endpoints.

    This client provides strongly-typed access to all UI endpoints:
    - GET /ui/deliveries - List delivery timelines
    - GET /ui/deliveries/{notification_id} - Get delivery timeline
    - GET /ui/policies/effective - Get effective policy resolution
    - GET /ui/invariants - List system invariants
    - GET /ui/invariants/summary - Get invariant summary
    - GET /ui/audit - List audit events

    The client handles:
    - HTTP communication via httpx
    - Error response parsing and typed exceptions
    - Request ID propagation
    - Pagination parameter handling
    - Response deserialization to typed models

    Example:
        >>> client = UIApiClient(base_url="http://localhost:8000")
        >>> # Get a specific delivery timeline
        >>> timeline = client.get_delivery_timeline(notification_id)
        >>> print(f"Status: {timeline.status}")
        >>> # List deliveries with pagination
        >>> response = client.list_deliveries(limit=10)
        >>> while response.pagination.has_more:
        ...     response = client.list_deliveries(
        ...         cursor=response.pagination.next_cursor
        ...     )
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        headers: dict[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the UI API client.

        Args:
            base_url: Base URL of the API (e.g., "http://localhost:8000")
            timeout: Request timeout in seconds (default: 30)
            connect_timeout: Connection timeout in seconds (default: 10)
            headers: Additional headers to include in all requests
            http_client: Optional pre-configured httpx.Client to use.
                        If provided, timeout and connect_timeout are ignored.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._default_headers = headers or {}

        if http_client is not None:
            self._client = http_client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=httpx.Timeout(timeout, connect=connect_timeout),
                headers=self._default_headers,
            )
            self._owns_client = True

    def __enter__(self) -> UIApiClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager and close the client."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client connection.

        Should be called when done using the client to release resources.
        """
        if self._owns_client:
            self._client.close()

    def _build_url(self, path: str) -> str:
        """Build the full URL for an API endpoint.

        Args:
            path: API path (e.g., "/ui/deliveries")

        Returns:
            Full URL including base_url
        """
        return f"{self._base_url}{path}"

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Parse error response and raise appropriate exception.

        Args:
            response: HTTP response with error status code

        Raises:
            UIApiError: Appropriate error type based on response
        """
        # Try to parse error response
        try:
            # Handle FastAPI HTTPException format (error in 'detail')
            data = response.json()
            if "detail" in data:
                # FastAPI HTTPException format
                detail = data["detail"]
                if isinstance(detail, dict):
                    error_info = detail.get("error", detail)
                    error_code = error_info.get("code", "unknown_error")
                    message = error_info.get("message", str(detail))
                    details = error_info.get("details")
                    request_id = detail.get("request_id", "unknown")
                else:
                    error_code = "unknown_error"
                    message = str(detail)
                    details = None
                    request_id = "unknown"
            elif "error" in data:
                # Standard error response format
                error_info = data["error"]
                error_code = error_info.get("code", "unknown_error")
                message = error_info.get("message", "Unknown error")
                details = error_info.get("details")
                request_id = data.get("request_id", "unknown")
            else:
                error_code = "unknown_error"
                message = "Unknown error"
                details = None
                request_id = "unknown"
        except Exception:
            error_code = "unknown_error"
            message = response.text or f"HTTP {response.status_code}"
            details = None
            request_id = "unknown"

        # Get retry-after header for rate limiting
        retry_after = None
        if response.status_code == 429:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header and retry_after_header.isdigit():
                retry_after = int(retry_after_header)

        raise error_from_response(
            status_code=response.status_code,
            error_code=error_code,
            message=message,
            request_id=request_id,
            details=details,
            retry_after=retry_after,
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request and return the JSON response.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            params: Query parameters
            request_id: Optional request ID for correlation

        Returns:
            Parsed JSON response

        Raises:
            UIApiError: On API errors
            ConnectionError: On connection failures
        """
        headers = {}
        if request_id:
            headers["X-Request-ID"] = request_id

        try:
            response = self._client.request(
                method=method,
                url=path,
                params=params,
                headers=headers,
            )
        except httpx.ConnectError as e:
            raise ConnectionError(
                message=f"Failed to connect to {self._base_url}: {e}",
                details={"original_error": str(e)},
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                message=f"Request timed out: {e}",
                details={"original_error": str(e)},
            ) from e
        except httpx.RequestError as e:
            raise ConnectionError(
                message=f"Request failed: {e}",
                details={"original_error": str(e)},
            ) from e

        if response.status_code >= 400:
            self._handle_error_response(response)

        return cast(dict[str, Any], response.json())

    # =========================================================================
    # Delivery Endpoints
    # =========================================================================

    def list_deliveries(
        self,
        filters: DeliveryFilters | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_LIMIT,
        request_id: str | None = None,
    ) -> DeliveryTimelineListResponse:
        """List delivery timelines with optional filtering.

        Args:
            filters: Optional filter criteria for the query
            cursor: Pagination cursor from previous response
            limit: Maximum items per page (1-100, default 25)
            request_id: Optional request ID for correlation

        Returns:
            DeliveryTimelineListResponse with items and pagination info

        Raises:
            InvalidParameterError: On invalid filter or limit values
            InvalidCursorError: On invalid pagination cursor
            UIApiError: On other API errors
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_LIMIT)}

        if cursor is not None:
            params["cursor"] = cursor

        if filters is not None:
            params.update(filters.to_query_params())

        data = self._request("GET", "/ui/deliveries", params=params, request_id=request_id)
        return DeliveryTimelineListResponse.model_validate(data)

    def get_delivery_timeline(
        self,
        notification_id: UUID,
        request_id: str | None = None,
    ) -> DeliveryTimelineResponse:
        """Get the full delivery timeline for a specific notification.

        Args:
            notification_id: UUID of the notification
            request_id: Optional request ID for correlation

        Returns:
            DeliveryTimelineResponse with full delivery details

        Raises:
            NotFoundError: If the notification doesn't exist
            UIApiError: On other API errors
        """
        data = self._request(
            "GET",
            f"/ui/deliveries/{notification_id}",
            request_id=request_id,
        )
        return DeliveryTimelineResponse.model_validate(data)

    def iter_deliveries(
        self,
        filters: DeliveryFilters | None = None,
        limit: int = DEFAULT_LIMIT,
        request_id: str | None = None,
    ) -> Iterator[DeliveryTimelineSummary]:
        """Iterate through all delivery timelines, handling pagination automatically.

        This is a convenience method that yields individual DeliveryTimelineSummary
        objects while handling pagination transparently.

        Args:
            filters: Optional filter criteria
            limit: Items per page (affects batch size)
            request_id: Optional request ID for correlation

        Yields:
            DeliveryTimelineSummary objects

        Raises:
            UIApiError: On API errors
        """
        cursor: str | None = None

        while True:
            response = self.list_deliveries(
                filters=filters,
                cursor=cursor,
                limit=limit,
                request_id=request_id,
            )

            yield from response.items

            if not response.pagination.has_more:
                break

            cursor = response.pagination.next_cursor

    # =========================================================================
    # Policy Endpoints
    # =========================================================================

    def get_effective_policy(
        self,
        notification_type: str,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool = False,
        request_id: str | None = None,
    ) -> EffectivePolicyResponse:
        """Get the effective policy resolution for a notification type.

        This endpoint shows how policy values are resolved through the chain:
        1. explicit_override
        2. mode_override
        3. policy_base
        4. sdk_default

        Args:
            notification_type: The notification type to resolve
            intent: The notification intent
            autonomy_mode: The autonomy mode
            irreversible: Whether the action is irreversible
            request_id: Optional request ID for correlation

        Returns:
            EffectivePolicyResponse with effective values and resolution trace

        Raises:
            InvalidParameterError: On invalid parameter values
            UIApiError: On other API errors
        """
        params = {
            "notification_type": notification_type,
            "intent": intent.value,
            "autonomy_mode": autonomy_mode.value,
            "irreversible": str(irreversible).lower(),
        }

        data = self._request(
            "GET",
            "/ui/policies/effective",
            params=params,
            request_id=request_id,
        )
        return EffectivePolicyResponse.model_validate(data)

    # =========================================================================
    # Invariant Endpoints
    # =========================================================================

    def list_invariants(
        self,
        filters: InvariantFilters | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_LIMIT,
        request_id: str | None = None,
    ) -> InvariantListResponse:
        """List system invariants with optional filtering.

        Args:
            filters: Optional filter criteria
            cursor: Pagination cursor from previous response
            limit: Maximum items per page (1-100, default 25)
            request_id: Optional request ID for correlation

        Returns:
            InvariantListResponse with items and pagination info

        Raises:
            InvalidParameterError: On invalid filter values
            InvalidCursorError: On invalid pagination cursor
            UIApiError: On other API errors
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_LIMIT)}

        if cursor is not None:
            params["cursor"] = cursor

        if filters is not None:
            params.update(filters.to_query_params())

        data = self._request("GET", "/ui/invariants", params=params, request_id=request_id)
        return InvariantListResponse.model_validate(data)

    def get_invariants_summary(
        self,
        request_id: str | None = None,
    ) -> InvariantSummaryResponse:
        """Get summary statistics for system invariants.

        Returns:
            InvariantSummaryResponse with counts and statistics

        Raises:
            UIApiError: On API errors
        """
        data = self._request("GET", "/ui/invariants/summary", request_id=request_id)
        return InvariantSummaryResponse.model_validate(data)

    def iter_invariants(
        self,
        filters: InvariantFilters | None = None,
        limit: int = DEFAULT_LIMIT,
        request_id: str | None = None,
    ) -> Iterator[InvariantEntry]:
        """Iterate through all invariants, handling pagination automatically.

        Args:
            filters: Optional filter criteria
            limit: Items per page (affects batch size)
            request_id: Optional request ID for correlation

        Yields:
            InvariantEntry objects

        Raises:
            UIApiError: On API errors
        """
        cursor: str | None = None

        while True:
            response = self.list_invariants(
                filters=filters,
                cursor=cursor,
                limit=limit,
                request_id=request_id,
            )

            yield from response.items

            if not response.pagination.has_more:
                break

            cursor = response.pagination.next_cursor

    # =========================================================================
    # Audit Endpoints
    # =========================================================================

    def list_audit_events(
        self,
        filters: AuditFilters | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_LIMIT,
        request_id: str | None = None,
    ) -> AuditEventListResponse:
        """List audit events with optional filtering.

        Args:
            filters: Optional filter criteria
            cursor: Pagination cursor from previous response
            limit: Maximum items per page (1-100, default 25)
            request_id: Optional request ID for correlation

        Returns:
            AuditEventListResponse with items and pagination info

        Raises:
            InvalidParameterError: On invalid filter values
            InvalidCursorError: On invalid pagination cursor
            UIApiError: On other API errors
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_LIMIT)}

        if cursor is not None:
            params["cursor"] = cursor

        if filters is not None:
            params.update(filters.to_query_params())

        data = self._request("GET", "/ui/audit", params=params, request_id=request_id)
        return AuditEventListResponse.model_validate(data)

    def iter_audit_events(
        self,
        filters: AuditFilters | None = None,
        limit: int = DEFAULT_LIMIT,
        request_id: str | None = None,
    ) -> Iterator[AuditEvent]:
        """Iterate through all audit events, handling pagination automatically.

        Args:
            filters: Optional filter criteria
            limit: Items per page (affects batch size)
            request_id: Optional request ID for correlation

        Yields:
            AuditEvent objects

        Raises:
            UIApiError: On API errors
        """
        cursor: str | None = None

        while True:
            response = self.list_audit_events(
                filters=filters,
                cursor=cursor,
                limit=limit,
                request_id=request_id,
            )

            yield from response.items

            if not response.pagination.has_more:
                break

            cursor = response.pagination.next_cursor


def create_ui_client(
    base_url: str,
    timeout: float = DEFAULT_TIMEOUT,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> UIApiClient:
    """Factory function to create a configured UIApiClient.

    This is the recommended way to create a client instance.

    Args:
        base_url: Base URL of the API
        timeout: Request timeout in seconds
        connect_timeout: Connection timeout in seconds
        headers: Additional headers for all requests

    Returns:
        Configured UIApiClient instance

    Example:
        >>> client = create_ui_client("http://localhost:8000")
        >>> with client:
        ...     deliveries = client.list_deliveries()
    """
    return UIApiClient(
        base_url=base_url,
        timeout=timeout,
        connect_timeout=connect_timeout,
        headers=headers,
    )

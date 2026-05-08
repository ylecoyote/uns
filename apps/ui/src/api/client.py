"""Typed API client for AGSignal Console endpoints.

This client provides typed access to the /ui/* endpoints defined in
src/agsignal/api/routes_ui.py. It supports:

- Request ID propagation via X-Request-ID header
- Consistent error handling per ErrorResponse contract
- Typed responses matching ui-data-contracts.md

Usage:
    client = UNSUIClient(base_url="http://localhost:8000")

    # List deliveries with filters
    deliveries = client.list_deliveries(
        status=DeliveryStatus.DELIVERED,
        limit=10,
    )

    # Get single delivery timeline
    timeline = client.get_delivery_timeline(notification_id)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx

from apps.ui.src.api.models import EffectivePolicyResponse
from apps.ui.src.api.types import (
    DeliveryFilterParams,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    ErrorResponse,
)

if TYPE_CHECKING:
    from datetime import datetime

    from notification.models import (
        AutonomyMode,
        Channel,
        DeliveryMode,
        DeliveryStatus,
        NotificationIntent,
    )


class APIError(Exception):
    """Exception raised when API returns an error response."""

    def __init__(
        self,
        status_code: int,
        error_response: ErrorResponse | None = None,
        message: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_response = error_response
        self.request_id = request_id or (error_response.request_id if error_response else None)
        self.message = message or (
            error_response.error.message if error_response else "Unknown error"
        )
        super().__init__(self.message)


class UNSUIClient:
    """Typed client for AGSignal Console API endpoints.

    Attributes:
        base_url: Base URL of the AGSignal API server
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        """Initialize the UI client.

        Args:
            base_url: Base URL of the AGSignal API server
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def _generate_request_id(self) -> str:
        """Generate a unique request ID for correlation."""
        return f"ui-{uuid.uuid4().hex[:12]}"

    def _get_headers(self, request_id: str | None = None) -> dict[str, str]:
        """Get headers for requests including request ID."""
        rid = request_id or self._generate_request_id()
        return {
            "X-Request-ID": rid,
            "Accept": "application/json",
        }

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses from the API."""
        if response.status_code >= 400:
            try:
                error_data = response.json()
                # Handle both direct error format and nested detail format
                if "error" in error_data:
                    error_response = ErrorResponse.model_validate(error_data)
                elif "detail" in error_data and isinstance(error_data["detail"], dict):
                    error_response = ErrorResponse.model_validate(error_data["detail"])
                else:
                    error_response = None
            except Exception:
                error_response = None
            raise APIError(
                status_code=response.status_code,
                error_response=error_response,
                message=response.text if error_response is None else None,
            )

    def get_effective_policy(
        self,
        notification_type: str,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool = False,
        request_id: str | None = None,
    ) -> EffectivePolicyResponse:
        """Get effective policy resolution for the policy inspector."""
        params = {
            "notification_type": notification_type,
            "intent": intent.value,
            "autonomy_mode": autonomy_mode.value,
            "irreversible": str(irreversible).lower(),
        }
        response = self._client.get(
            f"{self.base_url}/ui/policies/effective",
            params=params,
            headers=self._get_headers(request_id),
        )

        self._handle_error(response)
        return EffectivePolicyResponse.model_validate(response.json())

    def list_deliveries(
        self,
        cursor: str | None = None,
        limit: int = 25,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: DeliveryStatus | None = None,
        intent: NotificationIntent | None = None,
        delivery_mode: DeliveryMode | None = None,
        agent_id: uuid.UUID | None = None,
        autonomy_mode: AutonomyMode | None = None,
        notification_type: str | None = None,
        channel: Channel | None = None,
        request_id: str | None = None,
    ) -> DeliveryTimelineListResponse:
        """List delivery timelines with optional filtering.

        Args:
            cursor: Pagination cursor from previous response
            limit: Number of items per page (1-100, default 25)
            start_time: Filter by created_at >= start_time
            end_time: Filter by created_at < end_time
            status: Filter by delivery status
            intent: Filter by notification intent
            delivery_mode: Filter by GUARANTEED or BEST_EFFORT
            agent_id: Filter by agent UUID
            autonomy_mode: Filter by PREVIEW, SHADOW, or LIVE
            notification_type: Filter by notification type
            channel: Filter by channel attempted
            request_id: Optional request ID for correlation

        Returns:
            DeliveryTimelineListResponse with items and pagination info

        Raises:
            APIError: If the API returns an error response
        """
        params = DeliveryFilterParams(
            cursor=cursor,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            status=status,
            intent=intent,
            delivery_mode=delivery_mode,
            agent_id=agent_id,
            autonomy_mode=autonomy_mode,
            notification_type=notification_type,
            channel=channel,
        )

        response = self._client.get(
            f"{self.base_url}/ui/deliveries",
            params=params.to_query_params(),
            headers=self._get_headers(request_id),
        )

        self._handle_error(response)
        return DeliveryTimelineListResponse.model_validate(response.json())

    def get_delivery_timeline(
        self,
        notification_id: uuid.UUID,
        request_id: str | None = None,
    ) -> DeliveryTimelineResponse:
        """Get full delivery timeline for a specific notification.

        Args:
            notification_id: UUID of the notification
            request_id: Optional request ID for correlation

        Returns:
            DeliveryTimelineResponse with full timeline details

        Raises:
            APIError: If the notification is not found or other error
        """
        response = self._client.get(
            f"{self.base_url}/ui/deliveries/{notification_id}",
            headers=self._get_headers(request_id),
        )

        self._handle_error(response)
        return DeliveryTimelineResponse.model_validate(response.json())

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> UNSUIClient:
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager."""
        self.close()


UNSApiClient = UNSUIClient
UNSApiError = APIError

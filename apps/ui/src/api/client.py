"""Typed API client for UNS /ui endpoints.

This client provides typed access to the read-only UI endpoints:
- GET /ui/policies/effective - Get effective policy resolution trace

All methods are read-only. No mutating actions are supported.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import httpx
from apps.ui.src.api.models import (
    AutonomyMode,
    EffectivePolicyResponse,
    ErrorResponse,
    NotificationIntent,
)

if TYPE_CHECKING:
    pass


class UNSApiError(Exception):
    """Exception raised when an API call fails.

    Attributes:
        status_code: HTTP status code
        error_response: Parsed ErrorResponse if available
        request_id: Request ID for correlation/support
    """

    def __init__(
        self,
        message: str,
        status_code: int,
        error_response: ErrorResponse | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_response = error_response
        self.request_id = request_id


class UNSApiClient:
    """Typed client for UNS /ui API endpoints.

    All methods are read-only per UI Scope v1.

    Usage:
        client = UNSApiClient()
        response = client.get_effective_policy(
            notification_type="trading.order_placed",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        request_id: str | None = None,
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL for the UNS API. Defaults to UNS_API_BASE_URL env var
                     or http://localhost:8000.
            timeout: Request timeout in seconds.
            request_id: Optional request ID for correlation. If not provided,
                       a new UUID will be generated for each request.
        """
        self.base_url = base_url or os.environ.get("UNS_API_BASE_URL", "http://localhost:8000")
        self.timeout = timeout
        self._request_id = request_id
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def _get_request_id(self) -> str:
        """Get or generate a request ID."""
        return self._request_id or str(uuid.uuid4())

    def _make_headers(self, request_id: str | None = None) -> dict[str, str]:
        """Create headers with request ID for correlation."""
        rid = request_id or self._get_request_id()
        return {"X-Request-ID": rid}

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> UNSApiClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def get_effective_policy(
        self,
        notification_type: str,
        intent: NotificationIntent,
        autonomy_mode: AutonomyMode,
        irreversible: bool = False,
        request_id: str | None = None,
    ) -> EffectivePolicyResponse:
        """Get effective policy resolution for a notification type.

        This endpoint shows how policy values are resolved through the chain:
        1. explicit_override - Values passed directly (not applicable here)
        2. mode_override - Policy mode-specific override
        3. policy_base - Policy base value
        4. sdk_default - SDK default derived from intent + autonomy_mode

        Args:
            notification_type: The notification type to resolve (e.g., "trading.order_placed")
            intent: The notification intent (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
            autonomy_mode: The autonomy mode (PREVIEW, SHADOW, LIVE)
            irreversible: Whether the action is irreversible (affects channel selection)
            request_id: Optional request ID for correlation

        Returns:
            EffectivePolicyResponse with effective values and resolution trace

        Raises:
            UNSApiError: If the API returns an error response
        """
        headers = self._make_headers(request_id)

        response = self.client.get(
            "/ui/policies/effective",
            params={
                "notification_type": notification_type,
                "intent": intent.value,
                "autonomy_mode": autonomy_mode.value,
                "irreversible": str(irreversible).lower(),
            },
            headers=headers,
        )

        if response.status_code != 200:
            error_response = None
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_response = ErrorResponse.model_validate(error_data)
            except Exception:
                pass

            raise UNSApiError(
                message=f"API error: {response.status_code}",
                status_code=response.status_code,
                error_response=error_response,
                request_id=headers.get("X-Request-ID"),
            )

        return EffectivePolicyResponse.model_validate(response.json())

"""Error types for the UI API client.

This module defines typed exceptions that map to the API's error responses.
Each error type corresponds to a specific HTTP status code and error code
from the API, enabling precise error handling in client code.

Error codes from ui-data-contracts.md:
- not_found (404): Resource doesn't exist
- invalid_parameter (400): Malformed filter value
- invalid_cursor (400): Pagination cursor invalid/expired
- rate_limited (429): Too many requests
- internal_error (500): Unexpected server error
"""

from __future__ import annotations

from typing import Any


class UIApiError(Exception):
    """Base exception for UI API errors.

    All API errors include:
    - error_code: Machine-readable error code from the API
    - message: Human-readable error description
    - request_id: Request ID for correlation and support
    - status_code: HTTP status code of the response
    - details: Optional additional context from the error response

    Example:
        >>> try:
        ...     client.get_delivery_timeline(notification_id)
        ... except NotFoundError as e:
        ...     print(f"Not found: {e.message} (request_id: {e.request_id})")
        ... except UIApiError as e:
        ...     print(f"API error: {e.error_code} - {e.message}")
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        request_id: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize UIApiError.

        Args:
            error_code: Machine-readable error code from the API
            message: Human-readable error description
            request_id: Request ID for correlation
            status_code: HTTP status code
            details: Optional additional context
        """
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.message = message
        self.request_id = request_id
        self.status_code = status_code
        self.details = details or {}

    def __repr__(self) -> str:
        """Return detailed representation of the error."""
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"request_id={self.request_id!r}, "
            f"status_code={self.status_code})"
        )


class NotFoundError(UIApiError):
    """Raised when a requested resource is not found (404).

    This error is raised when:
    - A delivery timeline is requested for a non-existent notification_id
    - Any other resource lookup fails to find the target

    The message typically includes the resource identifier that wasn't found.
    """

    def __init__(
        self,
        message: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize NotFoundError.

        Args:
            message: Human-readable error description
            request_id: Request ID for correlation
            details: Optional additional context
        """
        super().__init__(
            error_code="not_found",
            message=message,
            request_id=request_id,
            status_code=404,
            details=details,
        )


class InvalidParameterError(UIApiError):
    """Raised when a request parameter is invalid (400).

    This error is raised when:
    - A filter value has an invalid format
    - A required parameter is missing
    - An enum value is not recognized

    Check the details dict for information about which parameter failed.
    """

    def __init__(
        self,
        message: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize InvalidParameterError.

        Args:
            message: Human-readable error description
            request_id: Request ID for correlation
            details: Optional additional context (e.g., which parameter was invalid)
        """
        super().__init__(
            error_code="invalid_parameter",
            message=message,
            request_id=request_id,
            status_code=400,
            details=details,
        )


class InvalidCursorError(UIApiError):
    """Raised when a pagination cursor is invalid or expired (400).

    This error is raised when:
    - The cursor string is malformed
    - The cursor has expired (cursors may have a time limit)
    - The cursor references data that no longer exists

    Recovery: Start pagination from the beginning (without a cursor).
    """

    def __init__(
        self,
        message: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize InvalidCursorError.

        Args:
            message: Human-readable error description
            request_id: Request ID for correlation
            details: Optional additional context
        """
        super().__init__(
            error_code="invalid_cursor",
            message=message,
            request_id=request_id,
            status_code=400,
            details=details,
        )


class RateLimitedError(UIApiError):
    """Raised when the API rate limit is exceeded (429).

    This error includes retry information when available:
    - details may contain 'retry_after' with seconds to wait

    Recovery: Implement exponential backoff or use the retry_after hint.
    """

    def __init__(
        self,
        message: str,
        request_id: str,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize RateLimitedError.

        Args:
            message: Human-readable error description
            request_id: Request ID for correlation
            details: Optional additional context
            retry_after: Seconds to wait before retrying (if provided by server)
        """
        super().__init__(
            error_code="rate_limited",
            message=message,
            request_id=request_id,
            status_code=429,
            details=details,
        )
        self.retry_after = retry_after


class UIApiServerError(UIApiError):
    """Raised when the API encounters an internal error (500).

    This error indicates a server-side issue that the client cannot fix.
    The request_id is especially important for support escalation.

    Recovery: Retry with exponential backoff. If persistent, contact support
    with the request_id for investigation.
    """

    def __init__(
        self,
        message: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize UIApiServerError.

        Args:
            message: Human-readable error description
            request_id: Request ID for correlation and support
            details: Optional additional context
        """
        super().__init__(
            error_code="internal_error",
            message=message,
            request_id=request_id,
            status_code=500,
            details=details,
        )


class ConnectionError(UIApiError):
    """Raised when the client cannot connect to the API.

    This error indicates a network-level failure:
    - Server is unreachable
    - DNS resolution failed
    - Connection timeout

    Recovery: Check network connectivity and server availability.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ConnectionError.

        Args:
            message: Human-readable error description
            details: Optional additional context (e.g., underlying exception)
        """
        super().__init__(
            error_code="connection_error",
            message=message,
            request_id="N/A",  # No request was made
            status_code=0,  # No HTTP response
            details=details,
        )


def error_from_response(
    status_code: int,
    error_code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
    retry_after: int | None = None,
) -> UIApiError:
    """Factory function to create the appropriate error type from an API response.

    Args:
        status_code: HTTP status code
        error_code: Error code from the API response
        message: Error message from the API response
        request_id: Request ID from the API response
        details: Optional additional details from the error
        retry_after: Optional retry-after hint (for rate limiting)

    Returns:
        The appropriate UIApiError subclass instance
    """
    if error_code == "not_found" or status_code == 404:
        return NotFoundError(message=message, request_id=request_id, details=details)

    if error_code == "invalid_cursor":
        return InvalidCursorError(message=message, request_id=request_id, details=details)

    if error_code == "invalid_parameter" or status_code == 400:
        return InvalidParameterError(message=message, request_id=request_id, details=details)

    if error_code == "rate_limited" or status_code == 429:
        return RateLimitedError(
            message=message, request_id=request_id, details=details, retry_after=retry_after
        )

    if status_code >= 500:
        return UIApiServerError(message=message, request_id=request_id, details=details)

    # Fallback to base error
    return UIApiError(
        error_code=error_code,
        message=message,
        request_id=request_id,
        status_code=status_code,
        details=details,
    )

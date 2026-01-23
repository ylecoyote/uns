"""Tests for UI API client errors."""

import pytest

from ui_client.errors import (
    ConnectionError,
    InvalidCursorError,
    InvalidParameterError,
    NotFoundError,
    RateLimitedError,
    UIApiError,
    UIApiServerError,
    error_from_response,
)


class TestUIApiError:
    """Tests for base UIApiError."""

    def test_error_attributes(self):
        """Test error has all expected attributes."""
        error = UIApiError(
            error_code="test_error",
            message="Test error message",
            request_id="req-123",
            status_code=400,
            details={"field": "value"},
        )

        assert error.error_code == "test_error"
        assert error.message == "Test error message"
        assert error.request_id == "req-123"
        assert error.status_code == 400
        assert error.details == {"field": "value"}

    def test_error_str(self):
        """Test error string representation."""
        error = UIApiError(
            error_code="test_error",
            message="Test message",
            request_id="req-123",
            status_code=400,
        )
        assert "test_error" in str(error)
        assert "Test message" in str(error)

    def test_error_repr(self):
        """Test error detailed representation."""
        error = UIApiError(
            error_code="test_error",
            message="Test message",
            request_id="req-123",
            status_code=400,
        )
        repr_str = repr(error)
        assert "UIApiError" in repr_str
        assert "test_error" in repr_str
        assert "req-123" in repr_str
        assert "400" in repr_str

    def test_default_details(self):
        """Test default empty details dict."""
        error = UIApiError(
            error_code="test",
            message="test",
            request_id="req",
            status_code=400,
        )
        assert error.details == {}


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_error_code_and_status(self):
        """Test error has correct code and status."""
        error = NotFoundError(message="Resource not found", request_id="req-456")
        assert error.error_code == "not_found"
        assert error.status_code == 404

    def test_inheritance(self):
        """Test error inherits from UIApiError."""
        error = NotFoundError(message="test", request_id="req")
        assert isinstance(error, UIApiError)


class TestInvalidParameterError:
    """Tests for InvalidParameterError."""

    def test_error_code_and_status(self):
        """Test error has correct code and status."""
        error = InvalidParameterError(
            message="Invalid filter value",
            request_id="req-789",
            details={"parameter": "status", "value": "INVALID"},
        )
        assert error.error_code == "invalid_parameter"
        assert error.status_code == 400
        assert error.details["parameter"] == "status"


class TestInvalidCursorError:
    """Tests for InvalidCursorError."""

    def test_error_code_and_status(self):
        """Test error has correct code and status."""
        error = InvalidCursorError(message="Cursor expired", request_id="req-abc")
        assert error.error_code == "invalid_cursor"
        assert error.status_code == 400


class TestRateLimitedError:
    """Tests for RateLimitedError."""

    def test_error_code_and_status(self):
        """Test error has correct code and status."""
        error = RateLimitedError(
            message="Too many requests",
            request_id="req-def",
            retry_after=30,
        )
        assert error.error_code == "rate_limited"
        assert error.status_code == 429
        assert error.retry_after == 30

    def test_no_retry_after(self):
        """Test error without retry_after hint."""
        error = RateLimitedError(message="Rate limited", request_id="req")
        assert error.retry_after is None


class TestUIApiServerError:
    """Tests for UIApiServerError."""

    def test_error_code_and_status(self):
        """Test error has correct code and status."""
        error = UIApiServerError(
            message="Internal server error",
            request_id="req-ghi",
        )
        assert error.error_code == "internal_error"
        assert error.status_code == 500


class TestConnectionError:
    """Tests for ConnectionError."""

    def test_connection_error_attributes(self):
        """Test connection error has expected attributes."""
        error = ConnectionError(
            message="Failed to connect",
            details={"host": "localhost", "port": 8000},
        )
        assert error.error_code == "connection_error"
        assert error.status_code == 0  # No HTTP response
        assert error.request_id == "N/A"
        assert error.details["host"] == "localhost"


class TestErrorFromResponse:
    """Tests for error_from_response factory function."""

    def test_not_found_by_code(self):
        """Test creating NotFoundError from error code."""
        error = error_from_response(
            status_code=404,
            error_code="not_found",
            message="Notification not found",
            request_id="req-1",
        )
        assert isinstance(error, NotFoundError)

    def test_not_found_by_status(self):
        """Test creating NotFoundError from status code alone."""
        error = error_from_response(
            status_code=404,
            error_code="resource_missing",  # Different code
            message="Not found",
            request_id="req-2",
        )
        assert isinstance(error, NotFoundError)

    def test_invalid_cursor(self):
        """Test creating InvalidCursorError."""
        error = error_from_response(
            status_code=400,
            error_code="invalid_cursor",
            message="Cursor expired",
            request_id="req-3",
        )
        assert isinstance(error, InvalidCursorError)

    def test_invalid_parameter_by_code(self):
        """Test creating InvalidParameterError from error code."""
        error = error_from_response(
            status_code=400,
            error_code="invalid_parameter",
            message="Invalid status value",
            request_id="req-4",
        )
        assert isinstance(error, InvalidParameterError)

    def test_invalid_parameter_by_status(self):
        """Test creating InvalidParameterError from 400 status."""
        error = error_from_response(
            status_code=400,
            error_code="validation_error",  # Different code
            message="Validation failed",
            request_id="req-5",
        )
        assert isinstance(error, InvalidParameterError)

    def test_rate_limited_by_code(self):
        """Test creating RateLimitedError from error code."""
        error = error_from_response(
            status_code=429,
            error_code="rate_limited",
            message="Too many requests",
            request_id="req-6",
            retry_after=60,
        )
        assert isinstance(error, RateLimitedError)
        assert error.retry_after == 60

    def test_rate_limited_by_status(self):
        """Test creating RateLimitedError from 429 status."""
        error = error_from_response(
            status_code=429,
            error_code="throttled",  # Different code
            message="Throttled",
            request_id="req-7",
        )
        assert isinstance(error, RateLimitedError)

    def test_server_error(self):
        """Test creating UIApiServerError from 5xx status."""
        for status in [500, 502, 503, 504]:
            error = error_from_response(
                status_code=status,
                error_code="internal_error",
                message="Server error",
                request_id="req-8",
            )
            assert isinstance(error, UIApiServerError)

    def test_fallback_to_base_error(self):
        """Test fallback to base UIApiError for unknown codes."""
        error = error_from_response(
            status_code=418,  # I'm a teapot
            error_code="teapot",
            message="I'm a teapot",
            request_id="req-9",
        )
        assert type(error) is UIApiError  # Exact type, not subclass
        assert error.error_code == "teapot"
        assert error.status_code == 418


class TestExceptionHandling:
    """Tests for exception handling patterns."""

    def test_catch_specific_error(self):
        """Test catching specific error types."""
        error = NotFoundError(message="Not found", request_id="req")

        with pytest.raises(NotFoundError) as exc_info:
            raise error

        assert exc_info.value.request_id == "req"

    def test_catch_base_error(self):
        """Test catching base error type catches all API errors."""
        errors = [
            NotFoundError(message="m", request_id="r"),
            InvalidParameterError(message="m", request_id="r"),
            RateLimitedError(message="m", request_id="r"),
            UIApiServerError(message="m", request_id="r"),
        ]

        for error in errors:
            with pytest.raises(UIApiError):
                raise error

    def test_catch_standard_exception(self):
        """Test API errors are standard exceptions."""
        error = NotFoundError(message="test", request_id="req")
        assert isinstance(error, Exception)
        # Verify the error inherits from Exception by checking the MRO
        assert Exception in type(error).__mro__

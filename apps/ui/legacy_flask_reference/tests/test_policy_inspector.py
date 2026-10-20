"""Tests for the Policy Inspector page.

Tests cover:
- Form data validation
- API client integration
- Resolution trace display formatting
- Error handling and request ID propagation
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.ui.src.api.client import UNSApiClient, UNSApiError
from apps.ui.src.api.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    ErrorDetail,
    ErrorResponse,
    NotificationIntent,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)
from apps.ui.src.components.resolution_trace import (
    ResolutionTraceDisplay,
    format_resolution_step,
    format_resolution_value,
)
from apps.ui.src.pages.policy_inspector import (
    PolicyInspectorFormData,
    PolicyInspectorPage,
    PolicyInspectorResult,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_effective_policy_response() -> EffectivePolicyResponse:
    """Create a sample effective policy response for testing."""
    return EffectivePolicyResponse(
        notification_type="trading.order_placed",
        effective=EffectivePolicyValues(
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.SLACK, Channel.EMAIL],
            require_ack=True,
            ack_timeout_minutes=10,
            dedup_window_seconds=300,
        ),
        resolution={
            "delivery_mode": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value="GUARANTEED",
                    applied=True,
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value="BEST_EFFORT",
                    applied=False,
                ),
            ],
            "channels": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=["SLACK", "EMAIL"],
                    applied=True,
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=["SLACK", "WEBSOCKET"],
                    applied=False,
                ),
            ],
            "require_ack": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=True,
                    applied=True,
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=False,
                    applied=False,
                ),
            ],
            "ack_timeout_minutes": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=10,
                    applied=True,
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=60,
                    applied=False,
                ),
            ],
            "dedup_window_seconds": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="Not configured in policy",
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=300,
                    applied=True,
                ),
            ],
        },
        resolution_context=ResolutionContext(
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
            irreversible=False,
            policy_found=True,
            policy_notification_type="trading.order_placed",
        ),
    )


@pytest.fixture
def sample_no_policy_response() -> EffectivePolicyResponse:
    """Create a sample response when no policy is registered."""
    return EffectivePolicyResponse(
        notification_type="unknown.type",
        effective=EffectivePolicyValues(
            delivery_mode=DeliveryMode.BEST_EFFORT,
            channels=[Channel.WEBSOCKET],
            require_ack=False,
            ack_timeout_minutes=None,
            dedup_window_seconds=300,
        ),
        resolution={
            "delivery_mode": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="No policy registered for notification_type",
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value="BEST_EFFORT",
                    applied=True,
                ),
            ],
            "channels": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="No policy registered for notification_type",
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=["WEBSOCKET"],
                    applied=True,
                ),
            ],
            "require_ack": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="No policy registered for notification_type",
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=False,
                    applied=True,
                ),
            ],
            "ack_timeout_minutes": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="No policy registered for notification_type",
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=None,
                    applied=True,
                ),
            ],
            "dedup_window_seconds": [
                ResolutionStep(
                    source=ResolutionSource.POLICY_BASE,
                    value=None,
                    applied=False,
                    reason="No policy registered for notification_type",
                ),
                ResolutionStep(
                    source=ResolutionSource.SDK_DEFAULT,
                    value=300,
                    applied=True,
                ),
            ],
        },
        resolution_context=ResolutionContext(
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_mode=AutonomyMode.PREVIEW,
            irreversible=False,
            policy_found=False,
            policy_notification_type=None,
        ),
    )


# =============================================================================
# Form Data Tests
# =============================================================================


class TestPolicyInspectorFormData:
    """Tests for PolicyInspectorFormData."""

    def test_validate_valid_data(self):
        """Test validation passes for valid data."""
        form_data = PolicyInspectorFormData(
            notification_type="trading.order_placed",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )

        errors = form_data.validate()
        assert errors == []

    def test_validate_empty_notification_type(self):
        """Test validation fails for empty notification_type."""
        form_data = PolicyInspectorFormData(
            notification_type="",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )

        errors = form_data.validate()
        assert len(errors) == 1
        assert "required" in errors[0].lower()

    def test_validate_blank_notification_type(self):
        """Test validation fails for blank (whitespace only) notification_type."""
        form_data = PolicyInspectorFormData(
            notification_type="   ",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )

        errors = form_data.validate()
        assert len(errors) == 1
        assert "blank" in errors[0].lower()

    def test_from_dict(self):
        """Test creating form data from dictionary."""
        data = {
            "notification_type": "test.notification",
            "intent": "SAFETY",
            "autonomy_mode": "LIVE",
            "irreversible": True,
        }

        form_data = PolicyInspectorFormData.from_dict(data)

        assert form_data.notification_type == "test.notification"
        assert form_data.intent == NotificationIntent.SAFETY
        assert form_data.autonomy_mode == AutonomyMode.LIVE
        assert form_data.irreversible is True

    def test_from_dict_defaults(self):
        """Test from_dict uses sensible defaults for missing values."""
        data = {"notification_type": "test"}

        form_data = PolicyInspectorFormData.from_dict(data)

        assert form_data.intent == NotificationIntent.INFORMATIONAL
        assert form_data.autonomy_mode == AutonomyMode.PREVIEW
        assert form_data.irreversible is False


# =============================================================================
# Resolution Trace Display Tests
# =============================================================================


class TestFormatResolutionValue:
    """Tests for format_resolution_value function."""

    def test_format_none(self):
        """Test formatting None value."""
        assert format_resolution_value(None) == "None"

    def test_format_bool_true(self):
        """Test formatting True value."""
        assert format_resolution_value(True) == "Yes"

    def test_format_bool_false(self):
        """Test formatting False value."""
        assert format_resolution_value(False) == "No"

    def test_format_list(self):
        """Test formatting list value."""
        assert format_resolution_value(["SLACK", "EMAIL"]) == "SLACK, EMAIL"

    def test_format_empty_list(self):
        """Test formatting empty list."""
        assert format_resolution_value([]) == "[]"

    def test_format_string(self):
        """Test formatting string value."""
        assert format_resolution_value("GUARANTEED") == "GUARANTEED"

    def test_format_int(self):
        """Test formatting integer value."""
        assert format_resolution_value(300) == "300"


class TestFormatResolutionStep:
    """Tests for format_resolution_step function."""

    def test_format_applied_step(self):
        """Test formatting an applied step."""
        step = ResolutionStep(
            source=ResolutionSource.POLICY_BASE,
            value="GUARANTEED",
            applied=True,
        )

        result = format_resolution_step(step)

        assert "Policy Base" in result
        assert "GUARANTEED" in result
        assert "APPLIED" in result

    def test_format_skipped_step_with_reason(self):
        """Test formatting a skipped step with reason."""
        step = ResolutionStep(
            source=ResolutionSource.SDK_DEFAULT,
            value=["WEBSOCKET"],
            applied=False,
            reason="Policy override takes precedence",
        )

        result = format_resolution_step(step)

        assert "SDK Default" in result
        assert "WEBSOCKET" in result
        assert "SKIPPED" in result
        assert "Policy override takes precedence" in result


class TestResolutionTraceDisplay:
    """Tests for ResolutionTraceDisplay component."""

    def test_notification_type(self, sample_effective_policy_response):
        """Test accessing notification_type property."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)
        assert display.notification_type == "trading.order_placed"

    def test_policy_found(self, sample_effective_policy_response):
        """Test accessing policy_found property."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)
        assert display.policy_found is True

    def test_policy_not_found(self, sample_no_policy_response):
        """Test policy_found when no policy exists."""
        display = ResolutionTraceDisplay(sample_no_policy_response)
        assert display.policy_found is False

    def test_context_properties(self, sample_effective_policy_response):
        """Test context property access."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)

        assert display.intent == "GOVERNANCE"
        assert display.autonomy_mode == "LIVE"
        assert display.irreversible is False

    def test_fields_count(self, sample_effective_policy_response):
        """Test that all policy fields are represented."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)

        assert len(display.fields) == 5  # delivery_mode, channels, require_ack, etc.

    def test_field_display_names(self, sample_effective_policy_response):
        """Test that fields have human-readable display names."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)

        field_names = {f.display_name for f in display.fields}

        assert "Delivery Mode" in field_names
        assert "Channels" in field_names
        assert "Require Acknowledgment" in field_names
        assert "Ack Timeout (minutes)" in field_names
        assert "Dedup Window (seconds)" in field_names

    def test_field_effective_values(self, sample_effective_policy_response):
        """Test that effective values are formatted correctly."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)

        fields_by_name = {f.field_name: f for f in display.fields}

        assert fields_by_name["delivery_mode"].effective_value == "GUARANTEED"
        assert "SLACK" in fields_by_name["channels"].effective_value
        assert "EMAIL" in fields_by_name["channels"].effective_value
        assert fields_by_name["require_ack"].effective_value == "Yes"
        assert fields_by_name["ack_timeout_minutes"].effective_value == "10"
        assert fields_by_name["dedup_window_seconds"].effective_value == "300"

    def test_field_applied_source(self, sample_effective_policy_response):
        """Test that applied source is tracked correctly."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)

        fields_by_name = {f.field_name: f for f in display.fields}

        # Most fields should have policy_base as applied source
        assert fields_by_name["delivery_mode"].applied_source == "policy_base"
        assert fields_by_name["channels"].applied_source == "policy_base"

        # dedup_window_seconds falls back to SDK default
        assert fields_by_name["dedup_window_seconds"].applied_source == "sdk_default"

    def test_get_summary(self, sample_effective_policy_response):
        """Test get_summary returns structured data."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)
        summary = display.get_summary()

        assert summary["notification_type"] == "trading.order_placed"
        assert summary["policy_found"] is True
        assert summary["intent"] == "GOVERNANCE"
        assert summary["autonomy_mode"] == "LIVE"
        assert "delivery_mode" in summary["effective_values"]
        assert "delivery_mode" in summary["applied_sources"]

    def test_to_text(self, sample_effective_policy_response):
        """Test to_text renders readable output."""
        display = ResolutionTraceDisplay(sample_effective_policy_response)
        text = display.to_text()

        assert "trading.order_placed" in text
        assert "GOVERNANCE" in text
        assert "LIVE" in text
        assert "Yes" in text  # policy_found
        assert "Delivery Mode" in text
        assert "GUARANTEED" in text
        assert "Resolution Trace" in text


# =============================================================================
# Policy Inspector Page Tests
# =============================================================================


class TestPolicyInspectorPage:
    """Tests for PolicyInspectorPage."""

    def test_get_form_defaults(self):
        """Test get_form_defaults returns sensible defaults."""
        page = PolicyInspectorPage()
        defaults = page.get_form_defaults()

        assert defaults.notification_type == ""
        assert defaults.intent == NotificationIntent.INFORMATIONAL
        assert defaults.autonomy_mode == AutonomyMode.PREVIEW
        assert defaults.irreversible is False

    def test_form_options_available(self):
        """Test that form options are defined."""
        assert len(PolicyInspectorPage.INTENT_OPTIONS) == 4
        assert len(PolicyInspectorPage.AUTONOMY_MODE_OPTIONS) == 3

        # Check option structure
        for value, label in PolicyInspectorPage.INTENT_OPTIONS:
            assert value in ["SAFETY", "GOVERNANCE", "OPERATIONAL", "INFORMATIONAL"]
            assert isinstance(label, str)

    def test_inspect_validation_error(self):
        """Test inspect returns error for invalid form data."""
        page = PolicyInspectorPage()
        form_data = PolicyInspectorFormData(
            notification_type="",
            intent=NotificationIntent.SAFETY,
            autonomy_mode=AutonomyMode.LIVE,
        )

        result = page.inspect(form_data)

        assert result.success is False
        assert result.error_message is not None
        assert "required" in result.error_message.lower()

    def test_inspect_success(self, sample_effective_policy_response):
        """Test successful inspection with mocked API."""
        mock_client = MagicMock(spec=UNSApiClient)
        mock_client.get_effective_policy.return_value = sample_effective_policy_response

        page = PolicyInspectorPage(api_client=mock_client)
        form_data = PolicyInspectorFormData(
            notification_type="trading.order_placed",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )

        result = page.inspect(form_data)

        assert result.success is True
        assert result.response is not None
        assert result.display is not None
        assert result.error_message is None

        # Verify API was called correctly
        mock_client.get_effective_policy.assert_called_once_with(
            notification_type="trading.order_placed",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
            irreversible=False,
            request_id=None,
        )

    def test_inspect_with_request_id(self, sample_effective_policy_response):
        """Test request_id is propagated to API."""
        mock_client = MagicMock(spec=UNSApiClient)
        mock_client.get_effective_policy.return_value = sample_effective_policy_response

        page = PolicyInspectorPage(api_client=mock_client)
        form_data = PolicyInspectorFormData(
            notification_type="test.type",
            intent=NotificationIntent.SAFETY,
            autonomy_mode=AutonomyMode.LIVE,
        )

        request_id = str(uuid4())
        result = page.inspect(form_data, request_id=request_id)

        assert result.success is True
        assert result.request_id == request_id

        mock_client.get_effective_policy.assert_called_once()
        call_kwargs = mock_client.get_effective_policy.call_args.kwargs
        assert call_kwargs["request_id"] == request_id

    def test_inspect_api_error(self):
        """Test inspect handles API errors gracefully."""
        mock_client = MagicMock(spec=UNSApiClient)
        error_response = ErrorResponse(
            error=ErrorDetail(
                code="invalid_parameter",
                message="Invalid intent value",
            ),
            request_id="req-123",
        )
        mock_client.get_effective_policy.side_effect = UNSApiError(
            message="API error",
            status_code=400,
            error_response=error_response,
            request_id="req-123",
        )

        page = PolicyInspectorPage(api_client=mock_client)
        form_data = PolicyInspectorFormData(
            notification_type="test.type",
            intent=NotificationIntent.SAFETY,
            autonomy_mode=AutonomyMode.LIVE,
        )

        result = page.inspect(form_data)

        assert result.success is False
        assert "400" in result.error_message
        assert "Invalid intent value" in result.error_message
        assert result.request_id == "req-123"

    def test_inspect_unexpected_error(self):
        """Test inspect handles unexpected exceptions."""
        mock_client = MagicMock(spec=UNSApiClient)
        mock_client.get_effective_policy.side_effect = RuntimeError("Connection failed")

        page = PolicyInspectorPage(api_client=mock_client)
        form_data = PolicyInspectorFormData(
            notification_type="test.type",
            intent=NotificationIntent.SAFETY,
            autonomy_mode=AutonomyMode.LIVE,
        )

        result = page.inspect(form_data)

        assert result.success is False
        assert "Connection failed" in result.error_message

    def test_render_text_success(self, sample_effective_policy_response):
        """Test render_text for successful result."""
        mock_client = MagicMock(spec=UNSApiClient)
        mock_client.get_effective_policy.return_value = sample_effective_policy_response

        page = PolicyInspectorPage(api_client=mock_client)
        form_data = PolicyInspectorFormData(
            notification_type="trading.order_placed",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )

        result = page.inspect(form_data)
        text = page.render_text(result)

        assert "trading.order_placed" in text
        assert "GOVERNANCE" in text
        assert "Resolution Trace" in text

    def test_render_text_failure(self):
        """Test render_text for failed result."""
        page = PolicyInspectorPage()
        result = PolicyInspectorResult(
            success=False,
            error_message="Test error message",
            request_id="req-456",
        )

        text = page.render_text(result)

        assert "Failed" in text
        assert "Test error message" in text
        assert "req-456" in text

    def test_context_manager(self, sample_effective_policy_response):
        """Test page can be used as context manager."""
        mock_client = MagicMock(spec=UNSApiClient)
        mock_client.get_effective_policy.return_value = sample_effective_policy_response

        with PolicyInspectorPage(api_client=mock_client) as page:
            form_data = PolicyInspectorFormData(
                notification_type="test",
                intent=NotificationIntent.SAFETY,
                autonomy_mode=AutonomyMode.LIVE,
            )
            result = page.inspect(form_data)
            assert result.success is True

    def test_strips_notification_type(self, sample_effective_policy_response):
        """Test that notification_type whitespace is stripped."""
        mock_client = MagicMock(spec=UNSApiClient)
        mock_client.get_effective_policy.return_value = sample_effective_policy_response

        page = PolicyInspectorPage(api_client=mock_client)
        form_data = PolicyInspectorFormData(
            notification_type="  trading.order_placed  ",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )

        page.inspect(form_data)

        call_kwargs = mock_client.get_effective_policy.call_args.kwargs
        assert call_kwargs["notification_type"] == "trading.order_placed"


# =============================================================================
# Integration Tests (with real backend)
# =============================================================================


class TestPolicyInspectorIntegration:
    """Integration tests that require the real backend.

    These tests are marked with pytest.mark.integration and will
    be skipped if the backend is not running.
    """

    @pytest.fixture
    def real_client(self):
        """Create a real API client for integration tests."""
        import httpx

        client = UNSApiClient(base_url="http://localhost:8000")
        # Check if backend is running
        try:
            httpx.get("http://localhost:8000/health", timeout=1.0)
            yield client
        except (httpx.ConnectError, httpx.ConnectTimeout):
            pytest.skip("Backend not running")
        finally:
            client.close()

    @pytest.mark.integration
    def test_real_api_call(self, real_client):
        """Test making a real API call to the backend."""
        page = PolicyInspectorPage(api_client=real_client)
        form_data = PolicyInspectorFormData(
            notification_type="test.integration",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_mode=AutonomyMode.PREVIEW,
        )

        result = page.inspect(form_data)

        assert result.success is True
        assert result.response is not None
        assert result.response.notification_type == "test.integration"
        # Should fall back to SDK defaults since policy doesn't exist
        assert result.response.resolution_context.policy_found is False

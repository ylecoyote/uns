"""Policy Inspector page for viewing effective policy resolution.

This page allows users to:
1. Enter notification_type, intent, autonomy_mode, and irreversible parameters
2. View the effective policy values that would be used
3. See the complete resolution trace showing how each value was determined

All functionality is READ-ONLY per UI Scope v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.ui.src.api.client import UNSApiClient, UNSApiError
from apps.ui.src.api.models import (
    AutonomyMode,
    EffectivePolicyResponse,
    NotificationIntent,
)
from apps.ui.src.components.resolution_trace import ResolutionTraceDisplay

if TYPE_CHECKING:
    pass


@dataclass
class PolicyInspectorFormData:
    """Form data for the Policy Inspector page.

    Attributes:
        notification_type: The notification type to resolve
        intent: The notification intent
        autonomy_mode: The autonomy mode
        irreversible: Whether the action is irreversible
    """

    notification_type: str
    intent: NotificationIntent
    autonomy_mode: AutonomyMode
    irreversible: bool = False

    def validate(self) -> list[str]:
        """Validate the form data.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.notification_type:
            errors.append("Notification type is required")
        elif not self.notification_type.strip():
            errors.append("Notification type cannot be blank")

        return errors

    @classmethod
    def from_dict(cls, data: dict) -> PolicyInspectorFormData:
        """Create form data from a dictionary.

        Args:
            data: Dictionary with form field values

        Returns:
            PolicyInspectorFormData instance
        """
        return cls(
            notification_type=data.get("notification_type", ""),
            intent=NotificationIntent(data.get("intent", "INFORMATIONAL")),
            autonomy_mode=AutonomyMode(data.get("autonomy_mode", "PREVIEW")),
            irreversible=data.get("irreversible", False),
        )


@dataclass
class PolicyInspectorResult:
    """Result of a policy inspection.

    Attributes:
        success: Whether the inspection succeeded
        response: The API response if successful
        display: The formatted display component if successful
        error_message: Error message if failed
        request_id: Request ID for correlation
    """

    success: bool
    response: EffectivePolicyResponse | None = None
    display: ResolutionTraceDisplay | None = None
    error_message: str | None = None
    request_id: str | None = None


class PolicyInspectorPage:
    """Policy Inspector page component.

    This page provides a form for entering policy resolution parameters
    and displays the effective policy with resolution trace.

    Usage:
        page = PolicyInspectorPage()

        # With form data
        form_data = PolicyInspectorFormData(
            notification_type="trading.order_placed",
            intent=NotificationIntent.GOVERNANCE,
            autonomy_mode=AutonomyMode.LIVE,
        )
        result = page.inspect(form_data)

        if result.success:
            print(result.display.to_text())
        else:
            print(f"Error: {result.error_message}")
    """

    # Form field options for UI rendering
    INTENT_OPTIONS = [
        ("SAFETY", "Safety - Critical safety notifications"),
        ("GOVERNANCE", "Governance - Compliance and approval requests"),
        ("OPERATIONAL", "Operational - System status updates"),
        ("INFORMATIONAL", "Informational - General information"),
    ]

    AUTONOMY_MODE_OPTIONS = [
        ("PREVIEW", "Preview - All notifications to WebSocket only"),
        ("SHADOW", "Shadow - Partial routing for testing"),
        ("LIVE", "Live - Full production routing"),
    ]

    def __init__(self, api_client: UNSApiClient | None = None):
        """Initialize the Policy Inspector page.

        Args:
            api_client: Optional API client. If not provided, a new one
                       will be created using default settings.
        """
        self._api_client = api_client
        self._owns_client = api_client is None

    @property
    def api_client(self) -> UNSApiClient:
        """Get or create the API client."""
        if self._api_client is None:
            self._api_client = UNSApiClient()
        return self._api_client

    def close(self) -> None:
        """Close resources."""
        if self._owns_client and self._api_client is not None:
            self._api_client.close()
            self._api_client = None

    def __enter__(self) -> PolicyInspectorPage:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def inspect(
        self,
        form_data: PolicyInspectorFormData,
        request_id: str | None = None,
    ) -> PolicyInspectorResult:
        """Inspect effective policy for the given parameters.

        This method calls the API to get the effective policy resolution
        and formats it for display.

        Args:
            form_data: The form data with resolution parameters
            request_id: Optional request ID for correlation

        Returns:
            PolicyInspectorResult with the response and display data
        """
        # Validate form data
        validation_errors = form_data.validate()
        if validation_errors:
            return PolicyInspectorResult(
                success=False,
                error_message="; ".join(validation_errors),
                request_id=request_id,
            )

        try:
            response = self.api_client.get_effective_policy(
                notification_type=form_data.notification_type.strip(),
                intent=form_data.intent,
                autonomy_mode=form_data.autonomy_mode,
                irreversible=form_data.irreversible,
                request_id=request_id,
            )

            display = ResolutionTraceDisplay(response)

            return PolicyInspectorResult(
                success=True,
                response=response,
                display=display,
                request_id=request_id,
            )

        except UNSApiError as e:
            error_msg = f"API error ({e.status_code})"
            if e.error_response:
                error_msg = f"{error_msg}: {e.error_response.error.message}"

            return PolicyInspectorResult(
                success=False,
                error_message=error_msg,
                request_id=e.request_id or request_id,
            )

        except Exception as e:
            return PolicyInspectorResult(
                success=False,
                error_message=f"Unexpected error: {e!s}",
                request_id=request_id,
            )

    def get_form_defaults(self) -> PolicyInspectorFormData:
        """Get default form values.

        Returns:
            PolicyInspectorFormData with sensible defaults
        """
        return PolicyInspectorFormData(
            notification_type="",
            intent=NotificationIntent.INFORMATIONAL,
            autonomy_mode=AutonomyMode.PREVIEW,
            irreversible=False,
        )

    def render_text(self, result: PolicyInspectorResult) -> str:
        """Render the result as formatted text.

        Args:
            result: The inspection result to render

        Returns:
            Multi-line string suitable for terminal display
        """
        if not result.success:
            lines = [
                "Policy Inspection Failed",
                "=" * 40,
                f"Error: {result.error_message}",
            ]
            if result.request_id:
                lines.append(f"Request ID: {result.request_id}")
            return "\n".join(lines)

        if result.display:
            return result.display.to_text()

        return "No result to display"

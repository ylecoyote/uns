"""Resolution trace display component.

Displays the policy resolution trace showing how each field value
was determined through the resolution chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.ui.src.api.models import (
    EffectivePolicyResponse,
    ResolutionSource,
    ResolutionStep,
)


def format_resolution_value(value: Any) -> str:
    """Format a resolution value for display.

    Args:
        value: The value to format (can be any type)

    Returns:
        Human-readable string representation
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        if not value:
            return "[]"
        return ", ".join(str(v) for v in value)
    return str(value)


def format_resolution_step(step: ResolutionStep) -> str:
    """Format a single resolution step for display.

    Args:
        step: The resolution step to format

    Returns:
        Human-readable string describing the step
    """
    source_labels = {
        ResolutionSource.EXPLICIT_OVERRIDE: "Explicit Override",
        ResolutionSource.MODE_OVERRIDE: "Mode Override",
        ResolutionSource.POLICY_BASE: "Policy Base",
        ResolutionSource.SDK_DEFAULT: "SDK Default",
    }

    source_label = source_labels.get(step.source, step.source.value)
    value_str = format_resolution_value(step.value)
    status = "APPLIED" if step.applied else "SKIPPED"

    result = f"{source_label}: {value_str} [{status}]"
    if step.reason:
        result += f" - {step.reason}"

    return result


@dataclass
class ResolutionFieldDisplay:
    """Display data for a single resolution field."""

    field_name: str
    display_name: str
    effective_value: str
    steps: list[str]
    applied_source: str | None


class ResolutionTraceDisplay:
    """Component for displaying policy resolution trace.

    This component takes an EffectivePolicyResponse and formats it
    for display, showing:
    - Effective values for each field
    - Resolution trace showing how each value was determined
    - Which source was applied for each field

    Usage:
        display = ResolutionTraceDisplay(response)
        for field in display.fields:
            print(f"{field.display_name}: {field.effective_value}")
            for step in field.steps:
                print(f"  {step}")
    """

    FIELD_DISPLAY_NAMES = {
        "delivery_mode": "Delivery Mode",
        "channels": "Channels",
        "require_ack": "Require Acknowledgment",
        "ack_timeout_minutes": "Ack Timeout (minutes)",
        "dedup_window_seconds": "Dedup Window (seconds)",
    }

    def __init__(self, response: EffectivePolicyResponse):
        """Initialize the display with an API response.

        Args:
            response: The effective policy response to display
        """
        self.response = response
        self._fields: list[ResolutionFieldDisplay] | None = None

    @property
    def notification_type(self) -> str:
        """Get the notification type."""
        return self.response.notification_type

    @property
    def policy_found(self) -> bool:
        """Whether a policy was found for this notification type."""
        return self.response.resolution_context.policy_found

    @property
    def intent(self) -> str:
        """Get the intent used for resolution."""
        return self.response.resolution_context.intent.value

    @property
    def autonomy_mode(self) -> str:
        """Get the autonomy mode used for resolution."""
        return self.response.resolution_context.autonomy_mode.value

    @property
    def irreversible(self) -> bool:
        """Whether the action was marked as irreversible."""
        return self.response.resolution_context.irreversible

    @property
    def fields(self) -> list[ResolutionFieldDisplay]:
        """Get the display data for all resolution fields.

        Returns:
            List of ResolutionFieldDisplay objects for each policy field
        """
        if self._fields is not None:
            return self._fields

        self._fields = []
        effective = self.response.effective

        # Process each field
        field_effective_values = {
            "delivery_mode": effective.delivery_mode.value,
            "channels": [c.value for c in effective.channels],
            "require_ack": effective.require_ack,
            "ack_timeout_minutes": effective.ack_timeout_minutes,
            "dedup_window_seconds": effective.dedup_window_seconds,
        }

        for field_name, effective_value in field_effective_values.items():
            steps = self.response.resolution.get(field_name, [])
            formatted_steps = [format_resolution_step(step) for step in steps]

            # Find the applied source
            applied_source = None
            for step in steps:
                if step.applied:
                    applied_source = step.source.value
                    break

            self._fields.append(
                ResolutionFieldDisplay(
                    field_name=field_name,
                    display_name=self.FIELD_DISPLAY_NAMES.get(field_name, field_name),
                    effective_value=format_resolution_value(effective_value),
                    steps=formatted_steps,
                    applied_source=applied_source,
                )
            )

        return self._fields

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the resolution for logging/display.

        Returns:
            Dictionary with summary information
        """
        return {
            "notification_type": self.notification_type,
            "policy_found": self.policy_found,
            "intent": self.intent,
            "autonomy_mode": self.autonomy_mode,
            "irreversible": self.irreversible,
            "effective_values": {field.field_name: field.effective_value for field in self.fields},
            "applied_sources": {field.field_name: field.applied_source for field in self.fields},
        }

    def to_text(self) -> str:
        """Render the resolution trace as formatted text.

        Returns:
            Multi-line string suitable for terminal display
        """
        lines = []
        lines.append(f"Policy Resolution for: {self.notification_type}")
        lines.append("=" * 60)
        lines.append("")

        # Context
        lines.append("Resolution Context:")
        lines.append(f"  Intent: {self.intent}")
        lines.append(f"  Autonomy Mode: {self.autonomy_mode}")
        lines.append(f"  Irreversible: {'Yes' if self.irreversible else 'No'}")
        lines.append(f"  Policy Found: {'Yes' if self.policy_found else 'No'}")
        lines.append("")

        # Effective values
        lines.append("Effective Policy Values:")
        lines.append("-" * 40)
        for field in self.fields:
            lines.append(f"  {field.display_name}: {field.effective_value}")
        lines.append("")

        # Resolution trace
        lines.append("Resolution Trace:")
        lines.append("-" * 40)
        for field in self.fields:
            lines.append(f"\n  {field.display_name}:")
            for step in field.steps:
                lines.append(f"    {step}")

        return "\n".join(lines)

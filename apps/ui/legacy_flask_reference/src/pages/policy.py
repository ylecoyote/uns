"""Policy Inspector page.

This module provides the policy resolution inspector functionality
for viewing effective policy configurations and resolution traces.

Routes:
    GET /policy - Policy inspector with resolution trace form

Features:
    - Form for notification_type, intent, autonomy_mode, irreversible
    - Render EffectivePolicyResponse including resolution steps
    - Shows resolution chain: explicit_override -> mode_override -> policy_base -> sdk_default
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyInspectorPageState:
    """State for the Policy Inspector page.

    Attributes:
        notification_type: The notification type to resolve.
        intent: Selected intent (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL).
        autonomy_mode: Selected autonomy mode (PREVIEW, SHADOW, LIVE).
        irreversible: Whether the action is irreversible.
        loading: Whether resolution is in progress.
        error: Error message if any.
    """

    notification_type: str | None = None
    intent: str | None = None
    autonomy_mode: str | None = None
    irreversible: bool = False
    loading: bool = False
    error: str | None = None


# Page placeholders - actual implementation in Phase 1 task 4


def get_policy_page_title() -> str:
    """Get the page title for the Policy Inspector."""
    return "Policy Inspector"


def get_intent_options() -> tuple[str, ...]:
    """Return the available intent options."""
    return ("SAFETY", "GOVERNANCE", "OPERATIONAL", "INFORMATIONAL")


def get_autonomy_mode_options() -> tuple[str, ...]:
    """Return the available autonomy mode options."""
    return ("PREVIEW", "SHADOW", "LIVE")


def get_resolution_sources() -> tuple[str, ...]:
    """Return the resolution source types in priority order."""
    return ("explicit_override", "mode_override", "policy_base", "sdk_default")

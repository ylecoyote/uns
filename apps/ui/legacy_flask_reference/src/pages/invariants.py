"""Invariants Viewer page (list + summary).

This module provides the invariants viewer functionality for
displaying system invariants and compliance status.

Routes:
    GET /invariants - List system invariants with filtering
    GET /invariants/summary - View summary statistics

Filters available:
    - severity: HIGH, MEDIUM, LOW
    - enforcement_type: guard, isolation, test, exception
    - status: active, inactive
    - search: Full-text search on statement

Important:
    If the API returns degraded=true, the UI should clearly
    display this degraded state to the user.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvariantsPageState:
    """State for the Invariants list page.

    Attributes:
        cursor: Current pagination cursor.
        filters: Active filter values.
        loading: Whether data is being fetched.
        error: Error message if any.
        degraded: Whether the system is in degraded state.
    """

    cursor: str | None = None
    filters: dict[str, str] | None = None
    loading: bool = False
    error: str | None = None
    degraded: bool = False


@dataclass(frozen=True)
class InvariantsSummaryPageState:
    """State for the Invariants summary panel.

    Attributes:
        loading: Whether data is being fetched.
        error: Error message if any.
    """

    loading: bool = False
    error: str | None = None


# Page placeholders - actual implementation in Phase 1 task 5


def get_invariants_page_title() -> str:
    """Get the page title for the Invariants list."""
    return "System Invariants"


def get_available_filters() -> tuple[str, ...]:
    """Return the available filter keys for the Invariants page."""
    return (
        "severity",
        "enforcement_type",
        "status",
        "search",
    )


def get_severity_options() -> tuple[str, ...]:
    """Return the available severity options."""
    return ("HIGH", "MEDIUM", "LOW")


def get_enforcement_type_options() -> tuple[str, ...]:
    """Return the available enforcement type options."""
    return ("guard", "isolation", "test", "exception")


def get_status_options() -> tuple[str, ...]:
    """Return the available status options."""
    return ("active", "inactive")

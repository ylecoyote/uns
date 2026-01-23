"""Main layout component for the UNS UI Dashboard.

This module provides the primary layout shell including navigation
and content area structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NavigationRoute(str, Enum):
    """Available navigation routes in the UI."""

    DELIVERIES = "/deliveries"
    POLICY = "/policy"
    INVARIANTS = "/invariants"
    AUDIT = "/audit"


@dataclass(frozen=True)
class NavigationItem:
    """Represents a navigation menu item.

    Attributes:
        route: The route path for this navigation item.
        label: Display label for the navigation item.
        icon: Optional icon identifier.
        description: Brief description of the page.
    """

    route: NavigationRoute
    label: str
    icon: str | None = None
    description: str = ""


# Primary navigation items for the dashboard
NAVIGATION_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem(
        route=NavigationRoute.DELIVERIES,
        label="Deliveries",
        icon="mail",
        description="View notification delivery timelines and channel attempts",
    ),
    NavigationItem(
        route=NavigationRoute.POLICY,
        label="Policy",
        icon="settings",
        description="Inspect effective policy resolution and traces",
    ),
    NavigationItem(
        route=NavigationRoute.INVARIANTS,
        label="Invariants",
        icon="shield",
        description="View system invariants and compliance status",
    ),
    NavigationItem(
        route=NavigationRoute.AUDIT,
        label="Audit",
        icon="history",
        description="Browse the audit event timeline",
    ),
)


def get_navigation_items() -> tuple[NavigationItem, ...]:
    """Return the navigation items for the main layout.

    Returns:
        Tuple of NavigationItem instances representing the main menu.
    """
    return NAVIGATION_ITEMS


def get_route_for_label(label: str) -> NavigationRoute | None:
    """Get the route for a given navigation label.

    Args:
        label: The display label to look up.

    Returns:
        The NavigationRoute if found, None otherwise.
    """
    for item in NAVIGATION_ITEMS:
        if item.label.lower() == label.lower():
            return item.route
    return None

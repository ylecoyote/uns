"""Router configuration for UNS Console.

This module defines the routing structure for the UI application,
mapping URL paths to page handlers.

All routes are read-only (GET requests only) per the v1 scope.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class HTTPMethod(str, Enum):
    """Supported HTTP methods for UI routes.

    Note: Only GET is supported in v1 (read-only posture).
    """

    GET = "GET"


@dataclass(frozen=True)
class Route:
    """Represents a UI route.

    Attributes:
        path: URL path pattern (may include path parameters like {id}).
        method: HTTP method (GET only in v1).
        name: Unique name for the route.
        description: Human-readable description.
    """

    path: str
    method: HTTPMethod
    name: str
    description: str = ""


# Route definitions
# All routes are GET-only (read-only posture per v1 scope)

# Deliveries routes
ROUTE_DELIVERIES_LIST = Route(
    path="/deliveries",
    method=HTTPMethod.GET,
    name="deliveries_list",
    description="List delivery timelines with filtering",
)

ROUTE_DELIVERIES_DETAIL = Route(
    path="/deliveries/{notification_id}",
    method=HTTPMethod.GET,
    name="deliveries_detail",
    description="View delivery timeline for a specific notification",
)

# Policy routes
ROUTE_POLICY_INSPECTOR = Route(
    path="/policy",
    method=HTTPMethod.GET,
    name="policy_inspector",
    description="Inspect effective policy resolution",
)

# Invariants routes
ROUTE_INVARIANTS_LIST = Route(
    path="/invariants",
    method=HTTPMethod.GET,
    name="invariants_list",
    description="List system invariants",
)

ROUTE_INVARIANTS_SUMMARY = Route(
    path="/invariants/summary",
    method=HTTPMethod.GET,
    name="invariants_summary",
    description="View invariant summary statistics",
)

# Audit routes
ROUTE_AUDIT_LIST = Route(
    path="/audit",
    method=HTTPMethod.GET,
    name="audit_list",
    description="Browse audit event timeline",
)

# All registered routes
ALL_ROUTES: tuple[Route, ...] = (
    ROUTE_DELIVERIES_LIST,
    ROUTE_DELIVERIES_DETAIL,
    ROUTE_POLICY_INSPECTOR,
    ROUTE_INVARIANTS_LIST,
    ROUTE_INVARIANTS_SUMMARY,
    ROUTE_AUDIT_LIST,
)


def get_all_routes() -> tuple[Route, ...]:
    """Return all registered routes.

    Returns:
        Tuple of all Route instances.
    """
    return ALL_ROUTES


def get_route_by_name(name: str) -> Route | None:
    """Get a route by its name.

    Args:
        name: The route name to look up.

    Returns:
        The Route if found, None otherwise.
    """
    for route in ALL_ROUTES:
        if route.name == name:
            return route
    return None


def build_path(route: Route, **params: str) -> str:
    """Build a URL path from a route and parameters.

    Args:
        route: The Route to build a path for.
        **params: Path parameters to substitute.

    Returns:
        The constructed URL path.

    Example:
        >>> build_path(ROUTE_DELIVERIES_DETAIL, notification_id="abc-123")
        '/deliveries/abc-123'
    """
    path = route.path
    for key, value in params.items():
        path = path.replace(f"{{{key}}}", value)
    return path


@dataclass
class RouteRegistry:
    """Registry for route handlers.

    This class manages the mapping between routes and their handlers.
    It is primarily used for testing and can be extended for
    different rendering frameworks.
    """

    _handlers: dict[str, Callable[..., object]]

    def __init__(self) -> None:
        """Initialize an empty route registry."""
        self._handlers = {}

    def register(self, route: Route, handler: Callable[..., object]) -> None:
        """Register a handler for a route.

        Args:
            route: The Route to register.
            handler: The handler function.
        """
        self._handlers[route.name] = handler

    def get_handler(self, route: Route) -> Callable[..., object] | None:
        """Get the handler for a route.

        Args:
            route: The Route to look up.

        Returns:
            The handler function if registered, None otherwise.
        """
        return self._handlers.get(route.name)

    def is_registered(self, route: Route) -> bool:
        """Check if a route has a registered handler.

        Args:
            route: The Route to check.

        Returns:
            True if a handler is registered, False otherwise.
        """
        return route.name in self._handlers

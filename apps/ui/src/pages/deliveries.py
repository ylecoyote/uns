"""Deliveries Explorer page (list + detail).

This module provides the delivery timeline explorer functionality
for viewing notification delivery history, channel attempts, and outcomes.

Routes:
    GET /deliveries - List delivery timelines with filtering
    GET /deliveries/{notification_id} - View single delivery timeline

Filters available:
    - intent: SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL
    - delivery_mode: GUARANTEED, BEST_EFFORT
    - status: PENDING, DELIVERED, FAILED, DEDUPLICATED, RATE_LIMITED
    - time_range: start_time, end_time
    - agent_id: Filter by agent UUID
    - autonomy_mode: PREVIEW, SHADOW, LIVE
    - channel: SLACK, EMAIL, WEBSOCKET, PAGERDUTY
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveriesPageState:
    """State for the Deliveries list page.

    Attributes:
        cursor: Current pagination cursor.
        filters: Active filter values.
        loading: Whether data is being fetched.
        error: Error message if any.
    """

    cursor: str | None = None
    filters: dict[str, str] | None = None
    loading: bool = False
    error: str | None = None


@dataclass(frozen=True)
class DeliveryDetailPageState:
    """State for the Delivery detail page.

    Attributes:
        notification_id: The notification ID being viewed.
        loading: Whether data is being fetched.
        error: Error message if any.
    """

    notification_id: str | None = None
    loading: bool = False
    error: str | None = None


# Page placeholders - actual implementation in Phase 1 task 3
# These stubs define the interface for the pages


def get_deliveries_page_title() -> str:
    """Get the page title for the Deliveries list."""
    return "Delivery Timelines"


def get_delivery_detail_page_title(notification_id: str) -> str:
    """Get the page title for a Delivery detail view."""
    return f"Delivery Timeline: {notification_id[:8]}..."


def get_available_filters() -> tuple[str, ...]:
    """Return the available filter keys for the Deliveries page."""
    return (
        "intent",
        "delivery_mode",
        "status",
        "start_time",
        "end_time",
        "agent_id",
        "autonomy_mode",
        "channel",
        "notification_type",
    )

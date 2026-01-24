"""Deliveries Explorer pages.

Provides read-only UI pages for viewing delivery timelines:
- List view with filters (intent, delivery_mode, status, time range, etc.)
- Detail view showing attempts and timestamps for a notification_id

Per ui-scope.md: These are read-only pages with no mutation capabilities.
"""

from __future__ import annotations

# Configure templates directory
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from mcp_server.read_models import DeliveryFilter, get_read_model_adapter
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

_template_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

router = APIRouter(prefix="/pages/deliveries", tags=["ui-pages"])


class DeliveryListFilters(BaseModel):
    """Filter parameters for delivery list page."""

    cursor: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: DeliveryStatus | None = None
    intent: NotificationIntent | None = None
    delivery_mode: DeliveryMode | None = None
    agent_id: UUID | None = None
    autonomy_mode: AutonomyMode | None = None
    notification_type: str | None = None
    channel: Channel | None = None


def _format_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_duration(ms: int) -> str:
    """Format duration in milliseconds for display."""
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    return f"{minutes:.1f}m"


def _get_status_badge_class(status: str) -> str:
    """Get CSS class for status badge."""
    status_classes = {
        "DELIVERED": "badge-success",
        "SUCCESS": "badge-success",
        "PENDING": "badge-warning",
        "FAILED": "badge-danger",
        "DEDUPLICATED": "badge-info",
        "RATE_LIMITED": "badge-warning",
        "SKIPPED": "badge-secondary",
    }
    return status_classes.get(status, "badge-secondary")


def _get_intent_badge_class(intent: str) -> str:
    """Get CSS class for intent badge."""
    intent_classes = {
        "SAFETY": "badge-danger",
        "GOVERNANCE": "badge-warning",
        "OPERATIONAL": "badge-primary",
        "INFORMATIONAL": "badge-info",
    }
    return intent_classes.get(intent, "badge-secondary")


# Register template filters
templates.env.filters["format_datetime"] = _format_datetime
templates.env.filters["format_duration"] = _format_duration
templates.env.filters["status_badge_class"] = _get_status_badge_class
templates.env.filters["intent_badge_class"] = _get_intent_badge_class


@router.get("/", response_class=HTMLResponse, name="deliveries_list")
async def list_deliveries_page(
    request: Request,
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    start_time: datetime | None = Query(default=None, description="Filter by created_at >="),
    end_time: datetime | None = Query(default=None, description="Filter by created_at <"),
    status: DeliveryStatus | None = Query(default=None, description="Filter by status"),
    intent: NotificationIntent | None = Query(default=None, description="Filter by intent"),
    delivery_mode: DeliveryMode | None = Query(default=None, description="Filter by delivery mode"),
    agent_id: UUID | None = Query(default=None, description="Filter by agent UUID"),
    autonomy_mode: AutonomyMode | None = Query(default=None, description="Filter by autonomy mode"),
    notification_type: str | None = Query(default=None, description="Filter by notification type"),
    channel: Channel | None = Query(default=None, description="Filter by channel"),
) -> HTMLResponse:
    """Render the deliveries list page.

    This page displays a paginated, filterable list of delivery timelines.
    Users can filter by intent, delivery_mode, status, time range, agent_id,
    autonomy_mode, notification_type, and channel.
    """
    # Build filter criteria
    filter_criteria = DeliveryFilter(
        start_time=start_time,
        end_time=end_time,
        status=status,
        intent=intent,
        delivery_mode=delivery_mode,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        notification_type=notification_type,
        channel=channel,
    )

    # Query read model adapter
    adapter = get_read_model_adapter()
    result = adapter.get_deliveries(filter_criteria, cursor, limit)

    # Build filter state for form
    filters = {
        "status": status.value if status else "",
        "intent": intent.value if intent else "",
        "delivery_mode": delivery_mode.value if delivery_mode else "",
        "autonomy_mode": autonomy_mode.value if autonomy_mode else "",
        "notification_type": notification_type or "",
        "channel": channel.value if channel else "",
        "agent_id": str(agent_id) if agent_id else "",
        "start_time": start_time.isoformat() if start_time else "",
        "end_time": end_time.isoformat() if end_time else "",
        "limit": limit,
    }

    # Build query string for pagination links
    def build_query_string(new_cursor: str | None = None) -> str:
        params: list[str] = []
        if new_cursor:
            params.append(f"cursor={new_cursor}")
        params.append(f"limit={limit}")
        if status:
            params.append(f"status={status.value}")
        if intent:
            params.append(f"intent={intent.value}")
        if delivery_mode:
            params.append(f"delivery_mode={delivery_mode.value}")
        if autonomy_mode:
            params.append(f"autonomy_mode={autonomy_mode.value}")
        if notification_type:
            params.append(f"notification_type={notification_type}")
        if channel:
            params.append(f"channel={channel.value}")
        if agent_id:
            params.append(f"agent_id={agent_id}")
        if start_time:
            params.append(f"start_time={start_time.isoformat()}")
        if end_time:
            params.append(f"end_time={end_time.isoformat()}")
        return "&".join(params)

    context: dict[str, Any] = {
        "request": request,
        "title": "Deliveries Explorer",
        "items": result.items,
        "pagination": {
            "next_cursor": result.next_cursor,
            "has_more": result.has_more,
            "total_count": result.total_count,
        },
        "filters": filters,
        "next_page_url": (
            f"?{build_query_string(result.next_cursor)}" if result.has_more else None
        ),
        # Enum options for filter dropdowns
        "status_options": [s.value for s in DeliveryStatus],
        "intent_options": [i.value for i in NotificationIntent],
        "delivery_mode_options": [d.value for d in DeliveryMode],
        "autonomy_mode_options": [a.value for a in AutonomyMode],
        "channel_options": [c.value for c in Channel],
    }

    return templates.TemplateResponse("deliveries/list.html", context)


@router.get("/{notification_id}", response_class=HTMLResponse, name="delivery_detail")
async def delivery_detail_page(
    request: Request,
    notification_id: UUID,
) -> HTMLResponse:
    """Render the delivery detail page.

    This page displays the full delivery timeline for a specific notification,
    including all channel attempts, outcomes, and timing information.
    """
    # Query read model adapter
    adapter = get_read_model_adapter()
    timeline = adapter.get_delivery_timeline(notification_id)

    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification not found: {notification_id}",
        )

    context: dict[str, Any] = {
        "request": request,
        "title": f"Delivery Timeline - {notification_id}",
        "timeline": timeline,
        "notification_id": notification_id,
    }

    return templates.TemplateResponse("deliveries/detail.html", context)

"""Deliveries Explorer API endpoints.

Provides read-only JSON API for delivery timeline data:
- List view with filters (intent, delivery_mode, status, time range, etc.)
- Detail view showing attempts and timestamps for a notification_id

Per ui-scope.md: These are read-only endpoints with no mutation capabilities.

Note: This module provides JSON API responses for the React frontend.
The React frontend handles all HTML rendering.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from mcp_server.read_models import DeliveryFilter, get_read_model_adapter
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

router = APIRouter(prefix="/pages/deliveries", tags=["ui-pages"])


# =============================================================================
# Response Models
# =============================================================================


class PaginationInfo(BaseModel):
    """Pagination metadata for list responses."""

    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for next page, null if no more pages"
    )
    has_more: bool = Field(default=False, description="Whether more pages exist")
    total_count: int | None = Field(
        default=None, description="Total count (included when efficient to compute)"
    )


class DeliveryAttemptResponse(BaseModel):
    """Single channel delivery attempt."""

    attempt_id: UUID
    channel: Channel
    status: str  # SUCCESS, FAILED, RATE_LIMITED, SKIPPED
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    error_message: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None


class AutonomyContextResponse(BaseModel):
    """Autonomy context in responses."""

    autonomy_mode: AutonomyMode
    agent_id: UUID
    plan_id: UUID | None = None
    decision_snapshot_id: UUID | None = None
    execution_snapshot_id: UUID | None = None
    skip_snapshot_id: UUID | None = None


class DeliveryTimelineSummary(BaseModel):
    """Summary view of delivery timeline for list responses."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None = None
    channels_attempted: list[Channel] = Field(default_factory=list)
    channels_succeeded: list[Channel] = Field(default_factory=list)
    autonomy_mode: AutonomyMode
    agent_id: UUID


class DeliveryTimelineDetailResponse(BaseModel):
    """Full delivery timeline for a notification (detail view)."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None = None
    attempts: list[DeliveryAttemptResponse] = Field(default_factory=list)
    channels_attempted: list[Channel] = Field(default_factory=list)
    channels_succeeded: list[Channel] = Field(default_factory=list)
    channels_failed: list[Channel] = Field(default_factory=list)
    autonomy_context: AutonomyContextResponse


class FilterOptions(BaseModel):
    """Available filter options for the UI."""

    status_options: list[str]
    intent_options: list[str]
    delivery_mode_options: list[str]
    autonomy_mode_options: list[str]
    channel_options: list[str]


class DeliveryListFilters(BaseModel):
    """Current filter state."""

    status: str = ""
    intent: str = ""
    delivery_mode: str = ""
    autonomy_mode: str = ""
    notification_type: str = ""
    channel: str = ""
    agent_id: str = ""
    start_time: str = ""
    end_time: str = ""
    limit: int = 25


class DeliveryListResponse(BaseModel):
    """Response for delivery list endpoint."""

    items: list[DeliveryTimelineSummary] = Field(default_factory=list)
    pagination: PaginationInfo
    filters: DeliveryListFilters
    filter_options: FilterOptions
    next_page_url: str | None = None


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/",
    response_model=DeliveryListResponse,
    name="deliveries_list",
    summary="List delivery timelines",
    description="Query delivery timelines with optional filtering. Returns JSON for React frontend.",
)
async def list_deliveries_page(
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    start_time: datetime | None = Query(default=None, description="Filter by created_at >="),
    end_time: datetime | None = Query(default=None, description="Filter by created_at <"),
    status: DeliveryStatus | None = Query(default=None, description="Filter by status"),
    intent: NotificationIntent | None = Query(default=None, description="Filter by intent"),
    delivery_mode: DeliveryMode | None = Query(
        default=None, description="Filter by delivery mode"
    ),
    agent_id: UUID | None = Query(default=None, description="Filter by agent UUID"),
    autonomy_mode: AutonomyMode | None = Query(
        default=None, description="Filter by autonomy mode"
    ),
    notification_type: str | None = Query(
        default=None, description="Filter by notification type"
    ),
    channel: Channel | None = Query(default=None, description="Filter by channel"),
) -> DeliveryListResponse:
    """Return paginated, filterable list of delivery timelines as JSON.

    This endpoint provides JSON data for the React frontend to render.
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

    # Convert items to response models
    items = [
        DeliveryTimelineSummary(
            notification_id=item.notification_id,
            notification_type=item.notification_type,
            intent=item.intent,
            delivery_mode=item.delivery_mode,
            status=item.status,
            created_at=item.created_at,
            delivered_at=item.delivered_at,
            channels_attempted=item.channels_attempted,
            channels_succeeded=item.channels_succeeded,
            autonomy_mode=item.autonomy_mode,
            agent_id=item.agent_id,
        )
        for item in result.items
    ]

    # Build filter state
    filters = DeliveryListFilters(
        status=status.value if status else "",
        intent=intent.value if intent else "",
        delivery_mode=delivery_mode.value if delivery_mode else "",
        autonomy_mode=autonomy_mode.value if autonomy_mode else "",
        notification_type=notification_type or "",
        channel=channel.value if channel else "",
        agent_id=str(agent_id) if agent_id else "",
        start_time=start_time.isoformat() if start_time else "",
        end_time=end_time.isoformat() if end_time else "",
        limit=limit,
    )

    # Build next page URL
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

    next_page_url = f"?{build_query_string(result.next_cursor)}" if result.has_more else None

    return DeliveryListResponse(
        items=items,
        pagination=PaginationInfo(
            next_cursor=result.next_cursor,
            has_more=result.has_more,
            total_count=result.total_count,
        ),
        filters=filters,
        filter_options=FilterOptions(
            status_options=[s.value for s in DeliveryStatus],
            intent_options=[i.value for i in NotificationIntent],
            delivery_mode_options=[d.value for d in DeliveryMode],
            autonomy_mode_options=[a.value for a in AutonomyMode],
            channel_options=[c.value for c in Channel],
        ),
        next_page_url=next_page_url,
    )


@router.get(
    "/{notification_id}",
    response_model=DeliveryTimelineDetailResponse,
    name="delivery_detail",
    summary="Get delivery timeline detail",
    description="Get full delivery timeline for a specific notification. Returns JSON for React frontend.",
)
async def delivery_detail_page(
    notification_id: UUID,
) -> DeliveryTimelineDetailResponse:
    """Return the full delivery timeline for a specific notification as JSON.

    This endpoint provides JSON data for the React frontend to render.
    """
    # Query read model adapter
    adapter = get_read_model_adapter()
    timeline = adapter.get_delivery_timeline(notification_id)

    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification not found: {notification_id}",
        )

    # Convert attempts to response model
    attempts = [
        DeliveryAttemptResponse(
            attempt_id=attempt.attempt_id,
            channel=attempt.channel,
            status=attempt.status,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            duration_ms=attempt.duration_ms,
            error_message=attempt.error_message,
            error_code=attempt.error_code,
            metadata=attempt.metadata,
        )
        for attempt in timeline.attempts
    ]

    return DeliveryTimelineDetailResponse(
        notification_id=timeline.notification_id,
        notification_type=timeline.notification_type,
        intent=timeline.intent,
        delivery_mode=timeline.delivery_mode,
        status=timeline.status,
        created_at=timeline.created_at,
        delivered_at=timeline.delivered_at,
        attempts=attempts,
        channels_attempted=timeline.channels_attempted,
        channels_succeeded=timeline.channels_succeeded,
        channels_failed=timeline.channels_failed,
        autonomy_context=AutonomyContextResponse(
            autonomy_mode=timeline.autonomy_mode,
            agent_id=timeline.agent_id,
            plan_id=timeline.plan_id,
            decision_snapshot_id=timeline.decision_snapshot_id,
            execution_snapshot_id=timeline.execution_snapshot_id,
            skip_snapshot_id=timeline.skip_snapshot_id,
        ),
    )

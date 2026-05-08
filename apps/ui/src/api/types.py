"""Typed response models for AGSignal Console API.

These types match the contracts defined in docs/ui/ui-data-contracts.md
and mirror the Pydantic models in src/agsignal/api/routes_ui.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)


class PaginationInfo(BaseModel):
    """Pagination metadata for list responses."""

    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for next page, null if no more pages"
    )
    has_more: bool = Field(default=False, description="Whether more pages exist")
    total_count: int | None = Field(
        default=None, description="Total count (included when efficient to compute)"
    )


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable description")
    details: dict[str, Any] | None = Field(default=None, description="Additional context")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: ErrorDetail
    request_id: str = Field(description="Request ID for correlation/support")


class DeliveryAttempt(BaseModel):
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


class DeliveryTimelineResponse(BaseModel):
    """Full delivery timeline for a notification (detail view)."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None = None
    attempts: list[DeliveryAttempt] = Field(default_factory=list)
    channels_attempted: list[Channel] = Field(default_factory=list)
    channels_succeeded: list[Channel] = Field(default_factory=list)
    channels_failed: list[Channel] = Field(default_factory=list)
    autonomy_context: AutonomyContextResponse


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


class DeliveryTimelineListResponse(BaseModel):
    """Paginated list of delivery timelines."""

    items: list[DeliveryTimelineSummary] = Field(default_factory=list)
    pagination: PaginationInfo


class DeliveryFilterParams(BaseModel):
    """Filter parameters for delivery list queries."""

    cursor: str | None = None
    limit: int = 25
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: DeliveryStatus | None = None
    intent: NotificationIntent | None = None
    delivery_mode: DeliveryMode | None = None
    agent_id: UUID | None = None
    autonomy_mode: AutonomyMode | None = None
    notification_type: str | None = None
    channel: Channel | None = None

    def to_query_params(self) -> dict[str, str]:
        """Convert to query parameters dict for HTTP requests."""
        params: dict[str, str] = {}
        if self.cursor is not None:
            params["cursor"] = self.cursor
        params["limit"] = str(self.limit)
        if self.start_time is not None:
            params["start_time"] = self.start_time.isoformat()
        if self.end_time is not None:
            params["end_time"] = self.end_time.isoformat()
        if self.status is not None:
            params["status"] = self.status.value
        if self.intent is not None:
            params["intent"] = self.intent.value
        if self.delivery_mode is not None:
            params["delivery_mode"] = self.delivery_mode.value
        if self.agent_id is not None:
            params["agent_id"] = str(self.agent_id)
        if self.autonomy_mode is not None:
            params["autonomy_mode"] = self.autonomy_mode.value
        if self.notification_type is not None:
            params["notification_type"] = self.notification_type
        if self.channel is not None:
            params["channel"] = self.channel.value
        return params

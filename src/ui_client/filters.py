"""Filter definitions for UI API queries.

This module provides dataclasses for constructing filter parameters
for the various UI API endpoints. Filters support all the query parameters
documented in the API and convert to query string parameters automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from ui_client.types import (
    AuditEventType,
    EnforcementType,
    InvariantSeverity,
    InvariantStatus,
)


@dataclass(frozen=True)
class DeliveryFilters:
    """Filter criteria for delivery timeline queries.

    All filter fields are optional. When not specified, that filter
    is not applied to the query.

    Attributes:
        start_time: Filter by created_at >= (inclusive)
        end_time: Filter by created_at < (exclusive)
        status: Filter by delivery status
        intent: Filter by notification intent
        delivery_mode: Filter by delivery mode
        agent_id: Filter by agent UUID
        autonomy_mode: Filter by autonomy mode
        notification_type: Filter by notification type string
        channel: Filter by channel attempted
    """

    start_time: datetime | None = None
    end_time: datetime | None = None
    status: DeliveryStatus | None = None
    intent: NotificationIntent | None = None
    delivery_mode: DeliveryMode | None = None
    agent_id: UUID | None = None
    autonomy_mode: AutonomyMode | None = None
    notification_type: str | None = None
    channel: Channel | None = None

    def to_query_params(self) -> dict[str, Any]:
        """Convert filters to query parameters for the API call.

        Returns:
            Dictionary of non-None filter parameters with appropriate
            string conversions for API consumption.
        """
        params: dict[str, Any] = {}

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


@dataclass(frozen=True)
class AuditFilters:
    """Filter criteria for audit event queries.

    All filter fields are optional. When not specified, that filter
    is not applied to the query.

    Attributes:
        start_time: Filter by event_time >= (inclusive)
        end_time: Filter by event_time < (exclusive)
        event_type: Filter by specific audit event type
        notification_id: Filter by notification UUID
        agent_id: Filter by agent UUID
        autonomy_mode: Filter by autonomy mode
        correlation_id: Filter by correlation ID string
    """

    start_time: datetime | None = None
    end_time: datetime | None = None
    event_type: AuditEventType | None = None
    notification_id: UUID | None = None
    agent_id: UUID | None = None
    autonomy_mode: AutonomyMode | None = None
    correlation_id: str | None = None

    def to_query_params(self) -> dict[str, Any]:
        """Convert filters to query parameters for the API call.

        Returns:
            Dictionary of non-None filter parameters with appropriate
            string conversions for API consumption.
        """
        params: dict[str, Any] = {}

        if self.start_time is not None:
            params["start_time"] = self.start_time.isoformat()
        if self.end_time is not None:
            params["end_time"] = self.end_time.isoformat()
        if self.event_type is not None:
            params["event_type"] = self.event_type.value
        if self.notification_id is not None:
            params["notification_id"] = str(self.notification_id)
        if self.agent_id is not None:
            params["agent_id"] = str(self.agent_id)
        if self.autonomy_mode is not None:
            params["autonomy_mode"] = self.autonomy_mode.value
        if self.correlation_id is not None:
            params["correlation_id"] = self.correlation_id

        return params


@dataclass(frozen=True)
class InvariantFilters:
    """Filter criteria for invariant queries.

    All filter fields are optional. When not specified, that filter
    is not applied to the query.

    Attributes:
        severity: Filter by invariant severity (HIGH, MEDIUM, LOW)
        enforcement_type: Filter by enforcement type (guard, isolation, test, exception)
        status: Filter by status (active, inactive)
        search: Full-text search on invariant statement
    """

    severity: InvariantSeverity | None = None
    enforcement_type: EnforcementType | None = None
    status: InvariantStatus | None = None
    search: str | None = None

    def to_query_params(self) -> dict[str, Any]:
        """Convert filters to query parameters for the API call.

        Returns:
            Dictionary of non-None filter parameters with appropriate
            string conversions for API consumption.
        """
        params: dict[str, Any] = {}

        if self.severity is not None:
            params["severity"] = self.severity.value
        if self.enforcement_type is not None:
            params["enforcement_type"] = self.enforcement_type.value
        if self.status is not None:
            params["status"] = self.status.value
        if self.search is not None:
            params["search"] = self.search

        return params


@dataclass
class PaginationParams:
    """Pagination parameters for list endpoints.

    Attributes:
        cursor: Opaque cursor string from previous response
        limit: Maximum number of items to return (1-100)
    """

    cursor: str | None = None
    limit: int = field(default=25)

    def __post_init__(self) -> None:
        """Validate pagination parameters."""
        if self.limit < 1 or self.limit > 100:
            raise ValueError("limit must be between 1 and 100")

    def to_query_params(self) -> dict[str, Any]:
        """Convert pagination to query parameters.

        Returns:
            Dictionary of pagination parameters.
        """
        params: dict[str, Any] = {"limit": self.limit}
        if self.cursor is not None:
            params["cursor"] = self.cursor
        return params

"""Core data contracts for the Unified Notification Service.

This module defines all enums and models as specified in the PRD.
These are the foundational types used throughout the notification system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class NotificationIntent(str, Enum):
    """Classification of notification urgency and handling requirements.

    SAFETY and GOVERNANCE imply elevated delivery guarantees.
    """

    SAFETY = "SAFETY"
    GOVERNANCE = "GOVERNANCE"
    OPERATIONAL = "OPERATIONAL"
    INFORMATIONAL = "INFORMATIONAL"


class DeliveryMode(str, Enum):
    """Delivery reliability semantics.

    GUARANTEED: Must raise error if all persistent channels fail.
    BEST_EFFORT: May fail silently but must log failure.
    """

    GUARANTEED = "GUARANTEED"
    BEST_EFFORT = "BEST_EFFORT"


class AutonomyMode(str, Enum):
    """Operating mode of the autonomous agent.

    Affects channel routing and acknowledgment requirements.
    """

    PREVIEW = "PREVIEW"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class AckStatus(str, Enum):
    """Acknowledgment lifecycle states."""

    PENDING = "PENDING"
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"


class Channel(str, Enum):
    """Delivery channels for notifications."""

    SLACK = "SLACK"
    EMAIL = "EMAIL"
    WEBSOCKET = "WEBSOCKET"
    PAGERDUTY = "PAGERDUTY"


class Priority(str, Enum):
    """Notification priority levels."""

    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class DeliveryStatus(str, Enum):
    """Outcome of a delivery attempt."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"


class AutonomyContext(BaseModel):
    """Context about the autonomous agent that triggered the notification.

    This is a REQUIRED field for all notifications - creation fails without it.
    """

    autonomy_mode: AutonomyMode = Field(description="Current operating mode - routing key")
    agent_id: UUID = Field(description="Unique identifier of the agent for attribution")
    plan_id: UUID | None = Field(default=None, description="Optional plan identifier")
    decision_snapshot_id: UUID | None = Field(
        default=None, description="Optional decision snapshot identifier"
    )
    execution_snapshot_id: UUID | None = Field(
        default=None, description="Optional execution snapshot identifier"
    )
    skip_snapshot_id: UUID | None = Field(
        default=None, description="Optional skip snapshot identifier"
    )

    model_config = {"frozen": True}


class Notification(BaseModel):
    """Core notification domain object.

    Represents a notification to be delivered through the UNS system.
    """

    notification_id: UUID = Field(default_factory=uuid4, description="Unique notification ID")
    notification_type: str = Field(
        description="Namespaced notification type (domain.event format)"
    )
    intent: NotificationIntent = Field(description="Notification classification")
    delivery_mode: DeliveryMode | None = Field(
        default=None, description="Derived from intent or policy"
    )
    irreversible: bool = Field(default=False, description="Whether action is irreversible")
    autonomy_context: AutonomyContext = Field(description="Required agent context")
    require_ack: bool | None = Field(
        default=None, description="Derived from intent + mode + policy"
    )
    ack_timeout_minutes: int | None = Field(
        default=None, description="Acknowledgment timeout based on intent"
    )
    priority: Priority | None = Field(default=None, description="Derived from intent")
    title: str = Field(max_length=200, description="Notification title (max 200 chars)")
    message: str = Field(max_length=4000, description="Notification body (max 4000 chars)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional JSON metadata")
    channels: list[Channel] = Field(default_factory=list, description="Router-derived channels")
    dedup_key: str | None = Field(default=None, description="Stable key within dedup window")
    source: str = Field(description="Producer identifier")
    correlation_id: str | None = Field(default=None, description="Optional correlation ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation timestamp")

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Title must be 200 characters or less")
        return v

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        if len(v) > 4000:
            raise ValueError("Message must be 4000 characters or less")
        return v


class NotificationResult(BaseModel):
    """Outcome of a notification delivery attempt."""

    notification_id: UUID = Field(description="ID of the notification")
    status: DeliveryStatus = Field(description="Overall delivery outcome")
    channels_attempted: list[Channel] = Field(
        default_factory=list, description="Channels that were attempted"
    )
    channels_succeeded: list[Channel] = Field(
        default_factory=list, description="Channels that succeeded"
    )
    channels_failed: list[Channel] = Field(
        default_factory=list, description="Channels that failed"
    )
    error_message: str | None = Field(default=None, description="Error details if failed")
    delivered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Delivery attempt timestamp"
    )


class AckEvent(BaseModel):
    """Acknowledgment event for a notification."""

    notification_id: UUID = Field(description="ID of the notification being acknowledged")
    ack_status: AckStatus = Field(description="Acknowledgment status")
    acked_by: str | None = Field(default=None, description="User/system that acknowledged")
    acked_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Ack timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional ack metadata"
    )

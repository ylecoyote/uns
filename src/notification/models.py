"""Core data contracts for the Unified Notification Service.

This module defines all enums, models, and validation guards as specified
in the PRD.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


class NotificationIntent(str, Enum):
    """Classification of notification importance and purpose.

    Invariants:
    - SAFETY and GOVERNANCE imply elevated delivery guarantees
    """

    SAFETY = "SAFETY"
    GOVERNANCE = "GOVERNANCE"
    OPERATIONAL = "OPERATIONAL"
    INFORMATIONAL = "INFORMATIONAL"


class DeliveryMode(str, Enum):
    """Delivery guarantee level.

    Invariants:
    - SAFETY -> GUARANTEED
    - GOVERNANCE -> GUARANTEED
    - OPERATIONAL -> BEST_EFFORT
    - INFORMATIONAL -> BEST_EFFORT
    """

    GUARANTEED = "GUARANTEED"
    BEST_EFFORT = "BEST_EFFORT"


class AutonomyMode(str, Enum):
    """Operating mode affecting routing behavior."""

    PREVIEW = "PREVIEW"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class AckStatus(str, Enum):
    """Acknowledgment state machine."""

    PENDING = "PENDING"
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"


class Channel(str, Enum):
    """Available notification delivery channels."""

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
    """Outcome of delivery attempt."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"


class AutonomyContext(BaseModel):
    """Context about the autonomous agent making the notification.

    Hard Guard: Notification creation MUST FAIL if autonomy_context is missing.
    """

    autonomy_mode: AutonomyMode = Field(..., description="Routing key")
    agent_id: UUID = Field(..., description="Attribution")
    plan_id: UUID | None = Field(default=None, description="Optional plan reference")
    decision_snapshot_id: UUID | None = Field(default=None)
    execution_snapshot_id: UUID | None = Field(default=None)
    skip_snapshot_id: UUID | None = Field(default=None)

    model_config = {"frozen": True}


class Notification(BaseModel):
    """Core notification payload with all required fields and validations."""

    notification_id: UUID = Field(default_factory=uuid4)
    notification_type: str = Field(..., description="Namespaced (domain.event)")
    intent: NotificationIntent
    delivery_mode: DeliveryMode | None = Field(
        default=None, description="Derived from intent or policy"
    )
    irreversible: bool = Field(default=False)
    autonomy_context: AutonomyContext = Field(
        ..., description="Hard requirement - must not be None"
    )
    require_ack: bool | None = Field(
        default=None, description="Derived from intent + mode + policy"
    )
    ack_timeout_minutes: int | None = Field(
        default=None, description="Intent-based timeout"
    )
    priority: Priority | None = Field(
        default=None, description="Derived from intent"
    )
    title: str = Field(..., max_length=200, description="<=200 chars")
    message: str = Field(..., max_length=4000, description="<=4000 chars")
    metadata: dict[str, Any] = Field(default_factory=dict)
    channels: list[Channel] = Field(default_factory=list, description="Router output")
    dedup_key: str | None = Field(
        default=None, description="Stable within dedup window"
    )
    source: str = Field(..., description="Producer identifier")
    correlation_id: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("title must be <= 200 characters")
        return v

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        if len(v) > 4000:
            raise ValueError("message must be <= 4000 characters")
        return v


class NotificationResult(BaseModel):
    """Result of a notification delivery attempt."""

    notification_id: UUID
    status: DeliveryStatus
    channels_attempted: list[Channel] = Field(default_factory=list)
    channels_succeeded: list[Channel] = Field(default_factory=list)
    channels_failed: list[Channel] = Field(default_factory=list)
    error_message: str | None = Field(default=None)
    delivered_at: datetime | None = Field(default=None)


class AckEvent(BaseModel):
    """Record of an acknowledgment action."""

    notification_id: UUID
    ack_status: AckStatus
    acked_by: str | None = Field(default=None)
    acked_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# Helper functions for default derivations
def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode:
    """Derive delivery mode from intent when no policy override exists."""
    if intent in (NotificationIntent.SAFETY, NotificationIntent.GOVERNANCE):
        return DeliveryMode.GUARANTEED
    return DeliveryMode.BEST_EFFORT


def get_default_priority(intent: NotificationIntent) -> Priority:
    """Derive priority from intent."""
    if intent == NotificationIntent.SAFETY:
        return Priority.HIGH
    if intent == NotificationIntent.GOVERNANCE:
        return Priority.HIGH
    if intent == NotificationIntent.OPERATIONAL:
        return Priority.NORMAL
    return Priority.LOW


def get_default_ack_timeout_minutes(intent: NotificationIntent) -> int | None:
    """Get default ack timeout based on intent."""
    if intent == NotificationIntent.SAFETY:
        return 15
    if intent == NotificationIntent.GOVERNANCE:
        return 30
    return None


def get_default_require_ack(
    intent: NotificationIntent, autonomy_mode: AutonomyMode
) -> bool:
    """Determine if ack is required based on intent and mode."""
    return intent == NotificationIntent.SAFETY and autonomy_mode == AutonomyMode.LIVE

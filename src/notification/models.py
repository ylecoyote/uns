"""Core data contracts for the Unified Notification Service.

This module defines all enums and models as specified in the UNS PRD.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class NotificationIntent(str, Enum):
    """Classification of notification purpose.

    Invariants:
    - SAFETY and GOVERNANCE imply elevated delivery guarantees (GUARANTEED mode)
    - OPERATIONAL and INFORMATIONAL use BEST_EFFORT mode by default
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
    """Agent autonomy level affecting routing behavior.

    Channel routing varies by mode:
    - PREVIEW: All intents -> WebSocket only
    - SHADOW: OPERATIONAL -> WebSocket, GOVERNANCE -> Slack + WebSocket
    - LIVE: Full channel routing based on intent
    """

    PREVIEW = "PREVIEW"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class AckStatus(str, Enum):
    """Acknowledgment state for notifications requiring human confirmation."""

    PENDING = "PENDING"
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"


class Channel(str, Enum):
    """Supported delivery channels."""

    SLACK = "SLACK"
    EMAIL = "EMAIL"
    WEBSOCKET = "WEBSOCKET"
    PAGERDUTY = "PAGERDUTY"


class Priority(str, Enum):
    """Notification priority level, derived from intent."""

    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class DeliveryStatus(str, Enum):
    """Outcome of a delivery attempt."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"


# Constants for validation
TITLE_MAX_LENGTH = 200
MESSAGE_MAX_LENGTH = 4000

# Default ack timeouts by intent (in minutes)
DEFAULT_ACK_TIMEOUTS: dict[NotificationIntent, int] = {
    NotificationIntent.SAFETY: 15,
    NotificationIntent.GOVERNANCE: 30,
}

# Intent to priority mapping
INTENT_PRIORITY_MAP: dict[NotificationIntent, Priority] = {
    NotificationIntent.SAFETY: Priority.HIGH,
    NotificationIntent.GOVERNANCE: Priority.HIGH,
    NotificationIntent.OPERATIONAL: Priority.NORMAL,
    NotificationIntent.INFORMATIONAL: Priority.LOW,
}

# Intent to default delivery mode mapping
INTENT_DELIVERY_MODE_MAP: dict[NotificationIntent, DeliveryMode] = {
    NotificationIntent.SAFETY: DeliveryMode.GUARANTEED,
    NotificationIntent.GOVERNANCE: DeliveryMode.GUARANTEED,
    NotificationIntent.OPERATIONAL: DeliveryMode.BEST_EFFORT,
    NotificationIntent.INFORMATIONAL: DeliveryMode.BEST_EFFORT,
}


class AutonomyContext(BaseModel):
    """Context capturing the autonomy state when a notification is created.

    Hard Guard: Notification creation MUST FAIL if autonomy_context is missing.
    """

    model_config = ConfigDict(frozen=True)

    autonomy_mode: AutonomyMode = Field(..., description="Routing key for channel selection")
    agent_id: UUID = Field(..., description="Attribution - which agent triggered this")
    plan_id: UUID | None = Field(default=None, description="Optional plan reference")
    decision_snapshot_id: UUID | None = Field(
        default=None, description="Optional decision snapshot reference"
    )
    execution_snapshot_id: UUID | None = Field(
        default=None, description="Optional execution snapshot reference"
    )
    skip_snapshot_id: UUID | None = Field(
        default=None, description="Optional skip snapshot reference"
    )


class Notification(BaseModel):
    """Core notification data contract.

    Validation guards:
    - autonomy_context is required (hard guard)
    - title max 200 chars
    - message max 4000 chars
    """

    model_config = ConfigDict(frozen=True)

    # Auto-generated fields
    notification_id: UUID = Field(default_factory=uuid4, description="Unique notification ID")
    created_at: datetime = Field(default_factory=_utc_now, description="Creation timestamp (UTC)")

    # Required fields
    notification_type: str = Field(..., description="Namespaced type (domain.event)", min_length=1)
    intent: NotificationIntent = Field(..., description="Notification intent classification")
    autonomy_context: AutonomyContext = Field(
        ..., description="Required autonomy context (hard guard)"
    )
    title: str = Field(..., description="Notification title", max_length=TITLE_MAX_LENGTH)
    message: str = Field(..., description="Notification body", max_length=MESSAGE_MAX_LENGTH)
    source: str = Field(..., description="Producer identifier", min_length=1)

    # Optional fields
    irreversible: bool = Field(
        default=False, description="If true, may trigger PagerDuty for SAFETY"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional JSON metadata")
    correlation_id: str | None = Field(default=None, description="Optional correlation ID")

    # Derived fields (computed on creation or by router)
    delivery_mode: DeliveryMode | None = Field(
        default=None, description="Derived from intent or policy"
    )
    require_ack: bool | None = Field(
        default=None, description="Derived from intent + mode + policy"
    )
    ack_timeout_minutes: int | None = Field(default=None, description="Intent-based timeout")
    priority: Priority | None = Field(default=None, description="Derived from intent")
    channels: list[Channel] = Field(default_factory=list, description="Router output")
    dedup_key: str | None = Field(default=None, description="Stable within dedup window")

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        if len(v) > TITLE_MAX_LENGTH:
            raise ValueError(f"title must be at most {TITLE_MAX_LENGTH} characters")
        return v

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        if len(v) > MESSAGE_MAX_LENGTH:
            raise ValueError(f"message must be at most {MESSAGE_MAX_LENGTH} characters")
        return v

    @model_validator(mode="before")
    @classmethod
    def set_derived_defaults(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Set derived field defaults based on intent if not already set."""
        if not isinstance(data, dict):
            return data

        intent = data.get("intent")
        if intent is None:
            return data

        # Convert string intent to enum if needed
        if isinstance(intent, str):
            try:
                intent = NotificationIntent(intent)
            except ValueError:
                return data  # Let normal validation handle invalid intent

        # Set delivery_mode if not provided
        if data.get("delivery_mode") is None:
            data["delivery_mode"] = INTENT_DELIVERY_MODE_MAP[intent]

        # Set priority if not provided
        if data.get("priority") is None:
            data["priority"] = INTENT_PRIORITY_MAP[intent]

        # Set ack_timeout_minutes if not provided and intent has a default
        if data.get("ack_timeout_minutes") is None and intent in DEFAULT_ACK_TIMEOUTS:
            data["ack_timeout_minutes"] = DEFAULT_ACK_TIMEOUTS[intent]

        return data


class NotificationResult(BaseModel):
    """Result of a notification delivery attempt."""

    model_config = ConfigDict(frozen=True)

    notification_id: UUID = Field(..., description="Reference to the notification")
    status: DeliveryStatus = Field(..., description="Delivery outcome")
    channels_attempted: list[Channel] = Field(
        default_factory=list, description="Channels that were attempted"
    )
    channels_succeeded: list[Channel] = Field(
        default_factory=list, description="Channels that succeeded"
    )
    channels_failed: list[Channel] = Field(default_factory=list, description="Channels that failed")
    error_message: str | None = Field(default=None, description="Error details if failed")
    delivered_at: datetime | None = Field(default=None, description="When delivery completed")
    deduplicated: bool = Field(default=False, description="Whether notification was deduplicated")


class AckEvent(BaseModel):
    """Record of an acknowledgment action."""

    model_config = ConfigDict(frozen=True)

    notification_id: UUID = Field(..., description="Reference to the notification")
    status: AckStatus = Field(..., description="New acknowledgment status")
    acked_by: str | None = Field(default=None, description="User who acknowledged")
    acked_at: datetime = Field(
        default_factory=_utc_now, description="When acknowledgment occurred (UTC)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional acknowledgment metadata"
    )

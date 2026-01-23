"""Core data contracts for the Unified Notification Service.

This module defines all enums, models, and validation guards as specified
in the PRD. These are the foundational types used throughout the notification system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class NotificationIntent(str, Enum):
    """Classification of notification urgency and handling requirements.

    Invariants:
    - SAFETY and GOVERNANCE imply elevated delivery guarantees (GUARANTEED mode)
    - OPERATIONAL and INFORMATIONAL use BEST_EFFORT mode by default
    """

    SAFETY = "SAFETY"
    GOVERNANCE = "GOVERNANCE"
    OPERATIONAL = "OPERATIONAL"
    INFORMATIONAL = "INFORMATIONAL"


class DeliveryMode(str, Enum):
    """Delivery reliability semantics.

    GUARANTEED: Must raise error if all persistent channels fail.
    BEST_EFFORT: May fail silently but must log failure.

    Invariants:
    - SAFETY -> GUARANTEED
    - GOVERNANCE -> GUARANTEED
    - OPERATIONAL -> BEST_EFFORT
    - INFORMATIONAL -> BEST_EFFORT
    """

    GUARANTEED = "GUARANTEED"
    BEST_EFFORT = "BEST_EFFORT"


class AutonomyMode(str, Enum):
    """Operating mode of the autonomous agent.

    Affects channel routing and acknowledgment requirements.

    Channel routing varies by mode:
    - PREVIEW: All intents -> WebSocket only
    - SHADOW: OPERATIONAL -> WebSocket, GOVERNANCE -> Slack + WebSocket
    - LIVE: Full channel routing based on intent

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
    """Supported delivery channels for notifications."""

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

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    SUCCESS = "SUCCESS"  # Alias for compatibility
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

# Helper functions for default value lookups
def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode:
    """Get the default delivery mode for an intent.

    Args:
        intent: The notification intent

    Returns:
        The appropriate DeliveryMode
    """
    return INTENT_DELIVERY_MODE_MAP[intent]


def get_default_priority(intent: NotificationIntent) -> Priority:
    """Get the default priority for an intent.

    Args:
        intent: The notification intent

    Returns:
        The appropriate Priority
    """
    return INTENT_PRIORITY_MAP[intent]


def get_default_ack_timeout_minutes(intent: NotificationIntent) -> int | None:
    """Get the default acknowledgment timeout for an intent.

    Args:
        intent: The notification intent

    Returns:
        Timeout in minutes, or None if no timeout applies
    """
    return DEFAULT_ACK_TIMEOUTS.get(intent)


def get_default_require_ack(intent: NotificationIntent, autonomy_mode: AutonomyMode) -> bool:
    """Determine if acknowledgment is required by default.

    Per PRD:
    - SAFETY in LIVE mode -> true
    - All other cases -> false

    Args:
        intent: The notification intent
        autonomy_mode: Current operating mode

    Returns:
        Whether acknowledgment is required
    """
    return intent == NotificationIntent.SAFETY and autonomy_mode == AutonomyMode.LIVE


class AutonomyContext(BaseModel):
    """Context about the autonomous agent that triggered the notification.

    This is a REQUIRED field for all notifications - creation fails without it.
    Hard Guard: Notification creation MUST FAIL if autonomy_context is missing.
    """

    model_config = ConfigDict(frozen=True)

    autonomy_mode: AutonomyMode = Field(..., description="Current operating mode - routing key")
    agent_id: UUID = Field(..., description="Unique identifier of the agent for attribution")
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

class Notification(BaseModel):
    """Core notification domain object.

    Represents a notification to be delivered through the UNS system.

    Validation guards:
    - autonomy_context is required (hard guard)
    - title max 200 chars
    - message max 4000 chars
    """

    model_config = ConfigDict(frozen=True)

    # Auto-generated fields
    notification_id: UUID = Field(default_factory=uuid4, description="Unique notification ID")
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp (UTC)"
    )

    # Required fields
    notification_type: str = Field(
        ..., description="Namespaced notification type (domain.event format)", min_length=1
    )
    intent: NotificationIntent = Field(..., description="Notification classification")
    autonomy_context: AutonomyContext = Field(
        ..., description="Required agent context (hard guard)"
    )
    title: str = Field(..., description="Notification title", max_length=TITLE_MAX_LENGTH)
    message: str = Field(..., description="Notification body", max_length=MESSAGE_MAX_LENGTH)
    source: str = Field(..., description="Producer identifier", min_length=1)

    # Optional fields
    irreversible: bool = Field(
        default=False, description="Whether action is irreversible - may trigger PagerDuty for SAFETY"
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
    ack_timeout_minutes: int | None = Field(
        default=None, description="Acknowledgment timeout based on intent"
    )
    priority: Priority | None = Field(default=None, description="Derived from intent")
    channels: list[Channel] = Field(default_factory=list, description="Router-derived channels")
    dedup_key: str | None = Field(default=None, description="Stable key within dedup window")

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        if len(v) > TITLE_MAX_LENGTH:
            raise ValueError(f"Title must be {TITLE_MAX_LENGTH} characters or less")
        return v

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        if len(v) > MESSAGE_MAX_LENGTH:
            raise ValueError(f"Message must be {MESSAGE_MAX_LENGTH} characters or less")
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
    """Outcome of a notification delivery attempt."""

    notification_id: UUID = Field(description="ID of the notification")
    status: DeliveryStatus = Field(description="Overall delivery outcome")
    channels_attempted: list[Channel] = Field(
        default_factory=list, description="Channels that were attempted"
    )
    channels_succeeded: list[Channel] = Field(
        default_factory=list, description="Channels that succeeded"
    )
    channels_failed: list[Channel] = Field(default_factory=list, description="Channels that failed")
    error_message: str | None = Field(default=None, description="Error details if failed")
    delivered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Delivery attempt timestamp"
    )
    deduplicated: bool = Field(default=False, description="Whether notification was deduplicated")


class AckEvent(BaseModel):
    """Acknowledgment event for a notification."""

    notification_id: UUID = Field(..., description="ID of the notification being acknowledged")
    # Both 'status' and 'ack_status' supported for compatibility;
    # 'status' is the preferred field, but 'ack_status' is maintained for legacy/compat.
    status: AckStatus | None = Field(default=None, description="Acknowledgment status")
    ack_status: AckStatus | None = Field(default=None, description="Alias for status (compatibility)")
    acked_by: str | None = Field(default=None, description="User/system that acknowledged")
    acked_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Ack timestamp (UTC)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional ack metadata"
    )

    @model_validator(mode="before")
    @classmethod
    def sync_status_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Sync status and ack_status fields for compatibility."""
        if not isinstance(data, dict):
            return data

        # If ack_status is provided but status is not, use ack_status as status
        if data.get("ack_status") is not None and data.get("status") is None:
            data["status"] = data["ack_status"]
        # If status is provided, also set ack_status for compatibility
        elif data.get("status") is not None and data.get("ack_status") is None:
            data["ack_status"] = data["status"]

        return data

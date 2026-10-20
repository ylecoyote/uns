"""Typed models for AGSignal Console API responses.

These models match the contracts in docs/ui/ui-data-contracts.md.
All models are read-only (frozen) to enforce the non-mutating UI posture.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResolutionSource(str, Enum):
    """Source of a policy resolution value per the resolution chain.

    Resolution order:
    1. EXPLICIT_OVERRIDE - Values passed directly to SDK.send()
    2. MODE_OVERRIDE - Policy mode-specific override (preview_override, etc.)
    3. POLICY_BASE - Policy base value
    4. SDK_DEFAULT - SDK default derived from intent + autonomy_mode
    """

    EXPLICIT_OVERRIDE = "explicit_override"
    MODE_OVERRIDE = "mode_override"
    POLICY_BASE = "policy_base"
    SDK_DEFAULT = "sdk_default"


class NotificationIntent(str, Enum):
    """Notification intent classification."""

    SAFETY = "SAFETY"
    GOVERNANCE = "GOVERNANCE"
    OPERATIONAL = "OPERATIONAL"
    INFORMATIONAL = "INFORMATIONAL"


class AutonomyMode(str, Enum):
    """Agent autonomy mode."""

    PREVIEW = "PREVIEW"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class DeliveryMode(str, Enum):
    """Delivery guarantee mode."""

    GUARANTEED = "GUARANTEED"
    BEST_EFFORT = "BEST_EFFORT"


class Channel(str, Enum):
    """Notification delivery channel."""

    SLACK = "SLACK"
    EMAIL = "EMAIL"
    WEBSOCKET = "WEBSOCKET"
    PAGERDUTY = "PAGERDUTY"


class ResolutionStep(BaseModel):
    """Single step in policy resolution chain.

    Each step shows a potential source for a policy field value,
    whether it was applied, and why if not.
    """

    model_config = ConfigDict(frozen=True)

    source: ResolutionSource = Field(description="Where this value comes from")
    value: Any = Field(description="The value at this resolution step")
    applied: bool = Field(description="Whether this value was actually used")
    reason: str | None = Field(default=None, description="Explanation if not applied")


class EffectivePolicyValues(BaseModel):
    """Effective policy values that were actually resolved.

    These are the final values that would be used for notification delivery.
    """

    model_config = ConfigDict(frozen=True)

    delivery_mode: DeliveryMode = Field(description="GUARANTEED or BEST_EFFORT")
    channels: list[Channel] = Field(description="Channels that will receive the notification")
    require_ack: bool = Field(description="Whether acknowledgment is required")
    ack_timeout_minutes: int | None = Field(
        default=None, description="Timeout for acknowledgment in minutes"
    )
    dedup_window_seconds: int = Field(description="Deduplication window in seconds")


class ResolutionContext(BaseModel):
    """Context used for policy resolution.

    Contains the input parameters and whether a policy was found.
    """

    model_config = ConfigDict(frozen=True)

    intent: NotificationIntent = Field(description="The notification intent")
    autonomy_mode: AutonomyMode = Field(description="The autonomy mode")
    irreversible: bool = Field(description="Whether the action is irreversible")
    policy_found: bool = Field(description="Whether a policy was found for this type")
    policy_notification_type: str | None = Field(
        default=None, description="The notification type if policy was found"
    )


class EffectivePolicyResponse(BaseModel):
    """Response from GET /ui/policies/effective.

    Shows the effective policy values and the complete resolution trace
    for how each field was determined.
    """

    model_config = ConfigDict(frozen=True)

    notification_type: str = Field(description="The notification type that was queried")
    effective: EffectivePolicyValues = Field(description="The effective policy values")
    resolution: dict[str, list[ResolutionStep]] = Field(
        description="Resolution trace for each field showing the chain"
    )
    resolution_context: ResolutionContext = Field(
        description="Context used for resolution (inputs + policy_found)"
    )


class ErrorDetail(BaseModel):
    """Error detail structure per ui-data-contracts.md."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable description")
    details: dict[str, Any] | None = Field(default=None, description="Additional context")


class ErrorResponse(BaseModel):
    """Standard error response per ui-data-contracts.md."""

    model_config = ConfigDict(frozen=True)

    error: ErrorDetail = Field(description="Error details")
    request_id: str = Field(description="Request ID for correlation/support")

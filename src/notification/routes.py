"""Standalone HTTP routes for producing AGSignal notifications."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from notification.acknowledgment import get_ack_engine
from notification.models import (
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
    Priority,
)
from notification.sdk import NotificationSDK, ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/notifications", tags=["signals"])


class AutonomyContextRequest(BaseModel):
    """Producer-supplied autonomy context."""

    model_config = ConfigDict(extra="forbid")

    autonomy_mode: AutonomyMode = Field(description="Current autonomy mode")
    agent_id: UUID = Field(description="Agent identifier for attribution")
    plan_id: UUID | None = Field(default=None, description="Optional plan identifier")
    decision_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional decision snapshot identifier",
    )
    execution_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional execution snapshot identifier",
    )
    skip_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional skip snapshot identifier",
    )

    def to_domain(self) -> AutonomyContext:
        """Convert request context into the domain model."""
        return AutonomyContext(
            autonomy_mode=self.autonomy_mode,
            agent_id=self.agent_id,
            plan_id=self.plan_id,
            decision_snapshot_id=self.decision_snapshot_id,
            execution_snapshot_id=self.execution_snapshot_id,
            skip_snapshot_id=self.skip_snapshot_id,
        )


class SendNotificationRequest(BaseModel):
    """HTTP request for sending an AGSignal notification."""

    model_config = ConfigDict(extra="forbid")

    notification_type: str = Field(description="Namespaced signal type", min_length=1)
    intent: NotificationIntent = Field(description="Signal intent")
    title: str = Field(description="Signal title", min_length=1, max_length=200)
    message: str = Field(description="Signal body", min_length=1, max_length=4000)
    source: str = Field(description="Producer identifier", min_length=1)
    autonomy_context: AutonomyContextRequest = Field(description="Required autonomy context")
    irreversible: bool = Field(default=False, description="Whether the action is irreversible")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional JSON metadata",
    )
    correlation_id: str | None = Field(default=None, description="Optional trace correlation ID")
    delivery_mode: DeliveryMode | None = Field(
        default=None,
        description="Optional delivery mode override",
    )
    require_ack: bool | None = Field(
        default=None,
        description="Optional acknowledgment override",
    )
    priority: Priority | None = Field(default=None, description="Optional priority override")
    dedup_key: str | None = Field(default=None, description="Optional deduplication key")


class SendNotificationResponse(BaseModel):
    """HTTP response for an accepted AGSignal notification."""

    notification_id: UUID = Field(description="Notification identifier")
    status: DeliveryStatus = Field(description="Delivery outcome")
    channels_attempted: list[Channel] = Field(description="Router-derived channels attempted")
    channels_succeeded: list[Channel] = Field(description="Channels that succeeded")
    channels_failed: list[Channel] = Field(description="Channels that failed")
    require_ack: bool = Field(description="Whether the signal requires acknowledgment")
    ack_status: AckStatus | None = Field(
        default=None,
        description="Current acknowledgment status when tracked",
    )
    message: str = Field(description="Acceptance summary")


def _capture_delivery(
    captured: dict[str, Notification],
) -> Callable[[Notification], NotificationResult]:
    def deliver(notification: Notification) -> NotificationResult:
        captured["notification"] = notification
        return NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.SUCCESS,
            channels_attempted=notification.channels,
            channels_succeeded=[],
            channels_failed=[],
        )

    return deliver


@router.post(
    "",
    response_model=SendNotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_notification(request: SendNotificationRequest) -> SendNotificationResponse:
    """Accept an AGSignal notification from an autonomous producer."""
    captured: dict[str, Notification] = {}
    sdk = NotificationSDK(delivery_handler=_capture_delivery(captured))

    try:
        result = sdk.send(
            notification_type=request.notification_type,
            intent=request.intent,
            title=request.title,
            message=request.message,
            source=request.source,
            autonomy_context=request.autonomy_context.to_domain(),
            irreversible=request.irreversible,
            metadata=request.metadata,
            correlation_id=request.correlation_id,
            delivery_mode_override=request.delivery_mode,
            require_ack_override=request.require_ack,
            priority_override=request.priority,
            dedup_key=request.dedup_key,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc

    notification = captured["notification"]
    ack_status: AckStatus | None = None
    if notification.require_ack:
        engine = get_ack_engine()
        engine.register_notification(
            notification_id=notification.notification_id,
            intent=notification.intent,
            autonomy_context=notification.autonomy_context,
            timeout_minutes=notification.ack_timeout_minutes,
            created_at=notification.created_at,
        )
        ack_status = engine.get_status(notification.notification_id)

    logger.info(
        "Accepted AGSignal notification: id=%s type=%s intent=%s",
        notification.notification_id,
        notification.notification_type,
        notification.intent.value,
    )

    return SendNotificationResponse(
        notification_id=result.notification_id,
        status=result.status,
        channels_attempted=result.channels_attempted,
        channels_succeeded=result.channels_succeeded,
        channels_failed=result.channels_failed,
        require_ack=bool(notification.require_ack),
        ack_status=ack_status,
        message="notification accepted",
    )

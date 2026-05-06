"""Standalone HTTP routes for producing AGSignal notifications."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from notification.acknowledgment import get_ack_engine
from notification.channel_health import ChannelHealthSummary, ChannelHealthTracker
from notification.dlq import DLQEntry, DLQService
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
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.policy_loader import load_policies_from_directory
from notification.sdk import NotificationSDK, ValidationError
from notification.websocket_runtime import (
    WebSocketConnectionManager,
    WebSocketFanoutEnvelope,
    WebSocketReplayStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/notifications", tags=["signals"])
ops_router = APIRouter(prefix="/api/v1", tags=["operations"])


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


class SimulateNotificationResponse(BaseModel):
    """HTTP response for a simulated AGSignal notification."""

    notification_id: UUID = Field(description="Preview notification identifier")
    simulated: bool = Field(description="Whether delivery was simulated")
    status: DeliveryStatus = Field(description="Simulated delivery outcome")
    channels_attempted: list[Channel] = Field(description="Router-derived channels")
    require_ack: bool = Field(description="Whether the signal would require acknowledgment")
    ack_status: AckStatus | None = Field(
        default=None,
        description="Always null because simulation has no ack side effect",
    )
    message: str = Field(description="Simulation summary")


class DLQListResponse(BaseModel):
    """HTTP response for DLQ inspection."""

    depth: int = Field(description="Current DLQ depth")
    items: list[DLQEntry] = Field(description="DLQ entries, newest first")


class PolicyReloadRequest(BaseModel):
    """Request body for reloading YAML notification policies."""

    model_config = ConfigDict(extra="forbid")

    policy_dir: str = Field(
        default="config/notification_policies",
        description="Directory containing YAML policy files",
    )


class PolicyReloadResponse(BaseModel):
    """HTTP response for policy reload operations."""

    loaded_count: int = Field(description="Number of policy files loaded")
    persisted_count: int = Field(description="Number of policies newly persisted")
    policy_count: int = Field(description="Number of policies active after reload")
    notification_types: list[str] = Field(description="Registered notification types")


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


def _resolve_notification(
    request: SendNotificationRequest,
) -> tuple[NotificationResult, Notification]:
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

    return result, captured["notification"]


@router.post(
    "",
    response_model=SendNotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_notification(
    http_request: Request,
    request: SendNotificationRequest,
) -> SendNotificationResponse:
    """Accept an AGSignal notification from an autonomous producer."""
    result, notification = _resolve_notification(request)
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

    websocket_payload: dict[str, object] = {
        "notification_id": str(notification.notification_id),
        "notification_type": notification.notification_type,
        "intent": notification.intent.value,
        "title": notification.title,
        "message": notification.message,
        "source": notification.source,
        "require_ack": bool(notification.require_ack),
        "ack_status": ack_status.value if ack_status is not None else None,
    }
    replay_store = getattr(http_request.app.state, "websocket_replay_store", None)
    if isinstance(replay_store, WebSocketReplayStore):
        replay_cursor = replay_store.record(
            notification.autonomy_context.agent_id,
            websocket_payload,
            created_at=notification.created_at,
        )
        websocket_payload["replay_cursor"] = replay_cursor
    manager = getattr(http_request.app.state, "websocket_manager", None)
    if isinstance(manager, WebSocketConnectionManager):
        await manager.send_to_agent(
            notification.autonomy_context.agent_id,
            {"type": "notification", "notification": websocket_payload},
        )
    fanout = getattr(http_request.app.state, "websocket_fanout", None)
    if fanout is not None:
        fanout.publish(
            WebSocketFanoutEnvelope(
                type="notification",
                agent_id=notification.autonomy_context.agent_id,
                notification=websocket_payload,
            )
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


@router.post("/simulate", response_model=SimulateNotificationResponse)
async def simulate_notification(request: SendNotificationRequest) -> SimulateNotificationResponse:
    """Preview routing and acknowledgment behavior without delivery side effects."""
    result, notification = _resolve_notification(request)

    return SimulateNotificationResponse(
        notification_id=result.notification_id,
        simulated=True,
        status=result.status,
        channels_attempted=result.channels_attempted,
        require_ack=bool(notification.require_ack),
        ack_status=None,
        message="notification simulated",
    )


@ops_router.get("/dlq", response_model=DLQListResponse)
async def list_dlq(request: Request) -> DLQListResponse:
    """List visible dead-lettered delivery failures."""
    dlq_service: DLQService = request.app.state.dlq_service
    return DLQListResponse(
        depth=dlq_service.depth(),
        items=dlq_service.list_entries(),
    )


@ops_router.get("/channels/health", response_model=ChannelHealthSummary)
async def get_channel_health(request: Request) -> ChannelHealthSummary:
    """Return runtime channel health without changing process readiness."""
    tracker: ChannelHealthTracker = request.app.state.channel_health_tracker
    return tracker.get_summary()


@ops_router.post("/policies/reload", response_model=PolicyReloadResponse)
async def reload_policies(
    reload_request: PolicyReloadRequest,
    http_request: Request,
) -> PolicyReloadResponse:
    """Reload notification policies from YAML files."""
    policy_dir = Path(reload_request.policy_dir)
    registry = PolicyRegistry()
    try:
        loaded_count = load_policies_from_directory(policy_dir, registry=registry)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": str(exc)},
        ) from exc
    except NotADirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "not_a_directory", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_policy", "message": str(exc)},
        ) from exc

    persisted_count = 0
    policy_store = getattr(http_request.app.state, "policy_store", None)
    if policy_store is not None:
        for policy in registry.get_all().values():
            result = policy_store.save_policy(policy)
            if result.created:
                persisted_count += 1

    configure_policy_registry(registry=registry)
    notification_types = sorted(registry.list_notification_types())
    return PolicyReloadResponse(
        loaded_count=loaded_count,
        persisted_count=persisted_count,
        policy_count=len(registry),
        notification_types=notification_types,
    )

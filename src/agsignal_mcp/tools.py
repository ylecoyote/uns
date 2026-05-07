"""AGSignal MCP tool implementations."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agsignal_mcp.runtime import MCPRuntimeConfig
from mcp_server.routes_ui import get_effective_policy as get_effective_policy_route
from mcp_server.routes_ui import get_invariants_summary as get_invariants_summary_route
from mcp_server.routes_ui import list_audit_events as list_audit_events_route
from mcp_server.routes_ui import list_deliveries as list_deliveries_route
from mcp_server.routes_ui import list_invariants as list_invariants_route
from notification.acknowledgment import configure_ack_engine, get_ack_engine
from notification.audit import create_ack_audit_record
from notification.models import AckStatus, AutonomyMode, NotificationIntent
from notification.runtime import RuntimeState
from notification.runtime import send_signal as send_runtime_signal
from notification.runtime import simulate_signal as simulate_runtime_signal


class SendSignalInput(BaseModel):
    """Input accepted by MCP signal preview and send tools."""

    model_config = ConfigDict(extra="forbid")

    notification_type: str
    intent: str
    title: str
    message: str
    source: str
    autonomy_context: dict[str, Any]
    irreversible: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    delivery_mode: str | None = None
    require_ack: bool | None = None
    priority: str | None = None
    dedup_key: str | None = None
    idempotency_key: str | None = None
    deliver: bool = False
    operator_intent: Literal["deliver"] | None = None
    operator_confirmation_token: str | None = None


class AckNotificationInput(BaseModel):
    """Input accepted by MCP ACK and dismiss tools."""

    model_config = ConfigDict(extra="forbid")

    notification_id: UUID
    acked_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _runtime_payload(payload: SendSignalInput) -> dict[str, Any]:
    data = payload.model_dump(
        exclude={"deliver", "operator_intent", "operator_confirmation_token"},
        exclude_none=True,
    )
    return dict(data)


def _get_ack_engine():
    try:
        return get_ack_engine()
    except RuntimeError:
        return configure_ack_engine()


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def simulate_signal(
    payload: SendSignalInput,
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Preview routing and policy behavior without delivery side effects."""
    response = simulate_runtime_signal(runtime_state or RuntimeState(), _runtime_payload(payload))
    data = response.model_dump(mode="json")
    data["delivered"] = False
    return data


def send_signal(
    payload: SendSignalInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Preview or send an AGSignal signal through MCP."""
    if not payload.deliver:
        return simulate_signal(payload, runtime_state=runtime_state)

    active_config = config or MCPRuntimeConfig()
    if active_config.read_only:
        raise ValueError("send_signal is disabled in read-only mode")
    if payload.operator_intent != "deliver":
        raise ValueError("send_signal deliver=true requires operator_intent='deliver'")
    if active_config.require_delivery_confirmation:
        if not active_config.delivery_confirmation_token:
            raise ValueError("send_signal delivery requires a configured confirmation token")
        if payload.operator_confirmation_token != active_config.delivery_confirmation_token:
            raise ValueError("send_signal delivery confirmation token is invalid")

    response = send_runtime_signal(runtime_state or RuntimeState(), _runtime_payload(payload))
    data = response.model_dump(mode="json")
    data["delivered"] = True
    return data


def ack_notification(
    payload: AckNotificationInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Acknowledge a tracked AGSignal notification."""
    active_config = config or MCPRuntimeConfig()
    if active_config.read_only:
        raise ValueError("ack_notification is disabled in read-only mode")
    if not active_config.operator_principal:
        raise ValueError("ack_notification requires an operator principal")
    if payload.acked_by is not None and payload.acked_by != active_config.operator_principal:
        raise ValueError("ack_notification acked_by must match the operator principal")
    engine = _get_ack_engine()
    before_commit = None
    if runtime_state is not None:
        def before_commit(old_status: AckStatus | None, ack_event) -> None:
            runtime_state.audit_store.save_ack_audit(
                create_ack_audit_record(
                    notification_id=ack_event.notification_id,
                    old_status=old_status,
                    new_status=ack_event.ack_status,
                    acked_by=ack_event.acked_by,
                    acked_at=ack_event.acked_at,
                    metadata=ack_event.metadata,
                )
            )

    event = engine.ack(
        notification_id=payload.notification_id,
        ack_status=AckStatus.ACKED,
        acked_by=active_config.operator_principal,
        metadata=payload.metadata,
        before_commit=before_commit,
    )
    return {
        "notification_id": str(event.notification_id),
        "ack_status": event.ack_status.value,
        "acked_by": event.acked_by,
        "acked_at": event.acked_at.isoformat(),
        "metadata": event.metadata,
    }


def dismiss_notification(
    payload: AckNotificationInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Dismiss a tracked AGSignal notification."""
    active_config = config or MCPRuntimeConfig()
    if active_config.read_only:
        raise ValueError("dismiss_notification is disabled in read-only mode")
    if not active_config.operator_principal:
        raise ValueError("dismiss_notification requires an operator principal")
    if payload.acked_by is not None and payload.acked_by != active_config.operator_principal:
        raise ValueError("dismiss_notification acked_by must match the operator principal")
    engine = _get_ack_engine()
    before_commit = None
    if runtime_state is not None:
        def before_commit(old_status: AckStatus | None, ack_event) -> None:
            runtime_state.audit_store.save_ack_audit(
                create_ack_audit_record(
                    notification_id=ack_event.notification_id,
                    old_status=old_status,
                    new_status=ack_event.ack_status,
                    acked_by=ack_event.acked_by,
                    acked_at=ack_event.acked_at,
                    metadata=ack_event.metadata,
                )
            )

    event = engine.ack(
        notification_id=payload.notification_id,
        ack_status=AckStatus.DISMISSED,
        acked_by=active_config.operator_principal,
        metadata=payload.metadata,
        before_commit=before_commit,
    )
    return {
        "notification_id": str(event.notification_id),
        "ack_status": event.ack_status.value,
        "acked_by": event.acked_by,
        "acked_at": event.acked_at.isoformat(),
        "metadata": event.metadata,
    }


def get_ack_status(notification_id: str | UUID) -> dict[str, Any]:
    """Return ACK status for a notification if it is tracked."""
    notification_uuid = UUID(str(notification_id))
    ack_status = _get_ack_engine().get_status(notification_uuid)
    return {
        "notification_id": str(notification_uuid),
        "ack_status": ack_status.value if ack_status is not None else None,
    }


def get_notification_status(notification_id: str | UUID) -> dict[str, Any]:
    """Return the tracked notification status available from the ACK engine."""
    notification_uuid = UUID(str(notification_id))
    state = _get_ack_engine().get_state(notification_uuid)
    if state is None:
        return {
            "notification_id": str(notification_uuid),
            "found": False,
            "ack_status": None,
        }
    return {
        "notification_id": str(notification_uuid),
        "found": True,
        "intent": state.intent.value if state.intent else None,
        "ack_status": state.status.value if state.status else None,
        "created_at": state.created_at.isoformat() if state.created_at else None,
    }


def get_delivery_status(
    notification_id: str | UUID,
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return persisted delivery audit status for a notification."""
    notification_uuid = UUID(str(notification_id))
    state = runtime_state or RuntimeState()
    audits = state.audit_store.get_delivery_audits_for_notification(notification_uuid)
    if not audits:
        return {
            "notification_id": str(notification_uuid),
            "found": False,
            "audit_count": 0,
            "audits": [],
        }
    latest = audits[0]
    return {
        "notification_id": str(notification_uuid),
        "found": True,
        "notification_type": latest.notification_type,
        "delivery_status": latest.status.value,
        "channels_attempted": [channel.value for channel in latest.channels_attempted],
        "channels_succeeded": [channel.value for channel in latest.channels_succeeded],
        "channels_failed": [channel.value for channel in latest.channels_failed],
        "error_message": latest.error_message,
        "audit_count": len(audits),
        "audits": [_json_safe(audit) for audit in audits],
    }


def list_dlq(runtime_state: RuntimeState | None = None) -> dict[str, Any]:
    """List visible dead-lettered delivery failures."""
    state = runtime_state or RuntimeState()
    return {
        "depth": state.dlq_service.depth(),
        "items": [entry.model_dump(mode="json") for entry in state.dlq_service.list_entries()],
    }


def get_channel_health(runtime_state: RuntimeState | None = None) -> dict[str, Any]:
    """Return runtime channel health."""
    state = runtime_state or RuntimeState()
    return state.channel_health_tracker.get_summary().model_dump(mode="json")


def ready(config: MCPRuntimeConfig | None = None) -> dict[str, Any]:
    """Return MCP runtime readiness."""
    active_config = config or MCPRuntimeConfig()
    return {
        "status": "ready",
        "service": "agsignal-mcp",
        "mode": active_config.mode,
        "read_only": active_config.read_only,
    }


def health() -> dict[str, str]:
    """Return MCP process liveness."""
    return {
        "status": "alive",
        "service": "agsignal-mcp",
    }


async def get_effective_policy(
    notification_type: str,
    intent: str,
    autonomy_mode: str,
    irreversible: bool = False,
) -> dict[str, Any]:
    """Return effective policy resolution for a signal shape."""
    response = await get_effective_policy_route(
        notification_type=notification_type,
        intent=NotificationIntent(intent),
        autonomy_mode=AutonomyMode(autonomy_mode),
        irreversible=irreversible,
    )
    return response.model_dump(mode="json")


async def list_invariants(limit: int = 25) -> dict[str, Any]:
    """Return registered AGSignal invariants."""
    response = await list_invariants_route(limit=limit)
    return response.model_dump(mode="json")


async def get_invariants_summary() -> dict[str, Any]:
    """Return invariant summary counts."""
    response = await get_invariants_summary_route()
    return response.model_dump(mode="json")


async def list_deliveries(limit: int = 25) -> dict[str, Any]:
    """Return delivery read-model entries."""
    response = await list_deliveries_route(
        cursor=None,
        limit=limit,
        start_time=None,
        end_time=None,
        status=None,
        intent=None,
        delivery_mode=None,
        agent_id=None,
        autonomy_mode=None,
        notification_type=None,
        channel=None,
    )
    return response.model_dump(mode="json")


async def list_audit_events(limit: int = 25) -> dict[str, Any]:
    """Return audit read-model entries."""
    response = await list_audit_events_route(
        cursor=None,
        limit=limit,
        start_time=None,
        end_time=None,
        event_type=None,
        notification_id=None,
        agent_id=None,
        autonomy_mode=None,
        correlation_id=None,
    )
    return response.model_dump(mode="json")

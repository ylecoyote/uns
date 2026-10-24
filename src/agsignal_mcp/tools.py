"""AGSignal MCP tool implementations."""

from __future__ import annotations

import hmac
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agsignal import signaling as agsignal_signaling
from agsignal.queries import (
    get_ack_status as query_get_ack_status,
)
from agsignal.queries import (
    get_effective_policy as query_get_effective_policy,
)
from agsignal.queries import (
    get_invariants_summary as query_get_invariants_summary,
)
from agsignal.queries import (
    get_notification_status as query_get_notification_status,
)
from agsignal.queries import (
    list_audit_events as query_list_audit_events,
)
from agsignal.queries import (
    list_deliveries as query_list_deliveries,
)
from agsignal.queries import (
    list_invariants as query_list_invariants,
)
from agsignal.responses import SendNotificationRequest
from agsignal_mcp.runtime import MCPRuntimeConfig, RuntimeState
from notification.models import AutonomyMode, NotificationIntent


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


def _signaling_request(payload: SendSignalInput) -> SendNotificationRequest:
    """Build a :class:`SendNotificationRequest` from MCP tool input.

    Drops MCP-transport-specific fields (``deliver``, ``operator_intent``,
    ``operator_confirmation_token``) that gate delivery in the MCP layer
    rather than belonging in the canonical service-layer request model.
    """
    # Note: keep this set in sync with MCP-only fields on SendSignalInput.
    # SendNotificationRequest forbids extras, so any new MCP-only field that
    # isn't excluded here will raise pydantic.ValidationError at request build
    # time. Add the field to this set when you add it to SendSignalInput.
    data = payload.model_dump(
        exclude={"deliver", "operator_intent", "operator_confirmation_token"},
        exclude_none=True,
    )
    return SendNotificationRequest.model_validate(data)


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return cast(dict[str, Any], _json_safe(asdict(value)))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


async def simulate_signal(
    payload: SendSignalInput,
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Preview routing and policy behavior without delivery side effects."""
    runtime = runtime_state.runtime if runtime_state is not None else None
    response = await agsignal_signaling.simulate_signal(
        request=_signaling_request(payload),
        policy_runtime=runtime.policy_runtime if runtime is not None else None,
        principal="mcp-simulation",
    )
    data = response.model_dump(mode="json")
    data["delivered"] = False
    return data


async def send_signal(
    payload: SendSignalInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Preview or send an AGSignal signal through MCP."""
    if not payload.deliver:
        return await simulate_signal(payload, runtime_state=runtime_state)

    active_config = config or MCPRuntimeConfig()
    if active_config.read_only or active_config.mode == "read-only":
        raise ValueError("send_signal is disabled in read-only mode")
    if payload.operator_intent != "deliver":
        raise ValueError("send_signal deliver=true requires operator_intent='deliver'")
    if active_config.require_delivery_confirmation:
        if not active_config.delivery_confirmation_token:
            raise ValueError("send_signal delivery requires a configured confirmation token")
        if not payload.operator_confirmation_token or not hmac.compare_digest(
            payload.operator_confirmation_token.encode(), active_config.delivery_confirmation_token.encode()
        ):
            raise ValueError("send_signal delivery confirmation token is invalid")

    if not active_config.operator_principal:
        raise ValueError("send_signal requires an operator principal")
    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        response = await state.runtime.send(_signaling_request(payload), principal=active_config.operator_principal)
        data = response.model_dump(mode="json")
        data["delivered"] = response.status.value == "DELIVERED"
        return data
    if not state.legacy_fixture_mode:
        raise ValueError("A durable runtime is required for MCP mutations")
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
    response = await agsignal_signaling.send_signal(
        request=_signaling_request(payload),
        audit_store=state.audit_store,
        idempotency_store=state.idempotency_records,
        transport_metadata={"runtime": "agsignal_mcp"},
    )
    data = response.model_dump(mode="json")
    data["delivered"] = response.status.value in ("DELIVERED", "SUCCESS")
    return data


async def ack_notification(
    payload: AckNotificationInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Acknowledge a tracked AGSignal notification."""
    active_config = config or MCPRuntimeConfig()
    if active_config.read_only or active_config.mode == "read-only":
        raise ValueError("ack_notification is disabled in read-only mode")
    if not active_config.operator_principal:
        raise ValueError("ack_notification requires an operator principal")
    if payload.acked_by is not None and payload.acked_by != active_config.operator_principal:
        raise ValueError("ack_notification acked_by must match the operator principal")

    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        response = state.runtime.acknowledge(payload.notification_id,
            actor=active_config.operator_principal, dismiss=False, metadata=payload.metadata)
        return response.model_dump(mode="json")
    if not state.legacy_fixture_mode:
        raise ValueError("A durable runtime is required for MCP mutations")
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
    response = await agsignal_signaling.acknowledge(
        notification_id=payload.notification_id,
        acked_by=active_config.operator_principal,
        metadata=payload.metadata,
        audit_store=state.audit_store,
    )
    return {
        "notification_id": str(response.notification_id),
        "ack_status": response.ack_status.value,
        "acked_by": response.acked_by,
        "acked_at": response.acked_at.isoformat(),
        "metadata": response.metadata,
    }


async def dismiss_notification(
    payload: AckNotificationInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Dismiss a tracked AGSignal notification."""
    active_config = config or MCPRuntimeConfig()
    if active_config.read_only or active_config.mode == "read-only":
        raise ValueError("dismiss_notification is disabled in read-only mode")
    if not active_config.operator_principal:
        raise ValueError("dismiss_notification requires an operator principal")
    if payload.acked_by is not None and payload.acked_by != active_config.operator_principal:
        raise ValueError("dismiss_notification acked_by must match the operator principal")

    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        response = state.runtime.acknowledge(payload.notification_id,
            actor=active_config.operator_principal, dismiss=True, metadata=payload.metadata)
        return response.model_dump(mode="json")
    if not state.legacy_fixture_mode:
        raise ValueError("A durable runtime is required for MCP mutations")
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
    response = await agsignal_signaling.dismiss(
        notification_id=payload.notification_id,
        dismissed_by=active_config.operator_principal,
        metadata=payload.metadata,
        audit_store=state.audit_store,
    )
    return {
        "notification_id": str(response.notification_id),
        "ack_status": response.ack_status.value,
        "acked_by": response.acked_by,
        "acked_at": response.acked_at.isoformat(),
        "metadata": response.metadata,
    }


def _obligation_projection(row: dict[str, Any]) -> dict[str, Any]:
    """Keep both durable MCP status tools aligned with the runtime projection."""
    return {
        key: row[key]
        for key in (
            "obligation_owner_id",
            "effective_ack_status",
            "ack_inherited",
            "obligation_resolution_status",
            "obligation_resolution_error",
        )
    }


async def get_ack_status(
    notification_id: str | UUID,
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return ACK status for a notification if it is tracked.

    A supplied runtime owns the read. Legacy callers without a runtime retain
    ``agsignal.queries.get_ack_status`` and the legacy two-field response.
    """
    if runtime_state is not None and runtime_state.runtime is not None:
        notification_key = str(notification_id)
        try:
            row = runtime_state.runtime.get(notification_key)
        except KeyError:
            return {"notification_id": notification_key, "ack_status": None}
        return {
            "notification_id": notification_key,
            "ack_status": row["ack_status"],
            **_obligation_projection(row),
        }
    notification_uuid = UUID(str(notification_id))
    response = await query_get_ack_status(notification_id=notification_uuid)
    return {
        "notification_id": str(response.notification_id),
        "ack_status": response.ack_status.value if response.ack_status is not None else None,
    }


async def get_notification_status(
    notification_id: str | UUID,
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return notification status from the owning runtime.

    Runtime reads preserve the durable MCP response shape. Legacy callers
    without a runtime retain the ACK engine's ``NotificationStatusResponse``
    schema through ``agsignal.queries.get_notification_status``.
    """
    if runtime_state is not None and runtime_state.runtime is not None:
        notification_key = str(notification_id)
        try:
            row = runtime_state.runtime.get(notification_key)
        except KeyError:
            return {"notification_id": notification_key, "found": False}
        return {
            "notification_id": notification_key,
            "found": True,
            "ack_status": row["ack_status"],
            "status": row["status"],
            **_obligation_projection(row),
        }
    notification_uuid = UUID(str(notification_id))
    response = await query_get_notification_status(notification_id=notification_uuid)
    return cast(dict[str, Any], _json_safe(response.model_dump()))


def get_delivery_status(
    notification_id: str | UUID,
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return persisted delivery audit status for a notification."""
    notification_uuid = UUID(str(notification_id))
    state = runtime_state or RuntimeState()
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
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
    if state.runtime is not None:
        items = state.runtime.dead_letters()
        return {"depth": len(items), "items": items}
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
    runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return effective policy resolution for a signal shape.

    Delegates to ``agsignal.queries.get_effective_policy``.
    """
    response = await query_get_effective_policy(
        notification_type=notification_type,
        intent=NotificationIntent(intent),
        autonomy_mode=AutonomyMode(autonomy_mode),
        irreversible=irreversible,
        policy_registry=(runtime_state.runtime.policy_runtime.registry()
                         if runtime_state is not None and runtime_state.runtime is not None else None),
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def list_invariants(limit: int = 25) -> dict[str, Any]:
    """Return registered AGSignal invariants.

    Delegates to ``agsignal.queries.list_invariants``.
    """
    response = await query_list_invariants(limit=limit)
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def get_invariants_summary() -> dict[str, Any]:
    """Return invariant summary counts.

    Delegates to ``agsignal.queries.get_invariants_summary``.
    """
    response = await query_get_invariants_summary()
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def list_deliveries(
    limit: int = 25, *, runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return delivery read-model entries.

    Delegates to ``agsignal.queries.list_deliveries``.
    """
    response = await query_list_deliveries(
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
        read_adapter=runtime_state.read_model_adapter if runtime_state is not None else None,
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def list_audit_events(
    limit: int = 25, *, runtime_state: RuntimeState | None = None,
) -> dict[str, Any]:
    """Return audit read-model entries.

    Delegates to ``agsignal.queries.list_audit_events``.
    """
    response = await query_list_audit_events(
        cursor=None,
        limit=limit,
        start_time=None,
        end_time=None,
        event_type=None,
        notification_id=None,
        agent_id=None,
        autonomy_mode=None,
        correlation_id=None,
        read_adapter=runtime_state.read_model_adapter if runtime_state is not None else None,
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))

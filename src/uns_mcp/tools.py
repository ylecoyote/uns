"""UNS MCP tool implementations."""

from __future__ import annotations

import hmac
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from notification.models import AutonomyMode, NotificationIntent
from uns import signaling as uns_signaling
from uns.api.auth import matches_scope_patterns
from uns.queries import (
    get_ack_status as query_get_ack_status,
)
from uns.queries import (
    get_effective_policy as query_get_effective_policy,
)
from uns.queries import (
    get_invariants_summary as query_get_invariants_summary,
)
from uns.queries import (
    get_notification_status as query_get_notification_status,
)
from uns.queries import (
    list_audit_events as query_list_audit_events,
)
from uns.queries import (
    list_deliveries as query_list_deliveries,
)
from uns.queries import (
    list_invariants as query_list_invariants,
)
from uns.responses import SendNotificationRequest
from uns_mcp.runtime import MCPRuntimeConfig, RuntimeState


def _mcp_has_non_wildcard_sources(config: MCPRuntimeConfig | None) -> bool:
    return bool(config is not None and config.allowed_sources and "*" not in config.allowed_sources)


def _mcp_has_non_wildcard_namespaces(config: MCPRuntimeConfig | None) -> bool:
    return bool(
        config is not None and config.allowed_namespaces and "*" not in config.allowed_namespaces
    )


def _mcp_has_record_bounds(config: MCPRuntimeConfig | None) -> bool:
    return _mcp_has_non_wildcard_sources(config) or _mcp_has_non_wildcard_namespaces(config)


def _mcp_allows_record(
    config: MCPRuntimeConfig | None,
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    if config is None:
        return True
    return matches_scope_patterns(source, config.allowed_sources) and matches_scope_patterns(
        notification_type, config.allowed_namespaces
    )


def _enforce_mcp_scope_bounds(
    config: MCPRuntimeConfig | None,
    *,
    source: str | None = None,
    notification_type: str | None = None,
    require_source: bool = True,
    require_namespace: bool = True,
) -> None:
    if config is None:
        return
    check_source = source is not None or (require_source and _mcp_has_non_wildcard_sources(config))
    if check_source and not matches_scope_patterns(source, config.allowed_sources):
        raise ValueError(f"MCP principal is not authorized for source '{source}'")
    check_namespace = notification_type is not None or (
        require_namespace and _mcp_has_non_wildcard_namespaces(config)
    )
    if check_namespace and not matches_scope_patterns(notification_type, config.allowed_namespaces):
        raise ValueError(
            f"MCP principal is not authorized for notification_type '{notification_type}'"
        )


_enforce_mcp_scope = _enforce_mcp_scope_bounds


def _resolve_mcp_notification_bounds(
    notification_id: str | UUID | None,
    runtime_state: RuntimeState | None = None,
    *,
    item: object | None = None,
) -> tuple[str | None, str | None]:
    source: str | None = None
    notification_type: str | None = None
    if isinstance(item, dict):
        raw_item_notif = item.get("notification")
        notif: dict[str, Any] = raw_item_notif if isinstance(raw_item_notif, dict) else {}
        raw_src = notif.get("source") or item.get("source")
        if isinstance(raw_src, str) and raw_src:
            source = raw_src
        raw_nt = notif.get("notification_type") or item.get("notification_type")
        if isinstance(raw_nt, str) and raw_nt:
            notification_type = raw_nt
    elif item is not None:
        raw_src = getattr(item, "source", None)
        if isinstance(raw_src, str) and raw_src:
            source = raw_src
        raw_nt = getattr(item, "notification_type", None)
        if isinstance(raw_nt, str) and raw_nt:
            notification_type = raw_nt
        meta = getattr(item, "metadata", None)
        if isinstance(meta, dict):
            if not source and isinstance(meta.get("source"), str):
                source = meta["source"]
            if not notification_type and isinstance(meta.get("notification_type"), str):
                notification_type = meta["notification_type"]

    if notification_id is None:
        return source, notification_type
    try:
        nid_uuid: UUID | None = UUID(str(notification_id))
    except Exception:
        nid_uuid = None

    if (
        (not source or not notification_type)
        and runtime_state is not None
        and runtime_state.runtime is not None
    ):
        try:
            row = runtime_state.runtime.get(str(notification_id))
        except Exception:
            row = None
        if isinstance(row, dict):
            raw_row_notif = row.get("notification")
            notif_dict: dict[str, Any] = raw_row_notif if isinstance(raw_row_notif, dict) else {}
            if not source and isinstance(notif_dict.get("source"), str):
                source = notif_dict["source"]
            elif not source and isinstance(row.get("source"), str):
                source = row["source"]
            if not notification_type and isinstance(notif_dict.get("notification_type"), str):
                notification_type = notif_dict["notification_type"]
            elif not notification_type and isinstance(row.get("notification_type"), str):
                notification_type = row["notification_type"]

    audit_store = runtime_state.audit_store if runtime_state is not None else None
    if (not source or not notification_type) and audit_store is not None and nid_uuid is not None:
        try:
            audits = audit_store.get_delivery_audits_for_notification(nid_uuid)
        except Exception:
            audits = []
        if audits:
            first = audits[0]
            if not source and isinstance(getattr(first, "source", None), str):
                source = first.source
            if not notification_type and isinstance(getattr(first, "notification_type", None), str):
                notification_type = first.notification_type

    from uns.api.read_models import get_read_model_adapter

    read_adapter = (
        runtime_state.read_model_adapter
        if runtime_state is not None and runtime_state.read_model_adapter is not None
        else get_read_model_adapter()
    )
    if (not source or not notification_type) and read_adapter is not None and nid_uuid is not None:
        ad_audit_store = getattr(read_adapter, "audit_store", None)
        if ad_audit_store is not None and ad_audit_store is not audit_store:
            get_audits = getattr(ad_audit_store, "get_delivery_audits_for_notification", None)
            if callable(get_audits):
                try:
                    ad_audits = get_audits(nid_uuid)
                except Exception:
                    ad_audits = []
                if ad_audits:
                    first = ad_audits[0]
                    if not source and isinstance(getattr(first, "source", None), str):
                        source = first.source
                    if not notification_type and isinstance(
                        getattr(first, "notification_type", None), str
                    ):
                        notification_type = first.notification_type
        get_session = getattr(read_adapter, "_get_session", None)
        if (not source or not notification_type) and callable(get_session):
            session = get_session()
            if session is not None:
                try:
                    from sqlalchemy import select

                    from db.models import NotificationAuditRecord

                    stmt = (
                        select(
                            NotificationAuditRecord.source,
                            NotificationAuditRecord.notification_type,
                        )
                        .where(NotificationAuditRecord.notification_id == nid_uuid)
                        .limit(1)
                    )
                    rec = session.execute(stmt).first()
                    if rec is not None:
                        if not source and isinstance(rec[0], str):
                            source = rec[0]
                        if not notification_type and isinstance(rec[1], str):
                            notification_type = rec[1]
                except Exception:  # nosec B110
                    pass
                finally:
                    session.close()

    return source, notification_type


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
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Preview routing and policy behavior without delivery side effects."""
    _enforce_mcp_scope_bounds(
        config,
        source=payload.source,
        notification_type=payload.notification_type,
    )
    runtime = runtime_state.runtime if runtime_state is not None else None
    response = await uns_signaling.simulate_signal(
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
    """Preview or send an UNS signal through MCP."""
    if not payload.deliver:
        return await simulate_signal(payload, runtime_state=runtime_state, config=config)

    active_config = config or MCPRuntimeConfig()
    _enforce_mcp_scope_bounds(
        active_config,
        source=payload.source,
        notification_type=payload.notification_type,
    )
    if active_config.read_only or active_config.mode == "read-only":
        raise ValueError("send_signal is disabled in read-only mode")
    if payload.operator_intent != "deliver":
        raise ValueError("send_signal deliver=true requires operator_intent='deliver'")
    if active_config.require_delivery_confirmation:
        if not active_config.delivery_confirmation_token:
            raise ValueError("send_signal delivery requires a configured confirmation token")
        if not payload.operator_confirmation_token or not hmac.compare_digest(
            payload.operator_confirmation_token.encode(),
            active_config.delivery_confirmation_token.encode(),
        ):
            raise ValueError("send_signal delivery confirmation token is invalid")

    if not active_config.operator_principal:
        raise ValueError("send_signal requires an operator principal")
    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        response = await state.runtime.send(
            _signaling_request(payload), principal=active_config.operator_principal
        )
        data = response.model_dump(mode="json")
        data["delivered"] = response.status.value == "DELIVERED"
        return data
    if not state.legacy_fixture_mode:
        raise ValueError("A durable runtime is required for MCP mutations")
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
    response = await uns_signaling.send_signal(
        request=_signaling_request(payload),
        audit_store=state.audit_store,
        idempotency_store=state.idempotency_records,
        transport_metadata={"runtime": "uns_mcp"},
    )
    data = response.model_dump(mode="json")
    data["delivered"] = response.status.value in ("DELIVERED", "SUCCESS")
    return data


async def ack_notification(
    payload: AckNotificationInput,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Acknowledge a tracked UNS notification."""
    active_config = config or MCPRuntimeConfig()
    if active_config.read_only or active_config.mode == "read-only":
        raise ValueError("ack_notification is disabled in read-only mode")
    if not active_config.operator_principal:
        raise ValueError("ack_notification requires an operator principal")
    if payload.acked_by is not None and payload.acked_by != active_config.operator_principal:
        raise ValueError("ack_notification acked_by must match the operator principal")

    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        if active_config.allowed_sources or active_config.allowed_namespaces:
            row = state.runtime.get(payload.notification_id)
            n = row.get("notification", {})
            _enforce_mcp_scope_bounds(
                active_config,
                source=n.get("source"),
                notification_type=n.get("notification_type"),
            )
        response = state.runtime.acknowledge(
            payload.notification_id,
            actor=active_config.operator_principal,
            dismiss=False,
            metadata=payload.metadata,
        )
        await state.runtime.sync_pagerduty_incident(payload.notification_id, resolve=False)
        return response.model_dump(mode="json")
    if not state.legacy_fixture_mode:
        raise ValueError("A durable runtime is required for MCP mutations")
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
    response = await uns_signaling.acknowledge(
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
    """Dismiss a tracked UNS notification."""
    active_config = config or MCPRuntimeConfig()
    if active_config.read_only or active_config.mode == "read-only":
        raise ValueError("dismiss_notification is disabled in read-only mode")
    if not active_config.operator_principal:
        raise ValueError("dismiss_notification requires an operator principal")
    if payload.acked_by is not None and payload.acked_by != active_config.operator_principal:
        raise ValueError("dismiss_notification acked_by must match the operator principal")

    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        if active_config.allowed_sources or active_config.allowed_namespaces:
            row = state.runtime.get(payload.notification_id)
            n = row.get("notification", {})
            _enforce_mcp_scope_bounds(
                active_config,
                source=n.get("source"),
                notification_type=n.get("notification_type"),
            )
        response = state.runtime.acknowledge(
            payload.notification_id,
            actor=active_config.operator_principal,
            dismiss=True,
            metadata=payload.metadata,
        )
        await state.runtime.sync_pagerduty_incident(payload.notification_id, resolve=True)
        return response.model_dump(mode="json")
    if not state.legacy_fixture_mode:
        raise ValueError("A durable runtime is required for MCP mutations")
    if state.audit_store is None:
        raise RuntimeError("MCP runtime state is missing its audit store")
    response = await uns_signaling.dismiss(
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
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Return ACK status for a notification if it is tracked.

    A supplied runtime owns the read. Legacy callers without a runtime retain
    ``uns.queries.get_ack_status`` and the legacy two-field response.
    """
    if runtime_state is not None and runtime_state.runtime is not None:
        notification_key = str(notification_id)
        try:
            row = runtime_state.runtime.get(notification_key)
        except KeyError:
            return {"notification_id": notification_key, "ack_status": None}
        if _mcp_has_record_bounds(config):
            source, ntype = _resolve_mcp_notification_bounds(
                notification_id,
                runtime_state,
                item=row,
            )
            _enforce_mcp_scope_bounds(
                config,
                source=source,
                notification_type=ntype,
            )
        return {
            "notification_id": notification_key,
            "ack_status": row["ack_status"],
            **_obligation_projection(row),
        }
    notification_uuid = UUID(str(notification_id))
    response = await query_get_ack_status(notification_id=notification_uuid)
    if _mcp_has_record_bounds(config):
        source, ntype = _resolve_mcp_notification_bounds(
            notification_uuid,
            runtime_state,
            item=response,
        )
        _enforce_mcp_scope_bounds(
            config,
            source=source,
            notification_type=ntype,
        )
    return {
        "notification_id": str(response.notification_id),
        "ack_status": response.ack_status.value if response.ack_status is not None else None,
    }


async def get_notification_status(
    notification_id: str | UUID,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Return notification status from the owning runtime.

    Runtime reads preserve the durable MCP response shape. Legacy callers
    without a runtime retain the ACK engine's ``NotificationStatusResponse``
    schema through ``uns.queries.get_notification_status``.
    """
    if runtime_state is not None and runtime_state.runtime is not None:
        notification_key = str(notification_id)
        try:
            row = runtime_state.runtime.get(notification_key)
        except KeyError:
            return {"notification_id": notification_key, "found": False}
        if _mcp_has_record_bounds(config):
            source, ntype = _resolve_mcp_notification_bounds(
                notification_id,
                runtime_state,
                item=row,
            )
            _enforce_mcp_scope_bounds(
                config,
                source=source,
                notification_type=ntype,
            )
        return {
            "notification_id": notification_key,
            "found": True,
            "ack_status": row["ack_status"],
            "status": row["status"],
            **_obligation_projection(row),
        }
    notification_uuid = UUID(str(notification_id))
    response = await query_get_notification_status(notification_id=notification_uuid)
    if _mcp_has_record_bounds(config):
        source, ntype = _resolve_mcp_notification_bounds(
            notification_uuid,
            runtime_state,
            item=response,
        )
        _enforce_mcp_scope_bounds(
            config,
            source=source,
            notification_type=ntype,
        )
    return cast(dict[str, Any], _json_safe(response.model_dump()))


def get_delivery_status(
    notification_id: str | UUID,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
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
    if _mcp_has_record_bounds(config):
        source, ntype = _resolve_mcp_notification_bounds(
            notification_uuid,
            state,
            item=latest,
        )
        _enforce_mcp_scope_bounds(
            config,
            source=source,
            notification_type=ntype,
        )
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


def list_dlq(
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """List visible dead-lettered delivery failures."""
    state = runtime_state or RuntimeState()
    if state.runtime is not None:
        items = state.runtime.dead_letters()
        if _mcp_has_record_bounds(config):
            filtered_items: list[dict[str, Any]] = []
            for item in items:
                source, ntype = _resolve_mcp_notification_bounds(
                    item.get("notification_id") if isinstance(item, dict) else None,
                    state,
                    item=item,
                )
                if _mcp_allows_record(
                    config,
                    source=source,
                    notification_type=ntype,
                ):
                    filtered_items.append(item)
            items = filtered_items
        return {"depth": len(items), "items": items}
    entries = state.dlq_service.list_entries()
    if _mcp_has_record_bounds(config):
        filtered_entries = []
        for entry in entries:
            source, ntype = _resolve_mcp_notification_bounds(
                entry.notification_id,
                state,
                item=entry,
            )
            if _mcp_allows_record(
                config,
                source=source,
                notification_type=ntype,
            ):
                filtered_entries.append(entry)
        return {
            "depth": len(filtered_entries),
            "items": [entry.model_dump(mode="json") for entry in filtered_entries],
        }
    return {
        "depth": state.dlq_service.depth(),
        "items": [entry.model_dump(mode="json") for entry in entries],
    }


list_dlq_entries = list_dlq


def get_channel_health(runtime_state: RuntimeState | None = None) -> dict[str, Any]:
    """Return runtime channel health."""
    state = runtime_state or RuntimeState()
    tracker = getattr(state, "channel_health", None) or state.channel_health_tracker
    sync_fn = getattr(tracker, "sync_from_runtime", None)
    if callable(sync_fn) and state.runtime is not None:
        sync_fn(state.runtime)
    return tracker.get_summary().model_dump(mode="json")


def ready(config: MCPRuntimeConfig | None = None) -> dict[str, Any]:
    """Return MCP runtime readiness."""
    active_config = config or MCPRuntimeConfig()
    return {
        "status": "ready",
        "service": "uns-mcp",
        "mode": active_config.mode,
        "read_only": active_config.read_only,
    }


def health() -> dict[str, str]:
    """Return MCP process liveness."""
    return {
        "status": "alive",
        "service": "uns-mcp",
    }


async def get_effective_policy(
    notification_type: str,
    intent: str,
    autonomy_mode: str,
    irreversible: bool = False,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Return effective policy resolution for a signal shape.

    Delegates to ``uns.queries.get_effective_policy``.
    """
    _enforce_mcp_scope_bounds(
        config,
        notification_type=notification_type,
        require_source=False,
    )
    response = await query_get_effective_policy(
        notification_type=notification_type,
        intent=NotificationIntent(intent),
        autonomy_mode=AutonomyMode(autonomy_mode),
        irreversible=irreversible,
        policy_registry=(
            runtime_state.runtime.policy_runtime.registry()
            if runtime_state is not None and runtime_state.runtime is not None
            else None
        ),
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def list_invariants(limit: int = 25) -> dict[str, Any]:
    """Return registered UNS invariants.

    Delegates to ``uns.queries.list_invariants``.
    """
    response = await query_list_invariants(limit=limit)
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def get_invariants_summary() -> dict[str, Any]:
    """Return invariant summary counts.

    Delegates to ``uns.queries.get_invariants_summary``.
    """
    response = await query_get_invariants_summary()
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def list_deliveries(
    limit: int = 25,
    *,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Return delivery read-model entries.

    Delegates to ``uns.queries.list_deliveries``.
    """
    read_adapter = runtime_state.read_model_adapter if runtime_state is not None else None
    if _mcp_has_record_bounds(config):
        assert config is not None
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
            read_adapter=read_adapter,
            allowed_sources=(
                config.allowed_sources
                if config.allowed_sources and "*" not in config.allowed_sources
                else None
            ),
            allowed_namespaces=(
                config.allowed_namespaces
                if config.allowed_namespaces and "*" not in config.allowed_namespaces
                else None
            ),
        )
        return cast(dict[str, Any], _json_safe(response.model_dump()))
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
        read_adapter=read_adapter,
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))


list_notifications = list_deliveries


async def list_audit_events(
    limit: int = 25,
    *,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Return audit read-model entries.

    Delegates to ``uns.queries.list_audit_events``.
    """
    read_adapter = runtime_state.read_model_adapter if runtime_state is not None else None
    if _mcp_has_record_bounds(config):
        assert config is not None
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
            read_adapter=read_adapter,
            allowed_sources=(
                config.allowed_sources
                if config.allowed_sources and "*" not in config.allowed_sources
                else None
            ),
            allowed_namespaces=(
                config.allowed_namespaces
                if config.allowed_namespaces and "*" not in config.allowed_namespaces
                else None
            ),
        )
        return cast(dict[str, Any], _json_safe(response.model_dump()))
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
        read_adapter=read_adapter,
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))


async def get_audit_trail(
    notification_id: str | UUID,
    *,
    runtime_state: RuntimeState | None = None,
    config: MCPRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Return audit trail for a single notification after scope verification."""
    notification_uuid = UUID(str(notification_id))
    if _mcp_has_record_bounds(config):
        source, ntype = _resolve_mcp_notification_bounds(
            notification_uuid,
            runtime_state,
        )
        _enforce_mcp_scope_bounds(
            config,
            source=source,
            notification_type=ntype,
        )
    response = await query_list_audit_events(
        cursor=None,
        limit=200,
        start_time=None,
        end_time=None,
        event_type=None,
        notification_id=notification_uuid,
        agent_id=None,
        autonomy_mode=None,
        correlation_id=None,
        read_adapter=runtime_state.read_model_adapter if runtime_state is not None else None,
    )
    return cast(dict[str, Any], _json_safe(response.model_dump()))

"""Shared AGSignal runtime helpers for HTTP routes and MCP tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from notification.acknowledgment import configure_ack_engine, get_ack_engine
from notification.audit import AuditStore, InMemoryAuditStore, create_audit_record
from notification.channel_health import ChannelHealthTracker
from notification.dlq import DLQService
from notification.models import AckStatus
from notification.routes import (
    SendNotificationRequest,
    SendNotificationResponse,
    SimulateNotificationResponse,
    _resolve_notification,
)
from notification.routes import simulate_notification as simulate_notification_route


class InMemoryRedisList:
    """Minimal Redis-list compatible store for local runtime helpers."""

    def __init__(self) -> None:
        self.values: list[str] = []

    def lpush(self, key: str, value: str) -> int:
        self.values.insert(0, value)
        return len(self.values)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        stop = None if end == -1 else end + 1
        return self.values[start:stop]

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        next_values = []
        for item in self.values:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            next_values.append(item)
        self.values = next_values
        return removed

    def llen(self, key: str) -> int:
        return len(self.values)


@dataclass
class RuntimeState:
    """Runtime services shared by AGSignal process entrypoints."""

    audit_store: AuditStore = field(default_factory=InMemoryAuditStore)
    dlq_service: DLQService = field(
        default_factory=lambda: DLQService(redis_client=InMemoryRedisList())
    )
    channel_health_tracker: ChannelHealthTracker = field(default_factory=ChannelHealthTracker)
    idempotency_records: dict[str, SendNotificationResponse] = field(default_factory=dict)


async def simulate_signal_async(
    state: RuntimeState,
    payload: dict[str, Any],
) -> SimulateNotificationResponse:
    """Preview routing and ACK behavior without delivery side effects."""
    del state
    request = SendNotificationRequest.model_validate(payload)
    return await simulate_notification_route(request)


def simulate_signal(
    state: RuntimeState,
    payload: dict[str, Any],
) -> SimulateNotificationResponse:
    """Synchronous wrapper for local MCP tool execution."""
    return asyncio.run(simulate_signal_async(state, payload))


def send_signal(
    state: RuntimeState,
    payload: dict[str, Any],
) -> SendNotificationResponse:
    """Accept an AGSignal signal through a local runtime state."""
    request = SendNotificationRequest.model_validate(payload)
    if request.idempotency_key is not None:
        record_key = f"{request.source}:{request.idempotency_key}"
        existing_response = state.idempotency_records.get(record_key)
        if existing_response is not None:
            return existing_response.model_copy(update={"idempotent_replay": True})

    result, notification = _resolve_notification(request)
    from notification.metrics import record_signal_received

    record_signal_received(
        intent=notification.intent.value,
        autonomy_mode=notification.autonomy_context.autonomy_mode.value,
        transport="mcp",
    )
    ack_status: AckStatus | None = None
    if notification.require_ack:
        try:
            engine = get_ack_engine()
        except RuntimeError:
            engine = configure_ack_engine()
        engine.register_notification(
            notification_id=notification.notification_id,
            intent=notification.intent,
            autonomy_context=notification.autonomy_context,
            timeout_minutes=notification.ack_timeout_minutes,
            created_at=notification.created_at,
        )
        ack_status = engine.get_status(notification.notification_id)

    state.audit_store.save_delivery_audit(
        create_audit_record(
            notification,
            result,
            metadata={"runtime": "agsignal_mcp"},
        )
    )
    response = SendNotificationResponse(
        notification_id=result.notification_id,
        status=result.status,
        channels_attempted=result.channels_attempted,
        channels_succeeded=result.channels_succeeded,
        channels_failed=result.channels_failed,
        require_ack=bool(notification.require_ack),
        ack_status=ack_status,
        idempotency_key=request.idempotency_key,
        idempotent_replay=False,
        created_at=notification.created_at,
        message="notification accepted",
    )
    if request.idempotency_key is not None:
        state.idempotency_records[f"{request.source}:{request.idempotency_key}"] = response
    return response

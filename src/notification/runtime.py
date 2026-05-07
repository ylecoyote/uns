"""Shared AGSignal runtime helpers for HTTP routes and MCP tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from notification.audit import AuditStore, InMemoryAuditStore
from notification.channel_health import ChannelHealthTracker
from notification.dlq import DLQService
from notification.routes import SendNotificationRequest, SimulateNotificationResponse
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

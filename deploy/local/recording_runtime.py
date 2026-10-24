"""Persistent, recording-only composition for a single-user local installation."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel, Notification
from notification.service import SimpleAdapterRegistry
from uns.runtime import Runtime


def append_receipt(filename: str, payload: dict[str, Any]) -> None:
    """Append a small receipt durably without duplicating notification content."""
    path = Path("/data") / filename
    data = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if not written:
                raise OSError("Recording receipt write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class RecordingAdapter(BaseAdapter):
    def __init__(self, channel: Channel) -> None:
        self._channel = channel

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        message_id = "recording:" + str(uuid4())
        observed_at = datetime.now(UTC)
        await asyncio.to_thread(
            append_receipt,
            "recordings.jsonl",
            {
                "notification_id": str(notification.notification_id),
                "channel": self.channel.value,
                "message_id": message_id,
                "at": observed_at.isoformat(),
                "recording_only": True,
            },
        )
        return DeliveryResult(
            success=True,
            channel=self.channel,
            message_id=message_id,
            metadata={"recording_only": True},
            delivered_at=observed_at,
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(AdapterStatus.HEALTHY, "Local recording sink; no provider message")


async def record_response(event: dict[str, Any]) -> None:
    await asyncio.to_thread(
        append_receipt,
        "responses.jsonl",
        {
            "event_id": event["id"],
            "notification_id": event["notification_id"],
            "kind": event["kind"],
            "attempt": event["callback_attempts"],
            "at": datetime.now(UTC).isoformat(),
            "recording_only": True,
        },
    )


def make_runtime() -> Runtime:
    from uns.config import configure_runtime_policies

    registry = SimpleAdapterRegistry()
    for channel in (Channel.SLACK, Channel.EMAIL, Channel.PAGERDUTY):
        registry.register(RecordingAdapter(channel))
    # Deliberately do not construct credential-driven real provider adapters.
    runtime = Runtime(os.environ["UNS_DATABASE_URL"], adapters=registry, callback=record_response)
    configure_runtime_policies(runtime)
    return runtime

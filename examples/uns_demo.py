"""Local recording-adapter acceptance demo; sends no external messages."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel
from notification.service import SimpleAdapterRegistry
from uns import Client, Runtime
from uns.responses import SendNotificationRequest


class Recorder(BaseAdapter):
    channel = Channel.SLACK

    async def deliver(self, notification):
        print(f"Recorded delivery: {notification.notification_id}")
        return DeliveryResult(success=True, channel=self.channel, message_id="local-recording")

    async def health_check(self):
        return HealthCheckResult(status=AdapterStatus.HEALTHY)


async def demo(directory):
    url = f"sqlite:///{Path(directory) / 'demo.db'}"
    registry = SimpleAdapterRegistry()
    registry.register(Recorder())
    runtime = Runtime(url, adapters=registry, create_tables=True)
    request = SendNotificationRequest(
        notification_type="demo.safety",
        intent="SAFETY",
        title="Local demonstration",
        message="Recording adapter only",
        source="demo",
        autonomy_context={"agent_id": str(uuid4()), "autonomy_mode": "LIVE"},
        idempotency_key="one",
    )
    result = await Client(runtime, principal="demo-operator").send(request)
    assert result.status.value == "DELIVERED"
    restarted = Runtime(url, adapters=registry)
    ack = restarted.acknowledge(result.notification_id, actor="demo-operator")
    assert ack.ack_status.value == "ACKED"
    assert restarted.events(result.notification_id)[-1]["kind"] == "ACKED"
    print("PASS: delivered, restarted, acknowledged, and audited")


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        asyncio.run(demo(directory))

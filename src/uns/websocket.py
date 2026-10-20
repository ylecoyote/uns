"""Bridge the existing WebSocket transport into the common dispatcher."""

from fastapi import FastAPI

from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel, Notification


class WebSocketDeliveryAdapter(BaseAdapter):
    channel = Channel.WEBSOCKET

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def deliver(self, notification: Notification) -> DeliveryResult:
        state = self.app.state
        agent_id = notification.autonomy_context.agent_id
        payload = notification.model_dump(mode="json")
        cursor = state.websocket_replay_store.record(
            agent_id, payload, created_at=notification.created_at
        )
        payload["replay_cursor"] = cursor
        count = await state.websocket_manager.send_to_agent(
            agent_id, {"type": "notification", "notification": payload}
        )
        if state.websocket_fanout is not None:
            from notification.websocket_runtime import WebSocketFanoutEnvelope

            state.websocket_fanout.publish(
                WebSocketFanoutEnvelope(
                    type="notification", agent_id=agent_id, notification=payload
                )
            )
        return DeliveryResult(
            success=count > 0,
            channel=self.channel,
            error=None if count else "No local WebSocket recipient; replay recorded",
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(AdapterStatus.HEALTHY, message="WebSocket transport configured")

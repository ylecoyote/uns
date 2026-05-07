"""AGSignal MCP tool implementations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


def _runtime_payload(payload: SendSignalInput) -> dict[str, Any]:
    data = payload.model_dump(exclude={"deliver", "operator_intent"}, exclude_none=True)
    return dict(data)


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
) -> dict[str, Any]:
    """Preview or send an AGSignal signal through MCP."""
    if payload.deliver and payload.operator_intent != "deliver":
        raise ValueError("send_signal deliver=true requires operator_intent='deliver'")
    if not payload.deliver:
        return simulate_signal(payload, runtime_state=runtime_state)
    response = send_runtime_signal(runtime_state or RuntimeState(), _runtime_payload(payload))
    data = response.model_dump(mode="json")
    data["delivered"] = True
    return data

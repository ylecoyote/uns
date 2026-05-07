from __future__ import annotations

from uuid import UUID

import pytest

from agsignal_mcp.tools import SendSignalInput, send_signal, simulate_signal
from notification.runtime import RuntimeState


def _input(**overrides: object) -> SendSignalInput:
    payload: dict[str, object] = {
        "notification_type": "agent.risk_limit_breach",
        "intent": "SAFETY",
        "title": "Risk limit breached",
        "message": "Agent entered a position outside configured limits.",
        "source": "agent-runtime",
        "autonomy_context": {
            "autonomy_mode": "LIVE",
            "agent_id": "00000000-0000-0000-0000-000000000001",
        },
    }
    payload.update(overrides)
    return SendSignalInput.model_validate(payload)


def test_send_signal_requires_confirmation_for_delivery() -> None:
    with pytest.raises(ValueError, match="operator_intent"):
        send_signal(_input(deliver=True))


def test_send_signal_defaults_to_preview() -> None:
    response = send_signal(_input())

    assert response["delivered"] is False
    assert response["simulated"] is True
    assert response["ack_status"] is None


def test_simulate_signal_is_always_dry_run() -> None:
    response = simulate_signal(_input(deliver=True, operator_intent="deliver"))

    assert response["delivered"] is False
    assert response["simulated"] is True
    assert response["ack_status"] is None


def test_send_signal_confirmed_delivery_records_audit_and_ack_state() -> None:
    state = RuntimeState()

    response = send_signal(
        _input(deliver=True, operator_intent="deliver"),
        runtime_state=state,
    )

    assert response["delivered"] is True
    assert response["status"] == "SUCCESS"
    assert response["ack_status"] == "PENDING"
    audits = state.audit_store.get_delivery_audits_for_notification(UUID(response["notification_id"]))
    assert len(audits) == 1

from __future__ import annotations

from uuid import uuid4

from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine
from notification.models import AutonomyMode, NotificationIntent
from notification.runtime import RuntimeState, simulate_signal


def _payload() -> dict[str, object]:
    return {
        "notification_type": "agent.risk_limit_breach",
        "intent": NotificationIntent.SAFETY,
        "title": "Risk limit breached",
        "message": "Agent entered a position outside configured limits.",
        "source": "agent-runtime",
        "autonomy_context": {
            "autonomy_mode": AutonomyMode.LIVE,
            "agent_id": uuid4(),
        },
    }


def test_simulate_signal_has_no_ack_side_effects() -> None:
    configure_ack_engine(storage=InMemoryAckStorage())
    state = RuntimeState()

    response = simulate_signal(state, _payload())

    assert response.simulated is True
    assert response.ack_status is None

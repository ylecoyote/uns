"""Tests for the reusable WebSocket replay smoke script."""

from __future__ import annotations

from uuid import uuid4

from scripts.smoke_websocket_replay import build_notification_payload


def test_build_notification_payload_targets_agent() -> None:
    agent_id = uuid4()

    payload = build_notification_payload(agent_id)

    assert payload["notification_type"] == "agent.websocket_replay_smoke"
    assert payload["intent"] == "SAFETY"
    autonomy_context = payload["autonomy_context"]
    assert isinstance(autonomy_context, dict)
    assert autonomy_context["agent_id"] == str(agent_id)

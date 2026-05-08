"""Smoke test AGSignal WebSocket reconnect replay.

The smoke starts one in-process AGSignal FastAPI app, records a notification
while no WebSocket client is connected, then connects and subscribes from an
older replay cursor. The WebSocket response must include the missed payload.

Usage:
    python scripts/smoke_websocket_replay.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
for import_path in (REPO_ROOT / "src", REPO_ROOT):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from fastapi.testclient import TestClient  # noqa: E402


def build_notification_payload(agent_id: UUID) -> dict[str, object]:
    """Build the notification payload used by the replay smoke."""
    return {
        "notification_type": "agent.websocket_replay_smoke",
        "intent": "SAFETY",
        "title": "WebSocket replay smoke",
        "message": "Verify AGSignal reconnect replay returns missed signals.",
        "source": "smoke:websocket-replay",
        "autonomy_context": {
            "autonomy_mode": "LIVE",
            "agent_id": str(agent_id),
        },
    }


def run_smoke() -> dict[str, Any]:
    """Run the reconnect replay smoke and return a compact result."""
    from agsignal.app import create_app
    from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine

    configure_ack_engine(storage=InMemoryAckStorage())
    app = create_app()
    agent_id = uuid4()
    baseline_cursor = "1970-01-01T00:00:00+00:00"
    payload = build_notification_payload(agent_id)

    with TestClient(app) as client:
        response = client.post("/api/v1/notifications", json=payload)
        response.raise_for_status()
        accepted = response.json()

        with client.websocket_connect(f"/ws/agents/{agent_id}") as websocket:
            connected = websocket.receive_json()
            if connected["type"] != "connected":
                raise RuntimeError(f"Unexpected connect event: {connected!r}")

            websocket.send_json({"type": "subscribe", "last_seen": baseline_cursor})
            subscribed = websocket.receive_json()

    missed = subscribed.get("missed_notifications")
    if not isinstance(missed, list) or len(missed) != 1:
        raise RuntimeError(f"Unexpected replay response: {subscribed!r}")
    notification = missed[0]
    if notification.get("notification_id") != accepted["notification_id"]:
        raise RuntimeError(
            "Replayed notification did not match accepted notification: "
            f"subscribed={subscribed!r} accepted={accepted!r}"
        )
    if not notification.get("replay_cursor"):
        raise RuntimeError(f"Replay response did not include replay_cursor: {subscribed!r}")

    return {
        "agent_id": str(agent_id),
        "notification_id": accepted["notification_id"],
        "replay_available": subscribed["replay_available"],
        "replay_cursor": notification["replay_cursor"],
    }


def main() -> None:
    result = run_smoke()
    print("AGSignal WebSocket replay smoke passed")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

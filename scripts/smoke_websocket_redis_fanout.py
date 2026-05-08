"""Smoke test AGSignal WebSocket Redis fanout with two app instances.

This script requires a reachable Redis server. It starts two in-process
AGSignal FastAPI apps with Redis fanout enabled:

- the consumer app owns a connected WebSocket client for one agent
- the producer app accepts an HTTP notification for that agent
- Redis pub/sub carries the event from producer to consumer

Usage:
    python scripts/smoke_websocket_redis_fanout.py
    python scripts/smoke_websocket_redis_fanout.py --redis-url redis://localhost:6379/0
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
for import_path in (REPO_ROOT / "src", REPO_ROOT):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from fastapi.testclient import TestClient  # noqa: E402
from redis import Redis  # noqa: E402


def build_notification_payload(agent_id: UUID) -> dict[str, object]:
    """Build the notification payload used by the Redis fanout smoke."""
    return {
        "notification_type": "agent.redis_fanout_smoke",
        "intent": "SAFETY",
        "title": "Redis fanout smoke",
        "message": "Verify AGSignal WebSocket fanout across app instances.",
        "source": "smoke:websocket-redis-fanout",
        "autonomy_context": {
            "autonomy_mode": "LIVE",
            "agent_id": str(agent_id),
        },
    }


@contextmanager
def _patched_env(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _receive_json_with_timeout(websocket: Any, timeout_seconds: float) -> dict[str, Any]:
    messages: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def receive() -> None:
        try:
            messages.put(("ok", websocket.receive_json()))
        except Exception as exc:  # pragma: no cover - surfaced to caller
            messages.put(("error", exc))

    thread = threading.Thread(target=receive, daemon=True)
    thread.start()

    try:
        kind, value = messages.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        websocket.close()
        raise TimeoutError(
            f"Timed out waiting {timeout_seconds:.1f}s for WebSocket Redis fanout"
        ) from exc

    if kind == "error":
        raise value
    return cast(dict[str, Any], value)


def run_smoke(
    redis_url: str,
    channel_prefix: str,
    timeout_seconds: float,
) -> dict[str, object]:
    """Run the real Redis fanout smoke and return a compact result."""
    redis_client = Redis.from_url(redis_url)
    redis_client.ping()

    env = {
        "UNS_REDIS_URL": redis_url,
        "UNS_WEBSOCKET_REDIS_ENABLED": "true",
        "UNS_WEBSOCKET_REDIS_CHANNEL": channel_prefix,
    }
    with _patched_env(env):
        from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine
        from agsignal.app import create_app

        configure_ack_engine(storage=InMemoryAckStorage())
        consumer_app = create_app()
        producer_app = create_app()

        consumer_origin = consumer_app.state.websocket_fanout.instance_id
        producer_origin = producer_app.state.websocket_fanout.instance_id
        if consumer_origin == producer_origin:
            raise RuntimeError("Smoke requires distinct AGSignal fanout origin IDs")

        agent_id = uuid4()
        payload = build_notification_payload(agent_id)

        with (
            TestClient(consumer_app) as consumer_client,
            TestClient(producer_app) as producer_client,
            consumer_client.websocket_connect(f"/ws/agents/{agent_id}") as websocket,
        ):
            connected = websocket.receive_json()
            if connected["type"] != "connected":
                raise RuntimeError(f"Unexpected connect event: {connected!r}")

            time.sleep(0.25)
            response = producer_client.post("/api/v1/notifications", json=payload)
            response.raise_for_status()
            accepted = response.json()

            event = _receive_json_with_timeout(websocket, timeout_seconds)

        notification = event.get("notification", {})
        if not isinstance(notification, dict):
            raise RuntimeError(f"Unexpected WebSocket event shape: {event!r}")
        if event.get("type") != "notification":
            raise RuntimeError(f"Unexpected WebSocket event type: {event!r}")
        if notification.get("notification_id") != accepted["notification_id"]:
            raise RuntimeError(
                "WebSocket notification did not match accepted notification: "
                f"event={event!r} accepted={accepted!r}"
            )

        return {
            "agent_id": str(agent_id),
            "notification_id": accepted["notification_id"],
            "channel_prefix": channel_prefix,
            "consumer_origin": consumer_origin,
            "producer_origin": producer_origin,
            "websocket_event_type": event["type"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("UNS_REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL used by both AGSignal app instances.",
    )
    parser.add_argument(
        "--channel-prefix",
        default=f"agsignal:smoke:websocket:{uuid4()}",
        help="Redis channel prefix. Defaults to a unique smoke prefix.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=5.0,
        help="How long to wait for the cross-process WebSocket event.",
    )
    args = parser.parse_args()

    result = run_smoke(
        redis_url=args.redis_url,
        channel_prefix=args.channel_prefix,
        timeout_seconds=args.timeout_seconds,
    )
    print("AGSignal WebSocket Redis fanout smoke passed")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

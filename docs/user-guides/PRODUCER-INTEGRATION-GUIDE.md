# Producer & Application Integration Guide

This guide provides step-by-step patterns for application developers integrating with UNS as a **notification producer** and **acknowledgment consumer**, using either the embedded Python runtime (`uns.Runtime` + `uns.Client`) or the remote HTTP REST API (`/api/v1/notifications`).

---

## 1. Choosing Your Producer Integration Mode

| Criterion | Embedded Python (`uns.Runtime` + `uns.Client`) | Remote HTTP Service (`POST /api/v1/notifications`) |
| :--- | :--- | :--- |
| **Language Support** | Python `>= 3.11` | Any language (`curl`, `httpx`, `fetch`, Go, Rust) |
| **Authentication** | Host-supplied `principal: str` on `uns.Client(runtime, principal=...)` | `Authorization: Bearer <UNS_API_KEY>` (or `X-UNS-API-Key`) |
| **Database Access** | Direct SQLAlchemy access to `UNS_DATABASE_URL` | No direct DB access required; `uns` server owns DB |
| **Worker Lifecycle** | Application runs `await runtime.worker()` or `await runtime.run_once()` | `uns` HTTP server runs `runtime.worker()` automatically |
| **Terminal Callbacks** | Native Python `async def callback(event: dict)` passed to `Runtime` | Poll `GET /api/v1/notifications/{id}` or `/ack-status` |

---

## 2. Cookbook 1: Embedded Python Producer (`uns.Runtime` + `uns.Client`)

### Step 2.1: Initialize `Runtime` and `Client`
```python
import asyncio
from typing import Any
from uuid import uuid4

from agsignal.responses import AutonomyContextRequest, SendNotificationRequest
from notification.adapters import EmailAdapter, EmailConfig, SlackAdapter, SlackConfig
from notification.models import AutonomyMode, NotificationIntent
from notification.service import SimpleAdapterRegistry
from uns import Client, Runtime
from uns.runtime import Conflict


async def on_terminal_response(event: dict[str, Any]) -> None:
    """At-least-once callback invoked when a notification is ACKED, DISMISSED, or TIMED_OUT.

    Always deduplicate by event["id"] in downstream consumers.
    """
    print(
        f"[Callback] event_id={event['id']} notification_id={event['notification_id']} "
        f"kind={event['kind']} payload={event['payload']}"
    )


async def run_producer_example() -> None:
    # 1. Register channel adapters
    adapters = SimpleAdapterRegistry()
    adapters.register(
        SlackAdapter(SlackConfig(bot_token="xoxb-your-token", default_channel="#ops-alerts"))
    )

    # 2. Initialize durable Runtime against SQLite
    runtime = Runtime(
        "sqlite:///./uns.db",
        adapters=adapters,
        create_tables=True,
        callback=on_terminal_response,
    )

    # 3. Create a principal-scoped Client
    client = Client(runtime, principal="order-execution-service")

    # 4. Build a notification request
    agent_id = uuid4()
    request = SendNotificationRequest(
        notification_type="trading.circuit_breaker",
        intent=NotificationIntent.SAFETY,
        title="Circuit Breaker Tripped",
        message="Order velocity exceeded 500 orders/min; execution paused.",
        source="order_router",
        idempotency_key="cb-trip-2026-10-22-window-01",
        dedup_key="circuit_breaker:order_router:velocity",
        correlation_id="trace-98123",
        autonomy_context=AutonomyContextRequest(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        ),
        metadata={
            "orders_per_min": 542,
            "limit": 500,
        },
    )

    # 5. Optional: Dry-run policy simulation (no DB writes, no network effects)
    sim = await client.simulate(request)
    print("Simulated channels:", sim.resolved_channels, "mode:", sim.resolved_delivery_mode)

    # 6. Send notification (accepts into outbox + attempts immediate dispatch)
    response = await client.send(request)
    print("Status:", response.status, "ID:", response.notification_id)

    # 7. Acknowledge the notification (if require_ack=True and status==DELIVERED)
    if response.require_ack and response.status.value == "DELIVERED":
        ack = runtime.acknowledge(
            response.notification_id,
            actor="oncall-engineer",
            metadata={"action": "verified_halt"},
        )
        print("Ack status:", ack.ack_status, "at:", ack.acked_at)
        await runtime.deliver_callbacks()

    runtime.engine.dispose()
```

---

## 3. Cookbook 2: Remote HTTP Producer (`POST /api/v1/notifications`)

### Step 3.1: Sending a Signal with `Idempotency` and Inspecting `status`
When calling `POST /api/v1/notifications`, the server returns HTTP `202 Accepted` as soon as the obligation is committed to the outbox and the initial dispatch attempt finishes. **Always check the JSON `status` field** in the response body:

```python
import httpx

UNS_URL = "http://127.0.0.1:8000"
HEADERS = {"Authorization": "Bearer replace-with-your-local-test-key"}

payload = {
    "notification_type": "system.alert",
    "intent": "SAFETY",
    "title": "Database Replica Lag High",
    "message": "Read replica lag is 42s (threshold 10s).",
    "source": "db_health_monitor",
    "idempotency_key": "replica-lag-incident-20261022-01",
    "dedup_key": "db_replica_lag:primary_cluster",
    "autonomy_context": {
        "autonomy_mode": "LIVE",
        "agent_id": "11111111-2222-3333-4444-555555555555",
    },
    "metadata": {
        "lag_seconds": 42,
        "cluster": "prod-us-east-1",
    },
}

with httpx.Client(base_url=UNS_URL, headers=HEADERS, timeout=15.0) as client:
    resp = client.post("/api/v1/notifications", json=payload)
    if resp.status_code == 409:
        raise RuntimeError("Idempotency key reused with different payload!")
    if resp.status_code == 422:
        raise ValueError(f"Policy or schema validation error: {resp.json()}")
    resp.raise_for_status()

    result = resp.json()
    notif_id = result["notification_id"]
    print(f"Accepted notification {notif_id}: status={result['status']}")
```

### Step 3.2: Understanding `idempotency_key` vs. `dedup_key`

| Field | Scope | Window | Behavior on Match |
| :--- | :--- | :--- | :--- |
| `idempotency_key` | `(principal, source, idempotency_key)` | Until expired by `uns-maintain` (`idempotency_seconds`) | **Exact request retry protection:**<br>- Identical payload $\rightarrow$ returns original `notification_id` with `idempotent_replay: true`.<br>- Different payload $\rightarrow$ raises `409 Conflict`. |
| `dedup_key` | `(principal, source, dedup_key, effective_hash)` | Policy's `dedup_window_seconds` (default `300s`) | **Alert storm coalescing:**<br>- Creates a **new** `notification_id` row linked via `dedup_owner_id` to the active window leader.<br>- If the leader is already `DELIVERED`, the new row immediately settles as `DEDUPLICATED`.<br>- If the leader is still `PENDING`, the new row waits as a follower (`PENDING`) and is either satisfied (`DEDUPLICATED`) when the leader delivers or promoted (`DEDUP_OWNER_PROMOTED`) if the leader exhausts all retries. |

---

## 4. Producer Rules for Policies & Metadata

1. **Never pass adapter-routing secrets or recipient overrides in `metadata`:**
   Keys `slack_channel`, `email_to`, `pagerduty_severity`, and `websocket_user_id` are reserved and rejected with `422 PolicyOverrideError`.
2. **Respect `ACTIVE` policy authority:**
   If an `ACTIVE` policy exists for `notification_type`, omit `delivery_mode`, `require_ack`, and `priority` from your producer payload (or ensure they match the policy's resolved values), otherwise `PolicyRuntime` rejects the request with `422`.
3. **Notification is not action approval:**
   Receiving `status: "DELIVERED"` or `ack_status: "ACKED"` records that a human or operator acknowledged the notification obligation; it is **not** an automated execution-approval or capability-grant mechanism (`docs/PRODUCT.md`).

## Related Documentation

- [API Reference](../API.md)
- [Integration Modes](../sections/integration-modes.md)
- [Delivery Semantics](../sections/delivery-semantics.md)
- [TSG-04: Policy Lifecycle & Overrides](../tsg/TSG-04-POLICY-LIFECYCLE-AND-OVERRIDES.md)

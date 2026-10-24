# AI Agent & MCP Integration Guide

This guide explains how autonomous agents, MCP hosts (such as Claude Desktop, Cursor, or custom agent runners), and WebSocket consumers integrate with UNS using the **`uns-mcp` stdio server** and the **`/ws/agents/{agent_id}` WebSocket stream**.

---

## 1. Security & Capability Boundaries for Agents

1. **Read-Only by Default:** `uns-mcp` starts in read-only mode (`mode="stdio-local"`, `read_only=True`) unless explicitly launched with `--enable-writes` and host-supplied environment secrets.
2. **Host-Controlled Identity (`UNS_API_PRINCIPAL`):** Tool inputs cannot spoof or escalate caller identity. Every write action (`send_signal`, `ack_notification`, `dismiss_notification`) is attributed to the host's `UNS_API_PRINCIPAL`.
3. **Explicit Confirmation Gate on `send_signal`:**
   Even when `--enable-writes` is active, calling `send_signal` defaults to a side-effect-free simulation (`deliver=False`) unless the tool call explicitly passes all three confirmation parameters:
   - `"deliver": true`
   - `"operator_intent": "deliver"`
   - `"operator_confirmation_token": "<value matching UNS_MCP_DELIVERY_CONFIRMATION_TOKEN>"`

---

## 2. Configuring `uns-mcp` in an MCP Host

### 2.1 Read-Only Configuration (Safe Inspection & Policy Simulation)
Use read-only mode when an agent only needs to preview policies (`simulate_signal`, `get_effective_policy`) and inspect delivery/audit history (`list_deliveries`, `list_audit_events`, `list_dlq`, `get_notification_status`):

```json
{
  "mcpServers": {
    "uns-readonly": {
      "command": "/path/to/uns/.venv/bin/uns-mcp",
      "args": [],
      "env": {
        "UNS_DATABASE_URL": "sqlite:////var/lib/uns/uns.db"
      }
    }
  }
}
```

### 2.2 Write-Enabled Configuration (Sending & Acknowledging Signals)
First, ensure the SQLite database has been migrated (`uns-migrate`). Then configure the MCP host with `--enable-writes` and the three mandatory environment variables:

```json
{
  "mcpServers": {
    "uns-operator": {
      "command": "/path/to/uns/.venv/bin/uns-mcp",
      "args": ["--enable-writes"],
      "env": {
        "UNS_DATABASE_URL": "sqlite:////var/lib/uns/uns.db",
        "UNS_API_PRINCIPAL": "agent-supervisor-01",
        "UNS_MCP_DELIVERY_CONFIRMATION_TOKEN": "replace-with-confirmation-secret",
        "UNS_SLACK_BOT_TOKEN": "xoxb-your-slack-token",
        "UNS_SLACK_CHANNEL": "#agent-governance"
      }
    }
  }
}
```

> [!IMPORTANT]
> **Keep the Unified `uns` Service Running Alongside Short-Lived MCP Hosts (`F-06`):**
> While `uns-mcp --enable-writes` runs an internal recovery worker (`uns-mcp-worker`) during its stdio lifespan, terminating the stdio process stops that worker. Always run the persistent `uns` daemon against the same `UNS_DATABASE_URL` so that delayed retries, lease recovery, and acknowledgment timeout sweeps continue if the MCP host disconnects.

---

## 3. Agent Tool Workflows (`uns-mcp`)

### 3.1 Step 1: Previewing a Signal (`simulate_signal`)
Before sending a governance or safety notification, agents should preview how the active policy will route it:

```json
// Tool: simulate_signal
{
  "payload": {
    "notification_type": "agent.execution.irreversible_action",
    "intent": "GOVERNANCE",
    "title": "Database Schema Migration Requested",
    "message": "Agent plan-42 is requesting human review before applying migration 004.",
    "source": "migration_agent",
    "irreversible": true,
    "autonomy_context": {
      "autonomy_mode": "LIVE",
      "agent_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
      "plan_id": "9a1b2c3d-0000-1111-2222-333344445555"
    }
  }
}
```

### 3.2 Step 2: Sending a Signal (`send_signal` with Confirmation Gate)
To actually persist and dispatch the signal in write-enabled mode:

```json
// Tool: send_signal
{
  "payload": {
    "notification_type": "agent.execution.irreversible_action",
    "intent": "GOVERNANCE",
    "title": "Database Schema Migration Requested",
    "message": "Agent plan-42 is requesting human review before applying migration 004.",
    "source": "migration_agent",
    "idempotency_key": "plan-42-step-3-migration-004",
    "irreversible": true,
    "autonomy_context": {
      "autonomy_mode": "LIVE",
      "agent_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
      "plan_id": "9a1b2c3d-0000-1111-2222-333344445555"
    },
    "deliver": true,
    "operator_intent": "deliver",
    "operator_confirmation_token": "replace-with-confirmation-secret"
  }
}
```

**Inspecting the Result:**
```json
{
  "notification_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "DELIVERED",
  "delivered": true,
  "channels_attempted": ["SLACK"],
  "channels_succeeded": ["SLACK"],
  "channels_failed": [],
  "require_ack": true,
  "ack_status": "PENDING",
  "idempotent_replay": false
}
```

### 3.3 Step 3: Checking Status & Acknowledging (`get_notification_status` / `ack_notification`)
- To poll whether a human or operator has acknowledged the notification:
  ```json
  // Tool: get_notification_status
  {
    "notification_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }
  ```
- To acknowledge or dismiss a notification from a write-enabled operator MCP session:
  ```json
  // Tool: ack_notification
  {
    "payload": {
      "notification_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "metadata": {
        "reviewed_by": "agent-supervisor-01",
        "notes": "Verified migration script in staging"
      }
    }
  }
  ```

---

## 4. Subscribing to Real-Time Agent Notifications via WebSocket (`/ws/agents/{agent_id}`)

Agents can receive real-time notifications routed to `Channel.WEBSOCKET` (and fanout envelopes from `POST /api/v1/notifications`) by connecting to `/ws/agents/{agent_id}` on the `uns` server.

### 4.1 Python Agent WebSocket Consumer Example
```python
import asyncio
import json
import websockets

UNS_WS_URL = "ws://127.0.0.1:8000/ws/agents/2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11"
API_KEY = "replace-with-your-local-test-key"

async def listen_for_agent_signals() -> None:
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with websockets.connect(UNS_WS_URL, additional_headers=headers) as ws:
        # 1. Receive initial connection confirmation frame
        connected = json.loads(await ws.recv())
        print("Connected frame:", connected)

        # 2. Process incoming notification frames
        async for raw_msg in ws:
            envelope = json.loads(raw_msg)
            if envelope.get("type") == "notification":
                notif = envelope["notification"]
                print(
                    f"Received signal {notif['notification_id']}: "
                    f"[{notif['intent']}] {notif['title']} (replay_cursor={notif.get('replay_cursor')})"
                )

asyncio.run(listen_for_agent_signals())
```

### 4.2 Interactive ACK/DISMISS over WebSocket
Connected agents can also send JSON commands over the authenticated WebSocket connection:
- **Acknowledge a notification:**
  ```json
  {
    "type": "ack",
    "notification_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "metadata": {"source": "ws-agent"}
  }
  ```
- **Replay missed WebSocket frames since a cursor:**
  ```json
  {
    "type": "replay",
    "since_cursor": 0
  }
  ```

## Related Documentation

- [API Reference — MCP & WebSocket](../API.md)
- [TSG-05: MCP Process Lifecycle & Agent WebSocket Recovery](../tsg/TSG-05-MCP-AND-AGENT-RECOVERY.md)
- [Security Model](../SECURITY-MODEL.md)

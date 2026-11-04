# TSG-05: MCP Process Lifecycle & Agent WebSocket Recovery

## 1. Symptoms & Alerts
- Launching `uns-mcp --enable-writes` exits immediately with a parser error (`Set UNS_DATABASE_URL...`, `Write-enabled MCP requires a persistent database`, `Set UNS_API_PRINCIPAL...`, or `Set UNS_MCP_DELIVERY_CONFIRMATION_TOKEN...`).
- Calling MCP `send_signal` with `deliver=true`, `ack_notification`, or `dismiss_notification` fails with `ValueError`.
- An MCP process terminates while a retry or callback is pending, and operators need to verify recovery.
- Agent WebSocket connections to `/ws/agents/{agent_id}` fail during handshake with WebSocket close code `1008` (`WS_1008_POLICY_VIOLATION`).

---

## 2. Root Cause & Component Mechanics

### 2.1 `uns-mcp` Security & Lifecycle Model (`src/uns_mcp/`)
1. **Read-Only by Default:** Running `uns-mcp` without `--enable-writes` starts in `mode="stdio-local"` with `read_only=True`. In this mode, `simulate_signal` and read tools (`list_deliveries`, `list_dlq`, `get_notification_status`, etc.) work, while `send_signal(deliver=True)`, `ack_notification`, and `dismiss_notification` are blocked.
2. **Runtime-Bound Read Helpers (`F-07`):**
   - Both the FastMCP server tools and direct Python helpers in `uns_mcp.tools` accept `runtime_state=RuntimeState(runtime=runtime)` and read directly from that runtime's durable SQLite or PostgreSQL outbox and audit stores.
3. **Write-Enabled Requirements (`uns-mcp --enable-writes`):**
   - `UNS_DATABASE_URL` must point to a persistent SQLite file (`sqlite:////path/to/uns.db`) or PostgreSQL database (`postgresql+psycopg://...`); volatile in-memory URLs (`sqlite://` and `:memory:`) are rejected.
   - `UNS_API_PRINCIPAL` must be set to a non-empty actor identifier.
   - `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` must be set to a non-empty secret.
   - Every `send_signal` call with `deliver=true` must also supply `operator_intent="deliver"` and `operator_confirmation_token` matching `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` (verified via constant-time `hmac.compare_digest`).
4. **In-Process Recovery Worker (`uns-mcp-worker`):**
   - When `uns-mcp --enable-writes` starts its FastMCP lifespan (`src/uns_mcp/factory.py`), it spawns `asyncio.create_task(runtime.worker(), name="uns-mcp-worker")`.
   - On `SIGINT` or `SIGTERM`, `_serve()` cancels the stdio task and uses `anyio.CancelScope(shield=True)` during lifespan teardown to cancel and join the recovery worker cleanly before disposing the SQLAlchemy engine.

### 2.2 Agent WebSocket Authentication (`/ws/agents/{agent_id}`)
Defined in `src/uns/api/auth.py`:
- Query-string tokens (`?api_key=...` or `?token=...`) are **never accepted**.
- If an `Origin` header is present, it must match `UNS_ALLOWED_ORIGINS` (default `http://localhost:5173,http://127.0.0.1:5173`).
- Native clients pass `Authorization: Bearer <UNS_API_KEY>` (or `X-UNS-API-Key`).
- Browser clients pass `Sec-WebSocket-Protocol: uns.v1, bearer.<base64url_nopad(UNS_API_KEY)>`.

---

## 3. Diagnostic Commands

### Step 3.1: Verify MCP environment variables before starting `uns-mcp --enable-writes`
```sh
python3 -c '
from uns_mcp.transports.stdio import runtime_config
cfg = runtime_config(enable_writes=True)
print("MCP Write Config Valid:", cfg.mode, "principal=", cfg.operator_principal)
'
```

### Step 3.2: Check for orphaned or pending work after an MCP process exit
```sh
sqlite3 "$UNS_DB_FILE" "
  SELECT id, principal, status, attempts, cycle, lease_until, next_attempt
  FROM uns_notifications
  WHERE status = 'PENDING'
  ORDER BY next_attempt ASC;
"
```

---

## 4. Safe Remediation Steps

### Scenario A: `send_signal` with `deliver=true` raises `ValueError`
Check the exact error string:
1. **`send_signal is disabled in read-only mode`:** Launch `uns-mcp` with `--enable-writes` and the three required environment variables (`UNS_DATABASE_URL`, `UNS_API_PRINCIPAL`, `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`).
2. **`send_signal deliver=true requires operator_intent='deliver'`:** Include `"operator_intent": "deliver"` in the tool arguments.
3. **`send_signal delivery confirmation token is invalid`:** Ensure `"operator_confirmation_token"` in the tool payload matches the host's `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` environment variable.

### Scenario B: `ack_notification` or `dismiss_notification` raises `ValueError`
- **`ack_notification acked_by must match the operator principal`:** Either omit `acked_by` from `AckNotificationInput` or set it to the exact value of `UNS_API_PRINCIPAL`.

### Scenario C: WebSocket connection fails with `1008 Policy Violation`
1. **Reason `"Origin is not allowed"`:** Add your frontend/agent origin to `UNS_ALLOWED_ORIGINS` (comma-separated, e.g., `export UNS_ALLOWED_ORIGINS="https://console.example.com"`).
2. **Reason `"Authentication required"`:**
   - For Python/Node/Go clients: pass `Authorization: Bearer <UNS_API_KEY>` in the handshake headers.
   - For Browser clients: pass `["uns.v1", "bearer.<base64url-unpadded-key>"]` as the `WebSocket` subprotocols argument.

---

## 5. Operational Best Practices

> [!IMPORTANT]
> **Short-Lived Stdio MCP Sessions & Recovery Continuity:**
> `uns-mcp --enable-writes` runs `runtime.worker()` only while the `uns-mcp` stdio process is alive.
> - If `send_signal(deliver=True)` experiences a transient adapter failure on Attempt 1 (leaving `status = "PENDING"` with `next_attempt = now + 1.0`) and the MCP host immediately terminates the `uns-mcp` stdio process, the stopped `uns-mcp` process can no longer run Attempt 2.
> - **Operational Mitigation:** In production, always run the long-lived `uns` service (or a dedicated persistent worker process) attached to the same `UNS_DATABASE_URL` so that background retries, lease recovery, and timeout sweeps continue even when stdio MCP client sessions disconnect.

## Related Documentation

- [Agent & MCP Integration Guide](../user-guides/AGENT-MCP-GUIDE.md)
- [Deployment Guide](../DEPLOYMENT.md)
- [Security Model](../SECURITY-MODEL.md)

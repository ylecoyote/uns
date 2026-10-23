# UNS API

This document is the authoritative API reference for the Unified Notification Service (`uns`), covering the Python SDK (`uns.Runtime` and `uns.Client`), HTTP REST endpoints, WebSocket streaming (`/ws/agents/{agent_id}`), MCP tools (`uns-mcp`), and maintenance CLI (`uns-maintain`).

## Python

Install `uns[full]` from the local wheel or `.[full]` from source. `uns.Runtime(database_url, adapters=registry, create_tables=False)` owns persistent state; `uns.Client(runtime, principal=...)` is the canonical in-process client. The principal is trusted host identity, not an untrusted request field.

- `await client.simulate(request)`: policy resolution only, no side effects.
- `runtime.accept(request, principal=...)`: atomic acceptance, returns pending owner/follower state or a satisfied duplicate; idempotent retry retains identity.
- `await client.send(request)`: accept and attempt dispatch; pending failures recover through the worker.
- `runtime.get(id)`, `runtime.events(id)`: inspect durable state and event history.
- `runtime.acknowledge(id, actor=..., dismiss=False)`: conditional terminal response.
- `await runtime.run_once()`: recover eligible work and process timeouts without awaiting callbacks.
- `await runtime.worker()`: owned dispatch, timeout and callback loops with independent progress.
- `runtime.replay(id, actor=...)`: recover an unsatisfied exhausted obligation with a fresh cycle budget and preserved history. Raises `Conflict` (HTTP 409) for pending/satisfied successor obligations or unresolved lineage; no force bypass.
- `runtime.dead_letters()`: retained exhausted histories, including `replay_blocked_by` and `replay_block_reason` when recovery is unsafe or redundant.
- `runtime.resolve_failure(id, actor=...)`: explicitly resolve a retained failure without erasing its FAILED status or audit.

Requests use the existing `agsignal.responses.SendNotificationRequest` model. Legacy domain types remain import-compatible. The low-level `notification.sdk.NotificationSDK` and `agsignal.SignalClient` are policy/handler adapters. Their no-handler result is PENDING, not a successful send.

### `uns.Runtime` Constructor & Methods

```python
from uns import Client, Runtime
from uns.runtime import Conflict
```

| Signature | Description | Raises |
| :--- | :--- | :--- |
| `Runtime(database_url: str, *, adapters: SimpleAdapterRegistry \| None = None, create_tables: bool = False, max_attempts: int = 3, retry_seconds: float = 1, clock: Callable[[], float] = time.time, callback: Callable[[dict[str, Any]], Awaitable[None]] \| None = None)` | Initialize durable outbox runtime, migrate/validate tables if `create_tables=True`, and bind `PolicyRuntime`. | `ValueError` if `max_attempts < 1` |
| `runtime.accept(request: SendNotificationRequest, *, principal: str) -> SendNotificationResponse` | Atomically resolve ACTIVE policy, check idempotency key (`principal + source + idempotency_key`), evaluate deduplication window (`uns_dedup`), and persist `uns_notifications` + `ACCEPTED` event. | `ValueError` (missing principal or disallowed policy override), `Conflict` (idempotency key reused with different payload) |
| `await runtime.send(request: SendNotificationRequest, *, principal: str) -> SendNotificationResponse` | Call `accept(...)` and, if not an idempotent replay, immediately execute `await runtime.dispatch(notification_id)`. | `ValueError`, `Conflict` |
| `await runtime.dispatch(notification_id: UUID \| str) -> bool` | Acquire a 60-second fenced lease (`lease_token`, `lease_until`) on a `PENDING` leader row, invoke adapters via `DeliveryService` (recording `CHANNEL_ATTEMPT_STARTED` and `CHANNEL_ATTEMPT_RESULT` events), and settle followers (`DEDUP_SATISFIED` on success or `OBLIGATION_HANDED_OFF` / `DEDUP_OWNER_PROMOTED` on terminal exhaustion). | Returns `False` if not claimable or lease lost |
| `runtime.acknowledge(notification_id: UUID \| str, *, actor: str, dismiss: bool = False, metadata: dict[str, Any] \| None = None) -> AckResponse` | Transition `ack_status` from `PENDING` to `ACKED` (or `DISMISSED` when `dismiss=True`) before `deadline`, persist `AckAuditRecord`, and enqueue terminal callback event. | `ValueError` (missing actor), `KeyError` (not found), `Conflict` (deadline elapsed, not awaiting ack, or already settled by a different actor) |
| `runtime.expire(*, now: float \| None = None) -> None` | Sweep up to 100 notifications with `ack_status == "PENDING"` and `deadline <= now` to `TIMED_OUT` with `actor="uns-timeout-worker"` and `{"escalation_required": True}`. | None (conflicts suppressed) |
| `runtime.replay(notification_id: UUID \| str, *, actor: str) -> None` | Reset an exhausted dead-letter notification (`dead_letter == True`) to `status="PENDING"`, increment `cycle`, reset `cycle_attempts=0`, reassign any failed successor lineage, and record `REPLAY_REQUESTED`. | `ValueError` (missing actor), `Conflict` (row is not `dead_letter=True`, or blocked by a pending/satisfied successor or unresolved lineage) |
| `runtime.resolve_failure(notification_id: UUID, *, actor: str) -> bool` | Clear `dead_letter=False` on a dead-lettered notification after external remediation without erasing `FAILED` status or audit, and record `FAILURE_RESOLVED`. | `ValueError` (missing actor) |
| `runtime.dead_letters() -> list[dict[str, Any]]` | Return all rows in `uns_notifications` where `dead_letter == True`, including `replay_blocked_by` and `replay_block_reason` when recovery is unsafe or redundant. | None |
| `await runtime.deliver_callbacks() -> None` | Claim up to 100 events ordered by `(callback_until, at, id)` with `callback_pending == True` and `callback_attempts < 3` under a 30-second lease, invoke `self.callback(event)` with a 10s timeout, and apply `2 ** attempts` backoff on error. | None |

### `SendNotificationRequest` Schema (`agsignal.responses`)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `notification_type` | `str` | **Yes** | — | Dot-separated notification identifier (e.g., `"system.alert"`). |
| `intent` | `NotificationIntent` | **Yes** | — | `"SAFETY"`, `"GOVERNANCE"`, `"OPERATIONAL"`, or `"INFORMATIONAL"`. |
| `title` | `str` | **Yes** | — | Human-readable summary (1–200 chars). |
| `message` | `str` | **Yes** | — | Full notification body. |
| `source` | `str` | **Yes** | — | Originating subsystem name. Scopes idempotency and deduplication keys. |
| `autonomy_context` | `AutonomyContextRequest` | **Yes** | — | Contains `autonomy_mode` (`"LIVE"`, `"SHADOW"`, `"PREVIEW"`, `"SUPERVISED"`, `"AUTONOMOUS"`), `agent_id` (`UUID`), optional `plan_id`, `step_id`, `run_id`. |
| `irreversible` | `bool` | No | `False` | Whether the triggering agent action is irreversible. |
| `idempotency_key` | `str \| None` | No | `None` | Producer retry key (`1..255` chars). Scoped by `(principal, source, idempotency_key)`. |
| `dedup_key` | `str \| None` | No | `None` | Explicit coalescing key. Defaults to content-derived hash if omitted. |
| `correlation_id` | `str \| None` | No | `None` | Cross-service trace/correlation identifier. |
| `delivery_mode` | `DeliveryMode \| None` | No | `None` | Producer override (`"GUARANTEED"` or `"BEST_EFFORT"`). Rejected with `422` if it contradicts an `ACTIVE` policy. |
| `require_ack` | `bool \| None` | No | `None` | Producer override for acknowledgment requirement. Rejected with `422` if it contradicts an `ACTIVE` policy. |
| `priority` | `Priority \| None` | No | `None` | `"CRITICAL"`, `"HIGH"`, `"NORMAL"`, or `"LOW"`. Rejected with `422` if it contradicts an `ACTIVE` policy. |
| `metadata` | `dict[str, Any]` | No | `{}` | Arbitrary context dictionary. Protected adapter keys (`email_to`, `slack_channel`, `pagerduty_routing_key`, `uns_resolution`, etc.) are rejected at intake. |

---

## HTTP

`uns.app:app` and `agsignal.app:app` mount the same service. Configure `UNS_API_KEY` and `UNS_API_PRINCIPAL`; send `Authorization: Bearer ...` for API reads and mutations, readiness, metrics and runtime inspection. Existing `AGSIGNAL_*` aliases remain usable.

| Method and path | Meaning |
|---|---|
| POST `/api/v1/notifications` | Accept and attempt delivery; 202 is request acceptance, inspect body status |
| POST `/api/v1/notifications/simulate` | Resolve without effects |
| GET `/api/v1/notifications/{id}/delivery` | Existing delivery audit history |
| GET `/api/v1/notifications/{id}` | Notification and response status |
| POST `/api/v1/notifications/{id}/ack` or `/dismiss` | Authenticated human response |
| POST `/api/v1/policies/reload` | Validate and atomically persist a notification-policy snapshot before swapping registry |
| GET `/api/v1/runtime/notifications/{id}` | Full state, policy provenance and recovery events |
| GET `/api/v1/runtime/dead-letters` | Durable exhausted failures |
| POST `/api/v1/runtime/notifications/{id}/replay` | Attributable replay request |
| GET `/ui/deliveries`, `/ui/audit`, `/ui/policies/effective` | Read-first console models |
| GET `/health`, `/healthz`, `/ready`, `/readyz`, `/metrics` | Process and operator probes |

Idempotency scope is authenticated principal plus source plus key. Same content replays the original notification; different content is a conflict (409). Invalid delivery configuration is 422. Storage failures do not return a successful unrecorded mutation. An ACK body cannot claim another principal. Same-actor replay returns the original result; a different actor conflicts. Only minimal liveness endpoints remain public by default.

### Authentication Headers

All HTTP endpoints except `GET /health` and `GET /healthz` require one of the following headers matching `UNS_API_KEY`:
- `Authorization: Bearer <UNS_API_KEY>` (recommended)
- `X-UNS-API-Key: <UNS_API_KEY>`
- `X-AGSignal-API-Key: <UNS_API_KEY>`

| Status Code | Error Code / Detail | Cause |
| :--- | :--- | :--- |
| `401 Unauthorized` | `unauthorized` | Missing or invalid API key. |
| `403 Forbidden` | `principal_override_forbidden` | `acked_by` or `dismissed_by` in request body does not match `UNS_API_PRINCIPAL`. |
| `404 Not Found` | `not_found` / `"Notification not found"` | Notification ID or DLQ entry ID does not exist. |
| `409 Conflict` | `"Idempotency key reused..."` / `"Obligation already satisfied..."` | Idempotency key payload mismatch, ACK after deadline/by different actor, or replay blocked by non-dead-letter status or active/satisfied successor lineage. |
| `422 Unprocessable Entity` | `validation_error` | Schema validation failure, disallowed producer override against ACTIVE policy, or forbidden adapter-control metadata key. |
| `503 Service Unavailable` | `write_auth_not_configured` | `UNS_API_KEY` is not set on the server. |

### Endpoint Details & Examples

#### 1. `POST /api/v1/notifications` (Status `202 Accepted`)
Accepts a `SendNotificationRequest`, commits the outbox row, and attempts immediate dispatch.
```json
{
  "notification_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
  "status": "DELIVERED",
  "channels_attempted": ["SLACK"],
  "channels_succeeded": ["SLACK"],
  "channels_failed": [],
  "require_ack": true,
  "ack_status": "PENDING",
  "idempotent_replay": false,
  "created_at": "2026-10-22T21:00:00Z",
  "message": "delivered"
}
```
> **Note:** Always inspect the response body `status` (`"DELIVERED"`, `"PENDING"`, `"FAILED"`, `"DEDUPLICATED"`). HTTP `202` means the notification obligation was durably accepted into the outbox, even if the first delivery attempt failed (`status: "PENDING"` or `"FAILED"`).

#### 2. `POST /api/v1/notifications/{id}/ack` and `/dismiss` (Status `200 OK`)
*(Also mounted at `/v1/notifications/{id}/ack` and `/v1/notifications/{id}/dismiss`)*
```json
// Request Body (optional; acked_by/dismissed_by must match UNS_API_PRINCIPAL if provided)
{
  "metadata": {
    "ticket_id": "INC-4092",
    "note": "Investigating margin spike"
  }
}
```
```json
// Response (200 OK)
{
  "notification_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
  "ack_status": "ACKED",
  "acked_by": "local-operator",
  "acked_at": "2026-10-22T21:03:12.410291Z",
  "metadata": {
    "ticket_id": "INC-4092",
    "note": "Investigating margin spike"
  }
}
```

#### 3. `GET /api/v1/runtime/notifications/{id}` (Status `200 OK`)
Returns the complete raw `uns_notifications` row plus its ordered `uns_events` recovery timeline (`ACCEPTED`, `ATTEMPT_STARTED`, `CHANNEL_ATTEMPT_STARTED`, `CHANNEL_ATTEMPT_RESULT`, `DELIVERY_RESULT`, `LEASE_LOST`, `OBLIGATION_HANDED_OFF`, `DEDUP_*`, `ACKED`/`DISMISSED`/`TIMED_OUT`, `REPLAY_REQUESTED`, `FAILURE_RESOLVED`).

#### 4. `GET /api/v1/runtime/dead-letters` & `POST /api/v1/runtime/notifications/{id}/replay`
- `GET /api/v1/runtime/dead-letters`: Lists all exhausted `GUARANTEED` notifications (`dead_letter = true`), including `replay_blocked_by` and `replay_block_reason` when a successor obligation is pending/satisfied or lineage is unresolved.
- `POST /api/v1/runtime/notifications/{id}/replay`: Starts a new delivery cycle (`cycle + 1`, `cycle_attempts = 0`, `status = "PENDING"`). Raises `409 Conflict` if `replay_blocked_by` is present.
- `DELETE /api/v1/dlq/{entry_id}`: Resolves/clears `dead_letter = false` without re-sending (`FAILURE_RESOLVED`).

#### 5. `POST /api/v1/policies/reload` (Status `200 OK`)
```json
// Request Body
{
  "policy_dir": "examples/policies/mip-uns"
}
```
Validates all YAML policy files in `policy_dir`, enforces `PolicyDelta` transition guards against the current durable snapshot (`409` on invalid promotion/lifecycle transition, `422` on schema error, `404` on missing directory), and atomically persists the new revision.

#### 6. Console Read-Model Endpoints (`GET /ui/*`)
All `/ui/*` endpoints are strictly read-only (`INV-UI-001`):
- `GET /ui/deliveries`: Cursor-paginated delivery summaries with filters (`status`, `intent`, `delivery_mode`, `agent_id`, `autonomy_mode`, `notification_type`, `channel`, `start_time`, `end_time`).
- `GET /ui/deliveries/{notification_id}`: Full delivery timeline and policy resolution steps for one notification.
- `GET /ui/policies/effective`: Query effective policy resolution (`?notification_type=...&intent=...&autonomy_mode=...&irreversible=false`).
- `GET /ui/invariants` & `GET /ui/invariants/summary`: System invariant registry and pass/fail summary counts.
- `GET /ui/audit`: Cursor-paginated compliance audit stream with filters (`event_type`, `notification_id`, `agent_id`, `autonomy_mode`, `correlation_id`).

---

## MCP

`uns-mcp` retains existing stdio tools: simulate_signal, send_signal, get_delivery_status, ack_notification, dismiss_notification, get_notification_status, get_ack_status, list_deliveries, list_audit_events, get_effective_policy, list_invariants, get_invariants_summary, list_dlq, get_channel_health, health, ready. The source registry in `agsignal_mcp.factory.AGSIGNAL_MCP_TOOL_NAMES` is authoritative. Embedded direct read helpers accept `runtime_state=RuntimeState(runtime=runtime)` and use that runtime's durable stores. Omitted dependencies bind to the runtime; explicit injected audit/read adapters remain supported. Legacy helper calls without a runtime retain fixture behavior.

The factory and CLI default to read-only. `uns-mcp --enable-writes` requires a persistent database, `UNS_API_PRINCIPAL` and `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`; it owns recovery for the process lifetime. Embedded hosts configure `MCPRuntimeConfig` explicitly. Secrets are supplied through host configuration, not command-line flags. `send_signal` does not label acceptance as delivery. No `check_policy`, `request_approval`, or action-resume tool is implemented.

### Complete MCP Tool Reference (`AGSIGNAL_MCP_TOOL_NAMES`)

| Tool Name | Mode | Input Parameters | Description |
| :--- | :--- | :--- | :--- |
| `simulate_signal` | Read-Only / Write | `payload: SendSignalInput` | Preview routing and policy resolution without side effects (`delivered: false`). |
| `send_signal` | Write (`deliver=true`) / Read-Only (`deliver=false`) | `payload: SendSignalInput` | When `deliver=false`, delegates to `simulate_signal`. When `deliver=true`, requires `--enable-writes`, `operator_intent="deliver"`, and `operator_confirmation_token` matching `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`. |
| `ack_notification` | Write | `payload: AckNotificationInput` (`notification_id`, optional `acked_by`, `metadata`) | Acknowledge a pending notification as `UNS_API_PRINCIPAL`. |
| `dismiss_notification` | Write | `payload: AckNotificationInput` (`notification_id`, optional `acked_by`, `metadata`) | Dismiss a pending notification as `UNS_API_PRINCIPAL`. |
| `get_delivery_status` | Read-Only / Write | `notification_id: str` | Return persisted delivery audit records (`found`, `delivery_status`, `channels_attempted`, `audits`). |
| `get_notification_status` | Read-Only / Write | `notification_id: str` | Return durable notification status (`found`, `status`, `ack_status`). |
| `get_ack_status` | Read-Only / Write | `notification_id: str` | Return current `ack_status` (`PENDING`, `ACKED`, `DISMISSED`, `TIMED_OUT`, or `null`). |
| `list_deliveries` | Read-Only / Write | `limit: int = 25` | Return recent delivery read-model entries. |
| `list_audit_events` | Read-Only / Write | `limit: int = 25` | Return recent audit read-model entries. |
| `get_effective_policy` | Read-Only / Write | `notification_type: str`, `intent: str`, `autonomy_mode: str`, `irreversible: bool = False` | Resolve effective policy and resolution provenance for a signal shape. |
| `list_invariants` | Read-Only / Write | `limit: int = 25` | List registered system invariants from `invariants.yml`. |
| `get_invariants_summary` | Read-Only / Write | *(None)* | Return aggregate invariant counts. |
| `list_dlq` | Read-Only / Write | *(None)* | Return durable dead-letter depth and items (`{"depth": ..., "items": [...]}`). |
| `get_channel_health` | Read-Only / Write | *(None)* | Return runtime channel health summary. |
| `health` | Read-Only / Write | *(None)* | Return MCP process liveness (`{"status": "alive", "service": "agsignal-mcp"}`). |
| `ready` | Read-Only / Write | *(None)* | Return MCP readiness and mode (`mode`, `read_only`). |

---

## Policy authority and compatibility

Canonical intake locks the ACTIVE revision in its acceptance transaction; steady-state simulation and inspection read revision plus immutable snapshot in a single SELECT without a write lock. Producer overrides that differ from resolved ACTIVE policy are rejected, including configured intent. Adapter-control metadata cannot bypass this boundary. No producer-level administrative exception exists. Direct low-level handler/adapter APIs remain trusted integration code, not a substitute for the protected intake API.

---

## WebSocket authentication

Authenticate before connecting to `/ws/agents/{agent_id}`. Native clients use a Bearer header. Browser clients offer `agsignal.v1` and `bearer.<base64url(UTF8(key))>` subprotocols; the selected protocol is only `agsignal.v1`. Query-string credentials are rejected. ACK/DISMISS messages use the verified principal and durable Runtime.

### WebSocket Handshake Examples

- **Non-Browser / Python Client:**
  ```python
  import websockets

  async with websockets.connect(
      f"ws://127.0.0.1:8000/ws/agents/{agent_id}",
      additional_headers={"Authorization": f"Bearer {api_key}"},
  ) as ws:
      frame = await ws.recv()
  ```
- **Browser Client (Subprotocol Authentication):**
  ```typescript
  const encodedKey = btoa(apiKey).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const ws = new WebSocket(`wss://uns.example.com/ws/agents/${agentId}`, [
    "agsignal.v1",
    `bearer.${encodedKey}`,
  ]);
  ```

---

## Maintenance CLI

`uns-maintain` is a local administrative command, not an HTTP endpoint. It defaults to dry-run and requires explicit cutoff/horizon. Apply requires an operator, protects unsettled obligations, and can export verified archives before pruning. See [deployment](DEPLOYMENT.md) for continuation-cursor semantics and archive failure behavior.

| Flag | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--database-url` | **Yes** (or `UNS_DATABASE_URL`) | `UNS_DATABASE_URL` | SQLite database URL (`sqlite:///path/to/uns.db`). |
| `--cutoff` | **Yes** | — | ISO-8601 timestamp with explicit timezone (e.g., `2026-10-01T00:00:00Z`). |
| `--idempotency-seconds` | **Yes** | — | Minimum positive idempotency preservation window in seconds. Effective cutoff is `min(cutoff, now - idempotency_seconds)`. |
| `--batch-size` | No | `100` | Row budget per invocation (`1..1000`). Includes event/audit rows when `--archive` is used. |
| `--apply` | No | `False` | Commit deletions and `RETENTION_APPLIED` receipt inside `BEGIN IMMEDIATE`. Omit for dry-run preview. |
| `--operator` | **Yes** (when `--apply`) | `None` | Non-empty operator attribution recorded in the retention receipt and archive file. |
| `--after-id` | No | `None` | Resume scan after notification UUID from a prior batch's `next_after_id`. |
| `--archive` | No | `None` | Path to a **new** JSON archive file in an existing trusted directory (created with `O_CREAT \| O_EXCL`, mode `0600`). |

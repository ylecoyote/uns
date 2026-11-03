# UNS API

This document is the authoritative API reference for the Unified Notification Service (`uns`), covering the Python SDK (`uns.Runtime` and `uns.Client`), HTTP REST endpoints, WebSocket streaming (`/ws/agents/{agent_id}`), MCP tools (`uns-mcp`), and maintenance CLI (`uns-maintain`).

## Python

Install `uns[full]` from the local wheel or `.[full]` from source. `uns.Runtime(database_url, adapters=registry, create_tables=False)` owns persistent state; `uns.Client(runtime, principal=...)` is the canonical in-process client. The principal is trusted host identity, not an untrusted request field.

- `await client.simulate(request)`: policy resolution only, no side effects.
- `runtime.accept(request, principal=...)`: atomic acceptance, returns pending owner/follower state or a satisfied duplicate; idempotent retry retains identity.
- `await client.send(request)`: accept and attempt dispatch; pending failures recover through the worker.
- `runtime.get(id)`, `runtime.events(id)`: inspect durable state, the [canonical obligation response projection](#canonical-obligation-response-projection), and event history.
- `runtime.acknowledge(id, actor=..., dismiss=False)`: conditional terminal response.
- `await runtime.run_once()`: recover eligible work and process timeouts without awaiting callbacks.
- `await runtime.worker()`: owned dispatch, timeout and callback loops with independent progress.
- `runtime.replay(id, actor=...)`: recover an unsatisfied exhausted obligation with a fresh cycle budget and preserved history. Raises `Conflict` (HTTP 409) for pending/satisfied successor obligations or unresolved lineage; no force bypass.
- `runtime.dead_letters()`: retained exhausted histories, including `replay_blocked_by` and `replay_block_reason` when recovery is unsafe or redundant.
- `runtime.resolve_failure(id, actor=...)`: explicitly resolve a retained failure without erasing its FAILED status or audit.

Requests use the existing `uns.responses.SendNotificationRequest` model. Legacy domain types remain import-compatible. The low-level `notification.sdk.NotificationSDK` and `uns.SignalClient` are policy/handler adapters. Their no-handler result is PENDING, not a successful send.

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
| `runtime.resolve_pagerduty_target(dedup_key: str) -> UUID \| None` | Resolve a PagerDuty incident `dedup_key` (`uns-<dedup_key>` or `uns-<notification_id>`) back to the canonical owner notification ID. | None |
| `await runtime.sync_pagerduty_incident(notification_id: UUID \| str, *, resolve: bool = False) -> DeliveryResult \| None` | Best-effort outbound PagerDuty Events API v2 `acknowledge_incident` / `resolve_incident` synchronization when a PagerDuty-delivered notification is acknowledged or dismissed via HTTP, WebSocket, or Slack, recording a `PAGERDUTY_OUTBOUND_SYNC` runtime event. | None |
| `await runtime.deliver_callbacks() -> None` | Claim up to 100 events ordered by `(callback_until, at, id)` with `callback_pending == True` and `callback_attempts < 3` under a 30-second lease, invoke `self.callback(event)` with a 10s timeout, and apply `2 ** attempts` backoff on error. | None |

### Canonical obligation response projection

Deduplicated notifications and failed predecessors can share a response obligation with another notification. The same projection is available from Python `runtime.get(id)` and `runtime.response(id)`, Python acceptance/send responses, HTTP submission and status/ACK-status reads, and runtime-bound MCP `send_signal`, `get_notification_status`, and `get_ack_status`. UUIDs are serialized as strings in JSON.

| Field | Type | Meaning |
|---|---|---|
| `ack_status` | `PENDING`, `ACKED`, `DISMISSED`, `TIMED_OUT`, or `null` | The requested notification's own stored response state. This historical value is never replaced by an owner's response. |
| `obligation_owner_id` | UUID or `null` | The terminal canonical owner after following the complete owner/successor lineage. Equals the requested ID for an independent owner; null if resolution fails. |
| `effective_ack_status` | ACK status or `null` | The resolved owner's current response state. Null can mean no response is tracked yet, no ACK is required, or owner resolution failed; inspect `obligation_resolution_status`. |
| `ack_inherited` | boolean | True when a successfully resolved owner differs from the requested notification. False for a self-owned or unresolved obligation. |
| `obligation_resolution_status` | `RESOLVED`, `UNRESOLVED`, or `null` | Whether the complete lineage resolved. Null is the additive schema default for legacy or missing-record responses. |
| `obligation_resolution_error` | `CYCLE`, `MISSING_TARGET`, `GROUP_MISMATCH`, or `null` | Why lineage could not be resolved. Null when resolution succeeds. |

Poll the original notification ID and use `effective_ack_status` only when resolution is `RESOLVED`. A follower can retain `ack_status: null` while its owner is `ACKED`; a failed predecessor can retain delivery status `FAILED` while the successor has satisfied the response obligation. Reads do not rewrite historical status or audit records. ACK/DISMISS mutations target the resolved `obligation_owner_id`; they do not automatically redirect a follower ID, and the normal actor/state/deadline checks still apply.

For example, an HTTP ACK-status read or runtime-bound MCP ACK-status tool can return:

```json
{
  "notification_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
  "ack_status": null,
  "obligation_owner_id": "3d6a0c5d-7c4f-4e2b-ad23-5b9f1d9f8c22",
  "effective_ack_status": "ACKED",
  "ack_inherited": true,
  "obligation_resolution_status": "RESOLVED",
  "obligation_resolution_error": null
}
```

When lineage is `UNRESOLVED`, both `obligation_owner_id` and `effective_ack_status` are null and `ack_inherited` is false, even if an intermediate row contains an ACK. Inspect the error and retained history; an intermediate row is never presented as the canonical owner. Missing-ID MCP reads keep their existing minimal shapes (`found: false` for notification status, or `ack_status: null` for ACK status). The legacy MCP ACK helper without a runtime keeps its two-field response and does not infer owner state.

### `SendNotificationRequest` Schema (`uns.responses`)

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

`uns.app:app` and `uns.app:app` mount the same service. Configure an operator or scoped credential from the matrix below; send `Authorization: Bearer ...` for protected API requests. Existing `UNS_*` aliases remain usable.

| Method and path | Meaning |
|---|---|
| POST `/api/v1/notifications` | Accept and attempt delivery; 202 is request acceptance, inspect body status |
| POST `/api/v1/notifications/simulate` | Resolve without effects |
| GET `/api/v1/notifications/{id}/delivery` | Existing delivery audit history |
| GET `/api/v1/notifications/{id}` | Notification and response status |
| GET `/api/v1/notifications/{id}/ack-status` | Stored and effective response state with canonical owner resolution |
| POST `/api/v1/notifications/{id}/ack` or `/dismiss` | Authenticated actor response to the canonical owner |
| POST `/api/v1/webhooks/slack` | Inbound signed Slack Block Kit interactivity webhook (`X-Slack-Signature` + `X-Slack-Request-Timestamp` verification) |
| POST `/api/v1/webhooks/pagerduty` | Inbound signed PagerDuty v3 webhook (`X-PagerDuty-Signature` verification) |
| POST `/api/v1/policies/reload` | Validate and atomically persist a notification-policy snapshot before swapping registry |
| GET `/api/v1/runtime/notifications/{id}` | Full state, policy provenance and recovery events |
| GET `/api/v1/runtime/dead-letters` | Durable exhausted failures |
| POST `/api/v1/runtime/notifications/{id}/replay` | Attributable replay request |
| GET `/ui/deliveries`, `/ui/audit`, `/ui/policies/effective` | Read-first console models |
| GET `/health`, `/healthz`, `/ready`, `/readyz`, `/metrics` | Process and operator probes |

Idempotency scope is authenticated principal plus source plus key. Same content replays the original notification; different content is a conflict (409). Invalid delivery configuration is 422. Storage failures do not return a successful unrecorded mutation. An ACK body cannot claim another principal. Same-actor replay returns the original result; a different actor conflicts. Only minimal liveness endpoints remain public by default.

### Authentication Headers

By default, all HTTP endpoints except `GET /health` and `GET /healthz` require an authenticated credential with the capability required by the endpoint. Supply it through one of these headers:

- `Authorization: Bearer <credential>` (recommended)
- `X-UNS-API-Key: <credential>`
- `X-UNS-API-Key: <credential>`

| Configured credential | Capabilities | Principal configuration |
|---|---|---|
| `UNS_API_KEY` | All reads (including `/metrics`), producer operations, responses, and administration | `UNS_API_PRINCIPAL` |
| `UNS_PRODUCER_API_KEY` | Send, simulate, and observer-protected reads; no ACK/DISMISS, `/metrics`, or administration | `UNS_PRODUCER_API_PRINCIPAL` |
| `UNS_RESPONDER_API_KEY` | ACK/DISMISS and observer-protected reads; no send, `/metrics`, or administration | `UNS_RESPONDER_API_PRINCIPAL` |
| `UNS_OBSERVER_API_KEY` | Observer-protected reads only, including Console, readiness, and runtime inspection; no `/metrics` | `UNS_OBSERVER_API_PRINCIPAL` |

Policy reload, DLQ resolution/replay, and `/metrics` require operator authority. These are capability scopes, not per-producer or tenant data isolation: an observer-capable credential can read the instance's records through observer-protected endpoints. Use distinct key values for distinct roles; reusing a value combines its configured capabilities. The verified credential's principal supplies response attribution. The optional legacy anonymous-read mode applies only to selected HTTP GET/HEAD reads; it never grants mutations, WebSockets, readiness, metrics, or runtime inspection. See [Security Model](SECURITY-MODEL.md).

| Status Code | Error Code / Detail | Cause |
| :--- | :--- | :--- |
| `401 Unauthorized` | `unauthorized` | Missing or invalid API key. |
| `403 Forbidden` | `insufficient_scope` | The authenticated credential lacks the endpoint's required capability. |
| `403 Forbidden` | `principal_override_forbidden` | `acked_by` or `dismissed_by` does not match the authenticated credential's principal. |
| `404 Not Found` | `not_found` / `"Notification not found"` | Notification ID or DLQ entry ID does not exist. |
| `409 Conflict` | `"Idempotency key reused..."` / `"Obligation already satisfied..."` | Idempotency key payload mismatch, ACK after deadline/by different actor, or replay blocked by non-dead-letter status or active/satisfied successor lineage. |
| `422 Unprocessable Entity` | `validation_error` | Schema validation failure, disallowed producer override against ACTIVE policy, or forbidden adapter-control metadata key. |
| `503 Service Unavailable` | `write_auth_not_configured` | No API credential is configured on the server. |

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
  "obligation_owner_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
  "effective_ack_status": "PENDING",
  "ack_inherited": false,
  "obligation_resolution_status": "RESOLVED",
  "obligation_resolution_error": null,
  "idempotent_replay": false,
  "created_at": "2026-10-22T21:00:00Z",
  "message": "delivered"
}
```
> **Note:** Always inspect the response body `status` (`"DELIVERED"`, `"PENDING"`, `"FAILED"`, `"DEDUPLICATED"`). HTTP `202` means the notification obligation was durably accepted into the outbox, even if the first delivery attempt failed (`status: "PENDING"` or `"FAILED"`).

#### 2. `POST /api/v1/notifications/{id}/ack` and `/dismiss` (Status `200 OK`)
*(Also mounted at `/v1/notifications/{id}/ack` and `/v1/notifications/{id}/dismiss`)*
```json
// Request Body (optional; acked_by/dismissed_by must match the credential's principal if provided)
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

#### 5. `POST /api/v1/policies/reload` & Governed Policy Promotion (`POST /api/v1/policies/proposals*`)
```json
// POST /api/v1/policies/reload Request Body
{
  "policy_dir": "examples/policies/mip-uns"
}
```
Validates all YAML policy files in `policy_dir`, enforces `PolicyDelta` transition guards against the current durable snapshot (`409` on invalid promotion/lifecycle transition, `422` on schema error, `404` on missing directory), and atomically persists the new revision.

In addition, UNS `v0.5.0+` exposes governed policy delta proposal, shadow evaluation inspection, and promotion endpoints:
- `GET /api/v1/policies/proposals` & `GET /ui/policies/proposals`: Lists durable `PolicyDelta` proposals (`?notification_type=...&status=...`) paired with `ShadowEvaluationSummaryItem` (`sample_count`, `matching_count`, `accuracy_rate`, `threshold`, `min_samples`, `meets_threshold`), guard check results (`BOUNDS`, `CONFLICT`, `INVARIANTS`), baseline hash drift state (`baseline_matches_current`), and promotion eligibility (`can_approve_to_draft`).
- `GET /api/v1/policies/proposals/{delta_id}` & `GET /ui/policies/proposals/{delta_id}`: Returns a single proposal with its recent `shadow_samples` (`ShadowEvaluationSampleItem`) and `transitions` (`PolicyTransitionItem`).
- `POST /api/v1/policies/proposals` (`admin` scope): Creates a `PROPOSED` (or immediately `SHADOW` when `start_shadow: true`) `PolicyDelta` against the current active/latest policy for `notification_type`, validating allow-listed field paths (`ALLOWED_POLICY_FIELD_PATHS`) and executing `PolicyChangeProposalService.evaluate_guards()`.
- `POST /api/v1/policies/proposals/{delta_id}/shadow` (`admin` scope): Transitions a `PROPOSED` delta into `SHADOW` so `ShadowPolicyEvaluator` evaluates it asynchronously against live intake.
- `POST /api/v1/policies/proposals/{delta_id}/approve` (`admin` scope): Verifies guard stages, baseline hash consistency (`409 policy_baseline_drift` on mismatch), and shadow sample/accuracy thresholds (`409 policy_promotion_conflict` if unmet), transitions the delta to `APPROVED`, and persists a `DRAFT` policy revision in `notification_policy_revisions`.
- `POST /api/v1/policies/proposals/{delta_id}/activate` & `POST /api/v1/policies/revisions/{policy_id}/activate` (`admin` scope): Promotes a `DRAFT` revision to `ACTIVE` (retiring prior `ACTIVE`/`PREVIEW` revisions and broadcasting a cross-process policy reload notification) and marks the corresponding `APPROVED` delta `APPLIED`.
- `POST /api/v1/policies/proposals/{delta_id}/reject` (`admin` scope): Transitions a `PROPOSED`, `SHADOW`, or `APPROVED` delta to `REJECTED` with operator attribution and audit trail.

#### 6. Console Read-Model Endpoints (`GET /ui/*`)
All `/ui/*` endpoints are strictly read-only (`INV-UI-001`):
- `GET /ui/deliveries`: Cursor-paginated delivery summaries with filters (`status`, `intent`, `delivery_mode`, `agent_id`, `autonomy_mode`, `notification_type`, `channel`, `start_time`, `end_time`).
- `GET /ui/deliveries/{notification_id}`: Full delivery timeline and policy resolution steps for one notification.
- `GET /ui/policies/effective`: Query effective policy resolution (`?notification_type=...&intent=...&autonomy_mode=...&irreversible=false`).
- `GET /ui/policies/active` & `GET /ui/policies/revisions`: Active policy catalog and revision history (`ACTIVE`, `PREVIEW`, `DRAFT`, `RETIRED`).
- `GET /ui/policies/proposals` & `GET /ui/policies/proposals/{delta_id}`: Governed `PolicyDelta` proposals, shadow evaluation aggregates, recent shadow samples, guard checks, and transition history.
- `GET /ui/invariants` & `GET /ui/invariants/summary`: System invariant registry and pass/fail summary counts.
- `GET /ui/audit`: Cursor-paginated compliance audit stream with filters (`event_type`, `notification_id`, `agent_id`, `autonomy_mode`, `correlation_id`).

#### 7. Inbound Signed Provider Webhooks (`POST /api/v1/webhooks/slack` & `POST /api/v1/webhooks/pagerduty`)
- `POST /api/v1/webhooks/slack`: Authenticates Slack Block Kit interactivity callbacks (`block_actions` and `url_verification`) using `UNS_SLACK_SIGNING_SECRET`, `X-Slack-Request-Timestamp` (`±300s` replay guard), and `X-Slack-Signature` (`v0=<hmac_sha256>`). Clicking `Acknowledge` (`ack_<id>`) or `Dismiss` (`dismiss_<id>`) resolves follower lineage to `obligation_owner_id`, transitions the notification as actor `slack:<team_id>:<user_id>`, triggers best-effort outbound PagerDuty synchronization, and returns an in-place Block Kit message update (`replace_original: true`). Fails closed with `503 slack_webhook_not_configured` when `UNS_SLACK_SIGNING_SECRET` is unset.
- `POST /api/v1/webhooks/pagerduty`: Authenticates PagerDuty v3 Generic Webhook subscriptions (`incident.acknowledged` and `incident.resolved`) using `UNS_PAGERDUTY_WEBHOOK_SECRET` and `X-PagerDuty-Signature` (`v1=<hmac_sha256>`, supporting comma-separated rotation signatures). Resolves `uns-<dedup_key>` / `uns-<notification_id>` to the canonical owner notification and settles `PENDING` obligations as `pagerduty:<agent_id>` (idempotently returning `already_settled: true` when already acknowledged/dismissed). Fails closed with `503 pagerduty_webhook_not_configured` when `UNS_PAGERDUTY_WEBHOOK_SECRET` is unset.

---

## MCP

`uns-mcp` retains existing stdio tools: simulate_signal, send_signal, get_delivery_status, ack_notification, dismiss_notification, get_notification_status, get_ack_status, list_deliveries, list_audit_events, get_effective_policy, list_invariants, get_invariants_summary, list_dlq, get_channel_health, health, ready. The source registry in `uns_mcp.factory.UNS_MCP_TOOL_NAMES` is authoritative. Embedded direct read helpers accept `runtime_state=RuntimeState(runtime=runtime)` and use that runtime's durable stores. Omitted dependencies bind to the runtime; explicit injected audit/read adapters remain supported. Legacy helper calls without a runtime retain fixture behavior.

The factory and CLI default to read-only. `uns-mcp --enable-writes` requires a persistent database, `UNS_API_PRINCIPAL` and `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`; it owns recovery for the process lifetime. Embedded hosts configure `MCPRuntimeConfig` explicitly. Secrets are supplied through host configuration, not command-line flags. `send_signal` does not label acceptance as delivery. No `check_policy`, `request_approval`, or action-resume tool is implemented.

### Complete MCP Tool Reference (`UNS_MCP_TOOL_NAMES`)

| Tool Name | Mode | Input Parameters | Description |
| :--- | :--- | :--- | :--- |
| `simulate_signal` | Read-Only / Write | `payload: SendSignalInput` | Preview routing and policy resolution without side effects (`delivered: false`). |
| `send_signal` | Write (`deliver=true`) / Read-Only (`deliver=false`) | `payload: SendSignalInput` | When `deliver=false`, delegates to `simulate_signal`. When `deliver=true`, requires `--enable-writes`, `operator_intent="deliver"`, and `operator_confirmation_token` matching `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`. |
| `ack_notification` | Write | `payload: AckNotificationInput` (`notification_id`, optional `acked_by`, `metadata`) | Acknowledge a pending notification as `UNS_API_PRINCIPAL`. |
| `dismiss_notification` | Write | `payload: AckNotificationInput` (`notification_id`, optional `acked_by`, `metadata`) | Dismiss a pending notification as `UNS_API_PRINCIPAL`. |
| `get_delivery_status` | Read-Only / Write | `notification_id: str` | Return persisted delivery audit records (`found`, `delivery_status`, `channels_attempted`, `audits`). |
| `get_notification_status` | Read-Only / Write | `notification_id: str` | Return durable notification status (`found`, `status`, raw `ack_status`) and the canonical obligation response projection above. |
| `get_ack_status` | Read-Only / Write | `notification_id: str` | Return raw `ack_status` plus canonical owner, effective ACK, inheritance, and resolution status/error when bound to a runtime. |
| `list_deliveries` | Read-Only / Write | `limit: int = 25` | Return recent delivery read-model entries. |
| `list_audit_events` | Read-Only / Write | `limit: int = 25` | Return recent audit read-model entries. |
| `get_effective_policy` | Read-Only / Write | `notification_type: str`, `intent: str`, `autonomy_mode: str`, `irreversible: bool = False` | Resolve effective policy and resolution provenance for a signal shape. |
| `list_invariants` | Read-Only / Write | `limit: int = 25` | List registered system invariants from `invariants.yml`. |
| `get_invariants_summary` | Read-Only / Write | *(None)* | Return aggregate invariant counts. |
| `list_dlq` | Read-Only / Write | *(None)* | Return durable dead-letter depth and items (`{"depth": ..., "items": [...]}`). |
| `get_channel_health` | Read-Only / Write | *(None)* | Return runtime channel health summary. |
| `health` | Read-Only / Write | *(None)* | Return MCP process liveness (`{"status": "alive", "service": "uns-mcp"}`). |
| `ready` | Read-Only / Write | *(None)* | Return MCP readiness and mode (`mode`, `read_only`). |

---

## Policy authority and compatibility

Canonical intake locks the ACTIVE revision in its acceptance transaction; steady-state simulation and inspection read revision plus immutable snapshot in a single SELECT without a write lock. When a snapshot is activated (`save_policy()`, `bootstrap_policies()`, or `POST /api/v1/policies/reload`), `SQLAlchemyPolicyStore` emits `SELECT pg_notify('uns_policy_reload', ...)` on PostgreSQL and `PolicyRuntime` broadcasts a `PolicyReloadEnvelope` on Redis pub/sub (`uns:policies:reload` / `UNS_POLICY_REDIS_CHANNEL`) when configured, allowing peer worker processes (`PostgresPolicyReloadListener` and `RedisPolicyReloadSubscriber`) to refresh their warm `PolicySnapshot` caches immediately. Producer overrides that differ from resolved ACTIVE policy are rejected, including configured intent. Adapter-control metadata cannot bypass this boundary. No producer-level administrative exception exists. Direct low-level handler/adapter APIs remain trusted integration code, not a substitute for the protected intake API.

---

## WebSocket authentication

Authenticate before connecting to `/ws/agents/{agent_id}`. Native clients use a Bearer header. Browser clients offer `uns.v1` and `bearer.<base64url(UTF8(key))>` subprotocols; the selected protocol is only `uns.v1`. Query-string credentials are rejected. Observer-capable credentials can connect and read, but every ACK/DISMISS command separately requires responder or operator capability and uses the verified principal and durable Runtime. A read-capable connection does not grant response authority.

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
    "uns.v1",
    `bearer.${encodedKey}`,
  ]);
  ```

---

## Maintenance CLI

`uns-maintain` is a local administrative command, not an HTTP endpoint. It defaults to dry-run and requires explicit cutoff/horizon. Apply requires an operator, protects unsettled obligations, and can export verified archives before pruning. See [deployment](DEPLOYMENT.md) for continuation-cursor semantics and archive failure behavior.

| Flag | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--database-url` | **Yes** (or `UNS_DATABASE_URL`) | `UNS_DATABASE_URL` | SQLite (`sqlite:///path/to/uns.db`) or PostgreSQL (`postgresql+psycopg://...`) database URL. |
| `--cutoff` | **Yes** | — | ISO-8601 timestamp with explicit timezone (e.g., `2026-10-01T00:00:00Z`). |
| `--idempotency-seconds` | **Yes** | — | Minimum positive idempotency preservation window in seconds. Effective cutoff is `min(cutoff, now - idempotency_seconds)`. |
| `--batch-size` | No | `100` | Row budget per invocation (`1..1000`). Includes event/audit rows when `--archive` is used. |
| `--apply` | No | `False` | Commit deletions and `RETENTION_APPLIED` receipt inside an exclusive writer transaction (`BEGIN IMMEDIATE` on SQLite or `pg_advisory_xact_lock` + `FOR UPDATE` on PostgreSQL). Omit for dry-run preview. |
| `--operator` | **Yes** (when `--apply`) | `None` | Non-empty operator attribution recorded in the retention receipt and archive file. |
| `--after-id` | No | `None` | Resume scan after notification UUID from a prior batch's `next_after_id`. |
| `--archive` | No | `None` | Path to a **new** JSON archive file in an existing trusted directory (created with `O_CREAT \| O_EXCL`, mode `0600`). |

---

## SLO Telemetry & Certification CLI (`uns-slo-certify`)

`uns-slo-certify` (`python -m uns.slo`) computes a deterministic, SHA-256 hash-verifiable operational SLO report (`receipt_sha256`) from a UNS SQLite or PostgreSQL database. It aggregates real-time operational gauges, obligation volume, human response latency percentiles (`p50`, `p95`, `max`), per-channel delivery error rates, and `recording_only` vs. live external provider classification (`#48`).

| Flag | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--database-url` | No | `UNS_DATABASE_URL` | SQLite (`sqlite+pysqlite:///...`) or PostgreSQL (`postgresql+psycopg://...`) database URL. |
| `--window-days` | No | `14.0` | Observation window in days (`> 0`). |
| `--min-live-days` | No | `14.0` | Minimum observed live-event span in days required for `v1.0` certification. |
| `--max-error-rate` | No | `0.05` | Maximum allowed persistent external channel error rate (`0.0..1.0`). |
| `--markdown` | No | `False` | Emit a Markdown certification receipt table instead of JSON. |
| `--output` | No | `None` | Write the JSON or Markdown receipt to a file path in addition to stdout. |
| `--require-certified` | No | `False` | Exit with code `2` if `v1_0_certified` is `False` (for CI/release gating). |

---

## Pre-Execution Governance Engine (`uns.governance`)

`uns.governance` provides an opt-in, deterministic pre-execution policy evaluation gate (`ALLOW` / `REQUIRE_APPROVAL` / `DENY`) layered on top of durable `uns.Runtime` notification obligations (`#49`):

- **Schema & Policy Validation (`uns.governance.context_schema`):** `ContextSchema` Registry, `validate_policy_against_schema()`, `validate_context_capsule()`, `resolve_field_path()`, and `compute_context_hash()` (RFC 8785-style canonical JSON SHA-256).
- **Pure Evaluator (`uns.governance.decide`):** Pure, side-effect-free `decide(policy, context, ...)` evaluating all rules in canonical YAML order with `DENY > REQUIRE_APPROVAL > ALLOW` precedence and default-`DENY` (`default_deny_no_matching_rule`) when no rule matches.
- **Impure Shell & Fail-Mode Engine (`uns.governance.DecisionEngine`):** Manages policy hot-reload with last-known-good quarantine, per-intent fail-mode semantics (`SAFETY` / `GOVERNANCE` / `ACTIONABLE` fail-closed `DENY`; `INFORMATIONAL` fail-open `ALLOW` with operational alert emission), and automatic `GovernanceApprovalBridge` invocation on `REQUIRE_APPROVAL`.
- **Approval Obligation Bridge & Signed Callbacks (`uns.governance.GovernanceApprovalBridge`):** Maps `REQUIRE_APPROVAL` outcomes to durable `uns.Runtime` notification obligations (`idempotency_key="gov-approval:{decision_id}"`), synchronizes `ACKED -> APPROVED`, `DISMISSED -> REJECTED`, and `TIMED_OUT -> TIMED_OUT`, and signs/verifies resume callbacks with HMAC-SHA256 (`sign_approval_callback()`, `verify_approval_callback()` with `X-UNS-Signature` and `X-UNS-Timestamp` `±300s` replay protection).

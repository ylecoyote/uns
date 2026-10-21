# UNS API

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

## MCP

`uns-mcp` retains existing stdio tools: simulate_signal, send_signal, get_delivery_status, ack_notification, dismiss_notification, get_notification_status, get_ack_status, list_deliveries, list_audit_events, get_effective_policy, list_invariants, get_invariants_summary, list_dlq, get_channel_health, health, ready. The source registry in `agsignal_mcp.factory.AGSIGNAL_MCP_TOOL_NAMES` is authoritative. Embedded direct read helpers accept `runtime_state=RuntimeState(runtime=runtime)` and use that runtime's durable stores. Omitted dependencies bind to the runtime; explicit injected audit/read adapters remain supported. Legacy helper calls without a runtime retain fixture behavior.

The factory and CLI default to read-only. `uns-mcp --enable-writes` requires a persistent database, `UNS_API_PRINCIPAL` and `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`; it owns recovery for the process lifetime. Embedded hosts configure `MCPRuntimeConfig` explicitly. Secrets are supplied through host configuration, not command-line flags. `send_signal` does not label acceptance as delivery. No `check_policy`, `request_approval`, or action-resume tool is implemented.

## Policy authority and compatibility

Canonical intake locks the ACTIVE revision in its acceptance transaction; steady-state simulation and inspection read revision plus immutable snapshot in a single SELECT without a write lock. Producer overrides that differ from resolved ACTIVE policy are rejected, including configured intent. Adapter-control metadata cannot bypass this boundary. No producer-level administrative exception exists. Direct low-level handler/adapter APIs remain trusted integration code, not a substitute for the protected intake API.

## WebSocket authentication

Authenticate before connecting to `/ws/agents/{agent_id}`. Native clients use a Bearer header. Browser clients offer `agsignal.v1` and `bearer.<base64url(UTF8(key))>` subprotocols; the selected protocol is only `agsignal.v1`. Query-string credentials are rejected. ACK/DISMISS messages use the verified principal and durable Runtime.

## Maintenance CLI

`uns-maintain` is a local administrative command, not an HTTP endpoint. It defaults to dry-run and requires explicit cutoff/horizon. Apply requires an operator, protects unsettled obligations, and can export verified archives before pruning. See [deployment](DEPLOYMENT.md) for continuation-cursor semantics and archive failure behavior.

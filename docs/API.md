# UNS API

## Python

Install `uns[full]` from the local wheel or `.[full]` from source. `uns.Runtime(database_url, adapters=registry, create_tables=False)` owns persistent state; `uns.Client(runtime, principal=...)` is the canonical in-process client. The principal is trusted host identity, not an untrusted request field.

- `await client.simulate(request)`: policy resolution only, no side effects.
- `runtime.accept(request, principal=...)`: atomic acceptance, returns PENDING or DEDUPLICATED; replay retains identity.
- `await client.send(request)`: accept and attempt dispatch; pending failures recover through the worker.
- `runtime.get(id)`, `runtime.events(id)`: inspect durable state and event history.
- `runtime.acknowledge(id, actor=..., dismiss=False)`: conditional terminal response.
- `await runtime.run_once()`: recover eligible work and process timeouts.
- `await runtime.worker()`: continuous recovery loop.
- `runtime.replay(id, actor=...)`: request attributable replay of an exhausted failure.

Requests use the existing `agsignal.responses.SendNotificationRequest` model. Legacy domain types remain import-compatible. The low-level `notification.sdk.NotificationSDK` and `agsignal.SignalClient` are policy/handler adapters. Their no-handler result is PENDING, not a successful send.

## HTTP

`uns.app:app` and `agsignal.app:app` mount the same service. Configure `UNS_API_KEY` and `UNS_API_PRINCIPAL`; send `Authorization: Bearer ...` for mutations and runtime inspection. Existing `AGSIGNAL_*` aliases remain usable.

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

Idempotency scope is authenticated principal plus source plus key. Same content replays the original notification; different content is a conflict (409). Invalid delivery configuration is 422. Storage failures do not return a successful unrecorded mutation. An ACK body cannot claim another principal unless an explicitly configured trusted override is enabled.

## MCP

`uns-mcp` retains existing stdio tools: simulate_signal, send_signal, get_delivery_status, ack_notification, dismiss_notification, get_notification_status, get_ack_status, list_deliveries, list_audit_events, get_effective_policy, list_invariants, get_invariants_summary, list_dlq, get_channel_health, health, ready. The source registry in `agsignal_mcp.factory.AGSIGNAL_MCP_TOOL_NAMES` is authoritative.

The factory defaults to read-only. Embedded hosts explicitly configure write intent, confirmation policy, and operator principal using `MCPRuntimeConfig`. `send_signal` does not label acceptance as delivery. No `check_policy`, `request_approval`, or action-resume tool is implemented.

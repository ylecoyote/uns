# UNS security model

## Identity and access

HTTP reads and mutations require the configured operator API key by default. Only `/health` and `/healthz` expose minimal unauthenticated liveness. Readiness, metrics, runtime inspection, notification state, policies and console data are protected. Configure `UNS_API_KEY` and `UNS_API_PRINCIPAL`.

The primary `UNS_API_KEY` grants full operator authority (`admin`, `producer`, `responder`, `observer`). For deployments where independent applications, ACK bots, or dashboards should not hold administrative authority (`POST /api/v1/policies/reload`, `DELETE /api/v1/dlq/{id}`, `POST /api/v1/runtime/notifications/{id}/replay`), UNS supports optional capability-scoped credentials:

| Environment Variable | Principal Variable | Granted Scopes | Permitted Operations |
|---|---|---|---|
| `UNS_API_KEY` | `UNS_API_PRINCIPAL` | `admin`, `producer`, `responder`, `observer` | Full operator access (all write, response, admin, and read routes) |
| `UNS_PRODUCER_API_KEY` | `UNS_PRODUCER_API_PRINCIPAL` | `producer`, `observer` | Submit and simulate notifications (`POST /api/v1/notifications*`) and read status/audit |
| `UNS_RESPONDER_API_KEY` | `UNS_RESPONDER_API_PRINCIPAL` | `responder`, `observer` | Acknowledge or dismiss notifications through HTTP (`POST /api/v1/notifications/{id}/ack`, `/dismiss`) or WebSocket commands, and read status/audit |
| `UNS_OBSERVER_API_KEY` | `UNS_OBSERVER_API_PRINCIPAL` | `observer` | Read-only access to Console (`/ui/*`), status, readiness (`/readyz`), and WebSocket streams |

Out-of-scope HTTP calls with a valid scoped key return `403 Forbidden` (`insufficient_scope`). Shared keys still identify a configured principal rather than individual end-user identities.

### Source- and namespace-scoped credentials

Role credentials (`UNS_PRODUCER_API_KEY`, `UNS_RESPONDER_API_KEY`, `UNS_OBSERVER_API_KEY`) and multi-team JSON credentials (`UNS_SCOPED_API_KEYS`) can be restricted to specific producer `source` patterns and `notification_type` namespace patterns (`*`, prefix `deploy.*` / `ci-*`, or exact match):

- **Role-level environment bounds:** `UNS_PRODUCER_ALLOWED_SOURCES`, `UNS_PRODUCER_ALLOWED_NAMESPACES`, `UNS_RESPONDER_ALLOWED_SOURCES`, `UNS_RESPONDER_ALLOWED_NAMESPACES`, `UNS_OBSERVER_ALLOWED_SOURCES`, `UNS_OBSERVER_ALLOWED_NAMESPACES`.
- **Multi-team JSON array (`UNS_SCOPED_API_KEYS`):** Each entry specifies `key`, `principal` (or `subject`), `role` (`admin`, `producer`, `responder`, `observer`) or `scopes`, `allowed_sources`, and `allowed_namespaces`.
- **Enforcement across transports:**
  - **HTTP REST & Console (`/ui/*`):** Out-of-scope `send`, `simulate`, `ack`, `dismiss`, `status`, `/ui/deliveries/{id}`, and `/ui/policies/effective` calls return `403 Forbidden` (`namespace_or_source_forbidden`). Collection endpoints (`/ui/deliveries`, `/ui/policies/active`, `/ui/policies/revisions`) filter results to the principal's allowed namespaces.
  - **WebSocket (`/ws/agents/{agent_id}`):** Both live push delivery and `subscribe` replay filter notifications by the connected principal's `allowed_sources` and `allowed_namespaces`, and out-of-scope `ack` frames return `{type: "error", error: "namespace_or_source_forbidden"}`.
  - **MCP (`uns-mcp`):** `UNS_MCP_ALLOWED_SOURCES` and `UNS_MCP_ALLOWED_NAMESPACES` enforce the same source and namespace bounds on `simulate_signal`, `send_signal`, `ack_notification`, `dismiss_notification`, `get_effective_policy`, and `list_deliveries`.

Mandatory event emission and classification belong in trusted host code (for example, an application worker or agent supervisor emitting a signal when a job exhausts its retry budget), rather than relying on an untrusted model prompt to self-report failures. UNS's durability guarantee begins at its acceptance boundary (`202 Accepted`).

ACK/DISMISS attribution derives from the verified principal. Payload identities must match it. A different actor cannot replay another actor's terminal response as their own: it conflicts while preserving original attribution. In-process Python callers and MCP launch configuration are trusted host boundaries, not authentication for arbitrary payload-supplied principals.

`UNS_ALLOW_UNAUTHENTICATED_READS=true` is an explicit legacy compatibility mode for selected HTTP GET/HEAD reads only. It never grants writes, WebSockets, runtime inspection, readiness or metrics. Leave it disabled for shared deployment.

## WebSocket and MCP

WebSocket connections authenticate and require `observer` scope before acceptance. This scope permits stream reads and notification replay. Native clients can use a Bearer header. Browser clients offer `uns.v1` and `bearer.<base64url(UTF8(key))>` in the subprotocol header; the server echoes only `uns.v1`, never the credential-bearing protocol. Tokens in query strings are rejected.

Every WebSocket ACK or DISMISS command separately checks the authenticated principal's `responder` scope, which the full operator/admin credential also grants. This uses the same capability enforcement as HTTP responses and the same durable Runtime and verified actor. Producer and observer credentials cannot mutate notification response state through WebSockets. An out-of-scope command returns an error frame with `type: "error"` and `error: "insufficient_scope"`, leaves response state and audit history unchanged, and keeps the authorized read stream open.

The MCP CLI exposes trusted local stdio. It is read-only by default. Write-enabled startup requires an explicit flag, a persistent database, an operator principal and a delivery confirmation token. The host owns access to the process and its environment. This is not an internet-facing MCP authentication scheme.

## Inbound provider webhooks

Inbound provider webhooks (`POST /api/v1/webhooks/slack` and `POST /api/v1/webhooks/pagerduty`) do not use Bearer API keys because external SaaS providers authenticate callbacks with per-request HMAC-SHA256 signatures over the raw HTTP request body:

- **Fail-Closed Default:** Both endpoints return `503 Service Unavailable` when their respective signing secret (`UNS_SLACK_SIGNING_SECRET` or `UNS_PAGERDUTY_WEBHOOK_SECRET`) is unset or empty.
- **Slack Interactivity (`POST /api/v1/webhooks/slack`):** Enforces a 256 KB body size limit (`413`), verifies `X-Slack-Request-Timestamp` within a `±300` second replay window, and validates `X-Slack-Signature` (`v0=<hex>`) using constant-time `hmac.compare_digest` over `v0:{timestamp}:{raw_body}`. Authenticated `block_actions` attribute the terminal transition to `slack:<team_id>:<user_id>` (with `slack_user_name`, `slack_channel_id`, and `slack_action_id` recorded in audit metadata) and resolve follower notifications to their canonical `obligation_owner_id`.
- **PagerDuty v3 Webhooks (`POST /api/v1/webhooks/pagerduty`):** Enforces a 256 KB body size limit (`413`) and validates `X-PagerDuty-Signature` (`v1=<hex>`, supporting comma-separated signatures during secret rotation) using constant-time `hmac.compare_digest` over the raw request body. Validated `incident.acknowledged` and `incident.resolved` events resolve `uns-<dedup_key>` / `uns-<notification_id>` to the canonical owner notification and attribute transitions to `pagerduty:<agent_id>`.

## Policy authority

Canonical intake, simulation and effective-policy inspection use runtime-scoped persisted snapshots. Producer overrides cannot change an ACTIVE policy's resolved delivery mode, channels, acknowledgment requirement, timeout, priority or configured intent. Matching values remain compatible. No producer payload can grant an administrative exception.

Canonical intake also rejects adapter-control metadata such as `slack_channel`, `email_to`, `pagerduty_severity`, and WebSocket recipient controls. Other metadata remains event data. Direct low-level adapter integrations remain trusted code and must not be mistaken for a protected producer API.

Notification policy approval governs configuration changes, not business actions. During canonical intake, `Runtime.accept()` invokes `ShadowPolicyEvaluator.evaluate_intake()` inline inside an isolated non-blocking exception guard (`ShadowEvaluationResult` and `ShadowEvaluationAggregate`) with zero external channel dispatch or obligation mutation, while `evaluate_intake_async()` is available for hosts that schedule background evaluation. `SHADOW -> DRAFT -> ACTIVE` promotion requires `admin` operator authority, passing `BOUNDS`/`CONFLICT`/`INVARIANTS` guards, matching `baseline_config_hash` (preventing stale-baseline promotion), and satisfied `UNS_SHADOW_MIN_SAMPLES` / `UNS_SHADOW_ACCURACY_THRESHOLD` gates. Hashes bind content and revisions; they are not cryptographic signatures.

## Persistence and external effects

Transactions protect acceptance, policy identity, state and audit consistency. Leases and provider-attempt checks prevent a worker that has lost ownership from starting further known attempts. They cannot retract effects already sent or make a database transaction atomic with an external provider.

Audit history is append-only by application paths, not cryptographically immutable or protected from the database administrator. Administrative archive-and-prune is explicit and produces a retained receipt. An archive's durable creation and verified hash precede database pruning, but operators still own archive access, backups and retention policy.

Custom adapters, callbacks and direct Python integrations execute trusted code. Built-in adapters check the provider-attempt guard on their retries; custom retrying adapters must follow the documented guard contract. Callbacks must be cooperative asynchronous code. The service cannot stop arbitrary blocking host code from blocking its event loop.

## Deployment limits

Use HTTPS/WSS and a trusted hosting origin for shared access. The console keeps its key only in tab memory and never embeds it in browser build configuration. Avoid secrets or unnecessary personal data in notification metadata.

SQLite WAL and PostgreSQL 16 (`postgres:16-alpine`), sustained multi-worker concurrency/load tests, and hosted GitHub Actions CI are verified, whereas real external provider delivery, human comprehension, and multi-node production capacity remain separate operational boundaries. Dependency audits are dated evidence, not a permanent guarantee; see [testing](TESTING.md). No regulatory compliance, human comprehension, exactly-once external delivery or production-security certification is claimed.

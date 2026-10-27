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

Mandatory event emission and classification belong in trusted host code (for example, an application worker or agent supervisor emitting a signal when a job exhausts its retry budget), rather than relying on an untrusted model prompt to self-report failures. UNS's durability guarantee begins at its acceptance boundary (`202 Accepted`).

ACK/DISMISS attribution derives from the verified principal. Payload identities must match it. A different actor cannot replay another actor's terminal response as their own: it conflicts while preserving original attribution. In-process Python callers and MCP launch configuration are trusted host boundaries, not authentication for arbitrary payload-supplied principals.

`UNS_ALLOW_UNAUTHENTICATED_READS=true` is an explicit legacy compatibility mode for selected HTTP GET/HEAD reads only. It never grants writes, WebSockets, runtime inspection, readiness or metrics. Leave it disabled for shared deployment.

## WebSocket and MCP

WebSocket connections authenticate and require `observer` scope before acceptance. This scope permits stream reads and notification replay. Native clients can use a Bearer header. Browser clients offer `uns.v1` and `bearer.<base64url(UTF8(key))>` in the subprotocol header; the server echoes only `uns.v1`, never the credential-bearing protocol. Tokens in query strings are rejected.

Every WebSocket ACK or DISMISS command separately checks the authenticated principal's `responder` scope, which the full operator/admin credential also grants. This uses the same capability enforcement as HTTP responses and the same durable Runtime and verified actor. Producer and observer credentials cannot mutate notification response state through WebSockets. An out-of-scope command returns an error frame with `type: "error"` and `error: "insufficient_scope"`, leaves response state and audit history unchanged, and keeps the authorized read stream open.

The MCP CLI exposes trusted local stdio. It is read-only by default. Write-enabled startup requires an explicit flag, a persistent database, an operator principal and a delivery confirmation token. The host owns access to the process and its environment. This is not an internet-facing MCP authentication scheme.

## Policy authority

Canonical intake, simulation and effective-policy inspection use runtime-scoped persisted snapshots. Producer overrides cannot change an ACTIVE policy's resolved delivery mode, channels, acknowledgment requirement, timeout, priority or configured intent. Matching values remain compatible. No producer payload can grant an administrative exception.

Canonical intake also rejects adapter-control metadata such as `slack_channel`, `email_to`, `pagerduty_severity`, and WebSocket recipient controls. Other metadata remains event data. Direct low-level adapter integrations remain trusted code and must not be mistaken for a protected producer API.

Notification policy approval governs configuration changes, not business actions. Shadow measurements come from trusted external evaluators. Hashes bind content and revisions; they are not signatures or proof that the measurements are honest.

## Persistence and external effects

Transactions protect acceptance, policy identity, state and audit consistency. Leases and provider-attempt checks prevent a worker that has lost ownership from starting further known attempts. They cannot retract effects already sent or make a database transaction atomic with an external provider.

Audit history is append-only by application paths, not cryptographically immutable or protected from the database administrator. Administrative archive-and-prune is explicit and produces a retained receipt. An archive's durable creation and verified hash precede database pruning, but operators still own archive access, backups and retention policy.

Custom adapters, callbacks and direct Python integrations execute trusted code. Built-in adapters check the provider-attempt guard on their retries; custom retrying adapters must follow the documented guard contract. Callbacks must be cooperative asynchronous code. The service cannot stop arbitrary blocking host code from blocking its event loop.

## Deployment limits

Use HTTPS/WSS and a trusted hosting origin for shared access. The console keeps its key only in tab memory and never embeds it in browser build configuration. Avoid secrets or unnecessary personal data in notification metadata.

SQLite is the operationally exercised profile. PostgreSQL-specific locking and deployment behavior require separate acceptance. Dependency audits are dated evidence, not a permanent guarantee; see [testing](TESTING.md). No regulatory compliance, human comprehension, exactly-once external delivery or production-security certification is claimed.

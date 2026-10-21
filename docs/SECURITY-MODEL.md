# UNS security model

## Identity and access

HTTP reads and mutations require the configured operator API key by default. Only `/health` and `/healthz` expose minimal unauthenticated liveness. Readiness, metrics, runtime inspection, notification state, policies and console data are protected. Configure `UNS_API_KEY` and `UNS_API_PRINCIPAL`; existing AGSIGNAL-prefixed aliases remain compatible.

The credential grants operator access. There is no RBAC, per-agent authorization or multi-tenant identity claim. Do not distribute an operator key to a producer that must be prevented from invoking administrative endpoints. The React console makes GET-only requests, but its credential is not a read-only credential.

ACK/DISMISS attribution derives from the verified principal. Payload identities must match it. A different actor cannot replay another actor's terminal response as their own: it conflicts while preserving original attribution. In-process Python callers and MCP launch configuration are trusted host boundaries, not authentication for arbitrary payload-supplied principals.

`UNS_ALLOW_UNAUTHENTICATED_READS=true` is an explicit legacy compatibility mode for selected HTTP GET/HEAD reads only. It never grants writes, WebSockets, runtime inspection, readiness or metrics. Leave it disabled for shared deployment.

## WebSocket and MCP

WebSocket connections authenticate before acceptance. Native clients can use a Bearer header. Browser clients offer `agsignal.v1` and `bearer.<base64url(UTF8(key))>` in the subprotocol header; the server echoes only `agsignal.v1`, never the credential-bearing protocol. Tokens in query strings are rejected. ACK messages use the same durable Runtime and verified actor as HTTP.

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

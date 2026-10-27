# UNS product scope

Register: product.

UNS serves platform developers integrating autonomous applications and operators reviewing notification delivery and human response. Its product boundary is the notification obligation: resolve a policy, accept durable work, attempt delivery, record a response or timeout, and retain the policy and event history explaining the result.

The console uses plain operational language and existing table/detail layouts. Preserve the established light theme and typography; use text labels as well as status color. Delivery and acknowledgment must be distinguishable at a glance. No approval or agent-control affordances belong in the console.

## Supported mechanisms

| Capability | Implementation owner |
|---|---|
| Canonical Python client and transactional runtime | `uns.client`, `uns.runtime` |
| HTTP and existing MCP tools | `uns.app`, `uns_mcp.factory` using the runtime |
| Runtime-scoped policy authority and channel adapters | `uns.policy_runtime`, existing `notification` modules |
| Versioned policy storage and validated snapshot reload | `db.policy_store`, `notification.routes` |
| Policy-change records and shadow-evidence gates | `db.policy_learning_store`, `notification.policy_config` |
| Authenticated delivery/audit/policy console | `apps/ui`, instance-scoped `uns.queries` |
| Explicit retention and archive-before-prune | `uns.maintenance` |

## Explicit boundaries

The authorization rule schemas in `uns.governance` are experimental. There is no supported business-action `decide()`/`evaluate()` engine, approval/resume workflow, network enforcement, autonomous optimizer, signed approval, or cryptographically immutable ledger. Normal audit writes append history; explicit administrative archive-and-prune can retire eligible records while retaining a receipt. External provider acknowledgment does not prove human receipt.

Policy approval concerns a proposed configuration change. It does not approve the action described by a notification. Externally supplied shadow evidence requires a trusted evaluator; UNS validates its binding and declared thresholds, not the evaluator's methodology.

The local recording-adapter profile is the reproducible acceptance baseline. Deployment with real channels needs credentials, an authorized recipient, and separately recorded provider evidence.

## Trust and operation

ACTIVE notification policy defines producer obligations. Caller-controlled adapter-routing metadata cannot bypass that policy. HTTP, WebSocket and MCP paths bind their data reads and writes to their own runtime. The service credential grants operator access; there is no RBAC or multi-tenant authorization claim.

Write-enabled MCP owns recovery throughout its lifespan. Callback processing cannot hold the timeout loop. Deduplication retains pending ownership across window expiry. Replay starts a fresh attempt cycle only when the obligation is not already satisfied or recovering under a successor, without erasing failed history. Channel observations retain lease attribution; timed-out in-flight SMTP can remain UNKNOWN. Optional maintenance is default-dry-run, SQLite-only and operator-directed; it does not choose retention policy or run automatically.

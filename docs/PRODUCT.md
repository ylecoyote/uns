# UNS product scope

Register: product.

UNS serves platform developers integrating autonomous applications and operators reviewing notification delivery and human response. Its product boundary is the notification obligation: resolve a policy, accept durable work, attempt delivery, record a response or timeout, and retain the policy and event history explaining the result.

The console uses plain operational language and existing table/detail layouts. Preserve the established light theme and typography; use text labels as well as status color. Delivery and acknowledgment must be distinguishable at a glance. All `/ui/*` endpoints remain strictly read-only (`INV-UI-001`), while capability-gated operator and responder actions in the console (ACK, Snooze, Dismiss, Escalate, DLQ Replay, and Policy Lifecycle `PolicyDelta` review/promotion/rollback) execute through `/api/v1/*` endpoints. Direct agent process-execution controls remain outside the console.

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
| Opt-in pre-execution governance gate & obligation bridge | `uns.governance` (`decide`, `DecisionEngine`, `GovernanceApprovalBridge`) |
| Operational SLO telemetry & certification receipts | `uns.slo` (`uns-slo-certify`) |

## Explicit boundaries

The core UNS runtime governs the notification obligation. Unless a caller explicitly integrates the opt-in `uns.governance` pre-execution gate (`decide()`, `DecisionEngine`, and `GovernanceApprovalBridge`), a standalone notification acknowledgment records human receipt and does not approve the action described by a notification. Historical pre-consolidation commercial plugins, network-level enforcement proxies, and autonomous policy optimizers remain experimental or out of scope. Normal audit writes append history; explicit administrative archive-and-prune can retire eligible records while retaining a receipt. External provider acknowledgment does not prove human receipt.

Policy approval concerns a proposed configuration change. It does not approve the action described by a notification. Automated intake shadow evaluation (`ShadowPolicyEvaluator`) and externally supplied shadow evidence validate candidate routing and declared thresholds before `SHADOW -> DRAFT -> ACTIVE` promotion.

The local recording-adapter profile is the reproducible acceptance baseline. Deployment with real channels needs credentials, an authorized recipient, and separately recorded provider evidence.

## Trust and operation

ACTIVE notification policy defines producer obligations. Caller-controlled adapter-routing metadata cannot bypass that policy. HTTP, WebSocket and MCP paths bind their data reads and writes to their own runtime. Operators can configure a full-authority service credential (`UNS_API_KEY`) as well as least-privilege `producer`, `responder`, and `observer` capability credentials (`UNS_PRODUCER_API_KEY`, `UNS_RESPONDER_API_KEY`, `UNS_OBSERVER_API_KEY`, `UNS_SCOPED_API_KEYS`) with optional `allowed_sources` and `allowed_namespaces` bounds.

Write-enabled MCP owns recovery throughout its lifespan. Callback processing cannot hold the timeout loop. Deduplication retains pending ownership across window expiry. Replay starts a fresh attempt cycle only when the obligation is not already satisfied or recovering under a successor, without erasing failed history. Channel observations retain lease attribution; timed-out in-flight SMTP can remain UNKNOWN. Optional maintenance (`uns-maintain`) is default-dry-run and operator-directed across both SQLite and PostgreSQL; it does not choose retention policy or run automatically.

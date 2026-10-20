# UNS product scope

Register: product.

UNS serves platform developers integrating autonomous applications and operators reviewing notification delivery and human response. Its product boundary is the notification obligation: resolve a policy, accept durable work, attempt delivery, record a response or timeout, and retain the policy and event history explaining the result.

The console uses plain operational language and existing table/detail layouts. Preserve the established light theme and typography; use text labels as well as status color. Delivery and acknowledgment must be distinguishable at a glance. No approval or agent-control affordances belong in the console.

## Supported mechanisms

| Capability | Implementation owner |
|---|---|
| Canonical Python client and transactional runtime | `uns.client`, `uns.runtime` |
| HTTP and existing MCP tools | `agsignal.app`, `agsignal_mcp.factory` using the runtime |
| Policy resolution and channel adapters | Existing `notification` modules |
| Versioned policy storage and validated snapshot reload | `db.policy_store`, `notification.routes` |
| Policy-change records and shadow-evidence gates | `db.policy_learning_store`, `notification.policy_config` |
| Delivery/audit/policy console | `apps/ui`, `agsignal.queries` |

## Explicit boundaries

The authorization rule schemas in `agsignal.governance` are experimental. There is no supported business-action `decide()`/`evaluate()` engine, approval/resume workflow, network enforcement, autonomous optimizer, signed approval, or cryptographically immutable ledger. Audit records are append-only by application convention. External provider acknowledgment does not prove human receipt.

Policy approval concerns a proposed configuration change. It does not approve the action described by a notification. Externally supplied shadow evidence requires a trusted evaluator; UNS validates its binding and declared thresholds, not the evaluator's methodology.

The local recording-adapter profile is the reproducible acceptance baseline. Deployment with real channels needs credentials, an authorized recipient, and separately recorded provider evidence.

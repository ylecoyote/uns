# UNS architecture

The canonical chain is producer -> transactional policy resolution and acceptance -> leased dispatch -> provider result -> durable response state -> audit and optional callbacks.

## Acceptance and policy identity

`uns.Runtime` owns a `PolicyRuntime` tied to its database session factory. An immutable ACTIVE snapshot and monotonic revision replace the mutable global registry as canonical authority. Acceptance locks/checks the revision in the same transaction that stores the resolved notification, recoverable work, deduplication relationship and audit. Concurrent activation is ordered against that commit. A fresh HTTP or MCP process hydrates persisted policy automatically.

Snapshots, full per-version policy content and lifecycle rows have separate roles. Lifecycle status remains authoritative; a serialized historical ACTIVE policy cannot revive a RETIRED row. Accepted work retains its exact resolved revision/settings after subsequent activation. Steady-state inspection and simulation read revision plus immutable snapshot with one SELECT and do not reserve the writer. Intake/mutations retain the revision lock. Cold initialization may write to bootstrap legacy snapshots; missing referenced snapshot state fails closed. Simulation creates no notification, delivery or acknowledgment state.

## Deduplication and replay

`uns_notifications` holds delivery work, response deadlines and idempotency identity. `uns_dedup` points to an owner and generation for a scoped effective obligation. A duplicate of pending work follows that live owner and is not dispatched independently. Owner success settles followers; owner failure elects one successor and re-links the group atomically, avoiding both a silent lost obligation and a parallel alert storm.

Pending ownership remains exclusive beyond TTL expiry. Promotion retains the suppression window. Durable `dedup_successor_id` handoffs protect replay after claim expiry/replacement and retain referenced satisfaction evidence during maintenance. Failed histories remain visible, but replay conflicts when a successor is pending/delivered or lineage cannot be established. FAILED owners never suppress a fresh obligation. Explicit replay starts a new delivery cycle with a fresh cycle budget while preserving cumulative attempt history. Old ownerless dedup claims cannot establish successful delivery and are not trusted after migration. Historical pre-upgrade suppressed events cannot be reliably reconstructed automatically.

## Delivery and recovery

The dispatcher commits its claim before adapter I/O. Conditional lease checks precede channel and built-in provider retry attempts. Expired owners cannot overwrite newer state, and stale workers record uncertainty instead of making further guarded calls. A pause after a final check or a provider-success/local-commit crash still leaves external effects uncertain.

`worker()` owns separate dispatch, timeout and callback loops. `run_once()` processes dispatch/expiry without waiting on callbacks. The HTTP lifespan and write-enabled MCP lifespan start and stop their owned recovery tasks. They coordinate jobs through database claims rather than a whole-process file lock.

Delivery status and acknowledgment state remain separate. The first qualifying delivery starts the response deadline. ACK, DISMISS and TIMEOUT use conditional transitions with atomic audit. Repeated same-actor responses are idempotent; conflicting state or actor is rejected.

## Transports and console

Python, HTTP and MCP share the durable application service. Public transport authentication is centralized; WebSocket response mutations use Runtime instead of a separate legacy engine. The React console consumes strictly read-only `/ui/*` read models (`INV-UI-001`) with runtime-memory operator authentication and invokes capability-gated `/api/v1/*` endpoints for operator/responder mutations (ACK, Snooze, Dismiss, Escalate, DLQ Replay, and Policy Lifecycle transitions).

Compatibility modules retain historical import/tool names. Explicit low-level fixture composition remains available for tests; it is not an alternative unauthenticated deployment profile. Transport-owned read adapters must stay tied to their runtime, not a mutable process-global reader.

## Maintenance and boundaries

`uns.schema` performs additive runtime migration and installs dispatch, response and callback scan indexes. `uns.maintenance` offers bounded, default-dry-run retention and optional verified archive-before-prune. It does not run automatically or vacuum the database.

Pre-execution action gating is provided via the opt-in `uns.governance` package (`decide()`, `DecisionEngine`, `GovernanceApprovalBridge`), while legacy root-level action-authorization models in `notification.models` remain experimental compatibility types. UNS is ATP-agnostic; host integration is optional. See [Integration Modes](sections/integration-modes.md), [delivery semantics](sections/delivery-semantics.md), and [policy lifecycle](sections/policy-lifecycle.md).

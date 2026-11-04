# UNS consolidation and migration

## Source inventory

| Source | Frozen basis | Disposition |
|---|---|---|
| `_UNS` | `e084b52d4c02c2b6fcd89fb2813f5d5c94efe924` | Keep history and implementation; adapt public identity/runtime; preserve experimental governance types |
| `_unified_notification_service` | `c43aa62` | Preserve original product/contracts as provenance; do not duplicate its earlier runtime |
| `uns-concepts` | Documentation directory, not a Git checkout | Preserve source documents under archive; reconcile claims into the current product contract |

The original checkout's dirty `docs/ui/contracts/ui-contracts.json` was not imported. Original branches, files and remotes remain unchanged. The isolated UNS repository has no publishing/deployment action attached.

## Cleanup plan and ownership

Keep notification adapters, models, policy resolution, SQL stores, console and MCP tools. Adapt acceptance/dispatch, acknowledgment durability, policy evidence and public naming. Archive old product visions and launch claims. The canonical owner is `uns.Runtime` for the supported send/response workflow; legacy low-level modules remain building blocks and compatibility surfaces.

## Compatibility

The distribution is now `uns`. Existing Python import namespaces remain present in the wheel: `uns`, `notification`, `uns_mcp`, `db`, and `ui_client`. `uns.Client` is the new async application client; `uns.SignalClient` retains its low-level handler-based interface. Its no-handler status changes from misleading SUCCESS to PENDING and channels_attempted is empty.

`uns`, `uns-mcp`, `uns-migrate`, and `uns-maintain` are the canonical CLI commands. Existing HTTP routes and MCP tool names remain available. Public product labels say UNS.

No-handler SDK success, acceptance-only HTTP success, and the GUARANTEED/WebSocket false-success path are intentionally corrected. Callers must inspect delivery status and acknowledgment separately. Legacy test-only fixture composition remains possible with `skip_persistence_config=True`.

## Historical documents

- [Pre-consolidation README](https://github.com/ylecoyote/uns/blob/main/docs/archive/pre-consolidation/README.md)
- [Earlier authorization PRD](https://github.com/ylecoyote/uns/blob/main/docs/archive/pre-consolidation/agent_governance_control_plane_prd.md)
- [Original UNS README](https://github.com/ylecoyote/uns/blob/main/docs/archive/uns-original/README.md)
- [UNS concept PRD](https://github.com/ylecoyote/uns/blob/main/docs/archive/uns-concepts/uns/uns-prd-general.md)

Older broad authorization, commercial plugin, enforcement, market and licensing narratives are retained here for provenance. Current behavior and scope are defined by PRODUCT.md and the acceptance checks. Unique future work is limited to completing authorization separately, governed policy-evaluation orchestration, and deployment-specific assurance. None is silently started by this consolidation.

The supported Python minimum is corrected to 3.11 because the inherited runtime imports `datetime.UTC`. The former 3.10 metadata claim was incompatible with that source. The consolidated CI covers 3.11 through 3.13; local evidence uses 3.12.

The superseded Python UI files and their layout-only tests are preserved in `apps/ui/legacy_flask_reference`. The canonical console contains React/TypeScript only. The boundary scanner excludes dependency/build output directories, while still rejecting Python application files.

Minimal imports now lazily load the optional read-model surface, so SDK-only installations do not require FastAPI. MCP remains on its supported version 1 API through the explicit `<2` dependency bound. Frontend lockfile updates stay within the existing declared version ranges.

## Adversarial remediation changes

The follow-up preserves notification/audit history while adding owner/generation and replay-cycle fields, scheduling indexes, immutable policy snapshots and complete policy-content storage. SQLite migrations handle pre-remediation stores and concurrent startup; old ownerless claims cannot suppress new intake. Previously lost owner links or discarded policy fields cannot be reconstructed.

Behavior intentionally tightens: ACTIVE policy is authoritative; producer and adapter-metadata bypasses are rejected; reads/WS/readiness/metrics require auth by default; cross-actor terminal retries conflict. `UNS_ALLOW_UNAUTHENTICATED_READS` is a narrow explicit HTTP-read compatibility flag, not a write/WS bypass. No privileged producer override path was added.

Write-enabled MCP owns its recovery lifecycle. Runtime policy and transport read adapters are instance-scoped. A read-only console uses a memory-only operator key. Node requirements changed with vulnerability remediation to `^20.19.0 || ^22.12.0 || >=24.0.0`; React stays on18. The original tests remain, with additional adversarial and migration cases rather than a test-suite reduction.

`uns-maintain` adds explicit dry-run, apply and archive modes. It never runs automatically and does not vacuum or choose a compliance retention duration. Follow the current deployment guide before pruning data.


## Second remediation iteration

Pending owners remain exclusive after suppression-window expiry; promotion preserves expiry. Replay now conflicts on pending/satisfied successor obligations or unresolved lineage. Failed histories remain in the dead-letter view with blocker fields until explicit operator resolution. No force-send bypass is added.

The additive `dedup_successor_id` column and index retain recovery/satisfaction references. Upgrade reconstructs promotion-connected groups from retained DEDUP_OWNER_PROMOTED events, including successful replay by a former owner and tied timestamps. Missing evidence blocks unsafe replay instead of assuming delivery failed. All-failed intact groups remain recoverable. Maintenance protects retained successor references. Back up and stop old writers before upgrade; the one-time reconstruction scans retained work and promotion events. Lost historical events cannot be reconstructed.

Old unattempted callbacks with due time zero are normalized to their event timestamp. Runtime delivery and ACK audits now use Runtime.clock. Steady-state policy inspection/simulation no longer reserves a writer; intake and mutations retain revision locking. Direct MCP reads accept an explicit runtime state; omitted runtime keeps legacy fixture behavior. See [iteration report](REMEDIATION_ITERATION2.md) and [delivery semantics](sections/delivery-semantics.md).

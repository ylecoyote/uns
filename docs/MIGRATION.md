# UNS consolidation and migration

## Source inventory

| Source | Frozen basis | Disposition |
|---|---|---|
| `_AGSignal` | `e084b52d4c02c2b6fcd89fb2813f5d5c94efe924` | Keep history and implementation; adapt public identity/runtime; preserve experimental governance types |
| `_unified_notification_service` | `c43aa62` | Preserve original product/contracts as provenance; do not duplicate its earlier runtime |
| `_UNS` | Documentation directory, not a Git checkout | Preserve source documents under archive; reconcile claims into the current product contract |

The original checkout's dirty `docs/ui/contracts/ui-contracts.json` was not imported. Original branches, files and remotes remain unchanged. The isolated UNS repository has no publishing/deployment action attached.

## Cleanup plan and ownership

Keep notification adapters, models, policy resolution, SQL stores, console and MCP tools. Adapt acceptance/dispatch, acknowledgment durability, policy evidence and public naming. Archive old product visions and launch claims. The canonical owner is `uns.Runtime` for the supported send/response workflow; legacy low-level modules remain building blocks and compatibility surfaces.

## Compatibility

The distribution is now `uns`. Existing Python import namespaces remain present in the wheel: `agsignal`, `notification`, `agsignal_mcp`, `db`, and `ui_client`. `uns.Client` is the new async application client; `agsignal.SignalClient` retains its low-level handler-based interface. Its no-handler status changes from misleading SUCCESS to PENDING and channels_attempted is empty.

The `agsignal` command remains an alias. `uns`, `uns-mcp`, and `uns-migrate` are canonical commands. Existing HTTP routes and MCP tool names remain available. Public product labels say UNS.

No-handler SDK success, acceptance-only HTTP success, and the GUARANTEED/WebSocket false-success path are intentionally corrected. Callers must inspect delivery status and acknowledgment separately. Legacy test-only fixture composition remains possible with `skip_persistence_config=True`.

## Historical documents

- [Original AGSignal README](archive/pre-consolidation/README.md)
- [Earlier authorization PRD](archive/pre-consolidation/agent_governance_control_plane_prd.md)
- [Original UNS README](archive/uns-original/README.md)
- [UNS concept PRD](archive/uns-concepts/uns/uns-prd-general.md)

Older broad authorization, commercial plugin, enforcement, market and licensing narratives are retained here for provenance. Current behavior and scope are defined by PRODUCT.md and the acceptance checks. Unique future work is limited to completing authorization separately, governed policy-evaluation orchestration, and deployment-specific assurance. None is silently started by this consolidation.

The supported Python minimum is corrected to 3.11 because the inherited runtime imports `datetime.UTC`. The former 3.10 metadata claim was incompatible with that source. The consolidated CI covers 3.11 through 3.13; local evidence uses 3.12.

The superseded Python UI files and their layout-only tests are preserved in `apps/ui/legacy_flask_reference`. The canonical console contains React/TypeScript only. The boundary scanner excludes dependency/build output directories, while still rejecting Python application files.

Minimal imports now lazily load the optional read-model surface, so SDK-only installations do not require FastAPI. MCP remains on its supported version 1 API through the explicit `<2` dependency bound. Frontend lockfile updates stay within the existing declared version ranges.

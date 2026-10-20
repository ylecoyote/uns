> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Audit Ledger Physical Structure

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD §2.7 and M6 lock **three semantically distinct audit streams** — Decision
(M6.1), Approval (M6.2), Delivery (M6.3) — correlated by `correlation_id` +
`decision_id`, append-only at the API level (M6.6). PRD §13.3 reinforces that
streams are correlated but never merged. OSS ships hash-chain semantics; the
commercial Merkle-Audit plugin (§6) provides external attestation. ADR-005
introduces a fourth, **operational** stream (`PluginAudit`). ADR-008 requires
every fail-mode decision to land in Decision Audit with `fail_mode = true`.
ADR-002 locks the envelope (`event_id`, `correlation_id`, `decision_id`,
per-payload `schema_version`). PRD §12.1 locks the v0.2 stack: **Postgres**
(existing audit table) + **Redis** (dedup, rate limit). PRD §12.4 flags
hash-chain throughput as a Medium risk; this ADR resolves it. Multi-region,
sharding, and HA topologies are out of scope.

## Decision

### 1. Physical layout: four Postgres tables

`decision_audit`, `approval_audit`, `delivery_audit`, `plugin_audit` — one
table per stream. The v0.2 audit table evolves into `delivery_audit`; the
other three are additive in v1. Rationale: each stream has a distinct payload
shape, retention class (decision 4), and index footprint (decision 8);
co-locating via a `stream` tag forces JSONB payloads and conflicts with
per-stream lifecycle. Cross-stream correlation is a `correlation_id` /
`decision_id` join (M6.4), not physical co-location.

### 2. PluginAudit relationship: fourth physical table, operational classification

`plugin_audit` records plugin lifecycle events (`loaded`, `disabled`,
`verification_failed`, `capability_violation`) and `GET /plugins` snapshots
per ADR-005 §6/§8. **Operational classification**: NOT subject to Article 12
record-keeping (§14.2.1), NOT chained (decision 3), shares only envelope
conventions with the authorization streams. A plugin failure that affects an
evaluation produces a fail-mode entry in `decision_audit` (per ADR-008) AND a
lifecycle entry in `plugin_audit`, linked by `correlation_id`. A flat-file log
is rejected: it loses the SQL query surface ADR-005 §8 enumeration needs.

### 3. Hash-chain semantics: per-stream chain, batched checkpoints

**One chain per authorization stream** (`decision_audit`, `approval_audit`,
`delivery_audit`); `plugin_audit` is not chained. Each entry carries
`prev_entry_hash`. The chain root is persisted at a configurable cadence
(default: every 1000 entries OR every 60 seconds) into a per-stream
`chain_checkpoint(stream, checkpoint_id, root_hash, range_start_event_id,
range_end_event_id, computed_at)` table. Tampering anywhere in a range is
detectable by re-walking against the persisted root. Per-entry hashing is
rejected: it serializes `evaluate()` and conflicts with §9.1 (p99 ≤ 5 ms);
§12.4 anticipates batched chaining as the mitigation. Per-`correlation_id`
mini-chains fragment audit-completeness (§10.1); cross-stream global chain
couples write paths and recreates single-table coupling at the crypto layer.

### 4. Retention defaults

OSS defaults (operator-overridable in `agsignal.yaml`):

| Stream            | Default retention | Rationale                                           |
|-------------------|-------------------|-----------------------------------------------------|
| `decision_audit`  | 7 years           | FINRA 4511 / SEC 17a-4 record-retention floor.      |
| `approval_audit`  | 7 years           | Same evidentiary class as Decision.                 |
| `delivery_audit`  | 1 year            | Transport diagnostic; not Article 12 evidence.      |
| `plugin_audit`    | 90 days           | Operational; longer windows are observability noise.|

**Soft-delete only.** Retention expiry sets `retention_expired_at`; rows
remain until a separate **operator-initiated** purge job runs as a distinct
DB role (decision 6). Application code never issues `DELETE` (M6.6); every
purge produces a `plugin_audit` entry recording the range. Hard delete from
the application path is rejected as a direct M6.6 violation.

### 5. OSS hash-chain → Merkle-Audit handoff: parallel, not replacement

The OSS per-stream chain is **always-on**. Merkle-Audit (registered as an
`AuditHook` per M8.2) runs **in parallel**: each entry is fed to the plugin
in addition to the OSS chain write. Merkle-Audit produces its own attestation
(externally published Merkle root); it does NOT replace the OSS chain.
Replacement is rejected: it creates a "downgrade-to-OSS-on-plugin-failure"
mode conflicting with ADR-005 §6 plugin-failure isolation. Parallel keeps the
OSS chain as the always-available floor and Merkle as additive non-repudiation.

### 6. Append-only enforcement: DB-level AND application-level

**DB-level**: `agsignal_app` role granted `INSERT, SELECT` on the four tables;
`UPDATE, DELETE` revoked. Separate `agsignal_purge` role holds `DELETE` for
the retention job; `agsignal_migrate` for schema changes.
**Application-level**: the audit DAO exposes only `append()` and `query()`;
no `update()` method. Defense-in-depth — either alone fails: DB-only lets
in-process bugs attempt UPDATEs that fail confusingly mid-transaction;
app-only lets a misconfigured operator bypass the contract.

### 7. Schema evolution: per-row `schema_version`, additive-only

Each row carries the envelope `schema_version` (ADR-002 decision 3) AND the
payload `schema_version` (M2.3 for DecisionRecord; analogous elsewhere).
Additive changes (new optional columns / payload fields) bump the minor
version; existing rows remain valid because the chain hash covers
canonical-JSON including absent-but-now-defined fields as null. Breaking
changes (column removal, type change, semantics change) are a major bump and
open a new `chain_checkpoint` range at the migration boundary; the prior
range remains queryable under its original schema. No in-place rewrites of
historical rows.

### 8. Indexing (required for correctness)

Per stream:

| Index                    | Purpose                                           |
|--------------------------|---------------------------------------------------|
| `event_id` (PK, unique)  | Wire-level dedup (ADR-002 decision 8); single-row fetch. |
| `correlation_id`         | M6.4 cross-stream query.                          |
| `decision_id`            | M6.4 cross-stream query (nullable on early `delivery_audit` rows). |
| `created_at`             | Range scans; retention purge.                     |

`decision_audit` adds `policy_config_hash` (M6.5 policy-retrieval AC).
`plugin_audit` adds `plugin_name` (ADR-005 §8 admin enumeration).
`delivery_audit` retains v0.2 indexes. Composite indexes deferred until a
query pattern demonstrably needs them.

## Rejected

- **Single table with `stream` tag column.** Forces JSONB payloads, conflicts
  with per-stream retention/index footprints, degrades typed query surface.
- **Per-entry hash chain.** Serial write barrier defeats §9.1 latency target;
  §12.4 anticipates batched chaining as the resolution.
- **Cross-stream global hash chain.** Couples write paths across streams;
  tampering in one stream invalidates the others' attestation.
- **Per-`correlation_id` mini-chain.** Fragments audit-completeness; auditor
  cannot verify "all decisions in time range T" without reassembling
  thousands of chains.
- **Hard delete on retention expiry.** Direct M6.6 append-only-at-API violation.
- **Merkle-Audit replaces the OSS chain.** Plugin failure becomes a downgrade
  mode that conflicts with ADR-005 §6 isolation.
- **Application-only append-only enforcement.** Single-layer; raw DB access
  bypasses it. DB-level revocation closes the gap.
- **PluginAudit as a flat-file log.** Loses the SQL query surface ADR-005 §8
  enumeration depends on.

## Consequences

- The three authorization streams are physically and operationally separable;
  retention, indexing, chain cadence, and Merkle projection evolve per stream.
- Per-stream + batched checkpoints meet §9.1 latency while preserving M6.6
  tamper detection; the detection window is bounded by the cadence config.
- 7-year Decision/Approval retention creates non-trivial Postgres storage
  growth; high-volume operators should plan for table partitioning (deferred
  to v1.x; not required for v1 correctness).
- The `agsignal_purge` DB role is a new operational concept that must be
  documented in the deployment guide; misconfiguring it (granting `DELETE` to
  the app role) silently breaks the append-only invariant.
- Merkle-Audit running in parallel doubles audit-write fan-out; per-entry
  cost lands on the `evaluate()` hot path via `AuditHook`. ADR-005 §6
  isolation ensures a slow Merkle-Audit degrades to `DISABLED` rather than
  stalling decisions.
- Breaking schema changes require a checkpoint-range boundary, giving
  auditors a clean schema-version transition marker.

## References

- PRD §2.7, §13.3, M6, §12.1, §12.4, §14.2.1 —
  `_AGSignal/agent_governance_control_plane_prd.md`
- ADR-002 (Event Schema Format) — `2026-05-08-event-schema-format.md`
- ADR-005 (Plugin Trust Model) — `2026-05-08-plugin-trust-model.md`
- ADR-008 (Fail-mode Semantics) — `2026-05-08-fail-mode-semantics.md`
- [SEC Rule 17a-4](https://www.sec.gov/rules/final/34-44238.htm) —
  broker-dealer record-retention basis for 7-year default
- [FINRA Rule 4511](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511) —
  general books-and-records retention requirement

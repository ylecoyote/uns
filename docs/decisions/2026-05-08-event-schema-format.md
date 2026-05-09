# Event Schema Format

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD §2.8 locks the wire format as **custom Pydantic with envelope/data
separation**, with CloudEvents adoption deferred to this ADR. HARD-06 in the
Stage 1 design-sync report ([2026-05-08-stage1-design-sync-report.md](../internal/superpowers/specs/2026-05-08-stage1-design-sync-report.md))
identified the original conflict: prior PRD §7.1 mandated CloudEvents while
the v0.2 func/tech specs shipped a flat custom Pydantic schema with no
CloudEvents envelope; engineers reading either side built incompatible
consumers. Vision B+ (§2.8, vision-b-plus-design.md) resolved this by locking
custom Pydantic with envelope/data separation **for low-cost CloudEvents
retrofit if adopted post-v1**, deferring the projection mechanics to this ADR.

CloudEvents reached **CNCF Graduated status in January 2024** and is the
de-facto interop format for cross-platform event consumers (Knative, Azure
Event Grid, Google Eventarc, Dapr). The `cloudevents-pydantic` library
(`febus982/cloudevents-pydantic`, v0.2.0 Oct 2025, MIT) provides a Pydantic v2
implementation matching AGSignal's locked stack (PRD §9.5, HARD-04). v0.2
already ships notifications with envelope-shaped fields (`notification_id`,
`intent`, `delivery_mode`, free-form `metadata: dict`); this ADR formalizes
that shape across all AGSignal events (notifications, decision records,
audit entries on the wire) and locks the projection rules.

ADR-007 fixes the `DecisionRecord` payload schema (M2.3); this ADR does not
re-spec it. ADR-004 fixes `agsignal.contracts` as the public boundary;
event envelope types live there. ADR-001 fixes callback semantics; the
callback POST body is an AGSignal event by this schema.

## Decision

### 1. Envelope structure: top-level metadata + nested `data:` payload

Every AGSignal event on the wire is a Pydantic model with a flat
**envelope** of AGSignal-specific metadata fields and a nested **`data`**
field carrying the business payload. Top-level envelope fields (v1):

```
event_id          : UUID         # globally unique; idempotency key
event_type        : str          # canonical type taxonomy (decision 2)
schema_version    : str          # envelope schema version (decision 3)
source            : str          # URI-reference identifying producer
created_at        : datetime     # RFC 3339, UTC
correlation_id    : str | None   # caller-supplied tracing key (PRD §M6.4)
decision_id       : str | None   # engine-generated when applicable (PRD §M6.4)
data              : <payload>    # nested, type-discriminated by event_type
metadata          : dict         # free-form caller extensions (decision 7)
```

`data` is the typed business payload (e.g., a `DecisionRecord` for
`agsignal.decision.evaluated`, a `Notification` for
`agsignal.notification.sent`). Envelope and data are separate Pydantic
models composed at the wire boundary; this enables independent versioning
(decision 3) and the CloudEvents retrofit (decision 4).

Rationale: the envelope/data separation is the load-bearing shape called out
in PRD §2.8. Top-level fields are exactly those that map 1:1 onto CloudEvents
context attributes (decision 4); business semantics stay in `data`, never
flattened to the envelope.

### 2. Event type taxonomy: reverse-DNS, dotted-snake, lifecycle-stage suffix

Type names follow `agsignal.<domain>.<action>` with reverse-DNS prefix and
dotted snake_case segments:

| Type                              | Producer            | `data` payload          |
|-----------------------------------|---------------------|-------------------------|
| `agsignal.decision.evaluated`     | Decision Engine     | `DecisionRecord`        |
| `agsignal.decision.failed`        | Decision Engine     | `DecisionRecord` (fail-mode) |
| `agsignal.approval.requested`     | Approval Workflow   | `ApprovalRequest`       |
| `agsignal.approval.acked`         | Approval Workflow   | `ApprovalAck`           |
| `agsignal.approval.timed_out`     | Approval Workflow   | `ApprovalTimeout`       |
| `agsignal.notification.sent`      | Notification Layer  | `Notification`          |
| `agsignal.notification.delivered` | Notification Layer  | `DeliveryReceipt`       |
| `agsignal.notification.failed`    | Notification Layer  | `DeliveryFailure`       |
| `agsignal.audit.recorded`         | Audit Hooks         | `AuditEntry`            |

Reverse-DNS prefix matches CloudEvents `type` recommendation; dotted
snake_case matches existing AGSignal Python idiom and v0.2 `notification_type`
casing. New types are added by amendment; the taxonomy is closed at v1 to
keep consumer dispatch tables tractable.

### 3. Versioning: independent envelope and data versioning

Two distinct version axes:

- `schema_version` (envelope) — format of the envelope itself; bumped only
  when envelope fields are added/removed/restructured. v1 ships as
  `schema_version = "1.0"`.
- `data.schema_version` (payload) — already locked per-payload in M2.3
  (`DecisionRecord.schema_version`); each `data` model carries its own
  version field independently.

Compatibility rules: minor envelope bumps add optional fields only;
consumers ignore unknown top-level fields. Major bumps are breaking and
require coordinated rollout. Data-payload versions evolve independently of
the envelope (M2.3 already commits to additive-only minor bumps for
`DecisionRecord`); `agsignal.contracts` re-exports both version constants so
plugins and consumers can pin against whichever surface they bind to.

The split mirrors ADR-004's per-Protocol semver decision: envelope and
payload evolve at different cadences and shouldn't be locked to the same
version line.

### 4. CloudEvents projection: off by default, opt-in via content negotiation

AGSignal v1 emits the **custom envelope as the default wire format**.
CloudEvents-compatible projection is **off by default** and exposed via two
opt-in mechanisms:

- **HTTP content negotiation**: callback POSTs and any HTTP event surface
  honor `Accept: application/cloudevents+json`; AGSignal returns the
  CloudEvents-projected event body. Default `application/json` returns the
  custom envelope. The structured-mode CloudEvents binding is the only
  projection v1 supports (binary mode deferred).
- **Per-callback configuration flag**: `agsignal.yaml` callback registration
  declares `format: cloudevents | native` (default: `native`); the flag
  pre-negotiates content type without per-request `Accept` headers.

Always-on dual emission is rejected (decision 4 rejected list). Off-by-default
keeps the v1 wire format stable for the locked v0.2 consumers and avoids
forcing CloudEvents library dependencies on every consumer.

**Mapping table (locked):**

| AGSignal envelope field   | CloudEvents context attribute |
|---------------------------|-------------------------------|
| `event_id`                | `id`                          |
| `event_type`              | `type`                        |
| `created_at`              | `time`                        |
| `source`                  | `source`                      |
| `schema_version`          | (omitted — CloudEvents `specversion = "1.0"` is fixed; AGSignal envelope version moves to extension `agsignalschemaversion`) |
| `data` (payload object)   | `data` (object) + `datacontenttype = "application/json"` |
| `correlation_id`          | extension `correlationid`     |
| `decision_id`             | extension `decisionid`        |
| `metadata` (free-form)    | extensions, prefixed `agsignalmeta_<key>` (lowercased, alphanumeric per CloudEvents extension naming) |

CloudEvents `specversion` is hardcoded to `"1.0"` in projected output.
Attribute name casing in CloudEvents extensions is constrained
(lowercase, alphanumeric); AGSignal projection maps fields accordingly.

### 5. Library choice: AGSignal-native Pydantic models; cloudevents-pydantic for projection

`agsignal.contracts` (per ADR-004 §7) is the public boundary and ships
**AGSignal-native Pydantic v2 models** (`Event`, `EventEnvelope`, typed
payload models per decision 2). The native models are the source of truth.

For the CloudEvents projection (decision 4), AGSignal uses
`cloudevents-pydantic` (febus982; v0.2.0; MIT; Pydantic v2 native; matches
the locked stack per PRD §9.5). It is added as an **optional dependency**:
projection is implemented in `agsignal.events.cloudevents` and only imports
`cloudevents-pydantic` when the projection is requested. Operators not
using the projection do not pay the dependency cost.

Rolling our own projection is rejected: cloudevents-pydantic is Pydantic
v2-native, ~5x faster than the official SDK for serialization (per
maintainer benchmarks), and absorbs the spec-conformance burden (binary
data encoding, extension-name casing rules, `datacontenttype` semantics).

### 6. Wire serialization: JSON only in v1

JSON is the only supported wire format in v1. MessagePack, CBOR, and
protobuf are rejected for v1 (no caller has demonstrated a performance
floor unmet by JSON; PRD §9.1 latency targets — engine p99 ≤ 5 ms,
notification p99 ≤ 100 ms — are met with JSON; the multi-format complexity
cost dominates the benefit).

The door is left open: `agsignal.events` exposes serialization through a
narrow interface (`to_wire(event) -> bytes`, `from_wire(content_type, body)
-> Event`) so a v1.x ADR can add formats without changing call sites. v1
implements the JSON branch only.

### 7. Extension fields: typed on registered ContextSchema; free-form `metadata` for the rest

Two extension mechanisms with explicit roles:

- **Typed extensions** via `ContextSchema` (ADR-009 territory): fields the
  caller registers with the engine and that the policy DSL can reference
  appear in `data` as typed payload fields. These are first-class to
  decision logic and audit; they evolve with `data.schema_version`.
- **Free-form `metadata: dict`** on the envelope: caller-attached
  extensions that do **not** participate in policy evaluation and do not
  contribute to `policy_config_hash` or `context_hash`. Use this for
  tracing fluff, vendor-specific tags, deployment labels — anything the
  caller wants to round-trip without forking the schema.

The split is load-bearing: typed extensions are part of the decision; free-
form is not. Mixing them in one bag causes the historical "is this field
used by the engine?" ambiguity (resolved by being explicit). The
`metadata` field maps to CloudEvents extensions per decision 4.

### 8. Idempotency keys: `event_id` is the universal dedup key

`event_id` is a producer-generated UUIDv7 (time-ordered, collision-resistant)
and is **the** dedup key across all AGSignal event surfaces. M5.2's
"receiver-side idempotency by `decision_id`" (PRD-locked) is preserved as
a domain-specific dedup tuple for *callback* receivers, but the wire-level
dedup is `event_id`:

- **Notifications** dedup on `event_id` for replay protection; the
  domain-level `dedup_key` (M1.6) is orthogonal and handles
  intent/notification_type-level deduplication windows.
- **Callback POSTs** carry `event_id` (envelope) AND `decision_id` (in
  `data`); receivers SHOULD use whichever key matches their persistence
  model (most use `decision_id` for resume-safety per M5.2).
- **Audit entries** are keyed by `event_id` for the audit-stream's own
  dedup; correlation across streams uses `correlation_id` + `decision_id`
  per PRD M6.4.

UUIDv7 over UUIDv4: time-ordering improves audit-ledger insert locality and
makes correlation queries naturally range-scannable.

### Example: native envelope (default wire format)

```json
{
  "event_id": "01939c2a-7e10-7d3c-9a4f-3b8a4f5e6d7c",
  "event_type": "agsignal.decision.evaluated",
  "schema_version": "1.0",
  "source": "/agsignal/engine/decisions",
  "created_at": "2026-05-08T14:30:00.123Z",
  "correlation_id": "trace-abc-123",
  "decision_id": "dec-d4e5f6",
  "data": {
    "decision_id": "dec-d4e5f6",
    "policy_config_hash": "sha256:7a8b9c...",
    "policy_id": "trade-approval-v3",
    "policy_version": "3.2.1",
    "context_hash": "sha256:1d2e3f...",
    "decision": "REQUIRE_APPROVAL",
    "reasons": [
      {"rule_id": "high_notional", "matched": true, "predicate": "notional_usd GT 1000000", "then": "REQUIRE_APPROVAL"}
    ],
    "evaluated_at": "2026-05-08T14:30:00.120Z",
    "schema_version": "0.4",
    "correlation_id": "trace-abc-123"
  },
  "metadata": {
    "agent_runtime": "langgraph-0.2",
    "deployment_env": "prod-us-east-1"
  }
}
```

### Example: CloudEvents projection (opt-in via `Accept: application/cloudevents+json`)

```json
{
  "specversion": "1.0",
  "id": "01939c2a-7e10-7d3c-9a4f-3b8a4f5e6d7c",
  "type": "agsignal.decision.evaluated",
  "source": "/agsignal/engine/decisions",
  "time": "2026-05-08T14:30:00.123Z",
  "datacontenttype": "application/json",
  "agsignalschemaversion": "1.0",
  "correlationid": "trace-abc-123",
  "decisionid": "dec-d4e5f6",
  "agsignalmeta_agent_runtime": "langgraph-0.2",
  "agsignalmeta_deployment_env": "prod-us-east-1",
  "data": {
    "decision_id": "dec-d4e5f6",
    "policy_config_hash": "sha256:7a8b9c...",
    "policy_id": "trade-approval-v3",
    "decision": "REQUIRE_APPROVAL",
    "reasons": [
      {"rule_id": "high_notional", "matched": true, "predicate": "notional_usd GT 1000000", "then": "REQUIRE_APPROVAL"}
    ],
    "evaluated_at": "2026-05-08T14:30:00.120Z",
    "schema_version": "0.4",
    "correlation_id": "trace-abc-123"
  }
}
```

## Rejected

### CloudEvents-as-mandate from v1 (Vision A position)

Rejected. PRD §2.8 explicitly retreats from this position. v0.2 already
ships custom envelope notifications in production; mandating CloudEvents at
v1 would break every existing consumer and force the cloudevents-pydantic
dependency on operators who have no need for cross-platform interop.
Off-by-default with content negotiation gives the same retrofit option at
zero cost to the dominant non-CloudEvents path.

### No CloudEvents projection ever

Rejected. CloudEvents is CNCF Graduated (January 2024) and is the de-facto
interop format for event consumers in the cloud-native ecosystem. Closing
the door entirely would cut off a low-cost integration path; PRD §2.8's
"low-cost CloudEvents retrofit" commitment forecloses this option. The
projection is built; it is just off by default.

### Always-on dual emission (native + CloudEvents on every event)

Rejected. Doubles the wire bytes, doubles the audit storage, and forces
every consumer to make a choice rather than allowing the single-format
default. Content negotiation gives the same flexibility on demand without
the per-event cost.

### Multi-format wire serialization in v1 (MessagePack, CBOR, protobuf)

Rejected. PRD §9.1 latency targets are met with JSON; no caller has
demonstrated a performance floor that JSON misses. Adding even one
alternative format multiplies test surface (encoder × event type × consumer
adapter) without commensurate user value. The narrow `to_wire`/`from_wire`
interface (decision 6) leaves the door open for a v1.x ADR if a concrete
need emerges.

### Single global `schema_version` for envelope and data combined

Rejected. Bumping `data` (e.g., adding a `DecisionRecord` field per M2.3's
additive-only rule) would force an envelope-version bump even though no
envelope field changed; consumers who only depend on envelope shape would
incorrectly perceive a breaking change. Independent versioning matches
ADR-004's per-Protocol semver and the natural cadence difference.

### Free-form payload (no `data` separation; everything top-level)

Rejected. The original v0.2 notifications used this shape, and HARD-06
identified it as exactly the obstacle to CloudEvents retrofit. The
envelope/data split is the load-bearing decision in PRD §2.8; collapsing
it back would re-create the conflict.

### Native event without idempotency key (let consumers decide)

Rejected. AGSignal core writes audit entries; without a wire-level dedup
key the at-least-once retry semantics in ADR-001 callback delivery would
produce duplicate audit rows on every retry. `event_id` as the universal
key removes the foot-gun for every consumer.

## Consequences

**Consumer integration cost.** Native-envelope consumers are unchanged
from v0.2's existing notification consumer shape — top-level metadata,
nested `data` payload — so no migration. CloudEvents consumers opt in via
content negotiation and get spec-compliant projection without AGSignal-side
fork. The `agsignal.contracts` package re-exports envelope and payload
models with type discrimination (`event_type` literal) so static checkers
can flag mishandled types.

**Commercial-plugin event-emit responsibilities.** Plugins that emit
events through AGSignal (notably commercial AuditHook implementations like
Merkle-Audit, and DurableWorkflow's resume callbacks) MUST construct events
through `agsignal.contracts.Event` rather than ad-hoc dicts; this
guarantees envelope conformance and prevents accidental schema drift.
Plugins set `source` to a plugin-identified URI (e.g.,
`/agsignal/plugins/merkle-audit`) and propagate `correlation_id` /
`decision_id` per ADR-004 §7's plugin-design principles. The
CloudEvents projection is centrally implemented; plugins do not need to
ship their own projection logic.

**v1 → v1.x retrofit cost if CloudEvents adoption is later required.**
Low. The envelope/data split (decision 1) and the locked mapping table
(decision 4) mean a future "always-on CloudEvents" decision is a
configuration flip, not a schema rewrite. The dominant unknown is whether
CloudEvents v2 (if/when standardized by CNCF) introduces breaking envelope
changes; the projection layer absorbs that risk on AGSignal's side, and the
native envelope is unaffected. If `cloudevents-pydantic` falls behind the
spec, AGSignal can pin to a known-good version or temporarily roll the
projection by hand using the official `cloudevents` SDK as a fallback.

**Operational implications.** OPERATIONAL notifications use the same
envelope; the existing v0.2 channel adapters (Slack/Email/WebSocket/
PagerDuty) need a one-time update to consume the typed envelope rather
than the prior flat shape. UUIDv7 `event_id` improves audit-ledger insert
locality (Postgres B-tree) and gives operators sortable IDs in log greps.
The CloudEvents projection adds a small per-request cost (sub-millisecond
serialization in `cloudevents-pydantic` benchmarks); content negotiation
ensures only opt-in callers pay it.

## References

- PRD §2.8 (Event schema commitment), §2.7 (three audit streams), M1
  (Notification layer), M2.3 (DecisionRecord schema), M5.2 (receiver-side
  idempotency), M6 (Audit ledger), §11 (ADR-002 description) —
  `_AGSignal/agent_governance_control_plane_prd.md`
- HARD-06 in Stage 1 design-sync conflict report —
  `docs/internal/superpowers/specs/2026-05-08-stage1-design-sync-report.md`
- Vision B+ scope sketch §2.8 (Architectural Commitment 8) —
  `docs/internal/superpowers/specs/2026-05-08-vision-b-plus-design.md`
- ADR-007 (DecisionRecord internal shape) —
  `2026-05-08-decision-engine-shape.md`
- ADR-004 (`agsignal.contracts` public boundary) —
  `2026-05-08-extension-api-surface.md`
- ADR-001 (Approval Workflow Semantics; callback POST body shape) —
  `2026-05-08-approval-workflow-semantics.md`
- Stage 2 production-pattern matrix (CloudEvents adoption signals) —
  `docs/internal/superpowers/specs/2026-05-08-stage2-production-pattern-matrix.md`
- [CloudEvents v1.0 specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md) — required attributes (`id`, `source`, `type`, `specversion`) and JSON envelope format
- [CloudEvents JSON Format v1.0.1](https://github.com/cloudevents/spec/blob/v1.0.1/json-format.md) — `application/cloudevents+json` media type; structured-mode binding; extension-name casing rules
- [CNCF announcement: CloudEvents Graduation (January 2024)](https://www.cncf.io/announcements/2024/01/25/cloud-native-computing-foundation-announces-the-graduation-of-cloudevents/) — CNCF Graduated status; basis for retrofit option
- [cloudevents-pydantic (febus982)](https://github.com/febus982/cloudevents-pydantic) — Pydantic v2 implementation; matches PRD §9.5 stack; benchmarks
- [Official CloudEvents Python SDK](https://github.com/cloudevents/sdk-python) — fallback if `cloudevents-pydantic` falls behind spec
- [RFC 9562 — UUID Version 7](https://www.rfc-editor.org/rfc/rfc9562) — time-ordered UUID format for `event_id`

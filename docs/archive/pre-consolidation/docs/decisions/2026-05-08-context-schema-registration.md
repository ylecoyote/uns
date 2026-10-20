> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Context Schema Registration

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD M3.4 locks the `ContextSchema` requirement: domain code registers a
declarative schema at engine construction; the engine validates every context
capsule and every policy field reference against the schema, and policies that
reference unregistered fields MUST be rejected at policy load (not at evaluate
time). PRD M3.4 explicitly defers schema versioning, evolution rules, and
multi-domain coexistence mechanics to this ADR. The decision is on the v0.4
Decision Engine critical path: ADR-007 §7 raises `ContextSchemaViolation` from
`decide()` and ADR-008 §3 maps `engine_failure_context_invalid` to fail-mode,
and both depend on this ADR locking what the schema *is* and *when* it's
checked. ADR-004 §3 separates `PluginLifecycle` from the contract Protocols, so
ContextSchema registration must compose cleanly with plugins that opt out of
lifecycle.

The PRD non-negotiables: AGSignal core has zero domain field names (§12.2);
multi-domain coexistence is required (§10.1 §1; M3.4 AC2); deny-by-default is
locked (ADR-007 §3); the Pydantic v2 + async FastAPI runtime is locked (§9.5,
HARD-04). This ADR locks ContextSchema mechanics inside that envelope.

## Decision

### 1. Schema definition format: Pydantic v2 model (`ContextSchema = type[BaseModel]`)

Domain plugins declare a `ContextSchema` as a Pydantic v2 `BaseModel` subclass.
AGSignal core treats the class as the canonical definition; field names, types,
nested models, and `Field(...)` constraints are the schema. Pydantic v2's
Rust-core validator gives both the load-time field-existence checks and the
evaluate-time capsule validation in one mechanism — no separate JSON Schema
runtime, no parallel validator. The model's auto-generated JSON Schema (via
`.model_json_schema()`) is exposed for external tooling (linting, IDE hints —
see decision 8) without forcing JSON Schema as the authoring surface.

```python
# Domain-side (e.g., MIP-AG-Trading; illustrative, not in core)
from pydantic import BaseModel, Field
from typing import Literal

class TradingContext(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}  # see decision 5
    notional_usd: int = Field(ge=0)
    plan_lifecycle: Literal["DRAFT", "PENDING", "ACTIVE", "RETIRED"]
    order_count: int = Field(ge=0)
    instrument: "Instrument"  # nested model

class Instrument(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]{1,5}$")
    exchange: Literal["NYSE", "NASDAQ", "ARCA"]
```

### 2. Registration API: at engine construction, named multi-schema map

Schemas are registered at `Engine` construction via a named map, not a runtime
registration call. One `Engine` instance MAY host multiple named schemas to
support multi-domain coexistence (decision 7); each `GovernancePolicy`
declares which schema name it binds to.

```python
engine = Engine(
    context_schemas={
        "trading": TradingContext,
        "healthcare": HealthcareContext,
    },
    # ... other engine config
)
```

Registration **at construction, not at runtime** matches ADR-007's pure-
function commitment for `decide()`: the schema set is part of the engine's
immutable configuration, and `policy_config_hash` (M2.3) incorporates the
schema map digest so identical (policy, schema) pairs produce identical
hashes. A `register_context_schema(name, schema)` runtime API is rejected
(see Rejected) — late registration would let a policy load against schema
A then evaluate against schema B, breaking the M3.4 load-time guarantee.
Hot-reload of schemas reuses the construction path via the same atomic
swap as policy hot-reload (decision 6).

ContextSchema registration is **not** a plugin lifecycle hook (ADR-004 §3).
Domain plugins are caller-side adapters per PRD §8, not loaded plugins per
ADR-004; they pass the schema to `Engine(...)` directly. This keeps the
ADR-004 plugin lifecycle minimal (it's for `OverrideAuthority`/`AuditHook`/
etc., not for domain integration).

### 3. Validation timing: both policy-load AND evaluate-time

**Policy-load**: every `when` clause's field reference is resolved against the
declared schema for that policy's `context_schema:` binding. Unknown fields,
type-incompatible operators (e.g., `GT` on a `str` field), and nested-path
typos are rejected at load. Failure is an `InvalidPolicyError` raised by the
loader; the policy never enters `ACTIVE`. This is the M3.4 AC1 contract.

**Evaluate-time**: the supplied `context` capsule is `model_validate`'d against
the bound schema before `decide()` executes. A capsule that fails validation
raises `ContextSchemaViolation` from `decide()` (per ADR-007 §7); `evaluate()`
catches it and applies fail-mode per ADR-008 §3 (`engine_failure_context_
invalid`).

Both checks are required: load-time alone cannot catch caller bugs that pass a
malformed dict; evaluate-time alone defeats the M3.4 promise of "catch typos
before any decision." The two checks share one Pydantic schema, so the
authoring surface stays singular even when validation runs twice. Pydantic v2's
`TypeAdapter` is cached at engine construction so evaluate-time validation hits
the Rust core, not Python schema rebuilding (latency budget per §9.1).

### 4. Field reference language: dot-notation with bracketed indexing

Policy YAML references context fields via dot-notation (`order.notional_usd`,
`instrument.symbol`) with optional bracketed integer indexing for lists
(`approvers[0].role`). Map keys with reserved characters (dots, brackets) use
quoted segments (`metadata."external.id"`). The grammar is a strict subset of
JSONPath — no wildcards, no descendant operators, no filters — keeping the
loader trivially auditable and the predicate set bounded.

```yaml
# In a policy YAML
context_schema: trading
rules:
  - id: large_notional_requires_approval
    when:
      - field: notional_usd
        op: GTE
        value: 1000000
      - field: instrument.exchange
        op: IN
        value: ["NYSE", "NASDAQ"]
    then: REQUIRE_APPROVAL
```

Dot-notation matches the PRD M3.3 examples (`agent.notional_usd` style) and
the operator allowlist in M3.2; JSONPath would import filter/predicate
semantics that compete with `when`'s own predicate model. Flat-keys-only is
rejected (see Rejected) — domain capsules nest naturally (e.g.,
`instrument.symbol`) and flattening forces every domain to invent a key
encoding.

### 5. Type coercion: strict mode, no implicit coercion

Pydantic strict mode is enabled by default for context-capsule validation:
`"42"` (string) does not become `42` (int) for an `int`-declared field;
the capsule is rejected with a structured ValidationError that maps to
`ContextSchemaViolation`. Domain code is responsible for parsing/coercing
upstream of `evaluate()`. This is the safer default for a governance engine —
silent string-to-int coercion has been the source of multiple production
authorization bugs in adjacent systems (OPA inputs, Cedar entity attributes).
The PRD §9.3 "schema-validated inputs" requirement and ADR-008's
`engine_failure_context_invalid` reason both presume strict semantics.

`extra: "forbid"` is the recommended schema config (illustrated in decision
1). Capsules carrying unexpected fields are rejected; this catches typos in
caller code that would otherwise produce silent under-evaluation. Authors
who deliberately need loose extras can override on their own schema, but
core's example uses `forbid`.

### 6. Schema evolution and versioning: schema-version-pinned in DecisionRecord; additive-only minor; major requires policy migration

**Versioning.** Each `ContextSchema` declares
`__schema_version__: str` (semver) at the class level, mirroring ADR-004 §5's
`__contract_version__` pattern for plugin Protocols. The engine pins
`context_schema_version` into every `DecisionRecord` (additive field on M2.3;
the M2.3 schema is additive-only per its own AC).

**Backward-compat rules for minor version bumps:**

- Adding optional fields with defaults: allowed.
- Widening field types (e.g., `int` → `int | float`): allowed if existing
  policy predicates remain type-compatible; rejected at load otherwise.
- Removing or renaming a field: forbidden in minor; requires major bump and
  per-policy migration (load-time error names the missing field).
- Tightening a constraint (e.g., `ge=0` → `ge=1`): allowed; existing capsules
  that pass the looser constraint may now fail. Treated as a fail-mode trigger
  per ADR-008 §3, not a load-time policy rejection.

**Hot-reload of schemas** reuses M1.5's policy-hot-reload mechanism: in-flight
evaluations stay pinned to the (policy, schema) pair they started with, and
a malformed candidate schema is quarantined per ADR-008 §6 (last-known-good
prevails). The engine does NOT support partial schema updates — schema
hot-reload is whole-map atomic swap.

**Cross-version evaluation** (context produced against v1 while engine is on
v2) is a deliberate non-feature in v1 OSS core. Capsules must conform to the
currently-active schema; older capsules that fail revalidation are
fail-moded. Versioned-context migration is deferred to a commercial plugin if
demand emerges; the OSS core's invariant is "one active schema per name at a
time."

### 7. Multi-domain coexistence: namespaced per-engine, one schema per policy

Each schema is registered under a **name** (decision 2). Each
`GovernancePolicy` YAML declares a `context_schema:` field naming exactly one
schema. A single policy cannot reference multiple schemas; cross-domain
governance composes by routing the request to the appropriate policy at the
caller side, not by composing schemas in YAML.

Names are case-sensitive bare identifiers (`[a-zA-Z_][a-zA-Z0-9_-]*`).
Reserved names: `default` (the engine's null-schema fallback for callers that
opt out of validation — see decision 8); names beginning with `_` are reserved
for AGSignal core extensions.

Multi-tenancy semantics (one engine instance per tenant vs. one shared
multi-domain engine) is a deployment choice, not a schema choice. The PRD
§9.4 single-tenant target means most v1 deployments will register one
schema per engine; the multi-schema map exists so a single-tenant engine
hosting multiple internal domains (e.g., a regulated platform running both
trading and treasury) doesn't need two engine instances.

### 8. Schema-aware tooling (Consequences, partial in v1)

The Pydantic-v2-based schema lets `agsignal lint policy <file.yaml>` (a v1
must-have for the policy author DX) emit field-not-in-schema errors,
type-incompatible-operator errors, and JSON Schema export for IDE plugins.
The v1 OSS CLI ships the lint subcommand (gating policy promotion from
DRAFT to PREVIEW, M1.5); IDE plugins are out of v1 scope per PRD §5.3 C2,
but the JSON Schema export (via `model_json_schema()`) is a 3-line surface
that third-party plugins consume without core changes.

## Rejected

### JSON Schema as the authoring format

Rejected. JSON Schema is language-agnostic and superficially attractive for
"share schemas across services," but the v1 runtime is locked Python (PRD
§9.5 Pydantic v2). Adopting JSON Schema as the authoring surface forces a
second validator (e.g., `jsonschema` library) on the evaluate-time hot path
— 2026 benchmarks show `jsonschema` is ~3.5× slower than Pydantic v2's
Rust core, eroding the §9.1 latency budget. JSON Schema export from
Pydantic (decision 8) gives the cross-language story without paying the
runtime cost. If a v2+ HTTP-only governance backend emerges, a separate
ADR can revisit.

### Plain Python dataclass

Rejected. Stdlib dataclasses don't validate at runtime — passing
`notional_usd="$1M"` to a `dataclass(notional_usd: int)` silently stores
the string. The whole point of the M3.4 contract is to reject malformed
context capsules; dataclasses provide zero of the required validation.
`pydantic.dataclasses` is a viable middle ground but offers no advantage
over `BaseModel` for this surface.

### Custom AGSignal `ContextSchemaDef` DSL

Rejected. Inventing a new schema language is a perpetual liability — every
type system feature (unions, literals, regex constraints, nested models)
re-invents Pydantic. Authors already learn Pydantic for `DecisionRecord`,
`AuditEntry`, and the rest of `agsignal.contracts` (ADR-004 §7); adding a
parallel surface for ContextSchema doubles the cognitive load with no
material benefit.

### Runtime registration API (`engine.register_context_schema(...)`)

Rejected. Late registration breaks the M3.4 load-time guarantee: a policy
loaded before its schema is registered would have to either (a) defer
field-reference validation to evaluate-time (defeats M3.4) or (b) fail
loading and require reload after registration (worse than failing at
construction). The construction-time map (decision 2) plus hot-reload
(decision 6) covers every legitimate use case.

### Validation only at policy-load, not at evaluate-time

Rejected. Load-time alone trusts every caller to construct well-formed
context dicts; in practice, callers ship malformed payloads (the canonical
case is forgotten optional fields after a domain refactor). ADR-008 §3
explicitly enumerates `engine_failure_context_invalid` as a fail-mode
trigger; that requires evaluate-time validation. Skipping evaluate-time
also forces ADR-007's `ContextSchemaViolation` exception to be unreachable
in practice, which contradicts ADR-007 §7's "defense in depth" framing.

### Validation only at evaluate-time, not at policy-load

Rejected. Defeats the entire M3.4 promise — typos in `when` clauses would
ship to production and only surface as fail-mode DENY. Compliance officers
can't review policies they can't load.

### Type coercion on (Pydantic lax mode)

Rejected. String-to-int coercion in security-sensitive predicates is a
latent footgun: `"1000000"` and `1000000` evaluate identically under lax
mode, but a malformed capsule sending `"1e6"` (which Pydantic happily
coerces to `1000000.0` then to `1000000`) hides upstream bugs. Strict mode
forces upstream code to handle parsing explicitly, with the
`engine_failure_context_invalid` audit trail naming the offending field.

### Cross-version capsule support in core

Rejected for v1 OSS. A v1-vs-v2 schema migration layer is a real feature for
long-running deployments, but it requires either a versioned-context
adapter Protocol (premature) or domain-specific migration code (which
defeats AGSignal's domain-agnostic invariant). Defer to a commercial plugin
once demand is concrete; current v1 invariant is "one active schema per
name."

### Flat-keys-only field reference

Rejected. Domain context capsules nest naturally
(`instrument.symbol`, `approvers[0].role`); flattening forces every domain
plugin to invent a key encoding (`instrument__symbol`, `approvers_0_role`)
and creates ambiguity when a key contains the encoding separator.
Dot-notation with bracketed indexing (decision 4) is the pattern OPA,
Cedar, and Casbin all converge on.

## Consequences

**v0.4 Decision Engine unblocked.** ADR-007's `decide()` and ADR-008's
fail-mode envelope have a concrete contract for what `ContextSchemaViolation`
means and when it's raised. The engine can ship M2.1/M2.2/M3.4 against this
ADR without further open questions on the schema surface.

**Policy-author DX.** Compliance officers writing YAML get load-time errors
("field `notional` not in schema `trading` — did you mean `notional_usd`?")
instead of production fail-mode DENY surprises. The `agsignal lint policy`
command (decision 8) becomes the gating tool for DRAFT→PREVIEW promotion;
PRD M1.5's policy lifecycle is stronger as a result. IDE plugin authors
get JSON Schema export for free.

**Multi-domain story.** A single AGSignal engine can host trading + treasury +
healthcare schemas with one map and per-policy `context_schema:` binding
(decision 7). The PRD §10.1 success criterion "two distinct domain plugins
integrated" has an unambiguous mechanical contract: each plugin registers
its schema under a unique name, writes policies that bind to that name, and
the engine never confuses them.

**Schema evolution discipline.** Decision 6 forces minor-version additivity
and major-version explicit migration. Compliance officers can rely on
"schema 1.x changes never break my policy"; engineers can rely on "schema
2.0 surface area is reviewed in code review." The
`context_schema_version` pin in DecisionRecord makes audit-time
reconstruction unambiguous: every Decision Audit entry names the exact
schema version that validated its capsule, parallel to
`policy_config_hash` for the policy.

**Performance.** Pydantic v2's Rust core (cached `TypeAdapter` per schema
at construction) keeps evaluate-time validation inside the §9.1 latency
budget (p99 ≤ 5ms for 100-rule policies); the strict-mode default avoids
the ~30% slowdown that lax-mode coercion adds for primitive-heavy
capsules. Policy-load validation is a one-time cost amortized across all
subsequent evaluations.

**Operational implications.** Schema hot-reload follows the same
last-known-good discipline as policy hot-reload (ADR-008 §6); a malformed
schema candidate quarantines without taking down the engine. The
`extra: "forbid"` recommendation (decision 5) gives operators a
diagnostic edge — capsules carrying drift fields surface as
`engine_failure_context_invalid` audit entries naming the unexpected
field, accelerating root-cause for caller-side bugs.

**Constraints on domain plugins.** Domain plugins MUST own
`ContextSchema` definition (PRD §8.1, restated). A plugin cannot rely on
core to invent a schema; it must declare one (or opt into the reserved
`default` no-schema name, which disables M3.4 validation and is intended
only for prototyping). Plugins that need versioned migration today must
upgrade their callers; they cannot rely on AGSignal to bridge.

**v1 → v2 evolution path.** When the §2.2 v2+ `AgentGovernor` Protocol
extracts from the adapter shape, ContextSchema becomes a method on that
Protocol (`AgentGovernor.context_schema() -> type[BaseModel]`). The
construction-time map (decision 2) absorbs cleanly:
`Engine(context_schemas={name: governor.context_schema() for name, governor
in governors.items()})`. Cross-version capsule migration, IDE-server
support, and visual schema authoring are natural commercial-plugin
surfaces consuming this ADR's contract.

## References

- PRD §1.2.4, §2.2, §2.5, §8, §9.1, §9.3, §9.5, §10.1, §12.2, M1.5, M2.1–M2.4, M3.1–M3.4, §11 ADR-009 row (`agent_governance_control_plane_prd.md`)
- ADR-004 (Plugin Extension API Surface) — `2026-05-08-extension-api-surface.md`
- ADR-007 (Decision Engine Internal Shape) — `2026-05-08-decision-engine-shape.md`
- ADR-008 (Fail-mode Semantics) — `2026-05-08-fail-mode-semantics.md`
- Vision B+ scope sketch (`docs/internal/superpowers/specs/2026-05-08-vision-b-plus-design.md`)
- [Pydantic v2 Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) — basis for decision 5 (no-coercion default)
- [Pydantic v2 TypeAdapter](https://docs.pydantic.dev/latest/concepts/type_adapter/) — caching pattern that meets §9.1 latency budget
- [Pydantic v2 JSON Schema export](https://docs.pydantic.dev/latest/concepts/json_schema/) — backs decision 8 (lint + IDE export from Pydantic source)
- [Pydantic v2 vs JSON Schema validation benchmarks (2026)](https://dasroot.net/posts/2026/02/structured-output-validation-pydantic-json-schema/) — 3.5× throughput delta supporting the JSON Schema rejection
- [Pydantic v2 at Scale (2026)](https://medium.com/@connect.hashblock/pydantic-v2-at-scale-7-tricks-for-2-faster-validation-9bd95bf27232) — TypeAdapter reuse, declarative-constraint-over-validator guidance

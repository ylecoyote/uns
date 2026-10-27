> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Decision Engine Internal Shape

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD §2.5 (Architectural Commitment) and M2.1 / M2.2 lock the two-layer split:
pure `decide(policy, context) → DecisionRecord` wrapped by impure `evaluate()`.
M2.3 locks the `DecisionRecord` schema. M3.1/M3.2 lock the `when`/`then` rule
shape and the operator allowlist. M3.4 locks `ContextSchema` validation at
policy-load time.

What §2.5 does **not** specify is what happens *inside* `decide()` when a
policy contains multiple rules: their iteration order, how matches combine,
what the no-match default is, what `reasons[]` carries, how operators evaluate
within a single `when`, regex semantics for `MATCHES`, error semantics, and
exactly where the impurity boundary sits. Stage 2 production-pattern research
confirms OPA and Cedar both keep the policy engine pure-function, but they
diverge sharply on combination semantics — OPA defaults to deny-overrides,
Cedar uses an explicit forbid-overrides + permit policy form. UNS's DSL
is its own thing; this ADR locks the internals.

## Decision

### 1. Rule iteration order: source order, with optional explicit `priority`

`decide()` iterates rules in **policy YAML source order**. Authors may set an
optional integer `priority:` field on a rule; rules with `priority` set sort
before unprioritized rules (lower numeric value first), and ties resolve by
source order. This makes ordering deterministic regardless of YAML loader
behavior, and the same input always produces the same `DecisionRecord` (M3.1).
Source order is a familiar default for policy authors; `priority` is the
escape hatch for layered policies without resorting to file gymnastics.

### 2. Match combination: deny-overrides, with all matched rules evaluated

`decide()` evaluates **every** rule's `when` predicate (no short-circuit on
first match). It then combines matched outcomes using **deny-overrides**:

- Any matched rule with `then: DENY` → `decision = DENY`
- Else any matched rule with `then: REQUIRE_APPROVAL` → `decision = REQUIRE_APPROVAL`
- Else if at least one rule matched with `then: ALLOW` → `decision = ALLOW`
- Else (no rule matched) → see decision 3

This is the Cedar/OPA precedent for security-sensitive engines: the most
restrictive outcome wins, and adding a new rule cannot accidentally weaken an
existing decision. Configurability is **not** offered in v1 — a per-policy
override knob would let authors silently invert security semantics. If a
future use case demands first-match-wins or permit-overrides, a separate ADR
introduces it as an explicit, named policy-level mode.

### 3. No-match default: DENY (deny-by-default)

If no rule's `when` predicate matches the context, `decide()` returns
`decision = DENY` with `reasons = ["no_rule_matched"]`. Authors who want a
permissive default declare an explicit catchall rule (`when: {}` or
equivalent always-true predicate, `then: ALLOW`). Deny-by-default aligns with
PRD M2.4 (default fail-closed for SAFETY/GOVERNANCE) and avoids the failure
mode where deleting the last rule silently flips the engine permissive.

### 4. `reasons[]` carries every rule's outcome, structured

`reasons[]` is a list of structured entries, one per rule evaluated:

```
{ rule_id: str, matched: bool, predicate: str, then: ALLOW|REQUIRE_APPROVAL|DENY|null }
```

`then` is `null` for non-matching rules. The list is in the iteration order
defined by decision 1. This supports M7.3's "why was this denied?" predicate-
by-predicate reconstruction and gives auditors the full trace, not just the
winning rule. Free-form prose belongs in `log_decision_reasoning` (M7.3), not
here.

### 5. Operator evaluation within `when`: short-circuit boolean, left-to-right

`when` predicates are evaluated **left-to-right with short-circuit semantics**
for `and` / `or`. Two operators on the same field evaluate left-to-right; the
DSL does not promise commutativity. Authors who need order-independence write
explicit `and`/`or` groupings. Short-circuit is required so that a
`field EXISTS and field GT 100` predicate does not raise on missing fields.

### 6. `MATCHES` regex: RE2 syntax, anchored, length+complexity capped

The `MATCHES` operator uses **RE2 syntax** (linear-time guarantee; no
backreferences) and is **fully anchored** (implicit `^...$`) by default. RE2
sidesteps ReDoS structurally; the M3.2-mandated length and complexity caps
apply on top of RE2 as defense in depth and as a budget constraint. Anchoring
by default removes the most common authoring footgun (a regex meant to match
the whole string accidentally matching a substring). Authors who want
substring matching write `.*pattern.*` explicitly.

### 7. Error semantics: typed exceptions, `decide()` does not swallow

`decide()` is pure but **not** total. It raises typed exceptions for
contract violations:

- `ContextSchemaViolation` — context references a field whose type does not
  match the registered `ContextSchema` (M3.4). Should be caught at validation
  time; raised here as defense in depth.
- `PolicyEvaluationError` — runtime evaluation failure (e.g., regex compile
  failure that escaped policy-load checks, type mismatch in numeric compare).
- `MissingFieldError` — `when` predicate references a field absent from the
  context, with no `EXISTS` guard. Subclass of `PolicyEvaluationError`.

`decide()` **raises**; it does not return DENY-with-reason on internal errors.
Mapping exceptions to a fail-closed `DecisionRecord` is `evaluate()`'s job
(M2.4 / ADR-008 fail-mode), so the impure layer owns the audit-emission and
fallback policy. This keeps `decide()` honest: pure functions either return a
valid result or raise.

### 8. Purity boundary: no I/O, no shared state mutation; allocation and
    debug-callback emission permitted

`decide()` MUST NOT perform I/O (no DB, no network, no filesystem, no audit
emission, no metrics emission). It MUST NOT mutate any state outside its own
stack frame. It MAY:

- Allocate freely (no caller-visible side effect).
- Invoke a caller-supplied **debug callback** if and only if the policy is
  evaluated in an explicit debug/trace mode and the callback is passed in as
  a parameter. The callback receives structured trace events; it MUST NOT be
  consulted for decision logic. Default is no callback.
- Read from an **internal predicate-compilation cache** keyed by
  `policy_config_hash`. The cache is a process-local memoization of compiled
  regexes and parsed predicates; it is observably equivalent to recompiling
  on every call (same inputs → same outputs).

Audit emission, metric emission, callback-URL registration with the
Approval Workflow, and DecisionRecord persistence all live in `evaluate()`.

## Rejected

### First-match-wins (decision 2)

Rejected. First-match-wins is simpler to reason about for individual rules,
but it makes rule order load-bearing for security correctness. A compliance
officer who reorders rules for readability could silently flip a DENY to an
ALLOW. Deny-overrides removes that footgun.

### Permit-overrides / all-must-allow intersection (decision 2)

Rejected. Permit-overrides inverts the security default; intersection
semantics make it impossible to express "DENY this specific case" without
restructuring every other rule. Neither matches the regulated-deployment
target audience.

### Explicit per-rule precedence operators in DSL (decision 2)

Rejected for v1. Adds DSL surface area to solve a problem the
deny-overrides default already handles. The optional `priority:` field
(decision 1) covers the legitimate "this rule must run first" case without
introducing per-rule combination semantics.

### Permissive (ALLOW) no-match default (decision 3)

Rejected. ALLOW-by-default contradicts the "regulated enterprise" target
audience and PRD §9.2's GUARANTEED-delivery framing. The catchall-rule
escape hatch is explicit and reviewable in policy YAML.

### Only the winning rule's reason in `reasons[]` (decision 4)

Rejected. Auditors investigating "why was this denied" need every
predicate's outcome, not just the last one that matched. Compactness is not
worth blinding the audit trail.

### PCRE / Python `re` flavor for `MATCHES` (decision 6)

Rejected. Both flavors admit pathological backtracking patterns; ReDoS caps
help but do not eliminate the class. RE2 makes the worst case linear-time
by construction.

### Unanchored regex default (decision 6)

Rejected. Unanchored is the more common authoring footgun; anchored-by-default
is the safer default for governance policy. Substring matching remains
expressible with explicit `.*` wildcards.

### `decide()` returns DENY-with-reason on internal errors (decision 7)

Rejected. Coupling fail-mode policy into the pure layer would force every
caller of `decide()` (including unit tests) to share `evaluate()`'s
fail-closed behavior. Keeping the fail-mode decision in `evaluate()` (and
its ADR-008 contract) preserves `decide()`'s testability and lets the
impure layer remain the single owner of audit emission on failure.

### Memoization cache forbidden inside `decide()` (decision 8)

Rejected. A process-local cache keyed by `policy_config_hash` is observably
equivalent to recompiling per call (pure-function semantics preserved) and is
necessary to meet the M2 / §9.1 latency target (p99 ≤ 5 ms for 100-rule
policies). The cache is an implementation detail; it does not change the
input-output contract of `decide()`.

## Consequences

### Testability

`decide()` is fully unit-testable in isolation: feed a policy and a context,
assert on the returned `DecisionRecord` or the typed exception. No mocks
required. The structured `reasons[]` (decision 4) makes failure assertions
specific — tests can check that rule X matched and rule Y did not, not just
that the final decision was DENY. The deterministic iteration order
(decision 1) means tests do not need to be tolerant of reordering.

### Implications for policy authors

- Source order matters when no `priority` is set; readability and ordering
  are coupled by default. Use `priority:` to decouple them when needed.
- Deny-overrides means adding a new DENY rule is always safe. Adding a new
  ALLOW rule cannot weaken an existing DENY.
- The deny-by-default no-match behavior means an empty policy denies
  everything. Authors writing permissive policies must include an explicit
  catchall.
- `MATCHES` patterns are anchored; substring matching needs explicit `.*`.

### Performance implications

- Evaluating every rule (no short-circuit) is O(n) in rule count. PRD §9.1
  targets p99 ≤ 5 ms for 100-rule policies, well within budget for typical
  predicate complexity. Policies that approach the budget can opt into
  `priority:` ordering and simpler predicates.
- The predicate-compilation cache (decision 8) amortizes regex compile and
  predicate parse across calls with the same `policy_config_hash`,
  preserving the §9.1 target under hot-reload.
- The structured `reasons[]` allocation is bounded by rule count; for very
  large policies this is the dominant per-call allocation. Acceptable at
  v1 scale; revisit if profiles show it dominating p99.

### Implications for `evaluate()` and audit

- `evaluate()` owns all fail-mode policy. It catches `decide()`'s typed
  exceptions, applies M2.4 / ADR-008 fail-closed semantics, and writes the
  resulting fail-closed `DecisionRecord` to the Decision Audit stream
  (M6.1) — including a reason indicating internal error.
- The structured `reasons[]` is what flows into `log_decision_reasoning`
  (M7.3). The MCP tool's "structured trace" requirement is satisfied by
  decision 4's shape directly; no additional translation layer is needed.

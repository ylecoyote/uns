> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Decision Engine Fail-mode Semantics

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD §1.2.4 and §2.5 lock UNS as a pre-execution-first control plane with a
two-layer Decision Engine (`decide()` pure + `evaluate()` impure wrapper). PRD
M2.4 names the default — fail-closed for SAFETY/GOVERNANCE, configurable for
OPERATIONAL/INFORMATIONAL — but does not specify the mechanics. PRD M1.5 has
already locked hot-reload version pinning for in-flight evaluations, and §9.2
locks the GUARANTEED delivery invariant for SAFETY/GOVERNANCE notifications.
Stage 2 anti-pattern research (`stage2-pre-vs-post-execution.md`) warns that
brittle governance becomes a data-plane availability problem; this ADR locks
behavior so a degraded engine never silently allows risky actions and never
stalls low-risk traffic.

## Decision

### 1. Per-intent default fail-mode

| Intent          | Default fail-mode                                    |
|-----------------|------------------------------------------------------|
| SAFETY          | fail-closed → `DecisionRecord(decision=DENY, reason=engine_failure_<type>)` |
| GOVERNANCE      | fail-closed → DENY with `reason=engine_failure_<type>`                       |
| OPERATIONAL     | fail-closed by default, but configurable per-policy (DENY \| REQUIRE_APPROVAL \| ALLOW) |
| INFORMATIONAL   | fail-open → ALLOW with `reason=engine_failure_<type>` (preserves observability without blocking low-risk traffic) |

Fail-mode never returns `REQUIRE_APPROVAL` for SAFETY/GOVERNANCE: a degraded
engine must not synthesize approval workflow state.

### 2. Configurability mechanism

Configuration lives in **policy YAML with global defaults**. Each
`GovernancePolicy` MAY declare a `fail_mode:` block; if absent, the engine
falls back to the UNS global config defaults from §1. SAFETY and
GOVERNANCE policies MAY tighten (always DENY) but MUST NOT loosen below DENY.
OPERATIONAL/INFORMATIONAL policies MAY override in either direction. Override
attempts that violate the SAFETY/GOVERNANCE floor are rejected at policy load.

### 3. Triggering conditions ("engine failure")

Exhaustive list. Any of these short-circuit `decide()`/`evaluate()` and emit a
fail-mode `DecisionRecord`:

- `engine_failure_decide_exception` — uncaught exception inside `decide()`
  (operator type errors, null deref, arithmetic, etc.).
- `engine_failure_policy_malformed` — policy YAML fails parse/validation at
  evaluation time (defense in depth — load-time validation is the primary
  guard).
- `engine_failure_context_invalid` — context capsule fails the registered
  `ContextSchema` despite schema-load-time validation (e.g., schema drift,
  caller bug).
- `engine_failure_evaluation_timeout` — bounded wall-clock cap on
  `decide()` (default: 250 ms; configurable). Triggered, e.g., when M3.2
  ReDoS cap is hit on `MATCHES`.
- `engine_failure_attribute_source` — any attribute-resolver hook (today:
  `IdentityProvider`; future: registered attribute plugins) raises or times
  out.
- `engine_failure_internal` — catch-all (resource exhaustion, programmer
  error). MUST be rare and MUST surface in operational alerting.

This list is closed: new failure types require an ADR amendment. Fail-mode is
**not** triggered by ALLOW/DENY/REQUIRE_APPROVAL outcomes — those are normal
decisions, not failures.

### 4. Audit semantics

Every fail-mode decision MUST produce a Decision Audit entry (M6.1). The
entry carries:

- `decision` = the fail-mode outcome (DENY / ALLOW / REQUIRE_APPROVAL per §1).
- `reasons` = `["engine_failure_<type>", "<short error class>", "<sanitized
  message>"]`. Stack traces and raw context are excluded from the audit body
  (use `context_hash`); raw error context is captured in the operator
  diagnostic stream, not the audit ledger.
- `fail_mode = true` (new boolean field on the audit envelope; existing
  `DecisionRecord` schema unchanged so M2.3 stays additive-only).
- `policy_config_hash` set to the pinned version per M1.5 if available;
  otherwise `policy_config_hash = "unresolved"`.

### 5. Notification on fail-mode

Yes. Every fail-mode decision emits an OPERATIONAL notification with
`dedup_key = engine_failure_<type>:<policy_id>` and a per-(type, policy)
suppression window (default 60 s) so that a flapping attribute source does not
flood the operator channel. Fail-mode rate (per-minute) is a first-class metric
(`uns_engine_fail_mode_total{type,intent,policy_id}`), and sustained
elevation triggers commercial Enterprise-Dashboards alerting (out of OSS
scope). The OPERATIONAL notification is distinct from the user-facing DENY
that the caller receives.

### 6. Hot-reload failure

When a candidate policy YAML fails validation at hot-reload time:

- In-flight evaluations: continue with their pinned version (locked by M1.5).
- New evaluations: **continue using the previous validated version**
  (last-known-good). The reload is rejected, the malformed candidate is
  quarantined, and an OPERATIONAL notification is emitted to the policy
  author. The engine does NOT switch to per-decision fail-mode at the
  policy-load layer; degrading from a working policy to fail-closed because
  the new version is malformed would be a self-inflicted denial of service.
- Operator action is required to clear the quarantine (re-deploy a valid
  YAML). The previous version remains canonical until then.

### 7. GUARANTEED delivery interaction

The notification of a fail-mode-DENY for a SAFETY/GOVERNANCE decision
inherits GUARANTEED semantics (§9.2) — it is delivered, escalated, or
visibly degraded, never silently dropped. The fail-mode flag does not
weaken the delivery guarantee; it only annotates *why* the decision was
DENY. The OPERATIONAL self-notification from §5 is best-effort (standard
OPERATIONAL semantics) and is separate from the user-facing GUARANTEED
SAFETY/GOVERNANCE notice.

### 8. Recovery mechanism

Per-evaluation degraded mode in v1 OSS core: each `evaluate()` independently
attempts the full path and falls into fail-mode on failure. Rationale:
simplest semantics, no shared state, no health check coordination. Sustained
fail-mode rates surface through the §5 metric and through the
`UNS_FAIL_MODE_RATE_HIGH` operator alert; manual remediation (config
fix, attribute-source restart) is the v1 recovery path.

A circuit-breaker pattern (open the circuit on a per-attribute-source error
threshold; serve fail-mode without retrying until cooldown) is **deferred to
the commercial Enterprise-Dashboards / DurableWorkflow plugin surface** — it
needs durable state and an operator console, neither of which belong in the
OSS core. Break-Glass is an `OverrideAuthority` operator action (commercial
plugin), not a fail-mode behavior.

## Rejected

- **Universal fail-open.** Rejected: violates the SAFETY/GOVERNANCE invariant
  that high-risk actions MUST NOT proceed without affirmative authorization.
- **Universal fail-closed.** Rejected: blocking INFORMATIONAL traffic on
  engine glitches degrades observability without proportionate safety
  benefit.
- **Per-decision fail-mode at policy-load layer (refuse to evaluate when new
  YAML is malformed).** Rejected: turns a publishing typo into a fleet-wide
  outage; inverts the principle that the previous valid policy is the safest
  fallback.
- **No audit on fail-mode.** Rejected: every authorization-side outcome must
  be reconstructable from the audit ledger, including outcomes produced by a
  degraded engine. Otherwise §10.1 audit-completeness invariant breaks.
- **Unbounded retries inside `evaluate()` on attribute-source failure.**
  Rejected: amplifies a slow dependency into a tail-latency outage; the
  bounded timeout in §3 plus per-evaluation degraded mode in §8 is the safer
  shape.

## Consequences

- Operators can rely on a closed list of fail-mode reasons for runbook
  authoring; no surprise DENY causes.
- Audit ledger remains complete during partial outages — every fail-mode DENY
  is reconstructable, supporting Article 12 record-keeping (§14.2.1) even
  when the engine is degraded.
- Policy authors gain explicit fail-mode override per OPERATIONAL/
  INFORMATIONAL policy, but cannot loosen SAFETY/GOVERNANCE; load-time
  validation enforces this.
- Commercial plugin surface gains a clean opportunity: circuit-breaker
  dashboards, durable fail-mode metrics, and break-glass override flows are
  natural Enterprise-Dashboards / Break-Glass features that consume the
  OSS-emitted `uns_engine_fail_mode_total` metric and `fail_mode=true`
  audit entries.
- Hot-reload last-known-good behavior creates an observability requirement:
  policy authors must monitor the OPERATIONAL "policy quarantined"
  notification or risk running on stale policy indefinitely.
- Per-evaluation degraded mode in OSS core is intentionally simple; high-
  throughput deployments with frequent attribute-source flaps will see
  elevated tail latency until they install the commercial circuit-breaker
  plugin or harden the upstream source.

## References

- PRD §1.2.4, §2.5, §9.2, M1.5, M2.4, M6 (`agent_governance_control_plane_prd.md`)
- Stage 2 pre-vs-post-execution research (`docs/internal/superpowers/specs/2026-05-08-stage2-pre-vs-post-execution.md`)
- Stage 2 production-pattern matrix (`docs/internal/superpowers/specs/2026-05-08-stage2-production-pattern-matrix.md`)
- Vision B+ scope sketch (`docs/internal/superpowers/specs/2026-05-08-vision-b-plus-design.md`)

> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Approval Workflow Semantics

Date: 2026-05-08

Updated: 2026-05-08 — DecisionRecord schema referenced throughout this ADR was
expanded after initial commit per Stage 2 production-audit research (Perplexity Deep
Research on field completeness vs OPA / Cedar / AVP). The expanded field set is
authoritative in PRD M2.3; this ADR's contractual semantics (retry, signing, timeout,
escalation, polling, restart, Protocol behavior diff) are unchanged. The amendment
adds required `engine_version` + `subject_id` and optional `tenant_id` / `resource_id` /
`resource_type` / `trace_id` / `span_id` / `parent_span_id` / `parent_decision_id` /
`request_origin` / `model_id` / `model_version` fields. Callers and commercial plugin
vendors MUST conform to the expanded schema; the wire-level callback contract is
unchanged.

Status: Accepted

Linear: TBD

## Context

PRD §2.4 and M5 lock the Approval Workflow as async-by-default with callback/webhook
as the primary transport, polling as fallback, and engine-side `evaluate()` that never
blocks waiting. PRD M5.6 marks the exact retry / timeout / escalation / sync-wrapper /
restart-recovery semantics as ADR-pending. Stage 2 production-pattern matrix research
across Temporal signals, Step Functions callback tokens, Restate awakeables, Airflow
HITL, and Casbin custom orchestrators yielded the five-method `WorkflowOrchestrator`
Protocol in M8.3. Stage 2 production-audit research subsequently expanded the
`DecisionRecord` schema referenced by this ADR (PRD M2.3) to include the additional
fields production OPA / Cedar / AVP audit systems treat as fundamental. This ADR ratifies
the remaining contractual semantics so domain plugin authors and commercial plugin vendors
can build against a stable contract; the `DecisionRecord` field list is authoritative
in PRD M2.3.

## Decision

**1. Callback retry semantics.** UNS retries callback POSTs on transport failure
(non-2xx, timeout, connection error) using exponential backoff with jitter. Default
schedule is 5 attempts over ~10 minutes (e.g., 15s / 45s / 2m / 4m / ~3m), refining the
PRD §M5.2 hint of 3/10min. Cap and curve are configurable per-deployment but bounded:
implementations MUST NOT exceed 24 hours of total retry duration without operator opt-in.
On final exhaustion, UNS writes a Delivery Audit failure entry AND a degraded-decision
marker on the Decision Audit entry; the decision remains queryable via polling (M5.3).
UNS never silently drops an approved decision.

**2. Callback signing.** HMAC-SHA256 signing is **enabled by default** using the
Default IdentityProvider's session key (M8.4). Signature is carried in the
`X-UNS-Signature: sha256=<hex>` header over the canonical request body; a
companion `X-UNS-Timestamp` header guards against replay (caller MUST reject
timestamps outside a configurable skew, default ±5 minutes). Signing MAY be disabled
at registration time per `callback_url` for trusted-network deployments. Commercial
JWS-Identity replaces this with signed payload bodies; the Protocol contract is the
same (ship a verifiable signature; algorithm pluggable).

**3. Timeout semantics.** A `PENDING_APPROVAL` decision transitions to `TIMED_OUT`
when no terminal ACK arrives within the policy-declared `approval_timeout`. Default
is **30 minutes**; configurable per-policy via `then.approval_timeout_minutes` and
overridable per-intent (SAFETY tighter, GOVERNANCE looser). Timeout is a **terminal
state by default** (decision finalizes as `TIMED_OUT`, not `REJECTED`); callers
treat it as decision-not-rendered rather than denial. Timeout fires the same callback
path as APPROVED/REJECTED with `decision = TIMED_OUT` so callers always receive a
terminal signal.

**4. Escalation.** OSS core supports **single-level escalation only**: if a notification
times out at the channel layer (M1.3 SAFETY re-escalation) before the decision-level
`approval_timeout` expires, the notification re-emits to the policy-declared escalation
recipient set. Decision-level multi-step escalation chains (re-notify approver A, then
B, then C with separate timers) are **deferred to commercial DurableWorkflow**. The OSS
lightweight orchestrator does not own multi-actor approval routing.

**5. Sync wrapper.** **No OSS sync wrapper ships in v1.0.** PRD §2.4 commits the engine
to async-only at core; the agent runtime owns suspension/resumption. Callers without an
async runtime use the polling endpoint (M5.3) or install the commercial DurableWorkflow
plugin which exposes a sync facade. Shipping an OSS `evaluate_sync()` would force a
threading-or-event-loop choice into the core API and re-introduce the engine-side
waiting we explicitly rejected.

**6. Polling fallback details.** Recommended client poll interval is **5 seconds**
minimum; UNS rate-limits the polling endpoint at **2 req/sec per `decision_id`**
(429 on excess). The polling endpoint and the callback POST return **the same
`DecisionRecord`** and are eventually consistent (callback typically arrives first on
ACK; polling reflects the same finalized state within one rate-limit window). Polling is
documented as **fallback-only**; clients SHOULD register a `callback_url` whenever
webhook infrastructure is available.

**7. OSS lightweight orchestrator restart behavior.** The in-memory default
`WorkflowOrchestrator` is **non-durable across platform restart** (PRD §2.9). On
restart, in-flight `PENDING_APPROVAL` decisions are **lost from orchestrator state**
but **recoverable from the Decision Audit Ledger** (M6.1) by an operator-run reconcile
job. UNS core does **not** auto-replay pending decisions on restart; the documented
fail behavior for non-regulated deployments is "caller MUST treat platform restart as
decision lost and re-evaluate." Regulated deployments install the commercial
DurableWorkflow plugin which preserves wait state across restart via Temporal/Restate.

**8. WorkflowOrchestrator method behavior diff.** All five Protocol methods (M8.3) carry
the same input/output contract regardless of backend. OSS-default and DurableWorkflow
differ only in durability guarantees: `expireApproval()` in OSS is a synchronous timer
firing in-process; in DurableWorkflow it is a durable timer surviving restart.
`queryApproval()` in OSS may return `LOST_ON_RESTART` as a status; DurableWorkflow never
returns this status. Plugin contract: implementations MUST document which statuses they
emit; callers consuming the Protocol MUST handle the status union, not specific backends.

## Rejected

- **Sync-block as default.** Re-introduces engine-side waiting that PRD §2.4 explicitly
  rejects; couples core API to a thread/event-loop runtime choice.
- **Engine-side polling of approver UIs.** Pushes orchestration responsibility into the
  decision engine; conflicts with the two-layer pure-`decide()` commitment (§2.5).
- **Polling as default transport.** Stage 2 research consistently identifies polling as
  the weakest production pattern; webhook is the documented strong-form contract.
- **Auto-replay of pending decisions on OSS restart.** Implies durability guarantees the
  in-memory orchestrator cannot honor; would mask correctness failures in non-regulated
  deployments where the lightweight orchestrator is the explicit choice.
- **Multi-level escalation chains in OSS core.** Belongs in DurableWorkflow plugin where
  durable timers and approver-routing state can be modeled correctly; OSS lightweight
  orchestrator scope is single-actor, single-timeout.
- **Optional or off-by-default callback signing.** Default IdentityProvider session keys
  are already present (M8.4); shipping unsigned callbacks by default would establish a
  weaker baseline than the OSS already supports.

## Consequences

**Enables:** Domain plugin authors can build against a stable callback/polling contract
without waiting for commercial plugin selection. Commercial DurableWorkflow vendors have
a clear differentiator surface (multi-level escalation, durable timers, restart-survival,
sync facade). Callers can adopt OSS-only for non-regulated workflows and migrate to
DurableWorkflow without changing their `callback_url` integration.

**Constrains:** Callers MUST implement receiver-side idempotency on `decision_id` (PRD
M5.2 AC). Callers MUST handle `TIMED_OUT` as a non-rejection terminal state. Non-regulated
deployments accept that platform restart loses pending decisions and requires reconcile;
this is the documented price of avoiding a Temporal/Restate dependency in OSS core.

**Migration:** Callers integrating against pre-ADR drafts that assumed sync-block, 3-retry
hardcoded backoff, or unsigned callbacks must update to the contract above. The
`callback_url` registration surface gains optional `signing_disabled` and
`approval_timeout_minutes` fields; defaults preserve secure-by-default behavior.

## References

- [Temporal HITL signal pattern](https://temporal.io/blog/very-long-running-workflows) - durable wait/resume semantics that DurableWorkflow Temporal adapter targets
- [AWS Step Functions callback tokens](https://docs.aws.amazon.com/step-functions/latest/dg/callback-task-sample-sqs.html) - canonical task-token retry/timeout pattern
- [Restate awakeable durability model](https://docs.restate.dev/concepts/durable_building_blocks/) - exactly-once wake-up reference; informs idempotency requirement
- [HMAC webhook signing best practices (Stripe pattern)](https://stripe.com/docs/webhooks/signatures) - timestamp-plus-signature replay protection precedent
- Stage 2 production-pattern matrix (`_UNS/docs/internal/superpowers/specs/2026-05-08-stage2-production-pattern-matrix.md`) - five-method `WorkflowOrchestrator` Protocol derivation
- Stage 2 pre-vs-post-execution analysis (`_UNS/docs/internal/superpowers/specs/2026-05-08-stage2-pre-vs-post-execution.md`) - control-plane-only viability framing

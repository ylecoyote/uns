# UNS remediation review brief

Updated 2026-10-20 (local date). Historical independently reviewed target: **`ba46a311d071736a6beca241a6e43a1407f29f3b`**. Current deployment candidate: **`07ef52a87b45128b77715f64c8b0e5f8f91387a9`**, described below. Iteration 2 base: `3f6005fa2907c1ecdac2e34eb97987ac2ab6af9a`; original remediation base: `b508cc367f9eccdec5a1cbec2b1c691d16d84132`. Subsequent documentation/receipt commits preserve this application code.

Both iterations are now integrated on **main** through `76fc43e`, with the same reviewed application source. [Consolidated baseline](CONSOLIDATED_BASELINE.md) records the local merge and fresh Python/console/package verification; use main for the current handoff.

This is an author-prepared handoff, not a production certification. An Astra/ultra implementation team addressed the earlier reproduced failures, and separate focused reviewers found additional issues that were repaired. Review the code and failure behavior independently; test totals and line coverage are supporting evidence, not proof of every interleaving.

## Subsequent deployment-candidate correction

The [deployment smoke report](DEPLOYMENT_SMOKE.md) records source `07ef52a87b45128b77715f64c8b0e5f8f91387a9`, which supersedes the earlier application target for current code. Container execution found distribution/probe/WebSocket packaging gaps; browser smoke found ACK context and UTC projection defects. They are fixed with 11 added regressions, 1,776 passing Python tests and 99 passing live checks. The earlier independent review applies to its frozen target; it is not retroactively claimed for these new corrections. The user subsequently chose the [persistent localhost recording deployment](LOCAL_DEPLOYMENT.md), now verified. Real external recipients remain outside that chosen scope.

## Product boundary

UNS resolves notification obligations, accepts recoverable work, delivers through configured adapters, and records explicit actor responses or timeouts. It also preserves policy versions and controlled policy-change evidence. It does not execute business actions, authorize them through a complete action-policy engine, intercept traffic or provide cryptographic non-repudiation.

An acknowledgment records an actor response, not human comprehension or permission to execute. Policy approval concerns a configuration proposal. The action-authorization models under `uns.governance` remain experimental.

## What changed after adversarial feedback

The first iteration added durable policy snapshots, owner/follower dedup, replay cycles, provider guards, isolated recovery, authenticated/scoped transport reads and explicit retention. The second review supplied 11 executable assertions, all reproduced on its base. [Iteration 2 decisions and dispositions](REMEDIATION_ITERATION2.md) records the exact response, including corrected source claims and by-design behavior.

| Area | Current behavior |
|---|---|
| Dedup ownership | Pending ownership survives TTL expiry; promotion preserves window expiry. Legacy overlapping failure follows the current owner without replacing it or electing parallel work. |
| Replay | Durable successor lineage prevents replay after satisfaction or during successor recovery. Atomic replay claims ownership; failed history remains visible with replay blockers until explicit resolution. Migration conservatively recovers recorded promotion groups, including prior root replay and missing successors. |
| Lease evidence | Completed channels append observations attributed to their original lease even when another channel loses ownership. Authoritative state remains fenced; evidence-store failure cannot trigger immediate fallback. |
| SMTP | Lease rechecks do not double-count sends. Shared deadlines/cancellation prevent later send admission. Already-started effects can finish after timeout and remain UNKNOWN locally. |
| Policy reads | Steady-state inspection/simulation uses one SELECT; acceptance and mutations keep transactional revision locking. |
| Scheduling | Callback initial due times and explicit ordering prevent fresh arrivals from systematically preempting overdue retries. Dispatch and expiry have explicit due-time ordering. |
| MCP | Direct runtime-bound helpers and server wrappers share durable reads, while explicit injected dependencies and legacy unbound behavior remain supported. |
| Retention/audit | Runtime audit clocks align. Successor references protect replay evidence. Non-archive receipt preservation is intentional; CLI help clarifies its storage limits. |

Authentication, override rejection, frontend controls and first-iteration fixes remain in place. There is no force-send override, fleet-wide rate limiter, or new action-authorization capability.

## Current mechanism

```text
Event + host identity + context
  -> policy revision and resolved settings within acceptance transaction
  -> durable notification / owner relationship / pending work / audit
  -> leased provider attempts outside database transactions
  -> qualifying delivery or visible failure
  -> actor response or deadline expiry
  -> independent optional callback and operator inspection
```

Simulation does not create notification/audit/delivery state. `send()` still attempts dispatch before returning; callers needing a fast handoff use `accept()` and a running worker. Idempotency uses principal/source/key plus request fingerprint; semantic deduplication is a separate producer-defined grouping contract.

GUARANTEED requires a selected persistent-channel success or visible exhausted failure. WebSocket success cannot satisfy it. Fallback stops at the first successful selected persistent channel. Default async adapter waits use 10 seconds with a 60-second lease; blocking DNS/SMTP effects already started may outlive that wait. The external call and database commit are not atomic: pauses after the last guard or crashes after provider acceptance can still repeat an external effect.

Response deadlines begin at qualifying delivery. Same-actor/same-state replay retains the original result; conflicting state or actor fails. An administrative retention operation can retire eligible history only under explicit operator parameters and a retained receipt. Normal append behavior is not cryptographic immutability.

## Trust and deployment limits

- The API credential is an operator credential. There is no RBAC or tenant authorization claim. A read-only console does not make that credential read-only.
- Embedded Python and local MCP launch configuration are trusted host boundaries. MCP defaults to read-only; CLI writes require explicit opt-in, a principal, persistent DB and confirmation token.
- The compatibility flag for anonymous legacy HTTP reads is explicit and limited. It never permits WS, mutations, runtime inspection, readiness or metrics.
- Callbacks and custom adapters are trusted code. Custom retrying adapters must obey the provider-attempt guard contract; arbitrary blocking host code can still block an event loop.
- SQLite WAL and PostgreSQL 16 (`postgres:16-alpine`), sustained multi-worker concurrency/load tests, and hosted GitHub Actions CI are verified, whereas real external provider delivery, human comprehension, and multi-node production capacity remain separate operational boundaries.
- Old ownerless dedup suppression and policy fields already lost by historical versions cannot be reconstructed automatically.
- Retention is row-bounded, not byte/time-bounded. It does not prescribe audit/compliance periods or perform automatic VACUUM. Archive storage and restore policy remain operator responsibilities.

## Recorded verification

| Check | Result at iteration 2 implementation |
|---|---|
| Python suite | 1,765 passed; 90.70% combined coverage |
| Static/boundaries | Ruff, mypy across 91 source files, Bandit, UI boundary and whitespace checks passed |
| Packaging | Wheel/sdist, 90 module source identities, separate minimal/full installs, delivery/ACK, repeated migration CLI and unchanged-byte retention preview |
| Independent focused review | 86 runtime/schema/retention tests, actual baseline upgrades and multi-node replay matrices; additional policy and adapter reviews |
| Reviewer reproductions | Baseline 11 failures reproduced. Final untouched file: 5 pass / 6 documented contract/setup mismatches; replacement regression assertions verify the adopted semantics. |
| Frontend/advisory evidence | Unchanged this iteration. Prior 305 console tests and zero-advisory snapshots were not rerun and are historical, not current audit claims. |

[Current testing report](TESTING.md) and [machine-readable receipts](../verification/iteration2/results.json) contain commands, hashes and remaining limits. No publication, deployment or live-database pruning occurred. Independent reviews are focused engineering evidence, not production/security certification. Logs can contain private machine paths; distinguish sanitized sharing copies from original receipts.

## Where to inspect

| Concern | Source and tests |
|---|---|
| Owner/follower transitions, cycles, leases, expiry | `src/uns/runtime.py`, `src/notification/service.py`, `src/notification/adapters/`, `tests/uns/test_delivery_remediation.py`, `tests/uns/test_iteration2_runtime.py`, `tests/notification/test_delivery_attempt_evidence.py` |
| Policy snapshots and linearization | `src/uns/policy_runtime.py`, `src/db/policy_store.py`, `tests/uns/test_policy_authority.py`, `tests/uns/test_policy_read_isolation.py` |
| Auth, lifecycle and scoped reads | `src/uns/api/`, `src/uns/queries.py`, `src/uns_mcp/`, `tests/uns/test_transport_security.py`, `tests/uns_mcp/test_lifecycle.py`, `tests/uns_mcp/test_runtime_bound_reads.py` |
| Real process policy refresh | `tests/uns/test_cross_transport_acceptance.py` |
| Retention and migrations | `src/uns/maintenance.py`, `src/uns/schema.py`, `tests/uns/test_maintenance.py` |
| Console access and dependency changes | `apps/ui/src/auth/`, `apps/ui/src/components/ConsoleSignIn.tsx`, `apps/ui/package-lock.json` |

## Requested adversarial follow-up

Challenge the transition boundaries, not just happy paths: kill processes around acceptance/provider/commit; race expiry and response; change policy during intake; interleave owner failure, follower promotion and replay; exhaust callbacks; create different runtimes/transports in one process; interrupt archive writes and commits; exercise old schemas and large groups.

Verify that explicit legacy/direct-helper paths cannot accidentally become canonical unauthenticated or globally scoped routes. Recheck producer-defined dedup semantics, limits on metadata/payload size, operator privilege assumptions and operational backpressure for the intended deployment. Avoid claiming exactly-once effects from lease checks alone.

For each finding provide severity, precise source location, violated contract, reproduction/failing test, expected and actual behavior, affected profile, confidence and the smallest correction. Label unconfirmed hypotheses. Distinguish code defects from declared limitations and new-feature requests.

Start in an isolated checkout of the target code. The recording demo sends nothing externally:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest tests/uns -q
.venv/bin/python -m pytest tests apps/ui/tests
.venv/bin/python examples/uns_demo.py
```

Use the testing report for static, packaging and console checks. Record the actual commit, dependency versions, checks run and untested areas. This brief contains no private workspace paths; original verification logs may contain machine paths, so label sanitized copies separately from hash-verifiable originals.

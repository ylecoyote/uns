# UNS adversarial remediation, iteration 2

Base: `3f6005fa2907c1ecdac2e34eb97987ac2ab6af9a`. Branch: `remediation/iteration2`. Reviewed implementation: `ba46a311d071736a6beca241a6e43a1407f29f3b`. This is local implementation and verification, not deployment acceptance.

## Contract decisions

1. Pending ownership survives dedup window expiry. Promotion transfers the existing window; it does not restart it. Delivered suppression expires at that window boundary. Older overlapping owners follow the current claim on failure settlement.
2. Replay recovers an unsatisfied obligation. Durable successor lineage blocks replay while a successor is pending or satisfied, even after restart/window replacement. Failed history and dead-letter visibility remain until explicit resolution/replay. No force-send API is added.
3. Non-archive retention preserves full removed operational records in receipts. It expires operational/idempotency records and promises neither payload erasure nor physical database shrinkage. F-08a is by design.

These clarify previously underspecified interactions. Delivery evidence means provider acceptance evidence, not human receipt or business authorization.

## Finding disposition

| Finding | Result and evidence |
|---|---|
| F-01 | Pending owner exclusivity, current-owner follower settlement, monotonic election and preserved expiry. The baseline already fenced the dedup UPDATE, but ignored the election result when promoting followers; the original claim of an unconditional UPDATE was inaccurate. |
| F-02 | Guarded replay, atomic claim, durable successor links, conservative migration, visible replay blockers, retention protection and failed-descendant reassignment. |
| F-03 | Completed channel results survive lease loss as lease-attributed CHANNEL_ATTEMPT_RESULT events. Authoritative aggregate outcome remains fenced. |
| F-04a | SMTP preparation rechecks leases without a second send-start event. |
| F-04b | Deadline/cancellation-aware SMTP admission, remaining socket budgets, no local retry of ambiguous send; timed-out in-flight sends explicitly UNKNOWN. External effects cannot be retracted. |
| F-05 | Warm policy inspection/simulation performs one consistent SELECT; intake/mutation locking and cold hydration preserved. |
| F-06 | Explicit batch ordering and actual initial callback due timestamps. Callback retry starvation reproduced; initial claim of observed SQLite dispatch/expiry insertion ordering was retracted. |
| F-07 | Runtime-bound direct helpers and factory delegation, explicit dependency injection preserved; SUCCESS audit alias also fixed. |
| F-08a | Closed as documented behavior; receipt preservation retained, CLI help clarified. |
| F-08b | Delivery/response audits use Runtime.clock; SQLite returned naive UTC values are interpreted as UTC in checks. |

## Evidence and independent review

The reviewer's exact 11 tests are preserved in `verification/iteration2/reviewer_reproductions.py`; all 11 baseline assertions failed locally. This is evidence of observed behavior, not acceptance of every assertion's contract. New executable regressions are in `tests/uns/test_iteration2_runtime.py`, `tests/uns/test_policy_read_isolation.py`, `tests/notification/test_delivery_attempt_evidence.py` and `tests/uns_mcp/test_runtime_bound_reads.py`.

The original reproduction is intentionally not the final pass gate: it expects no late SMTP completion, stale aggregate outcome mutation, unconditional execution of a now-conflicting replay, and removal of by-design retention payloads. The final tests exercise the documented contracts directly. Re-running the untouched reviewer file produces **5 passed, 6 failed** with these explicit dispositions:

| Original test still fails | Why it is not the final acceptance assertion |
|---|---|
| F-01 | Its setup tries to dispatch a second owner after TTL expiry; that request now correctly follows the original pending owner. A separately constructed legacy overlap is tested for settlement. |
| F-02 | Replay now raises Conflict before the old test reaches its send-count assertion. |
| F-03 | Stale aggregate outcome stays unchanged; the new test asserts the lease-attributed channel result event. |
| F-04b | An admitted blocking SMTP operation can still complete late; new tests assert UNKNOWN evidence, no internal retry and no post-timeout admission. |
| F-07 | Durable delivery and DLQ assertions pass. The last assertion invokes the legacy unbound status helper and expects non-null ACK state for failed delivery, which has not started an ACK deadline. Runtime-bound reads are tested separately. |
| F-08a | Complete removed payloads remain in receipts by documented design. |

 No original test file was removed; the older window-overlap assertion was updated for exclusive pending ownership.

Independent review found and corrected promotion resetting TTL, missing/pruned migration successors, tied replay/promotion timestamps, successful historical replay of a predecessor, and evidence-store failures being mistaken for provider errors. Runtime review also exercises multi-step failed replay chains. Exact receipts, final counts and reviewed code target are recorded in `verification/iteration2/results.json` and `docs/TESTING.md` after verification.

## Operational boundaries

SQLite is the locally exercised database. No live PostgreSQL, real-provider/human-receipt, representative production load, hosted CI, publication or deployment is claimed. Provider side effects remain at least once. SMTP DNS/in-flight operations can outlive async timeout; UNKNOWN cannot be interpreted as no send. Completed observation persistence can itself fail; recovery then retains uncertainty. Process-local rate limits are not fleet-wide limits. Retention is row-bounded, not byte/time-bounded, and historical erased lineage cannot be recovered.

# UNS remediation review brief

Prepared 2026-10-20. Reviewed implementation target: **`902300773d7ad41baefab8e007d0f37981ba6be9`**. Remediation base: `b508cc367f9eccdec5a1cbec2b1c691d16d84132`. Later documentation/receipt commits do not change this code target.

This is an author-prepared handoff, not a production certification. An Astra/ultra implementation team addressed the earlier reproduced failures, and separate focused reviewers found additional issues that were repaired. Review the code and failure behavior independently; test totals and line coverage are supporting evidence, not proof of every interleaving.

## Product boundary

UNS resolves notification obligations, accepts recoverable work, delivers through configured adapters, and records explicit actor responses or timeouts. It also preserves policy versions and controlled policy-change evidence. It does not execute business actions, authorize them through a complete action-policy engine, intercept traffic or provide cryptographic non-repudiation.

An acknowledgment records an actor response, not human comprehension or permission to execute. Policy approval concerns a configuration proposal. The action-authorization models under `agsignal.governance` remain experimental.

## What changed after adversarial feedback

| Area | Remediation |
|---|---|
| Failed-owner suppression | Dedup now records owner/generation and effective obligation. Pending followers remain linked to live work; failure elects one successor rather than silently dropping followers or releasing an alert storm. FAILED owners cannot suppress fresh intake. |
| Exhausted replay | A new replay cycle gets a fresh attempt budget; cumulative attempts and audit history remain. |
| Policy coherence | Cold processes hydrate immutable ACTIVE snapshots. A dedicated monotonic database revision is checked/locked in the acceptance transaction, ordering activation against intake across processes. |
| Producer authority | Differing ACTIVE-policy overrides and adapter-routing/severity metadata bypasses are rejected. No payload can grant an administrative exception. |
| Lease loss | Guards precede fallback channels, built-in internal retries, and queued SMTP effects. Stale database commits remain fenced. Already-sent effects remain uncertain. |
| Recovery lifecycle | HTTP and write-enabled MCP own dispatch, expiry and callback loops. Callback batches cannot hold the expiry loop. CLI shutdown joins workers; standalone writable MCP requires persistent storage. |
| Authentication | Reads, writes, readiness, metrics and WS handshake are authenticated by default. Only minimal liveness is public. WS ACK uses durable Runtime and verified identity. |
| Read isolation | HTTP/MCP readers are bound to their owning runtime. The independent reviewer reproduced cross-runtime disclosures before the fix and verified the original five cases pass afterward. |
| Retention | Explicit bounded dry-run/apply and optional durable archive-before-prune protect unsettled obligations. Continuation cursors prevent oversized groups from starving later groups. |
| Frontend | Runtime-memory operator sign-in, safe cancellation/logout and authenticated reads. Dependency upgrades removed the previously recorded frontend advisories. |

Other corrections preserve full draft/preview policy content, make first-upgrade policy schema creation concurrency-safe, align effective-policy inspection with actual mode resolution, and fix exact channel-array filtering in SQLite instead of serialized substring matching.

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

GUARANTEED requires a selected persistent-channel success or visible exhausted failure. WebSocket success cannot satisfy it. Fallback stops at the first successful selected persistent channel. Default adapter calls are bounded at 10 seconds with a 60-second lease. The external call and database commit are not atomic: pauses after the last guard or crashes after provider acceptance can still repeat an external effect.

Response deadlines begin at qualifying delivery. Same-actor/same-state replay retains the original result; conflicting state or actor fails. An administrative retention operation can retire eligible history only under explicit operator parameters and a retained receipt. Normal append behavior is not cryptographic immutability.

## Trust and deployment limits

- The API credential is an operator credential. There is no RBAC or tenant authorization claim. A read-only console does not make that credential read-only.
- Embedded Python and local MCP launch configuration are trusted host boundaries. MCP defaults to read-only; CLI writes require explicit opt-in, a principal, persistent DB and confirmation token.
- The compatibility flag for anonymous legacy HTTP reads is explicit and limited. It never permits WS, mutations, runtime inspection, readiness or metrics.
- Callbacks and custom adapters are trusted code. Custom retrying adapters must obey the provider-attempt guard contract; arbitrary blocking host code can still block an event loop.
- SQLite is operationally exercised. PostgreSQL behavior, real-provider delivery, human receipt, representative load and hosted CI are not established by local tests.
- Old ownerless dedup suppression and policy fields already lost by historical versions cannot be reconstructed automatically.
- Retention is row-bounded, not byte/time-bounded. It does not prescribe audit/compliance periods or perform automatic VACUUM. Archive storage and restore policy remain operator responsibilities.

## Recorded verification

| Check | Result |
|---|---|
| Python suite | 1,705 passed; 90.17% combined coverage |
| Console | 305 tests passed, with prior 289 retained; types/lint/build passed |
| Static and boundaries | Ruff, mypy across 91 source files, Bandit, UI boundary and whitespace checks passed |
| Dependencies | Zero advisories in current frontend full/production lock audits and installed Python dependency audit |
| Packaging | Wheel/sdist built; 90 shipped Python modules matched source; minimal/full installation and CLI checks passed |
| Installed migration | Legacy pending work preserved through repeated migrations; maintenance dry-run left DB bytes unchanged |
| Focused re-review | Original 5 disclosure reproductions passed after repair; 14 additional isolation/retention edge checks passed at the target commit |

The unpublished local package is not registry-audited. Advisory results are dated snapshots. No publication, deployment or live-database pruning was performed. [Current testing report](TESTING.md) and [machine-readable receipts](../verification/remediation/results.json) contain commands, hashes and remaining limits. The original consolidation evidence remains historical and does not supersede the adversarial findings.

## Where to inspect

| Concern | Source and tests |
|---|---|
| Owner/follower transitions, cycles, leases, expiry | `src/uns/runtime.py`, `src/notification/service.py`, `src/notification/adapters/`, `tests/uns/test_delivery_remediation.py` |
| Policy snapshots and linearization | `src/uns/policy_runtime.py`, `src/db/policy_store.py`, `tests/uns/test_policy_authority.py` |
| Auth, lifecycle and scoped reads | `src/agsignal/api/`, `src/agsignal/queries.py`, `src/agsignal_mcp/`, `tests/uns/test_transport_security.py`, `tests/agsignal_mcp/test_lifecycle.py` |
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

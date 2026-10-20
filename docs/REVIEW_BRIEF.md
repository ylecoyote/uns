# UNS external review brief

Prepared 2026-10-20. Implementation target: **`1f29b9602725628036c7bf55044c68ce9b45f137`**. Consolidation base: `e084b52d4c02c2b6fcd89fb2813f5d5c94efe924`.

This is an author-prepared handoff for independent, adversarial review. It summarizes the intended contracts, their implementation, and recorded local evidence. Treat the claims below as hypotheses to test against source and failure behavior, not as an independent assurance opinion. The requested outcome is a prioritized assessment of correctness, security, operability, and claim accuracy.

## Product and scope

**UNS, Unified Notification Service**, turns an application event into a policy-defined notification obligation, attempts delivery, and records an explicit human response or timeout. It also provides versioned notification policies and controlled policy-change records.

It consolidates an earlier notification implementation and its successor, AGSignal, into one repository. The implementation retains legacy Python namespaces and MCP tool names for compatibility. Public product identity is UNS; the core license remains Apache-2.0.

The supported product includes Python, HTTP and MCP interfaces; Slack, email, PagerDuty and WebSocket adapters; delivery and response auditing; policy loading and version storage; policy-change evidence; and a read-first React console.

**Boundary:** notification acknowledgment is a recorded response, not permission to execute the action described by the notification. Policy-change approval approves a proposed configuration change. The unfinished business-action `ALLOW / REQUIRE_APPROVAL / DENY` evaluator, action approval/resume workflow, network interception, autonomous optimizer and commercial plugin vision are outside the supported product.

UNS does not claim exactly-once external delivery, proof of human comprehension, cryptographic audit immutability, regulatory compliance, or production acceptance.

## Mechanism

```text
Producer event + identity + autonomy context
    -> resolve notification policy and record effective configuration
    -> atomically accept notification, pending dispatch work and audit
    -> claim dispatch work under a lease
    -> attempt selected delivery adapters
    -> commit delivery outcome and, if required, start response deadline
    -> ACK / DISMISS / TIMEOUT with atomic state and audit
    -> optional retriable callback and operator inspection
```

Python 3.11+ is declared supported; recorded local checks used Python 3.12. Storage uses the existing SQLAlchemy stack. SQLite file storage is the tested durable profile. MCP is constrained to major version 1 because its version 2 API is incompatible with the retained integration.

| Concern | Intended contract to verify |
|---|---|
| Simulation | Resolves behavior without delivery, acknowledgment registration, audit mutation or idempotency consumption. |
| Acceptance | Notification state, dispatch work and acceptance audit commit together. Acceptance is distinct from delivery. |
| Sending | `Runtime.send()` accepts and attempts dispatch before returning. It can wait for adapter calls; fast handoff uses `accept()` plus a recovery worker. |
| Policy identity | Accepted work snapshots policy/config identity, effective values, override values and evaluation identity. Defaults also receive a versioned identity. |
| Idempotency | Scope is authenticated principal, source and key, bound to a request fingerprint. Same content retains notification identity; changed content conflicts. |
| Deduplication | Separately suppresses semantically repeated events during a policy-defined window. It is not equivalent to idempotency or exactly-once delivery. |
| GUARANTEED | Requires a selected persistent-channel success or visible exhausted failure. WebSocket success cannot satisfy it. A WebSocket-only configuration must explicitly use BEST_EFFORT. |
| Fallback | Selected persistent channels run in Slack, email, PagerDuty order and stop at the first success. Channel presence does not promise a broadcast to every channel. |
| Retry and recovery | Bounded calls, finite retry budget, leased claims and conditional result commits. Recovery may repeat an external effect after an ambiguous provider-success/local-commit crash. |
| Human response | The deadline starts at first qualifying delivery. PENDING transitions to one terminal ACKED, DISMISSED or TIMED_OUT state. Same-state replay retains the original result; conflicting or late transitions fail. |
| Callback | Terminal state is committed independently of callback delivery. Callback attempts and failures are retained; consumers must deduplicate by event ID. |

The HTTP service runs dispatch and timeout recovery tasks. A persistent MCP-only installation requires an external recovery worker or the HTTP service against the same database. In-memory operation is a demo profile and loses state at exit.

## Policy system

The implemented policy system governs notification behavior. Its lifecycle distinguishes DRAFT, PREVIEW, ACTIVE and RETIRED. The default runtime registry admits ACTIVE policies; shadow loaders isolate PREVIEW policies. Explicit legacy overrides can supersede policy values, so reviewers should examine which obligations are configurable and how overrides are attributed.

Reload validates a candidate snapshot and persists it transactionally before replacing the runtime registry. Invalid reloads should leave the last known good state intact. Already accepted notifications retain resolved settings. Reload is serialized within a process; cross-process activation broadcast is not implemented. Retired versions cannot simply be reactivated; restoring prior behavior requires a new version.

Policy changes follow:

```text
PROPOSED -> SHADOW -> APPROVED -> new DRAFT configuration -> explicit activation
                    \-> REJECTED
```

The underlying delta state model also records APPLIED. A draft-producing operation and an activated notification policy are distinct events.

Shadow evidence binds to baseline and candidate hashes, identifies an evaluator, and declares sample/quality criteria. Required guards and numeric bounds are checked through the persisted transition path. Application checks baseline identity and the approved candidate identity; changed candidates invalidate approval. A new draft leaves active behavior unchanged.

External evaluators supply shadow measurements. The service checks their recorded binding and declared criteria; it does not prove the evaluator's honesty or automatically measure policy quality. Data models and direct database administration are not authorization boundaries.

## Trust and deployment assumptions

- HTTP mutation identity derives from a configured API key/principal. Response payloads must not impersonate a different actor without an explicit trusted override.
- In-process Python callers and embedded MCP host configuration are trusted. A caller-provided principal is not independent authentication.
- Runtime inspection is authenticated. Legacy console read and WebSocket surfaces retain their existing access model and require an authenticated reverse proxy before shared deployment. Public exposure is not an accepted default.
- Audit records are append-only by application convention. Hashes identify configuration content; they are not signatures or protection against a database administrator.
- Notification metadata must not be assumed safe to log or display. Tenant isolation, path access during reload, record visibility and secret handling deserve explicit review.
- Retention is operator controlled. Pending work and idempotency records are not silently purged. Cross-process channel-rate enforcement is not established by the locally tested process-level limiter.

## Recorded evidence and limits

The following are recorded implementation-session results for 2026-10-20. The nine stored receipt hashes were checked while preparing this brief. The tests and advisory databases were not rerun for this handoff.

| Check | Recorded result |
|---|---|
| Python suite | 1,564 passed; combined coverage 89.45%, above the 75% gate |
| Console | 289 tests passed; TypeScript, ESLint and production build passed |
| Static checks | Ruff passed; mypy passed for 88 source files; Bandit passed with a documented lease-clearing false-positive annotation |
| Packaging | Wheel and sdist built; 87 shipped Python modules matched source |
| Installation | Minimal/full wheel imports, CLI help, HTTP/MCP construction, recording-adapter demo and repeated additive migration passed |
| Python dependency audit | No known dependency advisories in that installed environment; the unpublished local package itself was not registry-audited |
| Frontend lockfile audit | **21 advisories remain:** 1 low, 5 moderate, 11 high, 4 critical |
| Frontend production dependency audit | **2 moderate advisories** remain in the router dependency chain; these are part of the remaining frontend risk, not an additional clean bill of health |

The predecessor suite had 1,867 passing tests. The count decreased because obsolete documentation-layout assertions and the superseded Python UI tests were retired; consolidation regressions were added. Review the test diff and inspect whether important behavior lost coverage. Passing totals and aggregate coverage are not proof that failure interleavings are adequately tested.

Known unverified areas: real-provider delivery and human receipt; PostgreSQL-specific behavior; hosted CI; representative load and long-running operational acceptance. No publication or deployment is asserted. Remaining frontend advisories are a release limitation. One SQLAlchemy JSON-operator deprecation warning remains.

## Priority adversarial challenges

These are proposed experiments, not assertions that the listed defects exist. Reviewers should add other failure modes they find.

| Priority area | Experiment or question |
|---|---|
| Transaction boundaries | Kill the process before/after acceptance, audit flush, claim commit, provider response and result commit. Can successful responses exist without recoverable state? Does ordinary exception injection model actual process death adequately? |
| Lease fencing | Delay an adapter beyond the lease, let another worker claim the item, then resume the first worker. Can a stale worker overwrite state? Can timed-out thread/executor work still send after cancellation? Distinguish fenced database writes from external side effects. |
| Idempotency and suppression | Race identical keys across separate processes and transports. Reuse a key with different content. Send semantically duplicate events while the first is pending, failed or dead-lettered. Can suppression silently remove an obligation that was never delivered? |
| Delivery semantics | Combine WebSocket success, persistent failures, missing adapters, rate limits, adapter-local retries and manual replay. Is GUARANTEED accurately named and documented for every outcome? Are all partial outcomes retained? |
| Response and callbacks | Race ACK, DISMISS and timeout around the exact deadline, including across processes and restarts. Saturate the callback queue with failures. Can callbacks or dispatch work delay timeout processing indefinitely, rewrite terminal state, or lose escalation evidence? |
| Policy activation | Inject failure after database persistence but before registry swap. Race reloads, omit policies from a snapshot and restart another process. Are database and process-local policy views coherent within the declared deployment model? |
| Policy-change evidence | Change nested candidate values, bounds, required guards or baseline version after shadow evaluation or approval. Supply stale, missing or fabricated evidence. Try every exposed mutation path, not only the tested store helper. Is the trusted-evaluator boundary honest and usable? |
| Authentication and exposure | Exercise all HTTP and MCP paths, read endpoints, WebSockets, legacy aliases and fixture modes. Can identity be spoofed, data cross principal boundaries, or a reload path access unintended files? Which controls actually depend on a proxy? |
| Installation and upgrades | Start from an older database, not just an empty one. Test partial migrations, unsupported backends, recovery-worker absence, dependency drift and rollback with pending work. Does an additive table bootstrap adequately describe the supported upgrade path? |
| Claims and scale | Verify the console, status APIs, readiness probes and documentation against real state. Exercise large queues, retention growth, large payloads and slow providers. Identify claims whose confidence exceeds the recorded evidence. |

A documented limitation is not automatically a new bug, but the reviewer should judge whether it makes the advertised use case unsafe or impractical. Separate implementation defects from product-boundary objections and requests for new features.

## Source and evidence map

All paths below are relative to the supplied repository at the implementation target.

| Area | Start here |
|---|---|
| Transactional intake, dispatch, response, recovery | `src/uns/runtime.py` |
| Canonical client and composition | `src/uns/client.py`, `src/uns/config.py`, `src/agsignal/app.py` |
| Delivery and adapters | `src/notification/service.py`, `src/notification/adapters/` |
| Policy loading, snapshot persistence, delta enforcement | `src/notification/policy_loader.py`, `src/notification/routes.py`, `src/db/policy_store.py`, `src/db/policy_learning_store.py`, `src/notification/policy_config.py` |
| HTTP/MCP trust boundaries | `src/agsignal/api/auth.py`, `src/agsignal/api/routes_notification.py`, `src/uns/routes.py`, `src/agsignal_mcp/` |
| Focused regressions | `tests/uns/test_runtime.py`, `tests/uns/test_policy_changes.py` |
| Complete contract and local receipts | `docs/PRODUCT.md`, `docs/API.md`, `docs/SECURITY-MODEL.md`, `docs/TESTING.md`, `verification/results.json` |
| Change review | Diff the consolidation base against the implementation target; inspect archived/deleted tests as well as additions. |

Start in a disposable checkout of the supplied implementation target. Do not infer that an old hosted-project URL or an arbitrary branch tip contains this commit.

```sh
git rev-parse HEAD
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest tests/uns -q
.venv/bin/python -m pytest tests apps/ui/tests
.venv/bin/python examples/uns_demo.py
```

Compare the first output to the target hash above. The demo uses a recording adapter and sends nothing externally. Use `docs/TESTING.md` for the remaining static, packaging and console checks. Record dependency versions: unconstrained package releases and advisory databases can change results over time.

## Requested reviewer output

For each finding provide: severity; violated contract; precise source location; reproducible sequence or failing test; observed versus expected behavior; impact and affected deployment profile; confidence; and the smallest suggested correction. A suspected issue without reproduction should be labeled unconfirmed.

Lead with release blockers, then other confirmed defects, documentation overclaims, missing tests and accepted limitations. State the commit and environment reviewed, checks actually run, and what remains untested. Assess local-demo suitability and shared/production readiness separately. Do not treat this handoff, a passing suite or a lack of findings as independent certification.

This brief is standalone and contains no local account paths or credentials. Code-level conclusions require source access. If original verification logs are shared, review their machine-path content first; sanitized copies will not match the hashes of the original receipts and must be labeled accordingly.

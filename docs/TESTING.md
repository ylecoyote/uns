# UNS verification

Run from the consolidated repository with its development environment:

```sh
.venv/bin/python -m pytest tests
.venv/bin/ruff check src tests scripts apps
.venv/bin/mypy -p uns -p notification -p db -p ui_client -p uns_mcp
.venv/bin/bandit -q -r src
.venv/bin/python examples/uns_demo.py
cd apps/ui
npm ci
npm run ci
```

Build a wheel and install it in a separate fresh environment. Verify canonical and legacy imports and command help. The local recording adapter establishes orchestration, not real provider or human receipt.

## Acceptance mapping

| Scenarios | Evidence owner |
|---|---|
| A01 installation and compatibility | Wheel/install smoke and public API tests |
| A02 simulation/no-handler | `tests/uns/test_runtime.py`, SDK tests |
| A03 transport parity | `test_http_sdk_mcp_share_identity_and_actual_delivery` |
| A04 policy isolation | Existing policy-store/loader tests |
| A05 policy/default/override provenance | Runtime metadata tests and SDK/audit-store tests |
| A06 failed reload | `test_policy_reload_failure_keeps_registry_and_database` |
| A07/A08 delivery predicate/config | Runtime failure/configuration tests and delivery service tests |
| A09 restart/claim recovery | Runtime restart and expired-lease tests |
| A10 scoped concurrency/idempotency | Runtime concurrent-intake and transport tests |
| A11 response lifecycle | Runtime timeout, replay and terminal-race tests |
| A12 attribution/audit failure | Runtime transport spoofing and acceptance rollback tests |
| A13/A14 policy-change evidence | `tests/uns/test_policy_changes.py`, existing policy/store tests |
| A15 console and adapters | UI checks, runtime timeline projection, existing host adapter tests |
| A16 documentation | Current docs links, runnable demo, packaging smoke |
| A17 engineering | Full Python suite, lint/type/security/package/UI checks |

The pre-change Python baseline was 1,867 passed and 1 skipped. Baseline Ruff reported 28 issues, primarily experimental governance typing/import style. Final results and unresolved limits are recorded below after verification.

## Optional external smoke

With separately authorized recipients and configured credentials, send one uniquely identified BEST_EFFORT signal, inspect adapter/provider evidence, then test one SAFETY acknowledgment and record the human actor. Do not label a recording-adapter test as this smoke. No external smoke is run by default.

## Historical consolidation result before adversarial remediation

The recorded original suite passed on Python 3.12 using a fresh wheel environment. Subsequent adversarial reproductions invalidated a broad local-acceptance conclusion; these results remain historical evidence, not the current reliability verdict. The MCP dependency is constrained to major version 1 because version 2 removed the API used by the retained integration.

| Check | Result |
|---|---|
| Python suite including consolidation regressions | 1,564 passed |
| Combined Python coverage | 89.45%, above the 75% gate |
| Console | 289 tests passed; type check, ESLint and production build passed |
| Python lint, type check, static security | Ruff passed; mypy passed for 88 files; Bandit passed |
| UI boundary and whitespace | Passed |
| Distribution | Wheel and sdist built; 87 shipped Python modules matched source |
| Clean installation | Minimal and full wheel imports passed; CLI help and HTTP/MCP construction passed |
| Installed demo and schema bootstrap | Recording delivery/restart/ACK passed; migration run twice successfully |
| Installed Python dependency audit | No known dependency advisories; local unpublished UNS package is not registry-audited |
| Frontend lockfile audit | 21 advisories remain: 1 low, 5 moderate, 11 high, 4 critical |
| Frontend production dependencies | 2 moderate advisories remain in the router dependency chain |

Safe lockfile updates reduced the inherited advisory set. Remaining frontend remediation requires broader dependency upgrades. This is a release limitation, not a passing security audit. Development servers remain local-only. Real-provider delivery, human receipt, PostgreSQL acceptance, and hosted CI are unverified; no deployment or publication occurred.

The test count differs from the predecessor because obsolete documentation-layout assertions and the superseded Python UI tests were retired. Current runtime tests remain, with additional crash, concurrency, guard, transport, and audit regressions. One inherited SQLAlchemy JSON-operator deprecation warning remains.

Machine-readable results and raw local receipts are in [verification/results.json](../verification/results.json). This evidence establishes local behavior only, not commercial or production acceptance.

## First adversarial remediation result (historical)

The remediation code target is `902300773d7ad41baefab8e007d0f37981ba6be9`. It preserves the notification-only product boundary and addresses the reproduced reliability, policy and access gaps. Original test files were not removed in this remediation; fixtures/assertions were adapted to explicit authenticated and runtime-scoped contracts.

| Check | Checked result |
|---|---|
| Full Python suite | 1,705 passed, 90.17% coverage against the 75% gate |
| Console | 305 tests passed, including all prior 289; types, lint and build passed |
| Frontend full/production lockfile audits | Zero advisories in both current reports |
| Python installed dependency audit | Zero known advisories; unpublished local package not registry-audited |
| Static and boundaries | Ruff, mypy across 91 files, Bandit, UI boundary and whitespace checks passed |
| Packaging | Wheel and sdist built; 90 Python modules matched source; minimal/full installs and CLI entrypoints passed |
| Installed migration/maintenance | Old pending work preserved through two migrations; retention dry-run left database bytes unchanged |
| Focused independent re-review | Original 5 read-isolation reproductions now pass; 14 additional scoped isolation/retention checks pass |

New cases exercise failed-owner dedup, successor election, replay budgets, stale lease fallback/provider retries, queued SMTP effects, actual subprocess termination, isolated timeout processing, exact policy revision/activation ordering across processes, cold MCP hydration, override/metadata rejection, durable authenticated WebSocket ACKs, MCP idle recovery and signal shutdown, same/mixed-transport read isolation, and archive failure/cursor safety.

Evidence is in [remediation results](../verification/remediation/results.json) and the [focused review record](../verification/remediation/review-findings.md). Original consolidation receipts remain unchanged under `verification/`; their broader acceptance wording was superseded by adversarial validation.

Remaining limits: external-provider and human-receipt acceptance, live PostgreSQL operation, hosted CI and representative production load are unverified. Credentials confer operator access, not RBAC. External effects remain at least once. Historical information already lost by earlier versions cannot be reconstructed. Retention is explicit, SQLite-only and row-bounded, not byte/time-bounded or automatic compliance retention. Existing dependency/framework deprecation warnings are recorded in the test log.


## Second adversarial remediation checkpoint

Implementation target: `ba46a311d071736a6beca241a6e43a1407f29f3b`, base `3f6005fa2907c1ecdac2e34eb97987ac2ab6af9a`. [Contract decisions and dispositions](REMEDIATION_ITERATION2.md) explain the distinction between reproduced behavior and accepted requirements.

| Check | Result |
|---|---|
| Full Python suite | 1,765 passed; 90.70% combined coverage, 75% gate |
| Static/boundaries | Ruff, mypy (91 files), Bandit, UI boundary and whitespace passed |
| Focused independent runtime/schema/retention review | 86 passed, three real baseline-to-upgrade reproductions and multi-node replay matrix; reviewed file hashes retained |
| Policy | Warm reads avoid UPDATE; 131 focused tests, including process ordering and cold bootstrap |
| MCP | 80 focused tests; durable direct reads, explicit injection, factory parity and SUCCESS mapping |
| Adapter/service/runtime | 182 focused tests; deterministic preparation/cancellation barriers, UNKNOWN outcomes, evidence-store failures and lease-loss results |
| Packaging | Wheel and sdist; 90 module source identities matched; separate minimal/full installations, local delivery/ACK, repeated migration CLI and no-write maintenance preview passed |
| Original reviewer file | Baseline 11 failed; final 5 passed / 6 expected contract/setup mismatches individually explained in the iteration report |
| Frontend/dependencies | No frontend/dependency changes; frontend CI and advisory audits were not rerun. Prior 305 console tests and advisory snapshots remain historical evidence only. |

Raw logs, the untouched reviewer reproduction, installed smoke script and SHA-256 manifest are in [iteration 2 receipts](../verification/iteration2/results.json). Validation used Python 3.12.9 and temporary SQLite databases. Two inherited framework deprecation warnings remain; Bandit also prints non-failing unmatched nosec warnings around the existing lease-clear annotation. No production data was modified. External acceptance limitations in the first report still apply.

Reproduce with the development environment and commands above. The reviewer file can be run separately with `python -m pytest verification/iteration2/reviewer_reproductions.py`; its expected residual failures are not the regression gate. Run the installed package smoke from outside the source tree with `python /path/to/repo/verification/iteration2/package_smoke.py /path/to/repo` after building/installing the full wheel.


## Consolidated main merge checkpoint

The canonical main branch fast-forwarded from `b508cc3` through `76fc43e`; application source is unchanged from `ba46a31`. Fresh verification in the canonical checkout passed 1,765 Python tests at 90.70% coverage, 305 console tests plus type/lint/build checks, Ruff, mypy (91 files), Bandit, UI boundary, wheel/source identity (90 modules), installed full-wheel delivery/ACK/repeated migration/no-write retention preview, and the recording demo. The console was freshly installed from its merged lockfile. Existing test/framework warnings are recorded. Advisory databases were not refreshed.

[Consolidated baseline](CONSOLIDATED_BASELINE.md) and [fresh merge receipts](../verification/consolidated/results.json) supersede the iteration checkouts as the current working location. Prior receipts remain unchanged. No remote push, hosted CI, live database migration, real-provider acceptance or deployment occurred.


## Container deployment-candidate verification (current)

The source target `07ef52a87b45128b77715f64c8b0e5f8f91387a9` adds packaging/probe/WebSocket support fixes and browser-discovered audit context/UTC corrections after the consolidated baseline. Full Python verification: 1,776 passed at 90.76% coverage. The installed image passed 99 live HTTP/WebSocket/MCP/recovery checks, module identity and dependency consistency checks, authenticated Compose readiness, and copied-data archive verification. Functional browser flows were exercised in Brave. See [deployment smoke](DEPLOYMENT_SMOKE.md) and [receipts](../verification/deployment/results.json). The lasting target and real recipients remain unspecified; this is isolated recording-profile rehearsal evidence, not production deployment acceptance.


## Persistent localhost deployment acceptance

The user accepted localhost plus recording adapters. The pinned application image is unchanged from `07ef52a`; the permanent recording composition and fixed ingress are versioned under `deploy/local/`. All 62 persistent-deployment checks passed, including real network transports, local provider recordings, one-minute timeout, callbacks and restart recovery. App isolation, loopback-only ingress and a consistent SQLite backup were checked. [Runbook](LOCAL_DEPLOYMENT.md) and [receipts](../verification/local-deployment/results.json) record the running deployment. No real-provider or remote-production acceptance is implied.

## Review follow-up verification — 2026-10-24

Base: `7cf5c12c7a25607fff8242b2bdfe115a145dc485`. This follow-up closes the WebSocket response-scope gap, applies the persistence guard to the default ASGI/application-factory path, shares SQLite URL classification across startup and diagnostics, resolves complete obligation lineage, aligns runtime-bound MCP response evidence, and aggregates readiness progress without loading work histories.

| Check | Result |
|---|---|
| Full Python suite (`tests`) | **1,854 passed**, 90.99% combined coverage against the 75% gate |
| New regressions | 16 scoped WebSocket cases, 37 persistence/entrypoint cases, 6 owner/projection cases, and 6 operational-progress cases |
| Python static checks | Ruff passed; mypy passed for 92 source files; Bandit passed |
| Console | 305 tests passed; TypeScript, ESLint, production build, and strict UI boundary passed |
| Generated API types | Refreshed from current OpenAPI; the canonical ACK-path type test passed both Vitest and direct strict TypeScript compilation |
| Distribution | Wheel and sdist built; 91 shipped Python modules matched source bytes; shared database helper present in both artifacts |
| Clean installation | Minimal SDK footprint and full-install application construction passed |
| Installed recording smoke | Delivery/ACK, repeated migration, CLI help, and unchanged-byte retention preview passed |
| Patch hygiene | `git diff --check` passed; dependency declarations and lockfiles unchanged |

Regression evidence lives in `tests/uns/test_scoped_websocket_auth.py`, `tests/uns/test_persistence_entrypoints.py`, `tests/uns/test_obligation_projection.py`, and `tests/uns/test_operational_progress.py`. The owner tests create twelve actual coalesced notifications and exercise successive promotion, complete exhaustion, root replay, and registered MCP/HTTP parity. The WebSocket tests cover both Bearer and browser-subprotocol authentication, assert unchanged durable state/audit on rejected commands, and preserve stream reads. Restoring the original WebSocket ACK handler in an isolated regression control caused all eight lower-scope rejection cases to fail as expected.

The two legacy MCP response-shape failures observed in the base commit's GitHub CI are covered by the existing `tests/uns_mcp/test_runtime_bound_reads.py` tests and pass in this run. Legacy no-runtime ACK responses retain their original two-field shape; runtime-bound responses include the canonical obligation projection.

Local verification used Python 3.12.14 and temporary SQLite databases. The executor's default asyncio loop stalled an unrelated minimal TestClient request and the MCP child-process test; a temporary **test-virtualenv-only** uvloop policy for parent and child interpreters allowed the unchanged tests to run. No event-loop workaround was added to repository or package code. The full run retained two framework deprecation warnings; Bandit and packaging also emitted existing non-failing annotation/license warnings.

These results establish local behavior. They do not establish real-provider receipt, human comprehension, production load capacity, or deployment of this commit. Hosted CI and the Python 3.11/3.13 matrix are separate checks.

## Release v0.2.0 Full-Stack, PostgreSQL 16 & Concurrency Verification — 2026-11-02

The `v0.2.0` release consolidates the durable notification runtime, MCP server, and operator console across Python and TypeScript stacks, adding full PostgreSQL 16 support, multi-worker concurrency validation, React 19 / TypeScript 5.9 / ESLint 9 flat config UI modernization, and automated GitHub Actions CI matrices.

### Complete Release v0.2.0 Verification Summary

| Verification Surface | Scope / Runner | Result |
|---|---|---|
| Python Test Suite | Python 3.11, 3.12, 3.13 via pytest | **1,877+ passed**, >90% coverage against 75% gate |
| PostgreSQL 16 & Sustained Load | `postgres:16-alpine` service container + SQLite WAL (`tests/uns/test_postgres_and_load.py`) | **22 passed** (schema, JSONB, lease contention, 100-request bursts, 0 duplicate sends) |
| UNS Console Test Suite (`apps/ui`) | Vitest 5.x / React Testing Library / jsdom | **344 passed** across all 6 console workspaces |
| Console Modernization Stack | React 19.3, TypeScript 5.9, ESLint 9.39 (`eslint.config.js`), Vite 8.3 | Type-check, flat lint, and production bundle built with 0 errors |
| Dependency Security Audits | `npm audit --omit=dev` & `pip-audit` | **0 advisories** (0 critical, 0 high, 0 moderate, 0 low) |
| Secret Leak Detection | Gitleaks across all commits (`gitleaks detect --config .gitleaks.toml`) | **0 leaks found** across 500+ scanned commits |
| Documentation Contracts | `tests/docs/` suite verifying cross-document integrity & invariant links | **259+ passed** |
| Persistent Localhost Deployment | `deploy/local/smoke.py` against `http://127.0.0.1:18080` (SQLite + ingress) | **66/66 checks passed**, including `/operations` and `/docs` |
| SQLite Backup Verification | Online SQLite backup API under private config volume | `PRAGMA quick_check=ok` verified |

### PostgreSQL 16 Operational Acceptance and Concurrency Details

| Check | Result |
|---|---|
| PostgreSQL 16 Live Operational Acceptance (`TestPostgresOperationalAcceptance`) | Schema bootstrap, idempotent migration, SQLite-only retention guard, warm/cold policy hydration, revision locking, idempotency replay, conflict detection, dedup coalescing/promotion, guarded replay, ACK/dismiss/TIMED_OUT lifecycle, and `SQLAlchemyReadModelAdapter` queries (with PostgreSQL JSONB containment channel filter) all passed. |
| 100-Request Concurrent Intake Burst & Deduplication Storm (`test_concurrent_intake_burst_and_deduplication_storm`) | 100 producer requests across 10 deduplication keys + 20 unique guaranteed requests (120 total) completed concurrently with zero lock errors, exactly 10 leaders + 90 followers, and sub-second P95 intake latency on both SQLite WAL and PostgreSQL 16. |
| Multi-Worker Lease Contention Zero Duplicate Sends (`test_multi_worker_lease_contention_zero_duplicate_sends`) | 40 pending guaranteed notifications raced by 4 concurrent `runtime.dispatch(limit=20)` workers reached `DELIVERED` with exactly 40 external send calls recorded by the adapter (0 duplicate sends) on both SQLite WAL and PostgreSQL 16. |
| Concurrent Policy Reload Under Active Intake (`test_concurrent_policy_reload_under_active_intake`) | 50 producer intake calls interleaved with 5 concurrent `save_snapshot()` policy reloads changing `ack_timeout_minutes` completed with 0 exceptions and 100% self-consistent `(policy_revision_id, policy_config_hash, ack_timeout_minutes)` provenance records. |
| PostgreSQL Driver Packaging | `psycopg[binary]>=3.2.0` added to the `sql` optional dependency extra in `pyproject.toml`, enabling `uns[full]` PostgreSQL support out of the box. |
| CI Integration | Dedicated `postgres` service container job using `postgres:16-alpine` running `tests/uns/test_postgres_and_load.py` integrated into `.github/workflows/python-tests.yml` under the `ci` required gate. |


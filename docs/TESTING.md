# UNS verification

Run from the consolidated repository with its development environment:

```sh
.venv/bin/python -m pytest tests apps/ui/tests
.venv/bin/ruff check src tests scripts apps
.venv/bin/mypy -p uns -p agsignal -p notification -p db -p ui_client -p agsignal_mcp
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

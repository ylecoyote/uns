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

## Consolidation result on 2026-10-20

Local functional acceptance passed on Python 3.12 using a fresh wheel environment with current compatible dependencies. The MCP dependency is constrained to major version 1 because version 2 removed the API used by the retained integration.

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

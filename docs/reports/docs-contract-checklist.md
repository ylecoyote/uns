# Documentation Contract Checklist

**Purpose:** Reviewer checklist to validate UNS documentation remains accurate over time.

**Usage:** Run through this checklist when:
- Code changes affect notification routing, delivery, or acknowledgment behavior
- Policy system changes are made
- Observability or health check implementations change
- Documentation is updated

---

## 1. Intent Routing Described

Documentation must accurately describe how notification intent determines routing behavior.

| Check | Location | What to Verify |
|-------|----------|----------------|
| ☐ | `delivery-semantics.md` §Intent × Delivery Mode Mapping | Intent → delivery mode table is accurate (SAFETY/GOVERNANCE → GUARANTEED, OPERATIONAL/INFORMATIONAL → BEST_EFFORT) |
| ☐ | `delivery-semantics.md` §Intent × Autonomy Mode × Channels Truth Table | Channel routing by intent and mode matches implementation |
| ☐ | `ARCHITECTURE.md` §Routing Rules | Delivery mode and channel resolution logic matches code |
| ☐ | `policy-lifecycle.md` §Channel Resolution by Mode | SDK default channel table is current |

**Key Invariant:** SAFETY and GOVERNANCE intents always default to GUARANTEED delivery mode.

---

## 2. Delivery Semantics Described

Documentation must accurately describe GUARANTEED and BEST_EFFORT delivery behavior.

| Check | Location | What to Verify |
|-------|----------|----------------|
| ☐ | `delivery-semantics.md` §GUARANTEED Delivery Semantics | Fallback order (Slack → Email → PagerDuty) is correct |
| ☐ | `delivery-semantics.md` §GUARANTEED Invariants | Must-succeed-or-raise behavior documented |
| ☐ | `delivery-semantics.md` §BEST_EFFORT Delivery Semantics | Concurrent delivery, no-exception-on-failure documented |
| ☐ | `delivery-semantics.md` §BEST_EFFORT Invariants | Partial success counts as SUCCESS |
| ☐ | `delivery-semantics.md` §Summary Table | Comparison table is accurate |

**Key Invariants:**
- GUARANTEED: Sequential fallback, raises `DeliveryError` if all persistent channels fail
- BEST_EFFORT: Concurrent delivery, no exception on failure, logs all attempts

---

## 3. Acknowledgment Rules and Boundaries Stated

Documentation must clearly state acknowledgment requirements and scope restrictions.

| Check | Location | What to Verify |
|-------|----------|----------------|
| ☐ | `delivery-semantics.md` §Acknowledgment Requirements | Ack truth table is accurate (only SAFETY + LIVE requires ack by default) |
| ☐ | `ARCHITECTURE.md` §Acknowledgment Engine | CRITICAL warning box present with scope restrictions |
| ☐ | `ARCHITECTURE.md` §Acknowledgment Engine | Anti-pattern examples correctly marked as forbidden |
| ☐ | `ARCHITECTURE.md` §Acknowledgment Engine | Correct pattern examples show fire-and-forget for execution |
| ☐ | `README.md` §Critical Constraints | Acknowledgment scope warning present |

**Key Invariant:** Acknowledgments exist ONLY to gate autonomy state transitions, NEVER order execution or risk operations.

**Anti-Patterns to Verify Are Marked Wrong:**
- Blocking order execution on ack status
- Gating risk unwind on acknowledgment
- Any `wait_for_ack()` in execution paths

---

## 4. Policy Lifecycle Described

Documentation must accurately describe policy resolution and fallback behavior.

| Check | Location | What to Verify |
|-------|----------|----------------|
| ☐ | `policy-lifecycle.md` §Policy States | State definitions (DRAFT, PREVIEW, ACTIVE, RETIRED) documented |
| ☐ | `policy-lifecycle.md` §Resolution Priority | Priority order is correct: 1) Explicit override, 2) Policy value, 3) SDK default |
| ☐ | `policy-lifecycle.md` §Registry Unavailability | Graceful fallback behavior documented |
| ☐ | `policy-lifecycle.md` §SDK Defaults Reference | Default values for delivery mode, ack, dedup window are current |
| ☐ | `policy-lifecycle.md` §API Reference | PolicyRegistry and NotificationPolicy API tables are current |

**Key Invariant:** Notifications are never blocked by missing policies; SDK defaults always apply as fallback.

---

## 5. Observability and Degradation Documented

Documentation must accurately describe health states, metrics, and degradation behavior.

| Check | Location | What to Verify |
|-------|----------|----------------|
| ☐ | `observability.md` §Health States | AdapterStatus enum values (HEALTHY, DEGRADED, UNHEALTHY) documented |
| ☐ | `observability.md` §What "DEGRADED" Means | Operational guidance for DEGRADED state is clear |
| ☐ | `observability.md` §DLQ Visibility | Escalation callback mechanism documented |
| ☐ | `observability.md` §DLQ Invariants | GUARANTEED-only, pre-exception, isolated failures rules stated |
| ☐ | `observability.md` §Key Metrics | Metric categories (latency, success/failure, fallback, DLQ, ack timeout) documented |
| ☐ | `observability.md` §System Degradation Modes | Degradation scenarios and behaviors documented |
| ☐ | `observability.md` §/health Endpoint | Current endpoint behavior accurately described |

**Key Invariants:**
- DEGRADED: Attempt delivery but expect some failures
- UNHEALTHY: Skip to fallback immediately
- DLQ: Only GUARANTEED failures trigger escalation callback

---

## Quick Reference: File Locations

| Topic | Primary Document | Supporting Documents |
|-------|------------------|---------------------|
| Intent Routing | `docs/sections/delivery-semantics.md` | `docs/ARCHITECTURE.md` |
| Delivery Semantics | `docs/sections/delivery-semantics.md` | `docs/ARCHITECTURE.md` |
| Acknowledgment Rules | `docs/ARCHITECTURE.md` | `docs/sections/delivery-semantics.md`, `README.md` |
| Policy Lifecycle | `docs/sections/policy-lifecycle.md` | `docs/API.md` |
| Observability | `docs/sections/observability.md` | `docs/sections/delivery-semantics.md` |

---

## Validation Test Coverage

Automated tests exist to validate documentation accuracy:

| Checklist Section | Test File |
|-------------------|-----------|
| Intent Routing | `tests/docs/test_delivery_semantics.py::TestIntentDeliveryModeMapping` |
| Delivery Semantics | `tests/docs/test_delivery_semantics.py::TestGuaranteedDeliveryInvariants`, `TestBestEffortDeliveryInvariants` |
| Acknowledgment Rules | `tests/docs/test_acknowledgment_scope.py` |
| Policy Lifecycle | `tests/docs/test_policy_lifecycle.py` |
| Observability | `tests/docs/test_observability.py` |
| Checklist Completeness | `tests/docs/test_docs_contract_checklist.py` |

Run all documentation tests:
```bash
pytest tests/docs/ -v
```

---

## Changelog

| Date | Change | Reviewer |
|------|--------|----------|
| 2025-01-23 | Initial checklist created | - |

---

*This checklist should be reviewed whenever documentation or related code changes are made.*

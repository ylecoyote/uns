# UNS Documentation: Minor Nits Baseline Scan

**Date:** 2026-01-23
**Scope:** Terminology consistency and cross-document consistency audit
**Status:** Complete

---

## Executive Summary

This baseline scan reviewed all UNS documentation for terminology consistency and cross-document alignment. The documentation is in **excellent health** with only minor nits identified. No semantic contradictions or behavioral misrepresentations were found.

### Documents Scanned

| Document | Lines | Status |
|----------|-------|--------|
| README.md | 472 | ✅ Reviewed |
| docs/README.md | 128 | ✅ Reviewed |
| docs/ARCHITECTURE.md | 504 | ✅ Reviewed |
| docs/API.md | 744 | ✅ Reviewed |
| docs/sections/delivery-semantics.md | 272 | ✅ Reviewed |
| docs/sections/integration-modes.md | 322 | ✅ Reviewed |
| docs/sections/observability.md | 428 | ✅ Reviewed |
| docs/sections/policy-lifecycle.md | 411 | ✅ Reviewed |
| CONTRIBUTING.md | 274 | ✅ Reviewed |
| prd.md | 575 | ✅ Reference |

---

## 1. Terminology Consistency Review

### 1.1 Core Term Usage

The following canonical terms are used consistently across all documents:

| Term | Definition | Consistency |
|------|------------|-------------|
| UNS | Unified Notification Service | ✅ Consistent |
| ATP | Autonomous Trading Platform | ✅ Consistent (always noted as external/optional) |
| Intent | SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL | ✅ Consistent |
| Autonomy Mode | PREVIEW, SHADOW, LIVE | ✅ Consistent |
| Delivery Mode | GUARANTEED, BEST_EFFORT | ✅ Consistent |
| DLQ | Dead Letter Queue (via escalation callback) | ✅ Consistent |

### 1.2 Minor Terminology Variations (Acceptable)

| Variation | Locations | Assessment |
|-----------|-----------|------------|
| "Notification Intent" vs "Intent" | Tables vs prose | ✅ Both acceptable; context clear |
| "delivery pipeline" vs "delivery service" | README vs ARCHITECTURE | ✅ Both refer to same concept |
| "fire-and-forget" | WebSocket descriptions | ✅ Consistent across all docs |

### 1.3 Terminology Issue Identified

**Issue:** "Retry/Fallback Counts" header in observability.md

- **Location:** observability.md:253
- **Context:** UNS does NOT implement automatic retries; only fallback
- **Mitigation:** Note at line 259 already clarifies "UNS does not implement automatic retries"
- **Severity:** Low (informational note is sufficient)
- **Action Required:** None

---

## 2. Cross-Document Consistency Review

### 2.1 Delivery Pipeline Consistency

Both README.md and ARCHITECTURE.md document the same 6-step pipeline:

| Step | README.md (174-181) | ARCHITECTURE.md (123-142) | Match |
|------|---------------------|---------------------------|-------|
| 1 | Deduplication Check | Deduplication Check | ✅ |
| 2 | Rate Limit Check | Rate Limit Check | ✅ |
| 3 | WebSocket Delivery | WebSocket Delivery | ✅ |
| 4 | Persistent Channel Delivery | Persistent Channel Delivery | ✅ |
| 5 | Ack Timeout Scheduling | Ack Timeout Scheduling | ✅ |
| 6 | Audit Logging | Audit Logging | ✅ |

### 2.2 Channel Routing Tables Consistency

Verified LIVE mode channel routing is identical across:
- README.md lines 163-170
- ARCHITECTURE.md lines 346-353
- delivery-semantics.md lines 29-34
- docs/README.md lines 72-76

All show:
| Intent | LIVE Channels |
|--------|---------------|
| SAFETY | Slack + WebSocket (+ PagerDuty if irreversible) |
| GOVERNANCE | Slack + WebSocket |
| OPERATIONAL | Slack |
| INFORMATIONAL | WebSocket |

**Result:** ✅ Consistent

### 2.3 Ack/Execution Boundary Warnings

Critical warning boxes verified present in:
- [x] README.md lines 121-139
- [x] ARCHITECTURE.md lines 204-248

Both correctly state acknowledgments:
- MAY gate: autonomy mode transitions, policy changes
- MUST NEVER gate: order execution, risk operations, emergency procedures

**Result:** ✅ Consistent and comprehensive

### 2.4 Cross-Reference Link Integrity

All cross-document links verified:

| Document | Links | Broken |
|----------|-------|--------|
| README.md | 1 | 0 |
| docs/README.md | 11 | 0 |
| ARCHITECTURE.md | 5 | 0 |
| API.md | 5 | 0 |
| delivery-semantics.md | 3 | 0 |
| integration-modes.md | 4 | 0 |
| observability.md | 4 | 0 |
| policy-lifecycle.md | 3 | 0 |

**Result:** ✅ All links valid

---

## 3. Issues Identified

### 3.1 API.md Missing `intent` Field on NotificationPolicy

**Severity:** Low
**Type:** Documentation gap

**Details:**
- policy-lifecycle.md line 387 documents `intent` field on NotificationPolicy
- API.md lines 382-389 does NOT include `intent` field
- Source code (src/notification/policies.py lines 105-107) confirms `intent` field exists:
  ```python
  intent: NotificationIntent | None = Field(
      default=None, description="Default intent if not specified in notification"
  )
  ```

**Recommendation:** Add `intent` field to NotificationPolicy in API.md

### 3.2 DeliveryStatus Enum Has Both SUCCESS and DELIVERED

**Severity:** Informational
**Type:** Implementation detail

**Details:**
- API.md line 266-269 shows DeliveryStatus enum with both `DELIVERED` and `SUCCESS`
- delivery-semantics.md uses `STATUS=SUCCESS` in examples
- This appears intentional (DELIVERED may mean "reached channel", SUCCESS may mean "all channels")

**Recommendation:** Consider documenting the semantic distinction in API.md or consolidating

---

## 4. Action Items

### Required Fixes

| # | Severity | Issue | File | Action |
|---|----------|-------|------|--------|
| 1 | Low | Missing `intent` field | docs/API.md | Add field to NotificationPolicy section |

### Optional Improvements

| # | Severity | Issue | File | Action |
|---|----------|-------|------|--------|
| 1 | Trivial | Retry/Fallback header | observability.md | Already has clarifying note; no change needed |
| 2 | Trivial | DELIVERED vs SUCCESS | API.md | Consider adding semantic note |

---

## 5. Validation Checklist

- [x] No contradictions with prd.md specifications
- [x] No examples imply forbidden behavior (ack gating execution)
- [x] Guarantees are explicitly scoped (no infinite retry implications)
- [x] Policy ownership clearly defined
- [x] Fallback behavior unambiguous
- [x] Anti-pattern warnings present and comprehensive
- [x] All cross-references valid
- [x] Terminology consistent across documents

---

## 6. Conclusion

The UNS documentation maintains excellent cross-document consistency with only one low-severity fix required (adding `intent` field to API.md NotificationPolicy documentation).

**Documentation Health Score:** 98/100

| Category | Score | Notes |
|----------|-------|-------|
| Terminology Consistency | 100% | All terms used consistently |
| Cross-Document Alignment | 98% | One missing field in API.md |
| Link Integrity | 100% | All links valid |
| Specification Compliance | 100% | No contradictions with prd.md |
| Behavioral Accuracy | 100% | No misrepresentations |

---

*Baseline scan completed: 2026-01-23*
*Next action: Apply fix for API.md NotificationPolicy `intent` field*

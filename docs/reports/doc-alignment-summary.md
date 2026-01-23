# Documentation Alignment Summary

**Generated:** 2025-01-23
**Specification Source:** prd.md (Ralphy-Compatible Build Specification)
**Documentation Reviewed:** README.md, docs/ARCHITECTURE.md, docs/API.md, CHANGELOG.md

---

## Executive Summary

This report identifies gaps between the project documentation and the authoritative specification (prd.md). Findings are categorized as contradictions, omissions, ambiguity, and unclear operational ownership.

---

## 1. Contradictions

### 1.1 SHADOW Mode Channel Routing for SAFETY Intent

| File | Section | Doc Statement | Spec Statement |
|------|---------|---------------|----------------|
| README.md | Lines 136-138, "Autonomy Mode" table | SHADOW mode row describes only "OPERATIONAL→WebSocket, GOVERNANCE→Slack+WebSocket" | prd.md Section 6.2 states SHADOW mode "Others follow LIVE defaults" for SAFETY/INFORMATIONAL |
| docs/ARCHITECTURE.md | Lines 298-304, "SHADOW Mode" | Lists only OPERATIONAL and GOVERNANCE, states "Others | LIVE defaults" | Correct, but README omits this fallback behavior |

**Impact:** README could mislead readers to believe SHADOW mode has no routing for SAFETY or INFORMATIONAL intents.

**Resolution:** README.md line 137 should explicitly list SAFETY and INFORMATIONAL routing in SHADOW mode.

---

### 1.2 API.md Missing Async `get()` Method

| File | Section | Doc Statement | Code Reality |
|------|---------|---------------|--------------|
| docs/API.md | Lines 396-401, PolicyRegistry | Documents `async def get(notification_type) -> NotificationPolicy | None` | src/notification/policies.py only implements `get_sync()`, no async `get()` method exists |

**Impact:** API documentation claims an async interface that doesn't exist.

**Resolution:** Either remove `async def get()` from API.md or implement the method in policies.py.

---

### 1.3 GOVERNANCE Default Ack Behavior Inconsistency

| File | Section | Doc Statement | Spec Statement |
|------|---------|---------------|----------------|
| README.md | Line 126, Intent table | GOVERNANCE: "Default Ack (LIVE): Optional (30 min)" | prd.md Section 7 states `require_ack = false` unless policy specifies otherwise (SAFETY+LIVE is the only default true case) |

**Impact:** "Optional (30 min)" in README is misleading. The 30-minute timeout only applies IF a policy explicitly sets `require_ack=true` for GOVERNANCE. By default, GOVERNANCE does NOT require ack.

**Resolution:** Clarify that GOVERNANCE ack is NOT required by default; the 30-minute timeout is the default timeout IF acknowledgment is explicitly enabled via policy.

---

## 2. Omissions

### 2.1 Execution Constraint Not Documented

| Spec Reference | Missing From |
|----------------|--------------|
| prd.md Section 1: "MUST NOT block execution loops", "MUST NOT participate in order routing or trade timing" | README.md, docs/ARCHITECTURE.md |

**Impact:** Critical safety constraint is not visible to consumers. Developers may incorrectly assume UNS can be used for execution-path gating.

**Resolution:** Add explicit "Execution Constraints" section to README and ARCHITECTURE stating these invariants.

---

### 2.2 DLQ / Dead Letter Queue Visibility

| Spec Reference | Missing From |
|----------------|--------------|
| prd.md Section 10: GUARANTEED mode "MUST escalate via PagerDuty or DLQ", "MUST surface system degradation" | README.md, docs/ARCHITECTURE.md, docs/API.md |

**Impact:** No documentation describes what happens to failed GUARANTEED notifications beyond raising DeliveryError. DLQ behavior and degradation surfacing are unspecified.

**Resolution:** Add section documenting DLQ behavior, degradation signals, and operator visibility for failed GUARANTEED deliveries.

---

### 2.3 Policy Lifecycle States Not Documented

| Spec Reference | Missing From |
|----------------|--------------|
| uns-doc-prd.yaml Task "Document notification policy lifecycle": DRAFT, PREVIEW, ACTIVE, RETIRED states | README.md, docs/ARCHITECTURE.md, docs/API.md |

**Impact:** No documentation describes how policies transition between states or how versioning/hashing works.

**Resolution:** Document policy lifecycle states and transitions.

---

### 2.4 Policy Registry Unavailability Fallback

| Spec Reference | Missing From |
|----------------|--------------|
| uns-doc-prd.yaml: "behavior when policy registry is unavailable (safe fallbacks)" | All documentation |

**Impact:** Operators have no guidance on what happens if the policy registry fails or is unreachable.

**Resolution:** Document that SDK falls back to intent-based defaults when registry lookup fails or returns None.

---

### 2.5 Health Check Endpoint Semantics

| Spec Reference | Missing From |
|----------------|--------------|
| uns-doc-prd.yaml: "/health endpoint semantics if present" | README.md, docs/API.md |

**Impact:** No documentation of health check endpoints for operational monitoring.

**Resolution:** Either document existing health endpoints or explicitly note they are not implemented.

---

### 2.6 Retry / Backoff Semantics

| Spec Reference | Missing From |
|----------------|--------------|
| prd.md Section 10: Failure handling describes raise/escalate but not retry behavior | All documentation |

**Impact:** Documentation does not clarify whether adapters retry, what backoff is used, or if "infinite retry" is possible.

**Resolution:** Explicitly document that there is NO automatic retry at the service level (adapters may have their own retry logic). State that GUARANTEED uses sequential fallback, not retry.

---

### 2.7 Dedup Key Generation Algorithm

| Spec Reference | Doc Coverage |
|----------------|--------------|
| prd.md Section 9: "dedup_key" mentioned | docs/ARCHITECTURE.md Line 158 mentions "SHA256 hash of `notification_type + agent_id + source + title`" |

**Partial Omission:** README.md and API.md do not document the dedup key algorithm. Only ARCHITECTURE.md covers this.

**Resolution:** Add dedup key algorithm to README or cross-reference ARCHITECTURE.md.

---

### 2.8 ATP Integration Mode Separation

| Spec Reference | Missing From |
|----------------|--------------|
| uns-doc-prd.yaml: "standalone UNS vs ATP-integrated operation" separation | README.md |

**Impact:** README does not explicitly state UNS can function without ATP. Current doc may imply ATP dependency.

**Resolution:** Add section clarifying UNS core is ATP-agnostic; integrations are optional.

---

## 3. Ambiguity

### 3.1 Acknowledgment Blocking Behavior

| File | Section | Ambiguous Statement |
|------|---------|---------------------|
| README.md | Lines 68-79 | "Requires acknowledgment in LIVE mode" |
| docs/ARCHITECTURE.md | Lines 12-13 | "Acknowledgment tracking with timeout and escalation" |

**Ambiguity:** Documentation does not clarify what "requires acknowledgment" means operationally. Could be misread to imply:
- Notification delivery blocks until ack received (WRONG)
- System execution blocks until ack received (WRONG - violates execution constraint)

**Spec Clarification:** Acknowledgment is tracked asynchronously. Timeout triggers escalation, but does NOT block delivery or execution.

**Resolution:** Add explicit statement: "Acknowledgment tracking is asynchronous and does not block notification delivery or system execution."

---

### 3.2 "Escalation" Definition

| File | Section | Ambiguous Statement |
|------|---------|---------------------|
| docs/ARCHITECTURE.md | Lines 184-191 | "SAFETY + LIVE + timeout → Triggers EscalationHandler" |
| README.md | Line 15 | "Acknowledgment Tracking: Timeout handling and escalation" |

**Ambiguity:** "Escalation" is mentioned but never defined. What actions does EscalationHandler take?

**Resolution:** Define escalation: callback invocation, potential PagerDuty alert, audit log entry. Document the EscalationHandler interface.

---

### 3.3 "Fire-and-Forget" WebSocket Semantics

| File | Section | Ambiguous Statement |
|------|---------|---------------------|
| README.md | Line 153 | "WebSocket Delivery - Fire-and-forget, non-blocking" |
| docs/ARCHITECTURE.md | Line 119 | "WebSocket Delivery → Fire-and-forget (non-blocking)" |

**Ambiguity:** Does "fire-and-forget" mean:
- No delivery confirmation is expected (correct)
- WebSocket failures don't affect GUARANTEED semantics (correct)
- WebSocket failures are not logged (incorrect - they are logged)

**Resolution:** Clarify: "WebSocket delivery is fire-and-forget: failures are logged but do not affect overall delivery status or trigger GUARANTEED fallback."

---

### 3.4 GUARANTEED Fallback Order vs Configured Channels

| File | Section | Ambiguous Statement |
|------|---------|---------------------|
| README.md | Line 155 | "GUARANTEED: Sequential fallback (Slack → Email → PagerDuty)" |
| docs/ARCHITECTURE.md | Line 124 | Same fallback order |
| prd.md Section 8 | "Persistent channel delivery" with fallback order |

**Ambiguity:** Does fallback use all three channels regardless of configured channels, or only those in the notification's channel list?

**Code Reality (src/notification/service.py lines 387-395):** Fallback only uses channels from `notification.channels`, sorted by the fallback order.

**Resolution:** Clarify: "GUARANTEED mode attempts only the channels configured for the notification, in fallback priority order (Slack → Email → PagerDuty)."

---

### 3.5 Policy Override vs SDK Default Precedence

| File | Section | Statement |
|------|---------|-----------|
| docs/ARCHITECTURE.md | Lines 103-107 | Resolution Priority: 1. Explicit parameter, 2. Policy value, 3. SDK default |
| README.md | Lines 184-212 | Shows policy configuration but doesn't explain resolution priority |
| docs/API.md | Lines 83-87 | Lists override parameters but doesn't explain precedence |

**Ambiguity:** API.md and README don't clearly state the resolution priority for overrides.

**Resolution:** Add resolution priority documentation to README and API.md.

---

## 4. Unclear Operational Ownership

### 4.1 Who Configures Policies?

| Gap | Missing From |
|-----|--------------|
| No documentation of who (role/team) is responsible for creating, reviewing, and deploying notification policies | All documentation |

**Resolution:** Add operational ownership section stating policy configuration responsibility.

---

### 4.2 Deployment and Environment Configuration

| Gap | Missing From |
|-----|--------------|
| No deployment documentation (Docker, K8s, environment variables, secrets management) | All documentation |

**Resolution:** Add deployment section or DEPLOYMENT.md with:
- Required environment variables
- Secrets management (Slack tokens, PagerDuty API keys, SMTP credentials)
- Redis configuration for deduplication/rate limiting

---

### 4.3 Monitoring and Alerting Ownership

| Gap | Missing From |
|-----|--------------|
| No guidance on who monitors UNS health, what alerts should be configured, or SLO targets | All documentation |

**Resolution:** Add observability section documenting:
- Key metrics (delivery latency, failure rate, DLQ depth, ack timeout counts)
- Suggested alerting thresholds
- Operational runbook references

---

### 4.4 Channel Adapter Configuration Ownership

| Gap | Current State |
|-----|---------------|
| README.md Lines 216-226 show adapter configuration but don't specify who manages credentials or when to rotate | No operational guidance |

**Resolution:** Add section on adapter credential management and rotation procedures.

---

## 5. Summary Table

| Category | Count | Critical |
|----------|-------|----------|
| Contradictions | 3 | 1 (GOVERNANCE ack behavior) |
| Omissions | 8 | 2 (Execution constraint, DLQ visibility) |
| Ambiguity | 5 | 1 (Ack blocking behavior) |
| Unclear Ownership | 4 | 1 (Deployment/secrets) |
| **Total** | **20** | **5** |

---

## 6. Recommended Priority

### High Priority (Address Immediately)
1. Add execution constraint documentation (MUST NOT block execution loops)
2. Clarify acknowledgment is asynchronous, does not block
3. Fix GOVERNANCE ack default behavior description
4. Document DLQ / degradation visibility

### Medium Priority
5. Add policy lifecycle documentation
6. Document policy registry fallback behavior
7. Clarify GUARANTEED fallback uses configured channels only
8. Add deployment/environment configuration
9. Remove or implement async `PolicyRegistry.get()` method
10. Document ATP-agnostic operation

### Low Priority
11. Add observability section
12. Document operational ownership
13. Add health check endpoint documentation
14. Clarify fire-and-forget semantics
15. Add resolution priority to all relevant docs

---

## 7. Files Requiring Updates

| File | Sections to Update |
|------|-------------------|
| README.md | Add execution constraints, clarify ack semantics, fix GOVERNANCE ack, add policy fallback, add ATP independence |
| docs/ARCHITECTURE.md | Add DLQ visibility, clarify escalation, add policy lifecycle |
| docs/API.md | Remove or implement async `get()`, add resolution priority, add health endpoints |
| CHANGELOG.md | (No changes needed - accurately reflects v0.1.0 features) |
| (New) docs/DEPLOYMENT.md | Environment variables, secrets, Redis config |
| (New) docs/OBSERVABILITY.md | Metrics, alerting, SLOs |

---

*Report generated by documentation alignment analysis against prd.md specification.*

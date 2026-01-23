# Documentation Update Plan

**Generated:** 2026-01-23
**Source:** docs/reports/doc-alignment-summary.md
**Total Gaps:** 20
**Critical:** 5

---

## Overview

This plan provides an ordered sequence of documentation updates to resolve gaps identified in the alignment analysis. Updates are prioritized by criticality and dependency order.

---

## Phase 1: Critical Fixes (High Priority)

### 1.1 Add Execution Constraints Documentation

**Gap Reference:** Omission 2.1 (Critical)
**Files:** README.md, docs/ARCHITECTURE.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| New section after "Features" (~line 19) | Addition | Add "Execution Constraints" section |

**New Content:**
```markdown
## Execution Constraints

UNS is a control-plane service with strict execution boundaries:

- **MUST NOT** block execution loops or trading paths
- **MUST NOT** participate in order routing or trade timing decisions
- Notifications are advisory only and do not gate system operations
```

**Expected Output:**
- New "Execution Constraints" section visible immediately after Features
- Clear statement that UNS cannot block execution

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| New section after "Design Principles" (~line 23) | Addition | Add "Execution Constraints" subsection |

**New Content:**
```markdown
### Execution Constraints

UNS operates strictly in the control plane:

1. **Non-Blocking**: No notification or acknowledgment operation blocks execution loops
2. **Advisory Only**: Notifications inform but do not gate trading decisions
3. **No Order Path**: MUST NOT participate in order routing or trade timing
```

**Expected Output:**
- Architecture document explicitly states execution boundaries

---

### 1.2 Clarify Acknowledgment Is Asynchronous

**Gap Reference:** Ambiguity 3.1 (Critical)
**Files:** README.md, docs/ARCHITECTURE.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Line 70 (SAFETY comment) | Edit | Add async clarification |
| Line 15 (Acknowledgment Tracking feature) | Edit | Add "(asynchronous)" qualifier |

**Line 15 Edit:**
```markdown
- **Acknowledgment Tracking**: Asynchronous timeout handling and escalation (does not block delivery)
```

**Line 70 Edit:**
```markdown
# SAFETY: Critical issues requiring immediate attention
# - GUARANTEED delivery
# - Requires acknowledgment in LIVE mode (tracked asynchronously, does not block)
```

**Expected Output:**
- Clear indication that ack tracking is non-blocking

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Line 12 (Acknowledgment tracking bullet) | Edit | Add async qualifier |
| Lines 175-191 (Acknowledgment Engine section) | Edit | Add explicit async statement |

**Line 12 Edit:**
```markdown
- Acknowledgment tracking with timeout and escalation (asynchronous, non-blocking)
```

**New paragraph after line 191:**
```markdown
**Important:** Acknowledgment tracking is fully asynchronous. Timeout checks and escalation do NOT block notification delivery or system execution paths.
```

**Expected Output:**
- ARCHITECTURE explicitly states async behavior

---

### 1.3 Fix GOVERNANCE Acknowledgment Default

**Gap Reference:** Contradiction 1.3 (Critical)
**File:** README.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Line 126 (Intent table, GOVERNANCE row) | Edit | Fix "Default Ack" column |

**Current:**
```markdown
| GOVERNANCE | GUARANTEED | Optional (30 min) | HIGH |
```

**Changed To:**
```markdown
| GOVERNANCE | GUARANTEED | Not required (30 min timeout if enabled) | HIGH |
```

**Expected Output:**
- Table accurately reflects that GOVERNANCE ack is NOT required by default
- 30-minute timeout only applies when policy enables acknowledgment

---

### 1.4 Document DLQ and Degradation Visibility

**Gap Reference:** Omission 2.2 (Critical)
**Files:** README.md, docs/ARCHITECTURE.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| New subsection under "Failure Semantics" (~line 163) | Addition | Add DLQ/degradation info |

**New Content:**
```markdown
### Failed Delivery Handling

When GUARANTEED delivery fails across all channels:

1. `DeliveryError` exception raised to caller
2. Failure logged with full notification context
3. Escalation callback invoked (if configured)
4. Future: DLQ persistence for retry/investigation

**Note:** DLQ storage and system degradation surfacing are planned features. Current implementation raises exception and logs.
```

**Expected Output:**
- README documents what happens on GUARANTEED failure
- Acknowledges DLQ as future work

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Lines 319-328 (GUARANTEED Mode failure section) | Edit | Expand failure handling |

**Additional content after line 328:**
```markdown
**Degradation Visibility:**

- Failed deliveries trigger escalation callback
- Audit log captures failure details
- Metrics (when implemented): `uns.delivery.failed` counter
- Future: Dead Letter Queue for persistent failure storage
```

**Expected Output:**
- Architecture documents degradation signals

---

## Phase 2: Contradiction and API Fixes (Medium Priority)

### 2.1 Fix SHADOW Mode Documentation

**Gap Reference:** Contradiction 1.1
**File:** README.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Lines 136-138 (Autonomy Mode table) | Edit | Complete SHADOW mode routing |

**Current:**
```markdown
| SHADOW | Limited routing (OPERATIONAL→WebSocket, GOVERNANCE→Slack+WebSocket) |
```

**Changed To:**
```markdown
| SHADOW | Limited routing: OPERATIONAL→WebSocket, GOVERNANCE→Slack+WebSocket, SAFETY/INFORMATIONAL→LIVE defaults |
```

**Expected Output:**
- SHADOW mode explicitly lists fallback behavior for all intents

---

### 2.2 Fix or Remove Async PolicyRegistry.get()

**Gap Reference:** Contradiction 1.2
**File:** docs/API.md

#### docs/API.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Lines 396-401 (PolicyRegistry section) | Edit | Remove async get() or mark as not implemented |

**Option A - Remove (Recommended):**

**Current:**
```python
class PolicyRegistry:
    def register(self, policy: NotificationPolicy) -> None
    def get_sync(self, notification_type: str) -> NotificationPolicy | None
    async def get(self, notification_type: str) -> NotificationPolicy | None
```

**Changed To:**
```python
class PolicyRegistry:
    def register(self, policy: NotificationPolicy) -> None
    def get_sync(self, notification_type: str) -> NotificationPolicy | None
    # Note: Async get() planned for future Redis-backed registry
```

**Expected Output:**
- API.md matches actual implementation

---

### 2.3 Add Resolution Priority to README and API

**Gap Reference:** Ambiguity 3.5
**Files:** README.md, docs/API.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| After "Policy Overrides" section (~line 212) | Addition | Add resolution priority explanation |

**New Content:**
```markdown
#### Resolution Priority

When determining notification values (channels, delivery_mode, require_ack):

1. **Explicit parameter override** - Highest priority
2. **Policy value** - Mode-specific, then base policy
3. **SDK default** - Based on intent + autonomy mode
```

**Expected Output:**
- README explains how overrides are resolved

#### docs/API.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| After line 87 (override parameters list) | Addition | Add resolution priority note |

**New Content:**
```markdown
**Resolution Priority:** Explicit override > Policy value > SDK default (see ARCHITECTURE.md for details)
```

**Expected Output:**
- API reference includes priority explanation

---

### 2.4 Clarify GUARANTEED Fallback Uses Configured Channels

**Gap Reference:** Ambiguity 3.4
**Files:** README.md, docs/ARCHITECTURE.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Line 155 (GUARANTEED fallback description) | Edit | Clarify channel scope |

**Current:**
```markdown
   - GUARANTEED: Sequential fallback (Slack → Email → PagerDuty)
```

**Changed To:**
```markdown
   - GUARANTEED: Sequential fallback through configured channels only, in priority order (Slack → Email → PagerDuty)
```

**Expected Output:**
- Clear that fallback only uses channels in notification.channels

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Line 123-124 (GUARANTEED delivery description) | Edit | Add clarification |

**Changed To:**
```markdown
   ├── GUARANTEED: Sequential fallback through notification's configured channels, in priority order (Slack → Email → PagerDuty)
```

**Expected Output:**
- Architecture clarifies fallback scope

---

## Phase 3: Omissions and Clarifications (Medium Priority)

### 3.1 Document Policy Lifecycle States

**Gap Reference:** Omission 2.3
**File:** docs/ARCHITECTURE.md

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| After "Policy System" section (~line 107) | Addition | Add policy lifecycle documentation |

**New Content:**
```markdown
#### Policy Lifecycle States

Policies transition through defined states:

| State | Description |
|-------|-------------|
| DRAFT | Policy under development, not active |
| PREVIEW | Testing in preview environments |
| ACTIVE | Live policy, used for production routing |
| RETIRED | Deprecated, kept for audit history |

**Note:** State management and versioning are planned features. Current implementation treats all registered policies as ACTIVE.
```

**Expected Output:**
- Architecture documents policy states (even if not fully implemented)

---

### 3.2 Document Policy Registry Unavailability Fallback

**Gap Reference:** Omission 2.4
**File:** docs/ARCHITECTURE.md

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| After Policy Lifecycle section | Addition | Add fallback behavior |

**New Content:**
```markdown
#### Registry Unavailability

When policy registry lookup fails or returns None:

1. SDK falls back to intent-based defaults
2. No exception raised for missing policy
3. Behavior equivalent to no policy being registered

This ensures notifications can always be delivered even if the registry is temporarily unavailable.
```

**Expected Output:**
- Clear documentation of safe fallback behavior

---

### 3.3 Document ATP-Agnostic Operation

**Gap Reference:** Omission 2.8
**File:** README.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| After "Architecture" section heading (~line 115) | Addition | Add ATP independence statement |

**New Content:**
```markdown
### ATP Independence

UNS core is ATP-agnostic. While designed for autonomous trading platform integration:

- UNS functions as a standalone notification service
- `AutonomyContext` fields beyond `autonomy_mode` and `agent_id` are optional
- ATP-specific integrations (plan tracking, decision snapshots) are opt-in
```

**Expected Output:**
- README clearly states UNS works without ATP

---

### 3.4 Define Escalation Behavior

**Gap Reference:** Ambiguity 3.2
**File:** docs/ARCHITECTURE.md

#### docs/ARCHITECTURE.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Lines 189-191 (Escalation Logic section) | Edit | Expand escalation definition |

**New Content after line 191:**
```markdown
**Escalation Actions:**

When EscalationHandler is triggered:

1. Invokes configured escalation callback
2. Creates audit record with escalation reason
3. Optionally triggers PagerDuty incident (if configured)
4. Logs escalation event at CRITICAL level

**EscalationHandler Interface:**
```python
class EscalationHandler(Protocol):
    def escalate(
        self,
        notification_id: UUID,
        reason: str,
        context: dict[str, Any],
    ) -> None: ...
```
```

**Expected Output:**
- Escalation behavior explicitly documented

---

### 3.5 Clarify Fire-and-Forget Semantics

**Gap Reference:** Ambiguity 3.3
**Files:** README.md, docs/ARCHITECTURE.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Line 153 (WebSocket Delivery) | Edit | Add clarification |

**Changed To:**
```markdown
3. **WebSocket Delivery** - Fire-and-forget (failures logged, does not affect GUARANTEED fallback)
```

**Expected Output:**
- WebSocket failure handling clarified

---

## Phase 4: New Documentation (Lower Priority)

### 4.1 Create DEPLOYMENT.md

**Gap Reference:** Unclear Ownership 4.2
**File:** docs/DEPLOYMENT.md (NEW)

**New File Content:**
```markdown
# Deployment Guide

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `UNS_REDIS_URL` | Yes (prod) | Redis connection URL for dedup/rate limiting |
| `UNS_DATABASE_URL` | Yes (prod) | Database URL for audit persistence |
| `SLACK_BOT_TOKEN` | For Slack | Slack Bot OAuth token |
| `PAGERDUTY_API_KEY` | For PagerDuty | PagerDuty integration key |
| `SMTP_HOST` | For Email | SMTP server hostname |
| `SMTP_PORT` | For Email | SMTP server port (default: 587) |
| `SMTP_USER` | For Email | SMTP authentication user |
| `SMTP_PASSWORD` | For Email | SMTP authentication password |

## Secrets Management

- Store adapter credentials in a secrets manager (Vault, AWS Secrets Manager)
- Rotate API keys per your organization's security policy
- Never commit credentials to version control

## Redis Configuration

Deduplication and rate limiting require Redis:

```bash
# Docker
docker run -d -p 6379:6379 redis:7-alpine

# Configure
UNS_REDIS_URL=redis://localhost:6379/0
```

## Container Deployment

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[all]"
CMD ["python", "-m", "uvicorn", "mcp_server.main:app", "--host", "0.0.0.0"]
```
```

**Expected Output:**
- New deployment documentation covering environment and secrets

---

### 4.2 Create OBSERVABILITY.md

**Gap Reference:** Unclear Ownership 4.3
**File:** docs/OBSERVABILITY.md (NEW)

**New File Content:**
```markdown
# Observability Guide

## Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `uns.notification.sent` | Counter | Notifications sent by intent |
| `uns.delivery.success` | Counter | Successful channel deliveries |
| `uns.delivery.failed` | Counter | Failed channel deliveries |
| `uns.delivery.latency_ms` | Histogram | Delivery latency by channel |
| `uns.dedup.hit` | Counter | Deduplicated notifications |
| `uns.ratelimit.rejected` | Counter | Rate-limited notifications |
| `uns.ack.timeout` | Counter | Acknowledgment timeouts |

## Suggested Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Failure Rate | `uns.delivery.failed / uns.notification.sent > 0.05` | WARNING |
| GUARANTEED Failures | Any GUARANTEED delivery failure | CRITICAL |
| Ack Timeout Spike | `rate(uns.ack.timeout) > 5/min` | WARNING |
| DLQ Depth | `uns.dlq.depth > 100` (future) | CRITICAL |

## Logging

UNS uses structured JSON logging:

```json
{
  "timestamp": "2025-01-23T10:00:00Z",
  "level": "INFO",
  "event": "notification_delivered",
  "notification_id": "...",
  "channels": ["SLACK"],
  "latency_ms": 150
}
```

## Health Endpoint

**Status:** Not yet implemented

Planned `/health` endpoint will return:
- Channel adapter connectivity
- Redis connectivity
- Database connectivity
```

**Expected Output:**
- Observability guidance for operators

---

### 4.3 Document Health Check Endpoints

**Gap Reference:** Omission 2.5
**File:** docs/API.md

#### docs/API.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| After "Error Handling" section (~line 720) | Addition | Add health check documentation |

**New Content:**
```markdown
## Health Checks

### Adapter Health Checks

Each adapter implements a health check method:

```python
result = await adapter.health_check()
# Returns: HealthCheckResult(healthy=True/False, channel=..., latency_ms=..., error=...)
```

### Service Health Endpoint

**Status:** Planned, not yet implemented

Future `/health` endpoint will aggregate:
- Individual adapter health
- Redis connectivity (dedup/rate limiting)
- Database connectivity (audit store)
```

**Expected Output:**
- API.md documents current health check capabilities

---

## Phase 5: Operational Guidance (Lowest Priority)

### 5.1 Document Operational Ownership

**Gap Reference:** Unclear Ownership 4.1, 4.4
**File:** README.md

#### README.md Changes

| Section | Change Type | Description |
|---------|-------------|-------------|
| Before "Testing" section (~line 350) | Addition | Add operational guidance section |

**New Content:**
```markdown
## Operational Guidance

### Policy Configuration

- **Owner:** Platform/SRE team
- Policies define routing rules per notification type
- Review policies during incident retrospectives
- Test policy changes in PREVIEW mode first

### Credential Management

- **Owner:** Platform/Security team
- Rotate Slack tokens, PagerDuty keys per security policy
- Store credentials in secrets manager (not environment variables in production)
- Document credential access in runbooks
```

**Expected Output:**
- README provides operational ownership guidance

---

## Summary

### Files to Change

| File | Phase | Changes |
|------|-------|---------|
| README.md | 1, 2, 3, 5 | 11 edits/additions |
| docs/ARCHITECTURE.md | 1, 2, 3 | 8 edits/additions |
| docs/API.md | 2, 4 | 3 edits/additions |
| docs/DEPLOYMENT.md | 4 | NEW FILE |
| docs/OBSERVABILITY.md | 4 | NEW FILE |

### Change Summary by Type

| Change Type | Count |
|-------------|-------|
| Section Additions | 14 |
| Line Edits | 8 |
| New Files | 2 |
| **Total Changes** | **24** |

### Expected Outcomes

After implementing this plan:

1. **Zero critical gaps** - All 5 critical issues resolved
2. **No contradictions** - Documentation matches specification and code
3. **Clear operational guidance** - Deployment, observability, and ownership documented
4. **Explicit async behavior** - No ambiguity about blocking/non-blocking operations
5. **Complete channel routing** - All modes and intents fully documented

---

*Plan generated from doc-alignment-summary.md gap analysis.*

# Unified Notification Service (UNS)

## Ralphy-Compatible Build Specification

> This document is a **code-generation–oriented specification** derived from the UNS PRD, Functional Spec, and Technical Spec.
> It is optimized for tools like **Ralphy** that require deterministic contracts, explicit invariants, and separable build units.
>
> Philosophy, rationale, and narrative context are intentionally minimized.

---

## 1. System Declaration

**System Name:** Unified Notification Service (UNS)

**System Type:** Control-plane notification and acknowledgment service

**Execution Constraint:**

* MUST NOT block execution loops
* MUST NOT participate in order routing or trade timing

---

## 2. Primary Build Targets (Authoritative)

Ralphy should generate code for the following components **independently**:

1. Notification Schema
2. Autonomy Context Schema
3. Notification Router
4. Delivery Engine
5. Acknowledgment Engine
6. Policy Registry
7. Deduplication Engine
8. Rate Limiter
9. Audit Logger

Each target has an explicit contract defined below.

---

## 3. Core Data Contracts

### 3.1 Enum: NotificationIntent

```text
SAFETY
GOVERNANCE
OPERATIONAL
INFORMATIONAL
```

**Invariants:**

* SAFETY and GOVERNANCE imply elevated delivery guarantees

---

### 3.2 Enum: DeliveryMode

```text
GUARANTEED
BEST_EFFORT
```

**Invariants:**

* SAFETY → GUARANTEED
* GOVERNANCE → GUARANTEED
* OPERATIONAL → BEST_EFFORT
* INFORMATIONAL → BEST_EFFORT

---

### 3.3 Enum: AutonomyMode

```text
PREVIEW
SHADOW
LIVE
```

---

### 3.4 Enum: AckStatus

```text
PENDING
ACKED
DISMISSED
TIMED_OUT
```

---

## 4. Contract: AutonomyContext

### Fields

| Field                 | Type         | Required | Notes       |
| --------------------- | ------------ | -------- | ----------- |
| autonomy_mode         | AutonomyMode | YES      | Routing key |
| agent_id              | UUID         | YES      | Attribution |
| plan_id               | UUID         | NO       | Optional    |
| decision_snapshot_id  | UUID         | NO       | Optional    |
| execution_snapshot_id | UUID         | NO       | Optional    |
| skip_snapshot_id      | UUID         | NO       | Optional    |

**Hard Guard:**

* Notification creation MUST FAIL if autonomy_context is missing

---

## 5. Contract: Notification

### Fields

| Field               | Type                  | Required | Default / Rule              |
| ------------------- | --------------------- | -------- | --------------------------- |
| notification_id     | UUID                  | Auto     | Generated                   |
| notification_type   | string                | YES      | Namespaced (domain.event)   |
| intent              | NotificationIntent    | YES      | —                           |
| delivery_mode       | DeliveryMode          | Derived  | From intent or policy       |
| irreversible        | boolean               | NO       | Default false               |
| autonomy_context    | AutonomyContext       | YES      | Hard requirement            |
| require_ack         | boolean               | Derived  | From intent + mode + policy |
| ack_timeout_minutes | int                   | Derived  | Intent-based                |
| priority            | enum(HIGH,NORMAL,LOW) | Derived  | From intent                 |
| title               | string                | YES      | <=200 chars                 |
| message             | string                | YES      | <=4000 chars                |
| metadata            | map                   | NO       | JSON                        |
| channels            | list<Channel>         | Derived  | Router output               |
| dedup_key           | string                | Derived  | Stable within window        |
| source              | string                | YES      | Producer identifier         |
| correlation_id      | string                | NO       | Optional                    |
| created_at          | timestamp             | Auto     | —                           |

---

## 6. Routing Rules (Deterministic)

### 6.1 Delivery Mode Resolution

```text
if policy exists:
  delivery_mode = policy.delivery_mode
else if intent in [SAFETY, GOVERNANCE]:
  delivery_mode = GUARANTEED
else:
  delivery_mode = BEST_EFFORT
```

---

### 6.2 Channel Resolution

**LIVE Mode Defaults**

| Intent        | Channels                                       |
| ------------- | ---------------------------------------------- |
| SAFETY        | Slack, WebSocket (+ PagerDuty if irreversible) |
| GOVERNANCE    | Slack, WebSocket                               |
| OPERATIONAL   | Slack                                          |
| INFORMATIONAL | WebSocket                                      |

**PREVIEW Mode Override**

* All intents → WebSocket only

**SHADOW Mode Override**

* OPERATIONAL → WebSocket
* GOVERNANCE → Slack + WebSocket

---

## 7. Acknowledgment Rules

### Require Ack

```text
if policy specifies require_ack:
  use policy value
else if intent == SAFETY and autonomy_mode == LIVE:
  require_ack = true
else:
  require_ack = false
```

### Ack Timeout Defaults

| Intent     | Timeout    |
| ---------- | ---------- |
| SAFETY     | 15 minutes |
| GOVERNANCE | 30 minutes |

---

## 8. Delivery Engine Contract

### Input

* Serialized Notification

### Steps (Strict Order)

1. Deduplication check
2. Rate limit check
3. WebSocket delivery (fire-and-forget)
4. Persistent channel delivery
5. Escalation (GUARANTEED only)
6. Ack timeout scheduling (if required)
7. Audit logging

---

## 9. Deduplication Engine

### Input

* dedup_key

### Behavior

* Enforce at-most-once delivery per key within window
* Window duration configurable (policy or default)

---

## 10. Failure Semantics

### GUARANTEED

* MUST raise error if all persistent channels fail
* MUST escalate via PagerDuty or DLQ
* MUST surface system degradation

### BEST_EFFORT

* MAY fail silently
* MUST log failure

---

## 11. Out of Scope for Codegen

Ralphy MUST IGNORE:

* UX rationale
* Organizational roles
* Human factors explanations
* Narrative examples

---

## 12. Codegen Readiness Status

**This document is authoritative for:**

* Schema generation
* Router logic
* Validation rules
* Delivery orchestration

**Source of Truth Priority:**

1. This document
2. Technical Spec
3. Functional Spec
4. PRD

---

## 13. Ralphy Task Map (Codegen Plan)

This section defines the **explicit sequence of generation tasks** Ralphy should follow. Each task produces a concrete artifact and has clear dependencies.

### Conventions

* **Artifact naming** uses the directory root `src/notification/` (adjust if your repo differs).
* **Interfaces first**, then **pure logic**, then **I/O adapters**, then **API routes**, then **tests**.
* Each task should be generated as a **small, reviewable PR chunk**.

---

## Task 0 — Project Scaffolding

**Goal:** Create file structure and minimal package wiring.

**Artifacts:**

* `src/notification/__init__.py`
* `src/notification/adapters/__init__.py`
* `src/notification/integrations/__init__.py` (if applicable)

**Acceptance:**

* Package imports resolve
* Empty modules compile

---

## Task 1 — Core Enums and Models

**Goal:** Generate core data contracts exactly as defined.

**Artifacts:**

* `src/notification/models.py`

**Must include:**

* `NotificationIntent`, `DeliveryMode`, `AutonomyMode`, `AckStatus`, `Channel`, `Priority`, `DeliveryStatus`
* `AutonomyContext`, `Notification`, `NotificationResult`, `AckEvent`

**Validation guards:**

* `Notification.autonomy_context` required
* title/message length constraints

**Acceptance:**

* Model validation succeeds for representative examples
* Serialization (`model_dump` / JSON) works

---

## Task 2 — Interfaces for Integration (Dependency Injection)

**Goal:** Make UNS core ATP-agnostic.

**Artifacts:**

* `src/notification/interfaces.py`

**Must include:**

* `NotificationContextProvider` protocol
* `AcknowledgmentCallback` protocol
* `DefaultContextProvider`

**Acceptance:**

* Core SDK can run without ATP imports

---

## Task 3 — Policy Schema + Registry

**Goal:** Define canonical policy object, loader, and lookup.

**Artifacts:**

* `src/notification/policies.py`

**Must include:**

* `NotificationPolicy` (typed object)
* `get_channels_for_mode(autonomy_mode)`
* `get_require_ack_for_mode(autonomy_mode)`
* `PolicyRegistry` with `get_sync(notification_type)`

**Acceptance:**

* Policy lookup failure falls back to SDK defaults
* Mode overrides apply deterministically

---

## Task 4 — Deduplication Engine

**Goal:** Provide at-most-once semantic delivery per dedup key within a window.

**Artifacts:**

* `src/notification/deduplication.py`

**Must include:**

* `should_deduplicate(notification) -> bool`
* Redis `SETNX` + TTL behavior

**Acceptance:**

* Second notification with same key within TTL deduplicates

---

## Task 5 — Rate Limiter

**Goal:** Prevent channel throttling using token bucket per channel.

**Artifacts:**

* `src/notification/rate_limiting.py`

**Must include:**

* `acquire_rate_limit(channel) -> bool`

**Acceptance:**

* Exceeding configured rate returns false

---

## Task 6 — Adapters (Channel I/O)

**Goal:** Implement delivery primitives per channel.

**Artifacts:**

* `src/notification/adapters/base.py`
* `src/notification/adapters/slack.py`
* `src/notification/adapters/email.py`
* `src/notification/adapters/websocket.py`
* `src/notification/adapters/pagerduty.py`
* `src/notification/adapters/__init__.py` (factory `get_adapter`)

**Acceptance:**

* Each adapter has `deliver(notification)` and `health_check()`
* Failures raise exceptions (do not swallow)

---

## Task 7 — Delivery Service (Orchestration)

**Goal:** Implement delivery flow with GUARANTEED vs BEST_EFFORT semantics.

**Artifacts:**

* `src/notification/service.py`

**Must include strict step order:**

1. Dedup
2. Rate limit
3. WebSocket fire-and-forget
4. Persistent delivery

   * GUARANTEED: sequential fallback (Slack → Email → PagerDuty)
   * BEST_EFFORT: attempt all channels
5. Ack timeout scheduling
6. Audit log write
7. GUARANTEED failure raises

**Acceptance:**

* GUARANTEED with all persistent failures raises
* BEST_EFFORT failure logs and returns FAILED

---

## Task 8 — SDK (Producer Interface)

**Goal:** Provide `send()` API for producers.

**Artifacts:**

* `src/notification/sdk.py`
* `src/notification/factory.py` (optional: `create_sdk(mode)`)

**Must include:**

* Hard validation for autonomy_context + autonomy_mode + agent_id
* Policy lookup override behavior
* Default channel derivation by mode + intent
* `send_safety`, `send_governance`, `send_operational`, `send_info`

**Acceptance:**

* Calls enqueue RQ job with serialized notification payload

---

## Task 9 — Acknowledgment Engine

**Goal:** Handle ACK transitions and timeouts.

**Artifacts:**

* `src/notification/acknowledgment.py`

**Must include:**

* `ack(notification_id, ack_status, acked_by, metadata)`
* Idempotency: repeated ack is safe
* `check_ack_timeout(notification_id, intent, autonomy_context)`

**Acceptance:**

* Timeout updates state to TIMED_OUT
* SAFETY timeout triggers re-escalation

---

## Task 10 — API Routes (If Service Exposes HTTP)

**Goal:** Provide endpoints for ack/status/policies.

**Artifacts:**

* `src/mcp_server/routes_notification.py`

**Must include:**

* `POST /v1/notifications/{id}/ack`
* `GET /v1/notifications/{id}` (status)
* `GET /v1/policies` (optional)

**Acceptance:**

* Ack endpoint writes audit + triggers callback

---

## Task 11 — Persistence (Audit + Policies)

**Goal:** Define database models and storage writes.

**Artifacts:**

* `src/db/models.py` additions
* `src/notification/audit.py` (optional)

**Acceptance:**

* Audit record created for delivered/failed/deduped outcomes

---

## Task 12 — Tests

**Goal:** Provide unit tests per component.

**Artifacts:**

* `tests/notification/test_models.py`
* `tests/notification/test_policies.py`
* `tests/notification/test_deduplication.py`
* `tests/notification/test_rate_limiting.py`
* `tests/notification/test_service.py`
* `tests/notification/test_sdk.py`
* `tests/notification/test_acknowledgment.py`

**Acceptance:**

* Coverage for invariants:

  * autonomy_context required
  * SAFETY requires ack in LIVE
  * GUARANTEED raises on failure
  * dedup window suppresses repeats

---

## Task Execution Notes (Important)

* Generate tasks **in order**.
* Do not combine more than two tasks in a single PR chunk.
* Keep adapters isolated from policy/router logic.

---

## Tasks
- [ ] Project scaffolding: create src/notification package skeleton
- [ ] Implement core enums + models (Notification, AutonomyContext, etc.)
- [ ] Implement integration interfaces (ContextProvider, AckCallback)
- [ ] Implement policy schema + registry (mode-aware routing)
- [ ] Implement deduplication (Redis SETNX + TTL)
- [ ] Implement rate limiting (token bucket per channel)
- [ ] Implement adapters (Slack, Email, WebSocket, PagerDuty)
- [ ] Implement delivery service (GUARANTEED vs BEST_EFFORT orchestration)
- [ ] Implement SDK (send(), validation guards, policy overrides)
- [ ] Implement acknowledgment engine (ack + timeout handling)
- [ ] Add API routes for ack/status (if applicable)
- [ ] Add audit/persistence wiring (if applicable)
- [ ] Add unit tests for invariants and core flows
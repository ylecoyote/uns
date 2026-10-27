> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

> Historical note: This document is preserved from the UNS extraction phase. In current public product terminology, UNS maps to UNS Core and UNS Dashboard maps to UNS Console.

# Unified Notification Service (UNS) Functional Specification v2.0

**Spec Type:** Functional / Product Specification
**Status:** DRAFT
**Audience:** Product, Engineering, Operations, Compliance
**Last Updated:** 2026-01-19

---

## 1. Purpose

UNS is the **human–agent interrupt and awareness layer** for MIP's autonomous trading platform.

It ensures that when autonomous agents:

* encounter risk
* require approval
* change operating conditions
* or need to inform humans

…the *right human* is notified, with the *right urgency*, through the *right channel*, **without overwhelming attention or blocking execution unnecessarily**.

### 1.1 Core Function

UNS provides **state-change signaling across autonomy boundaries**:

* ❌ NOT "send messages"
* ❌ NOT "alerting system"
* ✅ **Human-facing control-plane signal bus for autonomous trading**

### 1.2 Design Principles

1. **Intent over channel** — Semantic meaning drives routing
2. **Cognitive safety over completeness** — Protect human attention
3. **Determinism over convenience** — Behavior is policy-driven and auditable
4. **Autonomy-aware behavior** — Context varies by PREVIEW/SHADOW/LIVE
5. **No silent failure for safety paths** — GUARANTEED means GUARANTEED

### 1.3 Relationship to Safety Envelope

UNS is part of MIP's **safety envelope**, alongside:

| System | Relationship to UNS |
|--------|---------------------|
| Agent Governor | Emits GOVERNANCE + SAFETY notifications |
| Why Layer (Phase 17.2) | Provides explanation context for notifications |
| Policy Registry | Controls routing bounds and escalation rules |
| YOLO / Autonomy Controller | Primary notification producer for state transitions |
| Circuit Breaker | Emits SAFETY notifications on engagement |

When these systems need to communicate with humans, they do so through UNS.

### 1.4 Control Plane Boundary

> **UNS operates entirely outside the execution data plane.**

UNS is **control plane infrastructure**:

| UNS Does | UNS Does NOT |
|----------|--------------|
| Signal state changes | Execute trades |
| Route awareness to humans | Block execution loops |
| Gate autonomy transitions | Participate in order routing |
| Log acknowledgments | Hold positions open |

**This boundary is non-negotiable.** If a feature proposal would make UNS participate in execution timing, reject it.

### 1.5 Notification Lifecycle (Visual)

```
┌─────────────────────────────────────────────────────────────────┐
│                    NOTIFICATION LIFECYCLE                        │
└─────────────────────────────────────────────────────────────────┘

  Producer                UNS Core               Channels           Human
  ────────               ────────               ────────           ─────
      │                      │                      │                 │
      │  send(notification)  │                      │                 │
      │─────────────────────>│                      │                 │
      │                      │                      │                 │
      │                      │ [validate]           │                 │
      │                      │ [check policy]       │                 │
      │                      │ [route by mode]      │                 │
      │                      │                      │                 │
      │                      │  deliver(channel)    │                 │
      │                      │─────────────────────>│                 │
      │                      │                      │  display        │
      │                      │                      │────────────────>│
      │                      │                      │                 │
      │                      │                      │     [ack]       │
      │                      │<─────────────────────│<────────────────│
      │                      │                      │                 │
      │                      │ [emit AckEvent]      │                 │
      │                      │ [update audit]       │                 │
      │                      │                      │                 │
      │  AckEvent            │                      │                 │
      │<─────────────────────│                      │                 │
      │                      │                      │                 │
  ────┴──────────────────────┴──────────────────────┴─────────────────┴────

  States: PENDING ──> ACKED | DISMISSED | TIMED_OUT
```

### 1.6 Notification Routing Contract

Notification routing in UNS is **deterministic and declarative**.

* Notification producers emit **semantic intent**, **autonomy context**, and **event metadata**
* Producers **must not** select delivery channels
* All routing decisions are made exclusively by the UNS Router
* Routing behavior is governed by a **versioned routing policy**

This separation ensures:
* consistent behavior across producers
* auditable notification delivery decisions
* safe evolution of routing logic without code changes

### 1.7 Golden Path Example: Kill Switch Activation

This example shows the full notification flow for a SAFETY event:

```
1. Circuit Breaker engages kill switch
   └─> Agent Governor emits: safety.kill_switch

2. UNS receives notification
   └─> autonomy_context: { mode: LIVE, agent_id: "atp-1" }
   └─> intent: SAFETY, delivery_mode: GUARANTEED

3. UNS routes per policy (autonomy_mode=LIVE)
   └─> Slack: #trading-alerts (immediate)
   └─> WebSocket: dashboard banner (immediate)
   └─> PagerDuty: on-call escalation (irreversible event)

4. Operator sees PagerDuty alert, opens dashboard
   └─> Clicks "Acknowledge" on kill switch notification

5. UNS records acknowledgment
   └─> acked_by: "operator@company.com"
   └─> acked_at: "2026-01-19T15:32:00Z"
   └─> ack_status: ACKED

6. UNS emits AckEvent
   └─> Agent Governor receives: human confirmed awareness
   └─> Audit log: SAFETY notification acknowledged in 47 seconds

7. [If no ack within 15 min]
   └─> UNS re-escalates via PagerDuty
   └─> ack_status: TIMED_OUT
   └─> Audit log: SAFETY notification timed out
```

**Result:** Complete audit trail proving human-in-the-loop awareness for safety-critical event.

---

## 2. Scope

### 2.1 In-Scope (All Phases)

| Capability | Description |
|------------|-------------|
| **SDK Interface** | Simple `send()` API with intent, delivery mode, and context |
| **Intent-based routing** | SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL |
| **UNS Router** | Evaluates notification events against routing policy to determine delivery mode, channels, acknowledgment requirements, and deduplication behavior |
| **Delivery guarantees** | GUARANTEED (must succeed) vs BEST_EFFORT (can fail) |
| **Autonomy awareness** | Every notification declares autonomy_mode, agent_id, plan_id |
| **Notification acknowledgment** | ACKED, DISMISSED, TIMED_OUT states for SAFETY/GOVERNANCE |
| **Declarative policies** | YAML-based notification behavior configuration |
| **Decision coupling** | Link to DecisionSnapshot, ExecutionSnapshot, SkipSnapshot |
| **Multi-channel delivery** | Slack, Email, WebSocket (UI), PagerDuty |
| **Irreversibility-based escalation** | PagerDuty for irreversible events only |
| **Cognitive deduplication** | Suppress duplicates to protect operator attention |
| **Rate limiting** | Token bucket per channel to prevent throttling |
| **Audit logging** | Record all notifications with delivery + acknowledgment status |

### 2.2 Out-of-Scope (v1.0)

| Excluded | Rationale |
|----------|-----------|
| User notification preferences | Phase 2+ feature |
| Push notifications (mobile) | No mobile app currently |
| SMS delivery | PagerDuty handles escalation |
| ML-based alert correlation | Future enhancement |
| Notification replay/history | WebSocket is cognitive stream, not audit log |
| Human-in-the-loop execution blocking | UNS informs, it doesn't gate execution |

### 2.3 Producer Contract (Guardrail)

> **All notifications MUST include `autonomy_context`.** Notifications without autonomy context are **rejected at the SDK layer**.

This is a **hard guard** against producer misuse:

| Validation | Enforcement |
|------------|-------------|
| Missing `autonomy_context` | `ValidationError` — notification rejected |
| Missing `autonomy_mode` | `ValidationError` — notification rejected |
| Missing `agent_id` | `ValidationError` — notification rejected |

**Why enforce this?** Autonomy-unaware notifications cannot be routed correctly, cannot be audited properly, and violate the core design principle that UNS is autonomy-aware infrastructure.

**Producer Guardrail**

Notification producers must never specify delivery channels directly.
Any request that attempts to override routing decisions is rejected.

### 2.3.1 Notification Idempotency (Producer Requirement)

All notifications must include a stable, producer-defined `idempotency_key`.

UNS guarantees **at-most-once semantic delivery per idempotency_key** within the dedup window.

#### Idempotency Rules
- Re-sending the same notification with the same `idempotency_key` MUST NOT create a new notification record
- Idempotency applies before routing, delivery, or escalation
- Idempotency is enforced regardless of channel or intent

#### Rationale
This prevents:
- retry storms from agent loops
- duplicate PagerDuty incidents
- inconsistent audit trails

#### Example
```json
{
  "notification_type": "safety.kill_switch",
  "idempotency_key": "kill-switch:agent=atp-1:timestamp=2026-01-19T15:31"
}
```

### 2.4 Architecture: Standalone-First Design (New in v1.2)

UNS is designed as a **standalone service** that can be integrated with ATP, not as an ATP-coupled component.

#### Why Standalone-First?

| Benefit | Description |
|---------|-------------|
| **Independent development** | UNS can be built, tested, and deployed without ATP dependencies |
| **Clean boundaries** | ATP-specific behavior is isolated in an integration module |
| **Testability** | Core UNS logic can be unit tested without mocking ATP internals |
| **Reusability** | Could be used by other MIP systems (data pipeline alerts, etc.) |
| **Incremental integration** | ATP integration can be added/modified without touching core UNS |

#### Integration Architecture

```
src/notification/                    # Core UNS (ATP-agnostic)
├── models.py                        # Pydantic schemas
├── interfaces.py                    # Protocol definitions
├── sdk.py                           # NotificationSDK with dependency injection
├── service.py                       # Delivery engine
├── adapters/                        # Channel adapters (Slack, Email, etc.)
├── deduplication.py
├── rate_limiting.py
├── policies.py
└── acknowledgment.py

src/notification/integrations/       # ATP-specific (separate module)
├── __init__.py                      # get_atp_sdk() factory
├── atp_context.py                   # ATPContextProvider implementation
├── atp_callbacks.py                 # ATPAckCallback implementation
├── governor_hooks.py                # Agent Governor → UNS notifications
├── execution_alerts.py              # ExecutionAlerts migration shim
└── why_layer.py                     # Decision Snapshot linking
```

#### Key Interfaces

UNS defines **Protocol** interfaces that ATP implements:

```python
class NotificationContextProvider(Protocol):
    """Provides autonomy context to UNS (implemented by ATP)."""
    def get_autonomy_mode(self) -> str: ...
    def get_agent_id(self) -> Optional[UUID]: ...
    def get_plan_id(self) -> Optional[UUID]: ...
    def get_decision_snapshot_id(self) -> Optional[UUID]: ...

class AcknowledgmentCallback(Protocol):
    """Handles ack events (implemented by ATP)."""
    async def on_ack(self, notification_id, ack_status, acked_by, metadata) -> None: ...
```

#### Usage Modes

| Mode | Context Provider | Ack Callback | Use Case |
|------|-----------------|--------------|----------|
| **Standalone** | `DefaultContextProvider` | None | Testing, non-ATP systems |
| **ATP** | `ATPContextProvider` | `ATPAckCallback` | Production ATP integration |
| **Test** | `MockContextProvider` | `MockAckCallback` | Unit testing |

#### SDK Factory

```python
# For ATP integration
from src.notification.integrations import get_atp_sdk
sdk = get_atp_sdk()
sdk.send_safety(...)

# For standalone usage
from src.notification.sdk import NotificationSDK
sdk = NotificationSDK()  # Uses default provider
sdk.send(...)
```

This architecture ensures UNS remains a **clean, testable, reusable service** while still providing deep ATP integration when needed.

---

## 3. Key Definitions

| Term | Meaning |
|------|---------|
| **Notification** | A state-change signal to be delivered to humans via one or more channels |
| **Intent** | Semantic category for human cognition routing (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL) |
| **Delivery Mode** | Guarantee level: GUARANTEED (must succeed or escalate) vs BEST_EFFORT (can fail silently) |
| **Irreversibility** | Whether the triggering event can be undone — determines escalation path |
| **Acknowledgment** | Human response: ACKED, DISMISSED, TIMED_OUT |
| **Autonomy Context** | Current operating mode (PREVIEW, SHADOW, LIVE) + agent/plan identifiers |
| **Decision Snapshot** | Why Layer reference explaining the triggering decision |
| **Channel** | Delivery destination (Slack, Email, WebSocket, PagerDuty) |
| **Producer** | System component that generates notifications (Agent Governor, Autonomy Controller, etc.) |
| **Notification Policy** | Declarative YAML defining behavior for a notification type |
| **Dedup Key** | Unique identifier for suppressing duplicate notifications (cognitive safety) |
| **Priority** | Processing order: HIGH, NORMAL, LOW |
| **DLQ** | Dead Letter Queue - storage for failed notifications requiring investigation |
| **Notification Version** | Integer version of the notification schema used at send time |

### 3.1 Intent Categories

| Intent | Description | Delivery Mode | Typical Escalation | Require Ack |
|--------|-------------|---------------|-------------------|-------------|
| **SAFETY** | Events affecting trading safety (kill switch, breaches) | GUARANTEED | PagerDuty | **Yes** |
| **GOVERNANCE** | Policy and autonomy changes requiring awareness | GUARANTEED | PagerDuty | Configurable |
| **OPERATIONAL** | Execution metrics, trade events | BEST_EFFORT | Slack | No |
| **INFORMATIONAL** | Summaries, completions, status updates | BEST_EFFORT | WebSocket | No |

### 3.2 Irreversibility Rule

> **PagerDuty escalation is triggered by irreversibility, not urgency.**

| Event Category | Reversible? | Escalation Path |
|----------------|-------------|-----------------|
| Trade skipped | Yes | None (log only) |
| Slippage breach | Yes | Slack |
| Kill switch activated | **No** | PagerDuty |
| Policy applied/retired | **No** | PagerDuty |
| Execution mode → LIVE | **No** | PagerDuty |
| Autonomy level change | **No** | PagerDuty |
| Circuit breaker engaged | **No** | PagerDuty |

---

## 4. Autonomy Awareness (New in v1.2)

### 4.1 Autonomy Context

Every notification **must declare autonomy context**:

```json
{
  "autonomy_mode": "PREVIEW | SHADOW | LIVE",
  "agent_id": "uuid",
  "plan_id": "uuid | null",
  "decision_snapshot_id": "uuid | null"
}
```

### 4.2 Mode-Dependent Behavior

The *same* event means different things depending on autonomy mode:

| Autonomy Mode | Notification Behavior |
|---------------|----------------------|
| **PREVIEW** | All notifications → WebSocket only (low noise) |
| **SHADOW** | OPERATIONAL → WebSocket, GOVERNANCE → Slack |
| **LIVE** | Full routing per intent + escalation |

### 4.3 Decision Coupling

Notifications **can** (and should) link to Why Layer artifacts:

| Snapshot Type | When to Link |
|---------------|--------------|
| DecisionSnapshot | Policy/governance decisions |
| ExecutionSnapshot | Trade execution events |
| SkipSnapshot | Trade skip events with reasons |

This turns alerts into **explanations**, not noise.

---

## 5. Notification Acknowledgment (New in v1.2)

### 5.1 Purpose

Certain notifications require human acknowledgment to:

* Confirm the human received the signal
* Enable feedback loop to agents
* Satisfy audit requirements
* Optionally gate autonomy transitions

### 5.2 Acknowledgment States

| State | Meaning |
|-------|---------|
| **PENDING** | Delivered, awaiting acknowledgment |
| **ACKED** | Human acknowledged (saw and understood) |
| **DISMISSED** | Human dismissed (saw but chose not to act) |
| **TIMED_OUT** | No response within timeout window |

Acknowledgment is a **state-changing control-plane operation**, not a UI affordance.

* ACK signals are submitted via a dedicated API endpoint
* ACK operations are **idempotent**
* Each ACK produces an immutable audit record
* ACK transitions are validated against notification state

**ACK Safety Invariant**

Acknowledgments may influence **future governance or autonomy transitions**,
but must never block, delay, or modify **in-flight trading execution**.

### 5.3 Requirements by Intent

| Intent | Require Ack | Timeout | On Timeout |
|--------|-------------|---------|------------|
| SAFETY | **Yes** | 15 min | Re-escalate + audit |
| GOVERNANCE | Configurable | 30 min | Log + optional re-alert |
| OPERATIONAL | No | N/A | N/A |
| INFORMATIONAL | No | N/A | N/A |

### 5.4 Acknowledgment Feedback Loop

Acknowledgment events are emitted back into the system for:

* **Audit** — Compliance record of human awareness
* **Agent Learning** — Did the human act on this information?
* **Governance Enforcement** — Can autonomy proceed without ack?
* **Trust Calibration** — Human response patterns inform autonomy levels

### 5.5 Ack Identity Source of Truth

The `acked_by` field must be a **resolvable identity** for audit defensibility:

| Channel | Identity Source | Format |
|---------|-----------------|--------|
| WebSocket | Authenticated UI session | `user@example.com` (from JWT) |
| Slack | Slack user ID → internal mapping | `slack:U12345ABC` or resolved email |
| PagerDuty | On-call rotation identity | `pagerduty:oncall@service-name` |

**Rule:** If identity cannot be resolved to an internal user, preserve the qualified external identifier (e.g., `slack:U12345ABC`) for audit trail. Do not record "unknown."

### 5.6 Notification Invalidation

Producers may invalidate a previously sent notification.

Effects:
- Pending acknowledgments are canceled
- UI removes notification
- Audit record is updated with `INVALIDATED`

Invalidation does not delete audit history.

---

## 6. Declarative Notification Policies (New in v1.2)

### 6.1 Purpose

Notification behavior is **declarative**, versioned, and auditable — not embedded in code.

### 6.2 Policy Schema

```yaml
notification_policy:
  id: safety.kill_switch
  version: 1
  intent: SAFETY
  delivery_mode: GUARANTEED
  channels:
    - SLACK
    - WEBSOCKET
    - PAGERDUTY
  require_ack: true
  ack_timeout_minutes: 15
  block_autonomy_until_ack: false
  dedup_window_seconds: 60
  include_decision_snapshot: true
  recipients:
    - type: ROLE
      value: "trading_operator"
    - type: ON_CALL
      value: "trading-primary"
  autonomy_mode_overrides:
    PREVIEW:
      channels: [WEBSOCKET]
      require_ack: false
    SHADOW:
      channels: [SLACK, WEBSOCKET]
      require_ack: false
```

### 6.3 Recipient Resolution

Recipient resolution is performed at delivery time and may resolve to:
- individual users
- on-call rotations
- role-based groups

UNS does not store static user lists.

Recipients are specified in policy via:
```yaml
recipients:
  - type: ROLE
    value: "trading_operator"
  - type: ON_CALL
    value: "trading-primary"
```

### 6.4 `block_autonomy_until_ack` Semantics

> **Critical Rule:** `block_autonomy_until_ack` may only pause **state transitions**, never **execution loops**.

| Allowed to Block | NOT Allowed to Block |
|------------------|----------------------|
| PREVIEW → SHADOW transition | Running trade execution cycle |
| SHADOW → LIVE transition | Active order routing |
| Policy activation | Position management loop |
| Autonomy level escalation | Market data processing |

This ensures UNS remains **control plane only** and cannot accidentally create human-in-the-loop execution gating.

### 6.5 Notification Simulation Mode

UNS supports a dry-run mode where notifications are evaluated but not delivered.

Simulation outputs:
- resolved channels
- escalation paths
- ack requirements
- dedup/suppression decisions

Simulation is required before activating new notification policies.

### 6.6 Policy Registry

* Policies stored in `atp.notification_policy` table (migration: `053_notification_policy.sql`)
* Versioned with content hash (SHA-256) for audit and deduplication
* ACTIVE and PREVIEW policies loaded into in-memory cache on startup
* Policy lifecycle: DRAFT → PREVIEW → ACTIVE → RETIRED
* Version chain: `previous_version_id` links new activations to retired predecessors
* Hot-reload: `POST /api/v1/policies/reload` refreshes cache from DB without restart
* YAML loader: `policy_loader.py` loads from `config/notification_policies/` directory
* MIP-225 guardrail: Producers cannot specify channels — routing is policy-driven

### 6.7 Default Policies

Six default policies are registered at startup:

| notification_type | delivery_mode | escalation | require_ack |
|---|---|---|---|
| `safety.kill_switch` | GUARANTEED | PagerDuty ALWAYS (LIVE) | Yes (LIVE) |
| `governance.approval_required` | GUARANTEED | PagerDuty ON_FAILURE (LIVE) | Yes (LIVE) |
| `execution.slippage` | BEST_EFFORT | None | No |
| `governance.autonomy_level_change` | GUARANTEED | PagerDuty ON_FAILURE (LIVE) | Yes (LIVE) |
| `safety.circuit_breaker_engaged` | GUARANTEED | PagerDuty ALWAYS (LIVE) | Yes (LIVE) |
| `safety.circuit_breaker_recovered` | BEST_EFFORT | None | No |

---

## 7. User Stories

### 7.1 Safety & Governance (GUARANTEED Delivery + Acknowledgment)

1. **As an operator**, I want kill switch activations to **always** reach me, even if Slack is down.
2. **As an operator**, I want to acknowledge SAFETY notifications so the system knows I'm aware.
3. **As an operator**, I want policy changes that affect live trading to trigger PagerDuty escalation.
4. **As a risk owner**, I want circuit breaker engagement to be delivery-fatal (system fails loudly if undeliverable).
5. **As an auditor**, I want proof that safety-critical notifications were delivered **and acknowledged**.

### 7.2 Operational Awareness (BEST_EFFORT Delivery)

6. **As an operator**, I want execution alerts without being spammed during incidents.
7. **As an operator**, I want duplicate alerts summarized ("17 slippage alerts in 3m — regime misalignment").
8. **As a developer**, I want notifications to not block agent code (async delivery).

### 7.3 Cognitive Safety

9. **As an operator**, I want deduplication to protect my attention, not just reduce load.
10. **As an operator**, I want WebSocket notifications to show what I should notice **right now**, not history.
11. **As an operator**, I want different notification types to be visually distinct (intent-based formatting).

### 7.4 Autonomy Awareness (New)

12. **As an operator**, I want notifications to include autonomy context so I know if this is PREVIEW/SHADOW/LIVE.
13. **As an operator**, I want PREVIEW mode to be quieter than LIVE mode.
14. **As an operator**, I want to click through from a notification to see *why* this decision was made (Why Layer).

### 7.5 Agent Learning (New)

15. **As a system**, I want to know if humans acknowledged or dismissed notifications.
16. **As a system**, I never want to assume humans saw a message without confirmation.

---

## 8. Phased Delivery

### Phase 1: Foundation (Weeks 1-2)

**Goal:** SDK with intent/delivery-mode semantics + basic delivery

| Deliverable | Description | Success Criteria |
|-------------|-------------|------------------|
| NotificationSDK | `send()` with intent, delivery_mode, autonomy_context | Producers specify semantic intent + context |
| Intent Routing | Route based on SAFETY/GOVERNANCE/OPERATIONAL/INFO | Different intents → different handling |
| Autonomy Context | All notifications include mode + agent_id | Context always present |
| Slack Adapter | Extract from `execution/alerts.py` | Slack delivery works via SDK |
| Email Adapter | Extract from `execution/alerts.py` | Email delivery works via SDK |
| ExecutionAlerts Migration | First producer migrated | All execution alerts flow through UNS |

### Phase 2: Reliability & Safety Paths (Weeks 3-4)

**Goal:** GUARANTEED delivery for safety paths + cognitive deduplication

| Deliverable | Description | Success Criteria |
|-------------|-------------|------------------|
| Delivery Guarantees | GUARANTEED notifications fail loudly if undeliverable | Safety paths never silently fail |
| Cognitive Deduplication | Suppress duplicates with summary pulses | Operators see signal, not noise |
| Rate Limiting | Token bucket per channel | Slack webhook not throttled |
| Dead Letter Queue | Failed notifications visible + alerting | DLQ depth monitored |
| Audit Logging | Log to `notification_audit` table | All notifications queryable |
| Notification Policies | YAML-based policy definitions | Behavior is declarative |

### Phase 3: Integration & Acknowledgment (Weeks 5-6)

**Goal:** Full integration with safety envelope + acknowledgment loop

| Deliverable | Description | Success Criteria |
|-------------|-------------|------------------|
| PagerDuty Adapter | Irreversibility-based escalation | Only irreversible events trigger PagerDuty |
| WebSocket Adapter | Cognitive stream (not history) | UI shows current-attention items |
| Acknowledgment System | ACKED/DISMISSED/TIMED_OUT for SAFETY | Humans confirm receipt |
| Decision Coupling | Link notifications to DecisionSnapshot | Alerts include "why" |
| Agent Governor Integration | REQUIRE_APPROVAL → notification | Approval requests notify operators |
| Autonomy Controller Integration | State transitions → notification | LIVE transitions escalate to PagerDuty |
| Kill Switch Integration | Activation → GUARANTEED delivery + require_ack | Kill switch always reaches humans |

### Phase 4: Observability & Feedback (Post-MVP)

**Goal:** Operational visibility, compliance, and agent feedback loop

| Deliverable | Description | Success Criteria |
|-------------|-------------|------------------|
| Notification Dashboard | View by intent + delivery + ack status | Operators can filter by safety/governance |
| Delivery Metrics | Success rate by intent, latency, DLQ depth | Intent-specific monitoring |
| Acknowledgment Metrics | Ack rate, timeout rate by intent | Track human responsiveness |
| Agent Feedback Channel | Publish ack events for agent learning | Agents know if humans engaged |
| PII Masking | Regex-based hot path masking | No PII in notification payloads |

---

## 9. Notification Types by Intent

### 9.1 SAFETY Intent (Irreversible → GUARANTEED + Require Ack)

These notifications are part of the **safety envelope**. Delivery failure is a system failure.

| Type | Source | Channels | Delivery | Require Ack | SLA |
|------|--------|----------|----------|-------------|-----|
| Kill Switch Activated | Autonomy Controller | Slack, PagerDuty, WS | **GUARANTEED** | **Yes** | < 1 min |
| Circuit Breaker Engaged | Agent Runner | Slack, PagerDuty, WS | **GUARANTEED** | **Yes** | < 1 min |
| Portfolio Breach | Safety Monitor | Slack, PagerDuty | **GUARANTEED** | **Yes** | < 5 min |
| Margin Call Warning | Risk Engine | Slack, PagerDuty, Email | **GUARANTEED** | **Yes** | < 5 min |

### 9.2 GOVERNANCE Intent (Irreversible → GUARANTEED + Configurable Ack)

Policy and autonomy changes that humans must be aware of.

| Type | Source | Channels | Delivery | Require Ack | SLA |
|------|--------|----------|----------|-------------|-----|
| Policy Activated | Agent Governor | Slack, PagerDuty | **GUARANTEED** | Yes | < 5 min |
| Policy Retired | Agent Governor | Slack, PagerDuty | **GUARANTEED** | Yes | < 5 min |
| Execution Mode → LIVE | Autonomy Controller | Slack, PagerDuty | **GUARANTEED** | Yes | < 5 min |
| Autonomy Level Change | Autonomy Controller | Slack, PagerDuty | **GUARANTEED** | Yes | < 5 min |
| Approval Required | Agent Governor | Slack, WebSocket | BEST_EFFORT | No | < 15 min |
| Approval Granted/Rejected | Agent Governor | Slack, WebSocket | BEST_EFFORT | No | < 15 min |

### 9.3 OPERATIONAL Intent (Reversible → BEST_EFFORT)

Execution metrics and trade events. Important but not safety-critical.

| Type | Source | Channels | Delivery | Require Ack | SLA |
|------|--------|----------|----------|-------------|-----|
| Slippage Alert | ExecutionAlerts | Slack, Email | BEST_EFFORT | No | < 15 min |
| Fill Rate Alert | ExecutionAlerts | Slack | BEST_EFFORT | No | < 15 min |
| Error Rate Alert | ExecutionAlerts | Slack | BEST_EFFORT | No | < 15 min |
| Whale Accumulation | WhaleService | Slack, WebSocket | BEST_EFFORT | No | < 15 min |
| Validation Failure | ValidationMetrics | Slack | BEST_EFFORT | No | < 15 min |
| Trade Skipped | Execution Engine | WebSocket | BEST_EFFORT | No | Best effort |

### 9.4 INFORMATIONAL Intent (Reversible → BEST_EFFORT)

Status updates and summaries. Nice to have, not critical.

| Type | Source | Channels | Delivery | Require Ack | SLA |
|------|--------|----------|----------|-------------|-----|
| Daily Summary | ExecutionAlerts | Email | BEST_EFFORT | No | Best effort |
| Backtest Complete | BacktestService | WebSocket | BEST_EFFORT | No | Best effort |
| Agent Session End | AgentRunner | WebSocket | BEST_EFFORT | No | Best effort |
| Dedup Summary Pulse | UNS | Slack | BEST_EFFORT | No | Best effort |

---

## 10. Channel Specifications

### 10.1 Slack

| Property | Value |
|----------|-------|
| Rate Limit | 1 request/second (webhook limit) |
| Format | Block Kit with intent-based formatting |
| Intent Indicators | 🚨 SAFETY, 📋 GOVERNANCE, ⚙️ OPERATIONAL, ℹ️ INFO |
| Autonomy Badge | [PREVIEW] [SHADOW] [LIVE] |
| Ack Button | Interactive button for SAFETY/GOVERNANCE (if require_ack) |
| Retry | 3 attempts with backoff |
| Fallback | Email if Slack fails (for GUARANTEED) |

### 10.2 Email

| Property | Value |
|----------|-------|
| Rate Limit | 10 requests/second |
| Format | HTML with plain text fallback |
| Retry | 3 attempts with backoff |
| Batching | INFORMATIONAL intent batched hourly |

### 10.3 WebSocket (Cognitive Stream)

| Property | Value |
|----------|-------|
| Purpose | **What the human should notice right now** |
| NOT for | History, replay, audit |
| Rate Limit | None (internal) |
| Format | JSON with intent, autonomy_context, decision_snapshot_id |
| Retry | None (fire and forget) |
| Broadcast | All connected clients |
| Ack Support | UI can send ack events back via WebSocket |
| Persistence | **None** — persistence is in audit table, not WebSocket |

### 10.4 PagerDuty (Irreversibility Escalation)

| Property | Value |
|----------|-------|
| Trigger | **Irreversible events only** (not just HIGH priority) |
| Rate Limit | Per PagerDuty plan |
| Format | PagerDuty Events API v2 |
| Retry | 5 attempts with backoff |
| Dedup Key | Used to prevent duplicate incidents |
| Custom Details | Include autonomy_mode, decision_snapshot_id |

---

## 11. Deduplication (Cognitive Safety)

### 11.1 Purpose

Deduplication in UNS is **cognitive safety**, not performance optimization.

> The agent doesn't care about notification storms — the **human operator** does.

### 11.2 Dedup Key Generation

```
dedup_key = hash(notification_type + source + autonomy_mode + truncated_message[:100])
```

Note: `autonomy_mode` is included so PREVIEW/LIVE of same event are separate.

### 11.3 Window Configuration by Intent

| Intent | Window | Rationale |
|--------|--------|-----------|
| SAFETY | 1 minute | Critical — need fast re-alert if persistent |
| GOVERNANCE | 5 minutes | Important but less time-sensitive |
| OPERATIONAL | 5 minutes | Balance awareness and attention |
| INFORMATIONAL | 30 minutes | Can be heavily deduplicated |

### 11.4 Summary Pulse (Cognitive Aggregation)

When duplicates suppressed ≥ 5 in window, send summary:

```
"17 similar execution skips in last 3m — regime misalignment"
```

This matches **how a trader thinks** — pattern recognition, not individual events.

### 11.5 Suppression Windows

Policies may define suppression windows to intentionally silence repeat notifications.

Example:
```yaml
suppress_for_minutes: 30
```

During suppression:

* Notifications are recorded in audit logs
* No delivery occurs
* Suppression is visible in audit metadata

This protects operator focus during known noisy conditions.

---

## 12. Failure Handling

### 12.1 GUARANTEED Delivery (Safety Paths)

GUARANTEED delivery ensures that notifications are not silently dropped.
A GUARANTEED notification must result in exactly one of the following outcomes:
* successful delivery
* escalation according to routing policy
* visible system degradation signaling

Silent failure is forbidden.

For SAFETY and GOVERNANCE intents with `delivery_mode=GUARANTEED`:

```
1. Try primary channel (Slack)
2. If fails, try fallback channel (Email)
3. If fails, try escalation channel (PagerDuty)
4. If ALL fail:
   → Persist to crash-safe storage
   → Log CRITICAL error
   → System health check fails
   → DLQ alert via alternative path
```

**The control plane is allowed to fail loudly.** This does not violate non-blocking agent execution — the agent doesn't block, but the notification system raises alarms.

### 12.2 BEST_EFFORT Delivery (Operational Paths)

For OPERATIONAL and INFORMATIONAL intents:

```
1. Try primary channel
2. If fails, retry with backoff (1s, 2s, 4s, 8s)
3. After max retries, move to DLQ
4. Log warning (not critical)
```

### 12.3 Acknowledgment Timeout Handling

```
1. SAFETY notification delivered with require_ack=true
2. Start 15-minute timeout
3. If no ack:
   → Status = TIMED_OUT
   → Re-escalate to PagerDuty
   → Log audit event
   → Emit ack_timeout event for agent learning
```

### 12.4 DLQ Visibility for GUARANTEED Failures

When GUARANTEED notifications fail to DLQ, the invariant is:

> **GUARANTEED = delivered OR escalated OR visible system degradation**

NOT infinite retry loops.

| Condition | System Response |
|-----------|-----------------|
| DLQ depth > 0 for SAFETY/GOVERNANCE | System health = **DEGRADED** |
| Health degradation | Surfaces via `/health` endpoint + monitoring |
| DLQ batch alert | One OPERATIONAL alert per batch (not per item) |

**Why not re-page?** Recursive escalation creates alert storms. DLQ-caused degradation is visible through health monitoring, which operators already watch.

### 12.5 Retry Semantics by Intent

Retry behavior is intent-aware and deterministic.

| Intent | Retry Strategy |
|--------|---------------|
| SAFETY | Retry until success or escalation |
| GOVERNANCE | Retry primary channel, then escalate |
| OPERATIONAL | Fixed retry count with backoff |
| INFORMATIONAL | No retries beyond initial attempt |

Retry behavior MUST be defined in notification policy and never hard-coded.

### 12.6 Channel Health State

UNS maintains real-time health state per delivery channel.

| State | Meaning |
|-------|---------|
| HEALTHY | Delivering within SLA |
| DEGRADED | Elevated retries or latency |
| UNAVAILABLE | Delivery failures exceeding threshold |

Channel health is:
- queryable via `/health`
- emitted as OPERATIONAL notifications (deduplicated)
- included in audit context for failed deliveries

---

## 13. Audit Requirements

### 13.1 Required Fields

Every notification must log:

| Field | Type | Description |
|-------|------|-------------|
| `notification_id` | UUID | Unique identifier |
| `notification_type` | string | e.g., "safety.kill_switch" |
| `intent` | enum | SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL |
| `delivery_mode` | enum | GUARANTEED, BEST_EFFORT |
| `irreversible` | boolean | Whether triggering event is irreversible |
| `priority` | enum | HIGH, NORMAL, LOW |
| `channels` | array | Target channels |
| `autonomy_mode` | enum | PREVIEW, SHADOW, LIVE |
| `agent_id` | UUID | Agent that triggered notification |
| `plan_id` | UUID | Associated plan (if any) |
| `decision_snapshot_id` | UUID | Why Layer reference (if any) |
| `dedup_key` | string | For duplicate tracking |
| `require_ack` | boolean | Whether acknowledgment required |
| `created_at` | timestamp | When notification created |
| `delivered_at` | timestamp | When successfully delivered |
| `delivery_status` | enum | PENDING, DELIVERED, FAILED, DEDUPLICATED, ESCALATED |
| `ack_status` | enum | PENDING, ACKED, DISMISSED, TIMED_OUT (if require_ack) |
| `acked_at` | timestamp | When acknowledged |
| `acked_by` | string | User who acknowledged |
| `failure_reason` | string | If FAILED, why |
| `retry_count` | int | Number of retry attempts |
| `escalated_to` | string | If escalated, which channel |
| `notification_version` | int | Schema version used to emit this notification |
| `correlation_id` | UUID | Cross-system trace identifier |

Correlation IDs enable full traceability across:
- agent decision
- notification routing
- human acknowledgment
- subsequent agent behavior

### 13.2 Retention

| Environment | Retention |
|-------------|-----------|
| Development | 7 days |
| Production | 90 days |
| Compliance Archive | 7 years (S3) |

---

## 14. Success Criteria

### Phase 1 Complete When:

- [ ] SDK deployed with intent, delivery_mode, and autonomy_context
- [ ] ExecutionAlerts migrated to SDK
- [ ] Slack and Email delivery working via UNS
- [ ] Intent-based formatting visible in Slack with autonomy badge

### Phase 2 Complete When:

- [ ] GUARANTEED notifications fail loudly if undeliverable
- [ ] Cognitive deduplication prevents operator fatigue
- [ ] Summary pulses generated for duplicate storms
- [ ] All notifications logged to audit table with intent + autonomy_context
- [ ] At least 5 notification policies defined in YAML

### Phase 3 Complete When:

- [ ] Kill switch → PagerDuty (GUARANTEED + require_ack) working
- [ ] SAFETY acknowledgment workflow functional in UI
- [ ] Decision snapshot links visible in notifications
- [ ] Ack/dismiss events logged and available for agent learning
- [ ] All legacy notification code removed

### Overall Success:

| Metric | Target |
|--------|--------|
| GUARANTEED delivery success | **100%** (escalate if primary fails) |
| BEST_EFFORT delivery success | > 99.5% |
| SAFETY intent latency | < 1 min (99th percentile) |
| GOVERNANCE intent latency | < 5 min (99th percentile) |
| SAFETY ack rate | > 95% within timeout |
| Duplicate suppression during incidents | > 80% |
| DLQ depth (steady state) | < 5 |

---

## 15. Non-Goals (Explicit)

UNS is **not**:

* An inbox
* A chat replacement
* A manual retry UX
* A human-in-the-loop execution blocker (except where explicitly required)
* A notification history browser (that's the audit table)

Humans understand *why* they were interrupted.
Agents never assume humans saw a message.
Safety paths never fail silently.
Notifications improve decision quality, not noise.
Every critical interrupt is auditable and explainable.

---

## 16. Dependencies

| Dependency | Current State | Required Action |
|------------|---------------|-----------------|
| Redis | In use (RQ) | None |
| Slack Webhook | Configured in alerts.py | Move to environment variable |
| SMTP | Configured in alerts.py | Move to environment variable |
| PagerDuty | Not configured | **Required for Phase 3** — Add API key to secrets |
| WebSocket Manager | Exists (AtpConnectionManager) | Add notification + ack message types |
| Agent Governor | Exists | Add notification triggers for policy events |
| Autonomy Controller | Exists | Add notification triggers for state transitions |
| Why Layer (17.2) | Exists | Add decision_snapshot_id linking |

---

## 17. Future Considerations (Post-v1.0)

| Feature | Description | Phase |
|---------|-------------|-------|
| User Preferences | Per-user channel preferences by intent | 2.0 |
| Intent-based Routing Rules | Configurable routing by intent + source | 2.0 |
| Escalation Policies | Time-based escalation (Slack → PagerDuty after N min) | 2.0 |
| Notification Center | UI inbox filtered by intent | 2.0 |
| Agent Feedback Analysis | ML on ack patterns for trust calibration | 3.0 |
| Smart Batching | ML-based alert correlation by intent | 3.0 |

---

## Appendix A: Migration Checklist

### ExecutionAlerts Migration

- [ ] Extract `send_slack_alert()` to SlackAdapter
- [ ] Extract `send_email_alert()` to EmailAdapter
- [ ] Replace direct calls with `sdk.send()` with `intent=OPERATIONAL`
- [ ] Add `autonomy_context` to all send calls
- [ ] Add feature flag `USE_UNS=true`
- [ ] Test both paths in staging
- [ ] Remove old code after 1 week stable

### Agent Governor Integration

- [ ] Add notification for REQUIRE_APPROVAL outcome (`intent=GOVERNANCE`)
- [ ] Add notification for `approve_contract()` (`intent=GOVERNANCE`)
- [ ] Add notification for `reject_contract()` (`intent=GOVERNANCE`)
- [ ] Add notification for policy activation (`intent=GOVERNANCE`, `delivery_mode=GUARANTEED`, `require_ack=true`)
- [ ] Include `decision_snapshot_id` in all governance notifications
- [ ] Map TimelineEventType to NotificationType

### Autonomy Controller Integration

- [ ] Add notification for kill switch activation (`intent=SAFETY`, `delivery_mode=GUARANTEED`, `require_ack=true`)
- [ ] Add notification for LIVE transition (`intent=GOVERNANCE`, `delivery_mode=GUARANTEED`, `require_ack=true`)
- [ ] Add notification for autonomy level change (`intent=GOVERNANCE`, `delivery_mode=GUARANTEED`)
- [ ] Include `autonomy_context` in all notifications

### Circuit Breaker Integration

- [ ] Add notification for circuit breaker engagement (`intent=SAFETY`, `delivery_mode=GUARANTEED`, `require_ack=true`)
- [ ] Add notification for circuit breaker recovery (`intent=SAFETY`)

---

## Appendix B: Intent Decision Tree

```
Is this event part of the safety envelope?
├─ YES → intent = SAFETY, delivery_mode = GUARANTEED, require_ack = true
│        (kill switch, circuit breaker, breaches)
│
└─ NO → Does this event change policy or autonomy?
        ├─ YES → Is the change irreversible?
        │        ├─ YES → intent = GOVERNANCE, delivery_mode = GUARANTEED, require_ack = true
        │        │        (policy activated, LIVE mode, autonomy change)
        │        │
        │        └─ NO → intent = GOVERNANCE, delivery_mode = BEST_EFFORT
        │                (approval requested, approval granted)
        │
        └─ NO → Is this actionable operational data?
                ├─ YES → intent = OPERATIONAL, delivery_mode = BEST_EFFORT
                │        (slippage alert, whale accumulation)
                │
                └─ NO → intent = INFORMATIONAL, delivery_mode = BEST_EFFORT
                        (summaries, completions)
```

---

## Appendix C: Example Notification Policy (YAML)

```yaml
# config/notification_policies/safety_kill_switch.yaml
# Current format as implemented in policy_loader.py
notification_type: "safety.kill_switch"
version: "2.0.0"
status: "ACTIVE"
delivery_mode: "GUARANTEED"
delivery_mode_by_autonomy:
  PREVIEW: "BEST_EFFORT"
  LIVE: "GUARANTEED"
channels:
  PREVIEW: ["WEBSOCKET"]
  SHADOW: ["SLACK", "WEBSOCKET"]
  LIVE: ["SLACK", "WEBSOCKET"]
channels_escalation:
  LIVE: ["PAGERDUTY"]
escalation_trigger: "ALWAYS"
require_ack:
  PREVIEW: false
  SHADOW: false
  LIVE: true
dedup_window_seconds: 60
description: "Kill switch activation — highest priority safety notification"
```

> **Note:** The YAML schema evolved from the original v1.2 design (Pydantic-based
> `notification_policy:` wrapper with `autonomy_mode_overrides`) to a flat dataclass
> format with explicit per-mode dicts for `channels`, `channels_escalation`,
> `delivery_mode_by_autonomy`, and `require_ack`. The `policy_loader.py` module
> handles YAML parsing via `yaml.safe_load()` → `NotificationPolicy.from_dict()`.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-19 | Claude | Initial specification |
| 1.1 | 2026-01-19 | Claude | Added intent/delivery-mode framework, irreversibility-based escalation, cognitive safety framing, safety-path strictness |
| 1.2 | 2026-01-19 | Claude | Added autonomy awareness (autonomy_mode, agent_id, plan_id), notification acknowledgment (ACKED/DISMISSED/TIMED_OUT), declarative notification policies (YAML), decision coupling (decision_snapshot_id), agent feedback loop |
| 1.2.1 | 2026-01-19 | Claude | Pre-lock polish: Control plane boundary (§1.4), notification lifecycle diagram (§1.5), golden path example (§1.6), producer contract guardrail (§2.3), ack identity source of truth (§5.5), block_autonomy_until_ack semantics (§6.3), DLQ visibility invariant (§12.4) |
| 2.0 | 2026-01-19 | Claude | Version bump for standalone UNS service: This version marks the transition to a standalone, reusable notification service architecture. All previous features remain intact. |
| 2.1 | 2026-02-10 | Claude | Policy engine stabilization: Full lifecycle (DRAFT→PREVIEW→ACTIVE→RETIRED), YAML loader (`policy_loader.py`), policy versioning (`previous_version_id` chain), DB persistence (`NotificationPolicyModel`, migration 053), hot-reload endpoint (`POST /policies/reload`), MIP-225 resolution (channel overrides removed from governor/circuit breaker hooks), 6 default policies |

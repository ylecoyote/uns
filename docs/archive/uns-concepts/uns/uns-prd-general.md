> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Product Requirements Document: Unified Notification Service (UNS)
## A Governance Control Plane for Autonomous Systems

**Version:** 1.0
**Status:** STABLE
**Audience:** Product, Engineering, Platform Teams, Risk & Compliance
**Last Updated:** 2026-04-22

> **Note on scope:** This is the domain-agnostic PRD. For financial services deployments
> requiring DORA, FINRA, and HFT-specific requirements, see
> `unified_notification_and_signaling_prd.md`.

---

## 1. Introduction and Strategic Vision

### 1.1 Executive Summary

Autonomous systems have crossed a threshold. Agents no longer just recommend — they act.
They execute workflows, modify state, invoke external services, and make decisions faster
than any human can supervise in real time.

This shift creates a new class of organizational failure mode: **accountable but
unobservable autonomy**. When something goes wrong, the questions are inevitable:

- *Why did the system act?*
- *Who knew?*
- *Was there an opportunity to intervene?*
- *Can we prove what humans were aware of at the time?*

Today's tooling cannot answer these questions reliably. Logs explain what happened, not
who knew. Alerts notify humans, but acknowledgments have no durable meaning. Observability
platforms tell you what occurred; they cannot prove awareness or accountability.

**There is no standard infrastructure layer for human awareness and accountability in
autonomous systems.**

The Unified Notification Service (UNS) is that layer. It is a **governance control
plane** — not an alerting tool, not a logging pipeline, not an observability platform.
UNS introduces a new primitive:

> **Notifications and acknowledgments as auditable, machine-legible governance
> signals — without blocking execution.**

### 1.2 Product Vision

UNS is the missing layer between autonomous agents and the humans accountable for them.

It sits entirely outside the execution path. It does not make decisions. It does not
pause agents. It does not participate in whatever the agents are doing. It operates on
one axis only: **ensuring that human awareness of autonomous actions is provable,
durable, and governable**.

When agents act, UNS ensures:
- The right humans were notified
- With the right urgency and through the right channel
- That their acknowledgment (or silence) is captured as a durable, auditable event
- That the history of awareness and response is queryable after the fact

### 1.3 Core Value Proposition

Three things UNS provides that nothing else does together:

**1. Durable notification state**
Notifications are stateful objects, not fire-and-forget messages. Each has a lifecycle:
PENDING → DELIVERED → ACKED / DISMISSED / TIMED_OUT. Every transition is persisted and
auditable. Notifications cannot silently disappear.

**2. Acknowledgments that mean something**
An ACK in UNS is not a UI click. It is an explicit, idempotent API call that creates an
immutable governance record: this human, at this time, acknowledged this agent action.
Silence is also a state — TIMED_OUT — not an unknown. The system knows the difference
between "human acknowledged" and "nobody responded."

**3. Autonomy context**
Every notification carries context about the agent's operating mode (PREVIEW / SHADOW /
LIVE). Routing, delivery guarantees, and escalation behavior change based on this
context. A notification from an agent operating in PREVIEW (not yet acting on real data)
is handled differently from one in LIVE mode.

### 1.4 What UNS Explicitly Does Not Do

- **Does not execute actions.** UNS never tells agents what to do.
- **Does not block execution.** Agents never wait for humans before proceeding.
- **Does not contain business logic.** UNS is intentionally domain-agnostic.
- **Does not replace your channels.** It routes *to* Slack, PagerDuty, email, MCP — it
  doesn't replace them.
- **Does not duplicate your observability stack.** It is a governance layer, not a
  tracing or metrics system.

The boundary is non-negotiable: if a proposed feature would make UNS participate in
execution timing or decision-making, it is out of scope.

---

## 2. The Problem in Detail

### 2.1 Why Existing Tools Fall Short

**Logs** tell you what happened. They do not tell you who knew, whether escalation
paths worked, or whether a human meaningfully reviewed the information.

**Alerting tools** (PagerDuty, OpsGenie, Slack) notify humans but:
- Acknowledgments are ephemeral ("someone clicked"), not governance records
- Silence is optimized away, not surfaced as a visible state
- There is no concept of agent autonomy level affecting routing
- Alert history is not linkable to agent decisions

**Observability platforms** (Datadog, Grafana, LangSmith) trace what agents did but:
- They are post-hoc, not real-time governance
- They produce audit *substrates*, not accountability *evidence*
- They cannot prove who was aware of what at the time of action

**Human-in-the-loop frameworks** (LangGraph `interrupt()`, Temporal Signals, Restate
awakeables) provide excellent durable pause/resume primitives but:
- They are per-workflow, not fleet-level governance
- You wire all notification delivery, routing, escalation, and ack tracking yourself
- There is no domain model for governance signals — just workflow plumbing

**Enforcement platforms** (Galileo, Trussed AI, Microsoft Agent Governance Toolkit)
perform runtime policy enforcement but:
- They intercept and block; they do not model a notification lifecycle
- They produce enforcement events, not durable human-addressed governance signals
- When something goes wrong, they can say "it was blocked" — they cannot prove awareness

### 2.2 The Accountability Gap

The failure mode UNS addresses is subtle but consequential. In regulated or high-stakes
environments, accountability requires more than a log of what happened. It requires:

1. **Proof of notification** — the right stakeholder was informed
2. **Proof of delivery** — the notification reached them, or failure was visible
3. **Proof of awareness** — they acknowledged receipt and understood the situation
4. **Proof of response** — what they did (or that silence was intentional)
5. **Proof of context** — what level of autonomy the agent was operating at

No existing system produces all five as a unified, queryable record.

---

## 3. System Architecture

### 3.1 Design Principles

1. **Intent over channel** — Semantic meaning (SAFETY, GOVERNANCE, OPERATIONAL,
   INFORMATIONAL) drives routing, not just severity.
2. **Cognitive safety over completeness** — Protect human attention. Deduplication
   is not a performance optimization; it prevents alert storms from obscuring critical
   signals.
3. **Determinism over convenience** — Behavior is policy-driven and auditable.
   Notification routing must be reproducible and explainable.
4. **Autonomy-aware behavior** — Context varies by PREVIEW / SHADOW / LIVE. The same
   notification type behaves differently depending on what the agent is authorized to do.
5. **No silent failure for guaranteed paths** — GUARANTEED delivery means the system
   will either deliver, escalate, or surface visible degradation. Never silent loss.
6. **Control plane boundary is non-negotiable** — UNS never participates in execution
   timing, never blocks agent loops, never holds state that agents depend on to proceed.

### 3.2 Core Components

```
┌──────────────────────────────────────────────────────────────┐
│                        Producers                              │
│  (Autonomous agents, orchestrators, monitors, pipelines)      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                   Notification SDK                            │
│  Thin client. Validates intent + context. Async fire.        │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                   UNS Control Plane                           │
│                                                               │
│  ┌─────────────────┐  ┌───────────────┐  ┌───────────────┐  │
│  │ Policy Registry  │  │    Router     │  │  Deduplication│  │
│  │ (YAML, versioned)│  │ (intent+mode) │  │  + Rate Limit │  │
│  └─────────────────┘  └───────┬───────┘  └───────────────┘  │
│                               │                               │
│                      ┌────────▼────────┐                     │
│                      │ Notification    │                     │
│                      │ State Machine   │                     │
│                      │ PENDING →       │                     │
│                      │ DELIVERED →     │                     │
│                      │ ACKED /         │                     │
│                      │ DISMISSED /     │                     │
│                      │ TIMED_OUT       │                     │
│                      └────────┬────────┘                     │
│                               │                               │
│              ┌────────────────┼─────────────────┐            │
│              │                │                 │            │
│  ┌───────────▼──┐  ┌──────────▼──┐  ┌──────────▼──┐         │
│  │ Notification │  │  Ack        │  │  Audit      │         │
│  │ Store        │  │  Engine     │  │  Trail      │         │
│  └──────────────┘  └─────────────┘  └─────────────┘         │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   Slack / Email         PagerDuty           MCP Gateway
                                          (agent tooling)
         │                    │
         └──────────┬─────────┘
                    ▼
                  Human
                    │
                    ▼ (ACK API)
             UNS Ack Engine → Audit Trail → Governance Signal
```

### 3.3 Integration Surface

UNS integrates with your existing notification channels; it does not replace them.

| Integration | Role |
|---|---|
| Slack / Teams | Primary delivery for OPERATIONAL and INFORMATIONAL intents |
| PagerDuty / OpsGenie | Escalation target for SAFETY and GOVERNANCE intents |
| Email | Secondary delivery, compliance archives |
| MCP Gateway | Governance signals at the agent-tool integration layer |
| Webhook | Custom integrations, SIEM feeds, GRC platforms |

**MCP integration note:** The Model Context Protocol (Anthropic, Nov 2025) has become
the standard interface for agent-tool connectivity. UNS exposes governance tools via
MCP, allowing any MCP-compatible agent to emit notifications and receive governance
signals without a custom SDK.

---

## 4. Core Data Model

### 4.1 Notification Intent

Intent drives delivery semantics. It is set by the agent producer, not derived from
content.

| Intent | Meaning | Default Delivery Mode | Requires ACK |
|---|---|---|---|
| `SAFETY` | Agent detected a condition that may require human intervention | GUARANTEED | Yes (LIVE mode) |
| `GOVERNANCE` | Agent took an action that humans should be aware of for accountability | GUARANTEED | Yes (LIVE mode) |
| `OPERATIONAL` | Agent status update, performance signal, state change | BEST_EFFORT | No |
| `INFORMATIONAL` | Low-priority FYI, diagnostic output | BEST_EFFORT | No |

Invariants:
- `SAFETY` → always GUARANTEED, never BEST_EFFORT
- `GOVERNANCE` → always GUARANTEED, never BEST_EFFORT
- GUARANTEED notifications must fail loudly (DLQ escalation) — never silently

### 4.2 Autonomy Mode

Every notification carries the agent's operating context.

| Mode | Meaning | Routing Effect |
|---|---|---|
| `PREVIEW` | Agent is explaining what it would do; not acting on live systems | Reduced urgency; SAFETY still notifies, ACK not required |
| `SHADOW` | Agent is acting on real data but outcomes are not applied | Monitoring posture; governance tracking without escalation |
| `LIVE` | Agent is acting with real consequences | Full routing, escalation, ACK requirements enforced |

This is the core differentiator from traditional alerting. The same notification type
from a PREVIEW agent and a LIVE agent should not be treated identically.

### 4.3 Notification State Machine

```
                    ┌──────────┐
                    │ PENDING  │
                    └────┬─────┘
                         │ [delivered to channel]
                    ┌────▼─────┐
                    │DELIVERED │
                    └────┬─────┘
           ┌─────────────┼──────────────┐
           │             │              │
      ┌────▼───┐   ┌─────▼────┐  ┌─────▼──────┐
      │ ACKED  │   │DISMISSED │  │ TIMED_OUT  │
      └────────┘   └──────────┘  └────────────┘
```

Every transition is persisted as an immutable event. TIMED_OUT is not an error — it is
a valid, visible governance state meaning "no human responded within the configured
window." Silence must be observable, not invisible.

### 4.4 Acknowledgment Semantics

An ACK is:
- An **explicit API call** (not a UI event or read receipt)
- **Idempotent** — safe to call multiple times
- **Identity-resolved** — which human, at what time
- **Immutable** — once recorded, cannot be modified or deleted
- A **governance signal** that may influence future autonomy decisions

An ACK is not:
- A blocking gate that prevents the agent from proceeding
- A decision about whether the action was correct
- A real-time interrupt into execution

ACKs happen after execution. They inform future autonomy — they do not control present
execution.

---

## 5. Policy System

### 5.1 Policy-Driven Routing

Routing is deterministic and policy-driven. Policies are defined in YAML, versioned, and
auditable. The router never makes ad-hoc routing decisions.

Policy configuration controls:
- Which channel(s) receive each intent × mode combination
- Escalation rules (e.g., PagerDuty if unacknowledged after N minutes)
- Rate limiting per channel (protect human attention)
- Deduplication windows (prevent storm conditions)
- ACK timeout thresholds per intent

### 5.2 Policy Lifecycle

Policies follow a one-way lifecycle with immutability on activation:

```
DRAFT → PREVIEW → ACTIVE → RETIRED
```

- `DRAFT`: Editable. Not enforced.
- `PREVIEW`: Read-only. Shadow evaluation only — notifications are logged but not acted on.
- `ACTIVE`: Enforced in production. Immutable.
- `RETIRED`: Archived. No longer used.

No policy affects production routing without explicit promotion through this lifecycle.
UI edits to policy do not affect enforcement until the policy reaches ACTIVE.

### 5.3 Default Routing Behavior

When no policy is configured or policy resolution fails, UNS applies safe defaults:

| Intent | Default behavior |
|---|---|
| SAFETY | Deliver to all configured channels; escalate immediately; DLQ on failure |
| GOVERNANCE | Deliver to primary channel; escalate if unacknowledged after 30 min |
| OPERATIONAL | Deliver to primary channel; best-effort only |
| INFORMATIONAL | Deliver to primary channel; best-effort only |

---

## 6. Delivery Guarantees

### 6.1 GUARANTEED vs BEST_EFFORT

**GUARANTEED** means: the system will either deliver the notification, escalate to a
higher-priority channel, or surface visible degradation. It does not mean infinite
retries. It means failure is never silent.

Guarantee chain for SAFETY notifications:
1. Attempt primary channel delivery
2. If undelivered within retry window → escalate to PagerDuty
3. If PagerDuty delivery fails → DLQ escalation (ops alert)
4. DLQ escalation must be acknowledged by operations

**BEST_EFFORT** means: the system will attempt delivery once with configured retries.
Failure is logged but does not trigger escalation.

### 6.2 Dead Letter Queue (DLQ) Semantics

GUARANTEED notifications that exhaust retries are not dropped. They enter the DLQ, which
triggers a separate emergency escalation path. The DLQ is a visible system state — not
a trash bin. Operations teams must acknowledge DLQ items.

This enforces the invariant: **GUARANTEED notifications cannot silently disappear.**

---

## 7. Human-in-the-Loop Design

### 7.1 The Interrupt-Free Model

UNS deliberately does not implement synchronous human approval gates that block
execution. This is an explicit design choice, not a limitation.

Synchronous blocking introduces:
- Unpredictable latency in execution loops
- Single points of human failure under high load
- Incentives to bypass governance when humans are unavailable
- Compliance exposure when approvers click without context

UNS instead implements the **asynchronous awareness model**: agents act, notify, and
continue. Humans receive, acknowledge, and inform future autonomy. The governance record
is built asynchronously without ever inserting human latency into execution.

**Exception — autonomy transitions:** UNS ACKs may gate *autonomy state transitions*
(e.g., agent promotion from SHADOW → LIVE, policy activation, operating mode changes).
This is fundamentally different from blocking execution loops — it governs the
*level of trust* an agent operates at, not individual actions.

### 7.2 Escalation Chains

Escalation is declarative, not coded. Policy defines:
- Primary notification target
- Escalation target if unacknowledged after N minutes
- Secondary escalation if escalation target also times out
- Maximum escalation depth

No custom code required in agent implementations. Agents emit intent — UNS handles the
rest.

### 7.3 Deduplication and Cognitive Safety

Human attention is a finite resource. Deduplication in UNS is a governance primitive,
not just a performance optimization.

A storm of identical SAFETY notifications does not help an operator — it obscures the
signal. UNS deduplicates within configurable windows per notification type per agent,
ensuring that escalation remains meaningful rather than becoming noise.

---

## 8. MCP Integration

### 8.1 UNS as an MCP Server

UNS exposes governance primitives as MCP tools. Any agent framework that supports MCP
can integrate with UNS without a custom SDK. This covers LangChain, LangGraph, AutoGen,
OpenAI Agents, Anthropic Claude, and any framework that has adopted the Nov 2025 MCP
standard.

**Exposed MCP tools:**

```
notify(intent, title, message, autonomy_context, notification_type)
  → Emit a governance notification. Returns notification_id.

ack(notification_id, actor_id, notes?)
  → Acknowledge a notification. Idempotent.

check_policy(notification_type, autonomy_mode)
  → Pre-flight check: how would this notification be routed?

query_pending(agent_id?)
  → List unacknowledged notifications for this agent or fleet.
```

### 8.2 MCP Gateway as Distribution Layer

MCP gateways (TrueFoundry, IBM OpenPages MCP Server, custom implementations) are
increasingly deployed as the governance chokepoint between agents and their tools.
UNS integrating at the MCP layer means governance signals flow through the natural
agent-tool integration surface — no separate SDK required, no changes to agent code.

### 8.3 Agent Skills Integration

[Anthropic Agent Skills](https://github.com/anthropics/skills) is an emerging standard
for packaging reusable agent capabilities as `SKILL.md` files that Claude-based agents
load dynamically. Skills are available in Claude.ai, Claude Code, and via the Claude API.
The standard is defined at agentskills.io.

UNS should be distributed as an Agent Skill. A `uns-governance` skill would teach any
Claude-based agent:
- When and how to emit UNS notifications (intent classification, autonomy context)
- Which notification types are appropriate for which agent actions
- How to call the UNS ACK API
- How to reason about SAFETY vs GOVERNANCE vs OPERATIONAL vs INFORMATIONAL intent

**Why this matters for adoption:** The Agent Skills standard removes the SDK integration
requirement entirely for Claude-based agents. An agent that loads the `uns-governance`
skill acquires proper governance emission behavior the same way it acquires any other
procedural capability — without code changes, without custom integration, and without
the agent developer needing to understand the UNS architecture in depth.

**Relationship to MCP:** MCP defines the *protocol* through which UNS tools are invoked.
Agent Skills defines the *instructions* agents follow when deciding to invoke them. They
are complementary: MCP is the wire format, Agent Skills is the behavioral layer.

**Scope note:** This integration surface applies specifically to Claude-based agents
using Anthropic's SDK or Claude.ai/Claude Code. For non-Claude agents, the MCP
integration (§8.1) is the equivalent path.

---

## 9. Agent Identity and Fleet Governance

### 9.1 Agent Registration

Every notification producer must be registered with UNS with:
- `agent_id` — unique identifier
- `agent_name` — human-readable label
- `default_autonomy_mode` — initial operating context
- `notification_types` — declared notification types this agent may emit
- `routing_policy_id` — which policy governs this agent's notifications

Unregistered agents may not emit SAFETY or GOVERNANCE notifications in LIVE mode.
This enforces accountability at the fleet level — you cannot have anonymous
governance signals.

### 9.2 Autonomy Level Management

UNS tracks the current autonomy mode for each registered agent. Mode transitions
(PREVIEW → SHADOW → LIVE and reverse) are governance events recorded in the audit trail.

Demotion (LIVE → SHADOW → PREVIEW) may be triggered:
- Manually by operators
- Automatically by circuit breaker engagement
- By policy after a configurable number of unacknowledged SAFETY notifications

---

## 10. Audit Trail

### 10.1 What Is Recorded

Every UNS operation produces an immutable audit record:

- Notification created (producer, intent, mode, timestamp, content hash)
- Delivery attempt (channel, outcome, timestamp)
- State transition (from, to, reason, timestamp)
- Acknowledgment (actor, timestamp, notes)
- Escalation event (trigger, target, outcome)
- Policy evaluation (policy version, decision, timestamp)

### 10.2 Queryable Accountability

The audit trail answers, for any notification or time window:

- What risks were detected?
- Who was notified, through which channel?
- When did they receive it?
- Did they acknowledge? When? Who?
- If no one responded, what happened next?
- What policy version governed the routing?
- What autonomy mode was the agent operating in?

This is the accountability record that post-mortems, compliance reviews, and
regulatory inquiries require.

### 10.3 Immutability Guarantee

Audit records are append-only. No audit event may be modified or deleted after creation.
The audit trail must be queryable independently of the notification state machine — even
if notifications are purged, their audit history is retained.

---

## 11. Deployment and Integration Modes

### 11.1 Standalone Service

UNS runs as an independent service. Agents integrate via:
- The UNS Python SDK (thin client, async fire-and-forget)
- The MCP server interface
- The REST API directly

No agent framework dependency. No tight coupling to orchestration systems.

### 11.2 Embedded in Existing Safety Envelope

UNS is designed to sit alongside (not replace) existing safety systems:

| System | Relationship to UNS |
|---|---|
| Agent orchestrator | Emits GOVERNANCE notifications on state transitions |
| Circuit breaker | Emits SAFETY notifications on engagement; UNS tracks ACK |
| Policy registry | Controls routing bounds and escalation rules |
| Why layer / explainability | Provides decision context linked to notifications |
| Autonomy controller | Primary producer of LIVE/SHADOW/PREVIEW transitions |

When these systems need to communicate with humans, they do so through UNS.

### 11.3 Progressive Deployment

**Shadow mode (recommended for initial deployment):**
Deploy UNS with all notifications in BEST_EFFORT mode and no ACK requirements. Observe
routing, volume, deduplication behavior, and channel fit for 2-4 weeks before enabling
GUARANTEED delivery and ACK requirements for SAFETY notifications.

**Canary by intent:**
Enable GUARANTEED delivery for INFORMATIONAL first (lowest risk), then OPERATIONAL, then
GOVERNANCE, then SAFETY. Each phase validates delivery infrastructure before adding
escalation requirements.

---

## 12. Non-Functional Requirements

### 12.1 Latency

UNS is control plane, not data plane. 10-50ms notification processing latency is
acceptable. Sub-millisecond latency is not a requirement and is explicitly not a design
goal — that would require architectural trade-offs that are unnecessary for human-facing
governance signals.

### 12.2 Reliability

- GUARANTEED notifications: 99.9% delivery or visible DLQ escalation
- State machine persistence: survives process restarts and infrastructure failures
- Audit trail: 100% durability; no audit record may be lost

### 12.3 Scalability

- Horizontal scaling via worker pools
- Deduplication and rate limiting protect against storm conditions
- Fleet-level governance scales to hundreds of registered agents

### 12.4 Observability

UNS exposes its own health state:
- Notification throughput by intent and mode
- Delivery success rates by channel
- ACK rates and average time-to-acknowledge by notification type
- DLQ depth and escalation frequency
- Agent registration and autonomy mode distribution

---

## 13. Implementation Status

### Phase 1 — Complete

Core delivery pipeline, fully implemented and tested (90% coverage):

- [x] Notification SDK (async, fire-and-forget)
- [x] Intent-based routing engine
- [x] Delivery pipeline with retry logic
- [x] Channel adapters: Slack, Email, PagerDuty, WebSocket
- [x] Notification state machine (PENDING → DELIVERED → ACKED/DISMISSED/TIMED_OUT)
- [x] Acknowledgment engine (explicit API, idempotent, immutable)
- [x] Deduplication engine (configurable windows)
- [x] Rate limiting (per-channel, per-intent)
- [x] Audit trail (append-only, queryable)
- [x] MCP server interface
- [x] Dead letter queue with escalation handler

### Phase 2 — Policy Engine (Planned)

Policy engine built and operational in source platform; pending extraction:

- [ ] YAML policy loader with hot-reload
- [ ] Policy lifecycle management (DRAFT → PREVIEW → ACTIVE → RETIRED)
- [ ] Policy versioning and config hash audit
- [ ] Per-agent policy binding
- [ ] Policy learning layer (delta proposals, shadow evaluation, guard-gated approval)

### Phase 3 — Agent Governor (Planned)

- [ ] Agent registration and fleet registry
- [ ] Autonomy mode state machine (PREVIEW / SHADOW / LIVE transitions)
- [ ] ACK-driven autonomy calibration
- [ ] Circuit breaker integration hooks
- [ ] Fleet-level dashboard

---

## 14. Glossary

| Term | Definition |
|---|---|
| ACK | Explicit acknowledgment — an API call, not a UI event |
| AGS | Agent Governance Signaling — the infrastructure category UNS defines |
| Autonomy Mode | PREVIEW / SHADOW / LIVE — the operating context of an agent |
| Control Plane | Infrastructure that governs behavior without participating in execution |
| DLQ | Dead Letter Queue — visible failure state for GUARANTEED notifications |
| GUARANTEED | Delivery mode: the system will deliver, escalate, or surface visible failure |
| BEST_EFFORT | Delivery mode: attempt delivery; log failure; no escalation |
| HITL | Human-in-the-Loop — human awareness and acknowledgment, asynchronously |
| Intent | Semantic classification of a notification: SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL |
| MCP | Model Context Protocol (Anthropic, Nov 2025) — standard agent-tool integration protocol |
| Notification | A first-class stateful governance object, not a message |
| Policy | YAML-defined, versioned routing and escalation rules |
| Producer | Any autonomous agent or system that emits notifications to UNS |
| TIMED_OUT | Ack state meaning no human responded within the configured window — visible, not missing |

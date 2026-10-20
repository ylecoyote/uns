> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Agent Governance Signaling (AGS)

## Category Definition & Scope Guardrails

---

## Part I — Category Definition: **Agent Governance Signaling (AGS)**

### 1. Executive Definition

**Agent Governance Signaling (AGS)** is a class of infrastructure that provides **durable, auditable, machine-legible signals about human awareness and accountability in autonomous systems**, without participating in execution or decision-making.

AGS answers a narrow but critical question:

> *When autonomous systems act, can we prove what humans knew, when they knew it, and how the system responded to that knowledge?*

AGS systems treat notifications, acknowledgments, and silence as **governance signals**, not messages.

---

### 2. What AGS Is (Precisely)

AGS systems:

* Operate strictly in the **control plane**, never the execution plane
* Accept **semantic intent** from autonomous agents (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
* Route awareness deterministically based on **autonomy context** (PREVIEW / SHADOW / LIVE)
* Maintain **durable state machines** for notifications
* Capture **explicit human acknowledgments** as immutable events
* Emit governance signals back into agent governance systems

AGS does **not** decide *what* an agent should do.
It ensures the system can prove **who was aware and accountable**.

---

### 3. How AGS Is Different from “AI Governance”

| AI Governance (Broad)        | Agent Governance Signaling (AGS)   |
| ---------------------------- | ---------------------------------- |
| Policies, ethics, principles | Concrete operational primitives    |
| Often aspirational           | Mechanically enforceable           |
| Human-in-the-loop as concept | Human awareness as a signal        |
| Reviews models and behavior  | Observes decisions after execution |
| Heavy, slow-moving           | Lightweight, latency-safe          |

**AGS is not a replacement for AI Governance.**
It is the **substrate that makes AI Governance provable in production systems**.

---

### 4. How AGS Is Different from Alerting / Incident Management

| Traditional Alerting      | AGS                                |
| ------------------------- | ---------------------------------- |
| Fire-and-forget messages  | Durable stateful objects           |
| ACK = “someone clicked”   | ACK = governance signal            |
| Severity-based routing    | Intent + autonomy-based routing    |
| Silent failures tolerated | Silent failure forbidden           |
| Optimized for ops noise   | Optimized for human accountability |

AGS treats *silence* as information.

---

### 5. The AGS Value Proposition

AGS enables organizations to:

* Run autonomous systems **without pretending humans are watching everything**
* Prove effective supervision **after the fact**
* Separate execution speed from governance responsibility
* Survive audits, incidents, and retrospectives with defensible evidence

AGS is not about stopping bad outcomes.
It is about making outcomes **explainable, attributable, and governable**.

---

## Part II — Scope Guardrails: **What UNS Is Not**

This section exists to **protect the integrity of UNS as an AGS product**.

If a feature proposal violates these boundaries, it should be rejected or deferred.

---

### 6. UNS Is **Not** an Execution Engine

UNS does **not**:

* Execute trades, API calls, or actions
* Pause, delay, or block execution loops
* Sit on the critical execution path
* Make decisions on behalf of agents

**Invariant:**

> If UNS is down, agents may continue executing — governance visibility degrades, execution does not.

---

### 7. UNS Is **Not** a Human Approval System (by Default)

UNS does **not**:

* Synchronously wait for humans
* Gate in-flight execution on approval
* Replace workflow engines (Temporal, Step Functions)
* Implement business approval logic

UNS may *record* approvals or acknowledgments,
but it does not *enforce* them in real time.

---

### 8. UNS Is **Not** an Inbox, Chat, or Productivity Tool

UNS does **not**:

* Provide message history browsing
* Act as a task manager
* Support ad-hoc conversations
* Replace Slack, Email, PagerDuty, or Jira

Channels are **delivery surfaces**, not product surfaces.

---

### 9. UNS Is **Not** a Policy Engine

UNS does **not**:

* Evaluate business rules
* Encode compliance logic
* Interpret regulatory text
* Decide whether an action is allowed

UNS consumes policy *outputs* (intent, irreversibility, severity)
— it does not compute them.

---

### 10. UNS Is **Not** an Observability Platform

UNS does **not**:

* Replace logs, traces, or metrics
* Provide full execution timelines
* Act as a data warehouse
* Optimize performance debugging

UNS answers **governance questions**, not debugging questions.

---

### 11. UNS Is **Not** a Trust or Learning System

UNS does **not**:

* Train models
* Adjust agent parameters
* Make autonomy decisions
* Infer intent from behavior

UNS emits signals.
Other systems decide what to do with them.

---

### 12. The UNS Prime Directive

> **UNS makes human awareness explicit and auditable — nothing more, nothing less.**

When scope pressure arises, return to this question:

> *Does this feature improve the system’s ability to prove who knew what, when, and how the system responded?*

If the answer is no, it does not belong in UNS.

---

## Closing Note

Agent Governance Signaling is a narrow category by design.
Its power comes from being:

* boring at execution time
* strict at governance time
* uncompromising about failure visibility

UNS should remain the **reference implementation** of AGS —
not by doing more, but by refusing to do the wrong things.

> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

> Historical note: This document is preserved from the UNS extraction phase. In current public product terminology, UNS maps to AGSignal Core and UNS Dashboard maps to AGSignal Console.

## Looking for Feedback: UNS (Unified Notification Service for Autonomous Agents)

I’ve been working on a system called **UNS** and I’d love your take on whether this feels useful, over-engineered, obvious-in-hindsight, or genuinely novel.

### The problem I’m trying to solve

As systems become more autonomous (LLM agents, trading bots, schedulers, control systems), notifications start doing more than just “inform humans.”

In practice, we need notifications that can:

* escalate when something is genuinely risky
* be acknowledged in a way that *means something*
* affect **future agent behavior** without blocking execution
* provide an audit trail answering: *what happened, who knew, and when*

Right now, most systems treat notifications as:

* logs
* alerts
* Slack messages
* or PagerDuty incidents

None of those are designed to act as a **governance/control plane** for autonomous agents.

---

### What UNS is (at a high level)

UNS is a **control-plane service** for autonomous systems where:

* Notifications are **first-class, stateful objects** (not just messages)
* Each notification has:

  * intent (INFO / OPERATIONAL / SAFETY)
  * autonomy context (PREVIEW / SHADOW / LIVE)
  * delivery guarantees (BEST_EFFORT vs GUARANTEED)
* Acknowledgments (ACKs) are:

  * explicit API calls
  * idempotent
  * auditable
  * capable of influencing *future autonomy decisions* (but **never** blocking in-flight execution)

In short:

> Notifications become part of how an agent proves it behaved responsibly.

---

### What it explicitly does *not* do

* It does **not** execute trades, actions, or commands
* It does **not** pause or block execution waiting for humans
* It does **not** contain strategy, learning, or decision logic
* It does **not** replace PagerDuty / Slack / email — it routes *to* them

UNS is intentionally boring at the execution layer and strict at the governance layer.

---

### A concrete example

Imagine an autonomous trading agent:

* The agent detects a regime shift and reduces exposure
* It emits a SAFETY notification:

  * “Volatility spike detected, exposure reduced 40%”
* UNS routes it:

  * Slack immediately
  * PagerDuty if unacknowledged in 5 minutes
* A human ACKs it

That ACK:

* doesn’t change what already happened
* but becomes a **signal** that the system can use later:

  * to justify re-enabling autonomy
  * to explain why the agent proceeded
  * to show regulators or operators what humans knew

---

### Why I think this might be interesting

I haven’t found an open-source project that combines:

* autonomy awareness
* deterministic routing
* explicit ACK semantics
* safety-grade delivery guarantees
* and feedback into agent governance

Most systems handle *pieces* of this, but not the whole.

---

### What I’d love feedback on

Brutally honest answers welcome:

1. Does this solve a real problem, or am I inventing one?
2. Is the boundary between “notification” and “control” clear enough?
3. Would you trust this more if it were open-sourced?
4. Does this feel like infrastructure… or product?
5. What would you cut immediately?

If this sounds dumb, say so. If it sounds obvious, that’s also useful.

Happy to share more details if you want to go deeper.

---

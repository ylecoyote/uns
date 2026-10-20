> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# UNS Invariants as Contractual Guarantees

## Turning Architecture into Defensible Commitments

---

## Why Guarantees Matter

Autonomous Governance Infrastructure is purchased under scrutiny:

* legal reviews
* risk committees
* procurement checklists
* regulator expectations

Features do not survive these conversations.
**Guarantees do.**

UNS’s power comes from a small set of architectural invariants.
This document translates those invariants into **contract-ready guarantees**.

---

## Guarantee 1 — Control-Plane Only

**Invariant:** UNS never participates in execution.

**Contractual Guarantee:**

> *UNS shall not execute, block, delay, or modify customer workloads, transactions, or execution loops.*

**What This Means in Practice:**

* agents continue operating if UNS is unavailable
* UNS outages degrade governance visibility, not execution
* UNS cannot create market or operational risk by stalling systems

**Why Buyers Care:**

* reduces systemic risk
* simplifies failure-domain analysis
* lowers approval friction from trading, infra, and security teams

---

## Guarantee 2 — No Silent Failure for Safety-Critical Signals

**Invariant:** Silent failure is forbidden for SAFETY and GOVERNANCE intents.

**Contractual Guarantee:**

> *All safety- and governance-class notifications will result in one of the following observable outcomes: successful delivery, escalation, or visible degradation.*

**What This Means in Practice:**

* missed notifications are detectable
* degradation is externally observable
* audit logs reflect failure states

**Why Buyers Care:**

* eliminates “we didn’t know” failure modes
* supports regulatory incident narratives
* establishes clear accountability boundaries

---

## Guarantee 3 — Durable Notification State

**Invariant:** Notifications are stateful objects, not ephemeral messages.

**Contractual Guarantee:**

> *UNS shall persist notification lifecycle state transitions, including delivery attempts, acknowledgments, dismissals, and timeouts, for audit purposes.*

**What This Means in Practice:**

* acknowledgments cannot be lost
* silence is explicitly recorded
* notification history is reconstructible

**Why Buyers Care:**

* supports after-the-fact audits
* provides defensible timelines
* prevents disputes over “who saw what”

---

## Guarantee 4 — Explicit Human Acknowledgment

**Invariant:** Acknowledgments are explicit, identity-resolved events.

**Contractual Guarantee:**

> *All acknowledgments recorded by UNS shall be explicit, idempotent, identity-resolved events with immutable timestamps.*

**What This Means in Practice:**

* no inferred acknowledgment
* no implicit “read” semantics
* clear attribution to a human or role

**Why Buyers Care:**

* reduces personal liability ambiguity
* strengthens supervision claims
* aligns with regulatory expectations of accountability

---

## Guarantee 5 — Autonomy-Aware Routing

**Invariant:** Routing depends on autonomy context, not severity alone.

**Contractual Guarantee:**

> *UNS shall route notifications based on declared autonomy context and intent, ensuring that notification behavior differs between preview, shadow, and live operation.*

**What This Means in Practice:**

* preview systems do not generate production noise
* live systems receive stronger guarantees
* governance scales with autonomy level

**Why Buyers Care:**

* reduces alert fatigue
* supports staged autonomy rollouts
* demonstrates proportional governance

---

## Guarantee 6 — Attention Protection via Deduplication

**Invariant:** Deduplication protects humans, not infrastructure.

**Contractual Guarantee:**

> *UNS shall suppress duplicate notifications within configurable windows and provide aggregate summaries when thresholds are exceeded.*

**What This Means in Practice:**

* humans see patterns, not floods
* incidents do not overwhelm operators
* governance signals remain interpretable

**Why Buyers Care:**

* lowers operational burnout
* improves response quality
* supports human-centered safety claims

---

## Guarantee 7 — Auditability by Default

**Invariant:** Governance evidence is first-class.

**Contractual Guarantee:**

> *UNS shall provide a complete, queryable audit trail linking agent events, notification delivery, acknowledgment outcomes, and timestamps.*

**What This Means in Practice:**

* audits do not rely on log reconstruction
* timelines are provable
* disputes are resolvable

**Why Buyers Care:**

* shortens audits
* reduces compliance cost
* strengthens regulator confidence

---

## Guarantee 8 — Separation from Policy and Enforcement

**Invariant:** UNS emits signals; it does not decide outcomes.

**Contractual Guarantee:**

> *UNS shall not evaluate business policies, enforce compliance rules, or make execution decisions.*

**What This Means in Practice:**

* UNS is not a single point of governance failure
* enforcement systems remain independent
* governance logic is modular and evolvable

**Why Buyers Care:**

* avoids vendor lock-in
* preserves architectural flexibility
* simplifies risk assessments

---

## The Meta-Guarantee

> **UNS guarantees visibility and accountability, not correctness or outcomes.**

This distinction must be explicit.

UNS does not promise:

* that agents will not fail
* that humans will act optimally
* that incidents will not occur

UNS promises that failures will be:

* visible
* attributable
* auditable

---

## Closing

These guarantees transform UNS from a system into an institutionally adoptable product.

They allow buyers to say:

> *“We did not just deploy autonomous systems.
> We deployed them responsibly.”*

That is the real contract UNS fulfills.

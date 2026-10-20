> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# UNS Documentation Audit
**Date:** 2026-04-22
**Scope:** All documents in `_UNS/`
**Purpose:** Identify what needs updating to reflect current reality

---

## Summary

The core architecture, design principles, and product thinking hold up well.
The main areas requiring updates are:

1. **Category existence claims** — the market has moved since these were written
2. **Competitive landscape doc** — substantially stale, mostly superseded by new research
3. **MCP integration surface** — absent from all docs, now the dominant integration pattern
4. **MIP-specific framing** — func/tech specs still describe UNS as an MIP subsystem
5. **Implementation status** — Phase 1 is complete; docs don't reflect this
6. **Regulatory timing** — FINRA 2026 report and EU AI Act enforcement deadline are new tailwinds

---

## Document-by-Document Findings

---

### `external/executive-summary.md`
**Status: Needs targeted updates**

**Line 86:** `"This category does not currently exist as a product or open standard."`

This was accurate when written. It is no longer fully accurate. Microsoft released the
Agent Governance Toolkit (MIT, April 2, 2026). Google shipped native tool governance in
Vertex AI (Dec 2025). Prefactor and Charli AI are commercial entrants. The claim should
be reframed:

> *"This category is emerging but has no standard, no dominant product, and no open
> infrastructure primitive that combines durable notification state, explicit ack
> semantics, and autonomy context."*

The gap is real — but framing it as "does not exist" is now a liability in conversations
with sophisticated buyers who will have heard of these products.

**Lines 98-101 (Status section):**
```
* Core architecture designed and implemented internally
* Functional and technical specifications locked
* Production-grade semantics validated in an autonomous trading system
* Clear path to externalization as a standalone product
```

Missing: Phase 1 of the _unified_notification_service repo is complete (core SDK,
delivery pipeline, 4 adapters, deduplication, rate limiting, ack tracking, audit trail,
MCP server, 90% test coverage). This is a stronger claim than "core architecture
designed" — Phase 1 is **shipped code**.

Phase 2 (Policy Engine) has a clear path: the policy engine is built and operational in
MIP, needs porting. Worth adding.

---

### `external/category-kit/ags-competitive-landscape.md`
**Status: Substantially stale — needs major revision or replacement**

This is the most outdated document in the folder. It predates several significant
developments:

**Products missing entirely:**
- **Microsoft Agent Governance Toolkit** (April 2, 2026, MIT license) — open source
  runtime security for agent fleets with cryptographic identity (DIDs + Ed25519),
  trust scoring 0-1000, EU AI Act / HIPAA / SOC2 compliance mapping, sub-0.1ms policy
  engine. Closest open source AGS-adjacent infrastructure yet released.
- **Prefactor** (prefactor.tech) — "AgentOps records. Prefactor acts." Commercial
  runtime control plane with approval routing, scope adherence, composite risk scoring,
  agent registry with URNs. Direct commercial competitor framing.
- **Charli AI** (charliai.com) — Governance VM with ABAC, real-time forensic traces,
  escalation pipelines. Most philosophically aligned competitor found. Finance-vertical.
- **Trussed AI** (trussed.ai) — Zero-code proxy enforcement, SOC 2 + ISO 27001.
- **Zenity** (zenity.io) — Cross-platform agent security across all major agent
  platforms (Azure, GCP, Bedrock, OpenAI, Salesforce, Power Platform).
- **kore.ai Agent Management Platform** (launched March 2026) — Gartner-recognized AMP.
- **Google Vertex AI Tool Governance** (Dec 2025) — Native permissioned tool catalogs,
  policy checks before invocation, audit logs. Hyperscaler validation of the category.
- **Fiddler AI "Control Plane"** — Raised $30M Series C explicitly for "first control
  plane for AI." Enterprise customers include Mastercard, DTCC, Ally, AIG, US Navy.

**New competitive dynamics not reflected:**
- MCP (Anthropic Nov 2025) has become the de facto agent-tool integration standard and
  the dominant governance chokepoint. Every major governance vendor is building an MCP
  gateway. This changes the integration story for UNS significantly.
- The market now clearly splits into "enforcement-first" (Fiddler, Galileo, Trussed,
  Microsoft AGT) vs. "signaling-first" (UNS). This is a stronger differentiator to lead
  with than "no one does this."

**Recommendation:** Replace with `competitive-landscape-research-2026-04.md` (already
written and saved) or use it as the source for a condensed version.

---

### `external/category-kit/autonomous-governance-infrastructure.md`
**Status: One claim needs updating**

**Line 27:** `"There is no standard infrastructure for governing autonomous systems once they are live."`

This was precise when written. It needs nuancing now: there are products governing
deployed agents (Microsoft AGT, Prefactor, Google Vertex) — but none combine signaling,
durable ack tracking, and autonomy context as a unified primitive.

Suggested reframe:
> *"Existing infrastructure governs agents via enforcement or observation. None provides
> the signaling layer — durable, accountable human awareness — that makes governance
> defensible after the fact."*

Everything else in this document holds up well. The AGI stack model (UNS → Why Layer →
Agent Governor → Circuit Breakers → Policy Registry → Ack-driven learning) is still the
right architecture and is not replicated anywhere in the competitive landscape.

---

### `external/walking-deck.md`
**Status: Needs two new slides**

The existing slides are solid. Two things are now missing:

**Missing: Slide on competitive validation**
The hyperscaler and open source moves (Google Dec 2025, Microsoft April 2026) validate
the category. A slide acknowledging this and positioning UNS as the *signaling-first*
approach vs. the *enforcement-first* market would strengthen the narrative considerably.

Something like: *"The market is building enforcement. UNS is building the layer that
makes enforcement meaningful."*

**Missing: Slide on MCP integration**
MCP is now how agents connect to tools. A UNS that speaks MCP = governance at the
natural integration layer. This is a significant distribution and adoption angle that is
entirely absent from the deck.

---

### `external/uns-comms.md`
**Status: One line needs updating**

**Lines 88-96:**
```
I haven't found an open-source project that combines:
* autonomy awareness
* deterministic routing
* explicit ACK semantics
* safety-grade delivery guarantees
* and feedback into agent governance

Most systems handle *pieces* of this, but not the whole.
```

Microsoft's Agent Governance Toolkit (April 2, 2026, MIT) handles autonomy context and
fleet governance well. The last sentence is still true — "pieces, not the whole" —
but the opening claim needs qualification. Suggested:

> *"The closest open-source project — Microsoft's Agent Governance Toolkit (April 2026)
> — covers fleet identity and policy enforcement well, but does not model the
> notification lifecycle, ack semantics, or the signaling layer. Most systems handle
> pieces of this, but not the whole."*

---

### `external/why-ags-must-exist-before-enforcement.md`
**Status: No updates needed — strongest document in the folder**

This document has aged exceptionally well. The competitive research actively validates
its thesis: Galileo, Trussed, Fiddler, and Microsoft AGT all enforce without signaling,
which is exactly the problem this doc describes. The four arguments (false safety,
autonomy collision, audit failure, proportional governance) are all confirmed by the
market survey.

The only optional addition: a brief reference to FINRA's 2026 Annual Regulatory
Oversight Report, which explicitly called out "autonomous agents with no human-in-the-
loop" as a top risk. This is a real-world regulator confirming Section 3 of this doc
("Enforcement Without Signaling Breaks Audits").

---

### `external/category-kit/agence-governance-signaling.md`
**Status: Minor update needed**

The category definition itself is clean and holds up. The comparison tables are still
accurate. The only section that needs a light touch is wherever adjacent categories
are listed — PagerDuty/OpsGenie/VictorOps are correctly positioned as unable to become
AGS. Worth adding a note that the new entrants (Prefactor, Microsoft AGT, Google Vertex)
also cannot become AGS for the same architectural reasons — they are enforcement-first.

---

### `external/category-kit/who-buys-autonomous-governance-infrastructure.md`
**Status: No updates needed**

The buyer analysis is structural and doesn't depend on competitive state. CRO/CCO as
economic buyer, Platform Engineering as internal champion, traders as tolerators —
this is still the right model. The "operators must feel protected, not monitored" line
is strong and accurate.

One optional addition: the FINRA 2026 report creates a new urgency signal for the
CCO/CRO buyer. "FINRA named autonomous agents with no HITL as a top 2026 risk area"
is a compelling opening line for that buyer conversation.

---

### `uns/one-pager-diagram.md`
**Status: One structural gap**

The diagram is clean and accurate. Missing: **MCP as an integration surface**.

The current diagram shows:
```
Agent → UNS → [Slack / Email / PagerDuty / DLQ]
```

It should also show:
```
Agent → UNS → MCP Tool Gateway
```

MCP is now the standard protocol for agent-tool integration. Governance at the MCP
gateway layer is exactly where UNS belongs in 2026. Adding this as a delivery target
(alongside Slack/PagerDuty) would make the diagram significantly more relevant to
current infrastructure conversations.

---

### `uns/unified-notification-service-func-spec.md`
**Status: Framing needs generalization; content is technically solid**

**Line 12:** `"UNS is the human–agent interrupt layer for MIP's autonomous trading platform."`

This is accurate historically but wrong for the standalone product. The externalized
UNS is general-purpose infrastructure, not an MIP subsystem. The opening purpose
statement should read something like:

> *"UNS is the human–agent interrupt and awareness layer for autonomous systems. It
> ensures that when autonomous agents encounter risk, require approval, change operating
> conditions, or need to inform humans, the right human is notified through the right
> channel without overwhelming attention or blocking execution unnecessarily."*

**Section 1.3 (Relationship to Safety Envelope):** The table references MIP-specific
systems (Why Layer, YOLO/Autonomy Controller). This is fine as an example integration
but should be framed as "example: how UNS integrates within MIP's safety envelope"
rather than the canonical UNS integration model.

**Status field:** Still says DRAFT. Given that Phase 1 is implemented and tested, the
spec should graduate to STABLE for the implemented sections, with DRAFT retained only
for Phase 2+ sections.

**Last Updated: 2026-01-19** — should be updated to reflect the current date.

---

### `uns/unified-notification-service-tech-spec.md`
**Status: Minor framing update; content is accurate**

Same general notes as the func spec:
- Replace MIP-specific framing in introductory sections with general-purpose framing
- The tech stack decisions (RQ over Redis Streams, existing infrastructure preference)
  are well-reasoned and documented — keep them
- The anti-pattern warning on using UNS acks to pause execution is excellent — keep it
- **Last Updated: 2026-01-19** — should be updated

**One addition worth making:** A section on MCP integration. The tech spec currently
documents Slack, Email, PagerDuty, and WebSocket adapters. An MCP adapter would allow
UNS notifications to flow through the MCP gateway layer, which is now the standard
integration surface for agent tooling. This is a Phase 2+ item but worth noting in the
spec as a planned adapter.

---

### `uns_ralphy_task_list.md`
**Status: Needs status update; content valid for Phase 1**

**Execution Constraint:** `"MUST NOT participate in order routing or trade timing"`

This is trading-specific. For general-purpose UNS the constraint should be:
> *"MUST NOT participate in execution logic or decision-making for the systems it
> governs."*

**Build targets 1-8** (Notification Schema through Rate Limiter) are all implemented
in Phase 1 of the _unified_notification_service repo. These should be marked complete.

**Build target 9** (Policy Registry / Audit Logger) — Policy Registry is Phase 2
pending MIP port. Audit Logger is implemented. These should be split and statused.

---

### `uns/unified_notification_and_signaling_prd.md`
**Status: Vertical-specific version; needs a companion**

This document is the finance/DORA/FINRA PRD. It's well-written and the regulatory
framing is now *more* timely (FINRA 2026 report, EU AI Act August 2026 enforcement
deadline) than when it was written.

However, it hardcodes UNS as a financial services product. If the intent is to
position UNS as general-purpose infrastructure that happens to be validated in finance,
this PRD needs a companion: a general-purpose PRD where the MIP/trading references
are replaced with generic "autonomous agent system" framing.

The finance-specific PRD is a strong enterprise sales document for regulated industries.
It should be preserved as-is and supplemented, not replaced.

---

## Priority Order for Updates

**High — affects external credibility:**
1. `ags-competitive-landscape.md` — replace/supersede with new research artifact
2. `executive-summary.md` — update category existence claim + add implementation status
3. `uns-comms.md` — update the "haven't found" claim

**Medium — strengthens positioning:**
4. `walking-deck.md` — add MCP slide + competitive validation slide
5. `autonomous-governance-infrastructure.md` — reframe "no standard infrastructure" claim
6. `one-pager-diagram.md` — add MCP as delivery surface

**Low — housekeeping:**
7. `func-spec.md` — generalize MIP framing, update status + date
8. `tech-spec.md` — generalize MIP framing, add MCP adapter note, update date
9. `uns_ralphy_task_list.md` — update execution constraint, mark Phase 1 targets complete

**No changes needed:**
- `why-ags-must-exist-before-enforcement.md` — holds up perfectly
- `agence-governance-signaling.md` — minor optional addition only
- `who-buys-autonomous-governance-infrastructure.md` — structural, still accurate

---

## The One New Document Worth Writing

A **general-purpose PRD** (companion to the finance-specific one) that:
- Removes MIP/trading/FINRA/DORA specifics
- Positions UNS as infrastructure for any autonomous agent system
- Leads with the MCP integration story
- Reflects Phase 1 completion and Phase 2 (policy engine) roadmap

This would give you a document you can share with non-finance buyers (infrastructure
teams, AI platform teams, regulated-but-not-trading industries like healthcare, energy,
legal) without the financial services framing creating friction.

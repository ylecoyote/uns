> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# UNS/AGS Open Source Launch Strategy

**Date:** 2026-04-22
**Decision:** Full MIT open source
**Goal:** Category definition, press, notoriety
**Trigger:** Ship at Phase 1 + Policy Engine completion

---

## The Core Thesis

The implementation is table stakes. What gets press is the *thesis* — and it already
exists: **"signaling before enforcement"** is a genuinely original framing in a space
where everyone else is shipping enforcement-first.

`why-ags-must-exist-before-enforcement.md` is essentially a viral blog post already.
That's the launch asset, not the code.

---

## Why the Timing Is Right

- FINRA named autonomous agents a top risk in their 2026 Annual Regulatory Oversight
  Report — explicitly flagging autonomous agents with no HITL
- EU AI Act enforcement hits August 2026
- Microsoft Agent Governance Toolkit shipped MIT, April 2, 2026 — category validation
- Google Vertex AI tool governance shipped December 2025 — hyperscaler validation
- No open source project combines signaling + durable ack semantics + autonomy context

The story: *"I built this before they validated it."*

---

## Launch Decision: Full MIT

- Full MIT, no open core, no license restrictions
- Include the policy learning layer (Phase 17.3 delta proposals, shadow evaluation,
  guard-gated approval) — this is the piece that signals serious design. Holding it back
  does not serve the notoriety goal. Shipping it does.
- Goal is category definition and reputation, not revenue from the project itself

---

## The Naming Question (Resolve Before Launch)

"Unified Notification Service" is descriptive but forgettable. It sounds like
middleware. For a notoriety play, the project name matters.

Options:
- Ship as **AGS** — category name becomes project name, maximally Googleable
- Keep UNS as the implementation name, make AGS the headline category
- Something more evocative than either

Whatever is chosen: it must be Googleable and distinct. "UNS" will get lost in search.
Secure the domain (agentgovernancesignaling.com or equivalent) before launch regardless.

---

## Launch Sequence

### 1. Polish the repo README

The external docs are excellent but need a README that opens with the thesis, not the
architecture.

- First paragraph: the exec summary / AGS definition
- One-pager Mermaid diagram goes in the README
- Someone should understand AGS in 60 seconds without clicking anything
- The `why-ags-must-exist-before-enforcement.md` argument should be accessible from
  the README, not buried in a docs folder

### 2. Write one launch blog post

Not a changelog, not a feature overview. The "signaling before enforcement" argument,
adapted from existing docs, with market timing added:
- The FINRA 2026 report
- Microsoft AGT and Google Vertex validating the category
- Why they got it half right (enforcement without signaling)
- What AGS adds that they don't have

End with the GitHub link. This is the thing that gets shared.

**Source material already written:**
- `external/why-ags-must-exist-before-enforcement.md` — core argument
- `external/executive-summary.md` — positioning
- `external/category-kit/ags-competitive-landscape.md` + research artifact — market context
- `external/category-kit/agence-governance-signaling.md` — category definition

### 3. HN launch

Post: *"Show HN: UNS/AGS — open source governance control plane for autonomous agents"*

The AGS framing is novel enough to land. HN responds well to "I built the infrastructure
layer everyone needs but nobody made" posts. The timing is right. Link to the blog post,
not just the repo.

### 4. Register the category

- **agsignal.dev** — primary domain (lead with this)
- **agsignal.io** — redirect to .dev, prevent squatting
- Both secured: 2026-04-22

### 5. Publish the uns-governance Agent Skill

Once the `uns-governance` skill is written (teaches Claude-based agents when/how to emit
UNS notifications, intent classification, autonomy context rules), publish it to the
Anthropic Agent Skills registry. Puts UNS in Anthropic's ecosystem with a backlink and
makes adoption trivially easy for Claude-based agents.

---

## What Will Get You Cited

The policy learning layer is the piece that makes engineers say "this person thought
about this seriously":

- Delta proposals with explicit state machine (PROPOSED → SHADOW → APPROVED → APPLIED)
- Shadow evaluation before any policy change goes live
- Guard-gated approval with explicit rejection reasons
- No silent policy changes — every mutation is observable

This architecture is not in any open source project currently. It should be in the README
and the blog post, not just the docs.

---

## What Not To Do

- **Don't wait for Agent Governor** — Phase 1 + Policy Engine is the right launch moment.
  The category is hot now. Waiting for "completeness" is the wrong call when the goal is
  notoriety.
- **Don't hold back the learning layer** — it's the proof of serious design, include it
- **Don't ship without the blog post** — a GitHub link without a thesis gets no traction
- **Don't name it something forgettable** — resolve the naming before launch

---

## Realistic Timeline

The policy engine port is the gating item. Once complete:

| Task | Time |
|---|---|
| Policy engine port from MIP | [gating] |
| Repo cleanup + README | ~1 week |
| Launch blog post | ~1 week |
| Launch (HN + social + skill registry) | 1 weekend |

**Total post-port:** ~2-3 weeks to launch-ready.

The August EU AI Act enforcement deadline is a natural press hook. Aim to be live and
gaining traction before then.

---

## Supporting Documents in This Folder

| Document | Role |
|---|---|
| `external/why-ags-must-exist-before-enforcement.md` | Core blog post source material |
| `external/executive-summary.md` | README opening / positioning |
| `external/category-kit/agence-governance-signaling.md` | Category definition |
| `external/category-kit/ags-competitive-landscape.md` | Updated competitive summary |
| `external/competitive-landscape-research-2026-04.md` | Full market research |
| `external/walking-deck.md` | Slide narrative for press/investor conversations |
| `external/who-buys-autonomous-governance-infrastructure.md` | Buyer targeting |
| `uns/uns-prd-general.md` | General-purpose PRD (non-finance framing) |
| `uns/unified_notification_and_signaling_prd.md` | Finance/regulated industry PRD |
| `documentation-audit-2026-04.md` | Docs audit and update tracker |

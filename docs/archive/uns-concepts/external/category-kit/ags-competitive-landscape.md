> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Competitive Landscape: Agent Governance Signaling

> **This document has been superseded.**
>
> See: [`/external/competitive-landscape-research-2026-04.md`](../competitive-landscape-research-2026-04.md)
>
> Updated: 2026-04-22. Covers 20+ products across durable workflow engines, commercial
> governance platforms, open source frameworks, GRC vendors, and hyperscaler moves.
> Includes master comparison table scored against AGS criteria.

---

## Summary (from updated research)

The market splits into two camps that do not overlap:

**Camp 1 — Durable execution engines** (Temporal, Restate, Netflix Conductor OSS):
Have the technical substrate for notification state machines — crash-safe pause/resume,
typed ack signals, timeout handling — but are general-purpose workflow infrastructure.
You build all governance domain logic on top.

**Camp 2 — Governance/enforcement platforms** (Fiddler AI, Galileo, Prefactor, Trussed
AI, Zenity, Microsoft Agent Governance Toolkit): Perform runtime enforcement and
fleet-level visibility but model governance as an *interception event*, not a *durable
signal object*. They block or route — they do not model the full notification lifecycle.

**No product combines all four AGS requirements:**
1. Durable notification state machine (beyond PENDING/RESOLVED)
2. Explicit ack semantics distinct from decision
3. Autonomy context attached to signals
4. Fleet-level policy determining routing and escalation

**The "signaling before enforcement" thesis is confirmed.** Every enforcement-first
product (Galileo, Trussed, Microsoft AGT, Fiddler) blocks without explaining. When
something goes wrong, they cannot prove who was aware, when they knew, or whether
silence was intentional. AGS answers these questions. Enforcement does not.

**Notable new entrants since original landscape was written:**

| Product | URL | What it does | AGS gap |
|---|---|---|---|
| Microsoft Agent Governance Toolkit | github.com/microsoft/agent-governance-toolkit | OSS runtime security, cryptographic agent identity, trust scoring, EU AI Act mapping | Security/SRE, no notification lifecycle |
| Prefactor | prefactor.tech | Commercial runtime control plane, approval routing, agent registry | Approval routing not a durable signal object |
| Charli AI | charliai.com | Governance VM, ABAC policy context, forensic traces, escalation | Proprietary, finance-vertical, HITL details undisclosed |
| Fiddler AI | fiddler.ai/control-plane | $30M Series C "first control plane for AI," Mastercard/DTCC/US Navy customers | Observability-first, no signal lifecycle |
| Google Vertex AI Tool Governance | cloud.google.com | Native permissioned tool catalogs, policy checks, audit logs (Dec 2025) | GCP-locked, no ack semantics or autonomy context |
| kore.ai AMP | kore.ai | Gartner-recognized Agent Management Platform (March 2026) | Dashboard governance, no runtime signaling |

**The closest philosophical competitor:** Charli AI — Governance VM with ABAC policy
context attached to every execution event. Finance-vertical, proprietary, HITL mechanics
undisclosed. Worth monitoring.

**The MCP shift:** Anthropic's Nov 2025 MCP spec added authorization extensions and
audit hooks. Every major governance vendor is now building MCP gateways. A governed
MCP gateway is becoming the practical 2026 implementation surface for AGS — and a
natural integration and distribution point for UNS.

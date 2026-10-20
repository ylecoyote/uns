> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Competitive Landscape Research: Agent Governance Signaling
**Date:** 2026-04-22
**Research scope:** 20+ products across 4 categories, 28 web searches
**Purpose:** Map existing products against the AGS/UNS value proposition

---

## The Core Finding

The agent governance space in 2026 splits into two camps that do not overlap:

**Camp 1 — Durable execution engines** (Temporal, Restate, Conductor OSS): Have the
technical substrate for notification state machines — crash-safe pause/resume, typed ack
signals, timeout handling — but are general-purpose workflow infrastructure. You build
all governance domain logic on top.

**Camp 2 — Governance/enforcement platforms** (Fiddler, Galileo, Prefactor, Trussed,
Zenity): Perform runtime enforcement and fleet-level visibility but model governance as
an *interception event*, not a *durable signal object*. They block or route — they do
not model the full notification lifecycle.

**No product combines all four AGS requirements:**
1. Durable notification state machine (beyond PENDING/RESOLVED)
2. Explicit ack semantics distinct from decision
3. Autonomy context attached to signals
4. Fleet-level policy determining routing and escalation

---

## Evaluation Framework

Each product is scored against the AGS criteria:

- **(A) Durable State** — Notification lifecycle persists across crashes/restarts
- **(B) Ack Semantics** — Explicit typed acknowledgment, not fire-and-forget
- **(C) Autonomy Context** — Agent authorization level attached to the signal
- **(D) HITL Primitive** — Human-in-the-loop as a first-class governance mechanism
- **(E) Fleet Governance** — Cross-agent policy, not per-agent logic

---

## Category 1: Durable Workflow Engines (closest substrate)

### Temporal — temporal.io
Durable execution engine. Workflows survive crashes via event history log. Human approval
via Signals (async fire-and-wait) and Updates (synchronous signal+response).

- **(A)** STRONG — workflow state is durable
- **(B)** STRONG — typed signal/update schemas are explicit ack primitives
- **(C)** NONE — no agent authorization level concept
- **(D)** MODERATE — HITL is a pattern you implement, not a product feature
- **(E)** NONE — per-workflow, fleet governance is your problem

**AGS gap:** No governance domain model. No built-in escalation policy, agent identity,
or notification lifecycle object. You write workflow code that implements approval logic.

---

### Restate — restate.dev
Lightweight durable execution runtime. HITL via "awakeables" (durable promises) — agent
creates a promise, sends the ID to an approver, suspends with zero idle compute, resumes
on HTTP callback. Timeout is durably persisted.

- **(A)** STRONG — awakeable IS a durable notification token (PENDING/RESOLVED/REJECTED/TIMED_OUT)
- **(B)** STRONG — HTTP resolution call is the ack; promise ID is the correlation handle
- **(C)** NONE
- **(D)** STRONG — cleanest HITL primitive found; serverless-compatible, crash-safe
- **(E)** NONE

**AGS gap:** Pure infrastructure substrate. No agent registry, governance policies, fleet
visibility, or audit trail beyond journal replay. Excellent building block, needs domain
layer on top.

---

### Netflix Conductor OSS — conductor-oss.github.io
Open source workflow engine with first-class HUMAN task type. Workflow pauses durably
until human responds via Task Update API. Supports pre-execution approval gates and
conditional post-execution review (trigger HUMAN only when confidence < threshold).

- **(A)** STRONG — HUMAN task is a first-class durable pause object
- **(B)** STRONG — APPROVE/REJECT/MODIFY are structured response types
- **(C)** WEAK — conditional triggers are close to autonomy context but workflow-local
- **(D)** STRONG — best HITL task primitive in OSS workflow space
- **(E)** WEAK — governs workflows, not agent fleets

**AGS gap:** No agent registry, identity model, or fleet governance. The HUMAN task does
not model "who is the right human given this agent's autonomy scope."

---

### Cloudflare Agents — developers.cloudflare.com/agents
Agent runtime with `waitForApproval()` API. Durable state via Durable Objects. Two
modes: MCP Elicitation (in-conversation) and Workflow Approval (durable multi-step gate,
can wait hours/weeks). Timeout escalates to manager.

- **(A)** MODERATE — durable state, 2-phase lifecycle (PENDING/RESOLVED)
- **(B)** MODERATE — explicit accept/reject with `approvedBy` field
- **(C)** NONE
- **(D)** MODERATE — clean API, single-workflow scope
- **(E)** NONE

---

## Category 2: Commercial Agent Governance Platforms

### Prefactor — prefactor.tech
Positions as "agent runtime control plane" vs. observability. Core: outcome quality
assessment, scope adherence evaluation, composite risk scoring, inline blocking, approval
routing when thresholds crossed. Agent registry with URNs. Lifecycle governance from
registration through retirement. Framework-agnostic (LangChain, CrewAI, AutoGPT).

- **(A)** UNKNOWN — approval routing exists but durability not documented
- **(B)** MODERATE — approval routing implies ack semantics; mechanism not public
- **(C)** MODERATE — scope adherence = autonomy boundary awareness
- **(D)** MODERATE — approval routing is a governance primitive
- **(E)** STRONG — fleet-level governance is the core value prop

**AGS gap:** Closest commercial product to a governance control plane. But notification
lifecycle is not explicitly modeled — it's an enforcement action, not a stateful signal
object. No explicit autonomy level attached to signals.

---

### Charli AI — charliai.com
Finance-sector governance control plane with a "Governance Virtual Machine" (VM) sitting
between models and core systems. ABAC at entity level. Real-time forensic traces capture
inputs, policy context, agent decision parameters, data retrieved, and outcomes as a
single coherent trace. Designed for millions of agents.

- **(A)** MODERATE-STRONG — real-time forensic trace implied to be durable
- **(B)** MODERATE — escalation pipeline implies ack requirements
- **(C)** STRONG — ABAC policy context attached to every execution event IS autonomy context
- **(D)** UNKNOWN — escalation mentioned, HITL mechanics not disclosed
- **(E)** STRONG — designed for millions of agents at enterprise scale

**AGS gap:** Most conceptually aligned commercial product found. Right framing, right
primitives. Finance-vertical, proprietary, HITL mechanics undisclosed. Not open source.

---

### Fiddler AI — fiddler.ai/control-plane
Self-described "first control plane for AI." $30M Series C. Standardized telemetry
across agent steps, continuous monitoring, enforceable policy at runtime, auditable
governance. Enterprise customers: Mastercard, DTCC, Ally, AIG, Nielsen, US Navy.
Explicitly maps to SR 11-7, HIPAA, NAIC, NIST AI RMF, ISO/IEC 42001.

- **(A)** MODERATE — audit trails are strong, notification state machine not documented
- **(B)** WEAK — enforcement events logged but not durable ack-tracked notifications
- **(C)** WEAK — no explicit autonomy context model
- **(D)** NONE documented
- **(E)** STRONG — production fleet-level, most mature dedicated platform

**AGS gap:** Best for regulated industries (finance, healthcare). Runtime enforcement +
full audit trail + regulatory mapping. But observability-first, not signaling-first.

---

### Galileo — galileo.ai
Full-loop: eval in dev → promote to production guardrails → monitor enforcement via
integrated observability. Complete decision traceability. Luna-2 proprietary SLMs for
sub-200ms policy enforcement. Tracks "mean time to adjudicate a policy exception" as a
governance health metric — close to ack semantics framing.

- **(A)** WEAK — guardrails intercept, they don't have notification lifecycle state
- **(B)** WEAK — policy exception adjudication implies decision point, mechanism not tracked
- **(C)** NONE
- **(D)** NONE — human oversight is policy config review, not runtime approval gates
- **(E)** STRONG — continuous fleet evaluation

**AGS gap:** Excellent at the guardrails/observability layer. Detects and blocks, does
not send governance signals to humans with durable ack tracking.

---

### Zenity — zenity.io
Cross-platform agent security and governance. Covers Azure AI Foundry, Google Vertex,
Amazon Bedrock, OpenAI AgentKit, Copilot Studio, Salesforce Agentforce, Power Platform.
Expanded from visibility to active defense in 2025. Demonstrated real-world agent
hijacking attacks at Black Hat USA 2025. Covers MCP security, shadow AI, prompt injection.

- **(A)** WEAK
- **(B)** WEAK
- **(C)** WEAK
- **(D)** NONE
- **(E)** VERY STRONG — best cross-platform agent coverage

**AGS gap:** Security-first, not governance-signaling. Best for attack surface coverage,
not for accountability and ack tracking.

---

### Trussed AI — trussed.ai
Zero-code drop-in proxy between applications and AI models. SOC 2 Type II + ISO 27001.
Runtime enforcement before requests reach models and before responses return. Agentic
governance module for tool calls, database queries, workflow triggers. Insurance,
healthcare, financial services focused.

- **(A)** WEAK
- **(B)** WEAK
- **(C)** WEAK
- **(D)** NONE
- **(E)** MODERATE

**AGS gap:** Enforcement chokepoint is elegant architecture. Zero-code deployment is a
significant enterprise advantage. But it's a proxy/firewall, not a signaling system.

---

### Microsoft Agent Governance Toolkit — github.com/microsoft/agent-governance-toolkit
Released April 2, 2026. MIT license. Multi-package: Agent OS (stateless policy engine,
<0.1ms p99), Agent Mesh (cryptographic identity, DIDs + Ed25519, Inter-Agent Trust
Protocol, dynamic trust scoring 0-1000 on five behavioral tiers), Agent SRE (SLOs,
circuit breakers, chaos engineering), Agent Compliance (EU AI Act / HIPAA / SOC2 mapping,
OWASP Agentic AI Top 10).

- **(A)** WEAK — policy engine intercepts, no notification state machine
- **(B)** NONE
- **(C)** STRONG — trust scoring + identity IS autonomy context in a different form
- **(D)** WEAK — circuit breakers stop agents but humans aren't first-class
- **(E)** VERY STRONG — designed for agent fleets with cryptographic identity

**AGS gap:** Best open source runtime security framework found. But it's security and
reliability governance, not notification/signaling. It stops agents and adjusts trust
scores — it doesn't send durable human-addressed governance signals with ack semantics.
The missing piece is exactly AGS.

---

### kore.ai Agent Management Platform — kore.ai
Launched March 2026. Centralized agent registry across any framework/cloud. Governance
policy enforcement. Real-time anomaly detection. Immutable audit trails. Described by
Gartner as covering all six AMP elements.

- **(A)** UNKNOWN
- **(B)** NONE
- **(C)** NONE
- **(D)** WEAK — "human oversight" via dashboard, not interrupt/approve/reject primitive
- **(E)** VERY STRONG — positioned as full fleet governance platform

**AGS gap:** Broad enterprise platform governance (inventory, policy, audit, evaluation)
rather than runtime governance signaling.

---

### Arthur AI — arthur.ai
Agent observability + staged autonomy calibration. Calibrate autonomy via staged levels
and HITL checkpoints. Executive review dashboards. Risk tier segmentation.

- **(A)** WEAK
- **(B)** NONE
- **(C)** MODERATE — staged autonomy levels is the closest any observability product gets
- **(D)** MODERATE — HITL checkpoints exist as concept, details not public
- **(E)** MODERATE

**Note:** Arthur AI's autonomy staging concept is the most relevant analogue to UNS's
AutonomyMode (PREVIEW/SHADOW/LIVE) found in any commercial product.

---

## Category 3: Open Source Agent Governance Frameworks

### LangGraph — github.com/langchain-ai/langgraph
Stateful agent framework. `interrupt()` pauses graph execution at any node. Checkpointed
state is persistent and queryable during pause. `Command(resume=decision)` is the typed
ack. Supports approve/edit/reject per tool. Best HITL primitive in OSS agent frameworks.

- **(A)** MODERATE — checkpointed state is durable, no multi-phase notification lifecycle
- **(B)** MODERATE — approve/edit/reject schema with thread ID correlation
- **(C)** NONE
- **(D)** STRONG — `interrupt()` is cleaner than callback-based alternatives
- **(E)** NONE

**AGS gap:** Framework for building agents that can include HITL logic, not governance
infrastructure. You wire all routing, notification delivery, escalation, and ack tracking.

---

### NVIDIA NeMo Guardrails — github.com/NVIDIA-NeMo/Guardrails
Programmable guardrails using Colang DSL. Synchronous interceptors, not notification
state machines. Content/behavior safety layer. Can trigger human escalation but no
durable HITL mechanism.

**AGS gap:** Content firewall, not a governance signaling infrastructure.

---

### GaaS (Governance-as-a-Service) — arXiv 2508.18765v2
Academic multi-agent governance framework. Trust Factor mechanism scoring agents based
on longitudinal compliance history. Blocks unsafe actions. Every enforcement decision
logged with timestamp, agent ID, rule ID, violation type, severity, and trust state.

**AGS gap:** Research paper, not a product. Useful theoretical precedent for AGS's
autonomy context model — longitudinal behavioral trust scoring is the right direction.

---

## Category 4: GRC Vendors and Regulatory Compliance

### Regulatory Context (April 2026)

- **FINRA 2026 Annual Regulatory Oversight Report** explicitly named AI agents as a top
  risk area: autonomous agents with no HITL, agent permission/access issues, AI
  independently misusing sensitive data. Told member firms to update Written Supervisory
  Procedures (WSPs) to cover AI agent monitoring.
- **DORA enforcement** intensifying through 2026. Requires continuous risk assessment,
  real-time traceability, audit-ready reporting for ICT providers including AI systems.
- **EU AI Act** enforcement deadline: August 2026.

**Key gap identified:** No startup yet specifically governs autonomous AI agent behavior
against FINRA Written Supervisory Procedure requirements at runtime. Open white space.

---

### GRC Vendors Adding AI Governance

| Vendor | AGS Fit | Notes |
|---|---|---|
| IBM OpenPages + MCP Server | PARTIAL | GRC + agent telemetry via MCP server |
| MetricStream AiSPIRE | PARTIAL | AI Trust Framework, audit logs, DORA module |
| ServiceNow AI Control Tower | PARTIAL | AI inventory + governance policies |
| Credo AI | PARTIAL-STRONG | Policy lifecycle, compliance evidence, EU AI Act mapping |

All are documentation/lifecycle governance, not runtime signaling.

---

### Hyperscaler Moves (significant signal)

**Google Vertex AI Agent Builder Tool Governance (Dec 19, 2025)**
Added: permissioned tool catalogs, policy checks before tool invocation, audit logs for
all tool calls, Agent Engine for fleet management. Native AGS core primitives inside
Google Cloud. Validates the problem; will commoditize basic AGS for GCP-locked teams.

**Anthropic MCP Nov 2025 spec**
Added authorization extensions and audit hook patterns. Every governance vendor
(TrueFoundry, IBM, Zenity, Credo) is now building MCP gateway capabilities. An MCP
gateway with audit + policy + auth is becoming the practical 2026 implementation of
what UNS describes architecturally.

**Microsoft + IBM Blueprint for MCP Agent Governance (Oct 2025)**
Joint reference architecture for secure enterprise AI agents via MCP. Covers ADLC, eval
services, guardrails, AI/MCP gateways, drift detection, certification gates, governed
tool catalogs. Essentially defines what enterprise AGS should look like.

---

## Master Comparison Table

| Product | URL | Durable State | Ack Semantics | Autonomy Ctx | HITL | Fleet Gov | AGS Gap |
|---|---|---|---|---|---|---|---|
| Temporal | temporal.io | STRONG | STRONG | NONE | MODERATE | NONE | No domain model |
| Restate | restate.dev | STRONG | STRONG | NONE | STRONG | NONE | Pure substrate |
| Conductor OSS | conductor-oss.github.io | STRONG | STRONG | WEAK | STRONG | WEAK | No fleet governance |
| Cloudflare Agents | cloudflare.com/agents | MODERATE | MODERATE | NONE | MODERATE | NONE | Per-agent scope |
| Prefactor | prefactor.tech | UNKNOWN | MODERATE | MODERATE | MODERATE | STRONG | No signal lifecycle object |
| Charli AI | charliai.com | MODERATE | UNKNOWN | STRONG | UNKNOWN | STRONG | Proprietary, finance-vertical |
| Fiddler AI | fiddler.ai | MODERATE | WEAK | WEAK | NONE | STRONG | Observability-first |
| Galileo | galileo.ai | WEAK | NONE | NONE | NONE | STRONG | Guardrails not signals |
| Zenity | zenity.io | WEAK | NONE | NONE | NONE | VERY STRONG | Security, not signaling |
| Trussed AI | trussed.ai | WEAK | NONE | NONE | NONE | MODERATE | Proxy/firewall |
| Microsoft AGT | github.com/microsoft/... | WEAK | NONE | STRONG | NONE | VERY STRONG | Security/SRE, no notification lifecycle |
| kore.ai AMP | kore.ai | UNKNOWN | NONE | NONE | WEAK | VERY STRONG | Dashboard governance |
| Arthur AI | arthur.ai | WEAK | NONE | MODERATE | MODERATE | MODERATE | Autonomy staging closest analogue |
| AgentOps | agentops.ai | NONE | NONE | NONE | NONE | MODERATE | Observability only |
| LangGraph | langchain.com/langgraph | MODERATE | MODERATE | NONE | STRONG | NONE | Framework, not infrastructure |
| NeMo Guardrails | github.com/NVIDIA-NeMo | NONE | NONE | NONE | WEAK | MODERATE | Content firewall |
| Portkey | portkey.ai | NONE | NONE | NONE | NONE | MODERATE | API gateway |
| LangSmith | smith.langchain.com | MODERATE | NONE | NONE | NONE | MODERATE | Audit substrate, DIY compliance |
| Credo AI | credo.ai | MODERATE | NONE | NONE | NONE | STRONG | Policy lifecycle, not runtime signals |
| Oracle Integration | docs.oracle.com | STRONG | STRONG | NONE | STRONG | MODERATE | Platform-locked, no autonomy context |

---

## Synthesis: The AGS Gap

The substrate exists but the domain layer does not.

The closest a single product gets to AGS is the combination of:
- **Restate** (durable promises as notification substrate)
- **Charli AI's Governance VM** (ABAC policy context attached to signals)
- **Microsoft AGT's trust scoring** (autonomy context as behavioral history)
- **Conductor's HUMAN task** (structured ack and decision semantics)
- **Prefactor's outcome/scope assessment** (risk scoring to determine when signals trigger)

No product combines all five. The AGS concept — treating notifications as governance
signals with durable state, explicit ack semantics, and autonomy context — is a genuine
infrastructure gap.

**The "signaling before enforcement" thesis holds.** Most enforcement products block
without explaining why. When something goes wrong the questions are:
- *Who knew this was happening?*
- *When did they know?*
- *What signals did the system surface?*
- *Was silence intentional or accidental?*

Pure enforcement systems cannot answer these reliably. AGS signals before it enforces.

---

## Key Strategic Observations

**1. FINRA whitespace is real.**
No startup governs autonomous agent behavior against FINRA WSP requirements at runtime.
DORA coverage exists (MetricStream, FD Ryze) but is documentation-focused. Agent-specific
FINRA compliance tooling hasn't materialized despite the 2026 oversight report.

**2. MCP is becoming the de facto governance chokepoint.**
The Anthropic Nov 2025 MCP auth extensions + every major governance vendor building MCP
gateways = the practical 2026 AGS implementation is a governed MCP gateway. UNS's
architecture maps cleanly onto this pattern.

**3. Google's Dec 2025 move validates the category, not the solution.**
Google shipping native tool governance in Vertex AI means the problem is confirmed.
It will commoditize basic AGS for GCP-locked teams. Leaves multi-cloud and
regulated-industry use cases open for a dedicated AGS product.

**4. The audit layer is well-served; the signaling layer is not.**
LangSmith (SOC 2 Type II), Fiddler, Galileo, and LangGraph's checkpointing give the
industry solid audit substrate. The gap is upstream: making notifications first-class
governance objects before they become audit entries.

**5. Charli AI is the closest competitor philosophically.**
Governance VM + ABAC + real-time forensic trace + escalation. Finance-vertical,
proprietary, HITL details undisclosed. Worth monitoring.

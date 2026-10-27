> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# UNS vs Cloud-Native Agent Governance Stacks

**Complementary positioning analysis for UNS v1.0**

| Field | Value |
|---|---|
| Date | 2026-05-08 |
| Status | Strategic positioning — informs PRD §1.x and external messaging |
| Audience | Investors, partners, design-partner candidates, platform-leadership stakeholders |

---

## Thesis

The agent governance category has shifted from "single product" to "multi-layer stack." Every major cloud vendor (Microsoft, AWS, Google) now ships an agent-governance stack. Every major agent framework (LangGraph, AutoGen, CrewAI) ships HITL ergonomics. **None of them ship a neutral, runtime, durable approval primitive that composes cleanly with the others.** That gap is UNS's market.

This document maps the cloud-vendor stacks layer-by-layer and shows where UNS fits. It is the positioning briefing — *not* a competitive teardown. UNS sells *with* these stacks, not *against* them.

---

## The four-layer agent governance framework

Microsoft's [Cloud Adoption Framework for AI agents](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization) lays out a useful canonical four-layer model. Other clouds and OSS stacks map onto the same layers:

| Layer | What it does | Microsoft | AWS | Google | UNS |
|---|---|---|---|---|---|
| **1. Data governance & compliance** | Translates regulations into technical controls; data residency; retention; PII | Purview Compliance Manager + Purview APIs | Macie + DLP + Glue Data Catalog + Compliance reports | DLP + Cloud Data Catalog + Assured Workloads | **Out** (consumes vendor stack via plugins) |
| **2. Agent observability** | Inventory, behavioral visibility, cost tracking | Agent 365 + Defender for Cloud + Azure Monitor + Application Insights | CloudWatch + AgentCore observability + Cost Explorer | Cloud Monitoring + Vertex AI Model Monitoring | **Adjacent** — emits to vendor stack via AuditHook |
| **3. Agent security** | Threat protection, RBAC, red teaming, content safety | Defender AI threat protection + Content Safety + AI Red Teaming Agent + Sentinel | GuardDuty + Bedrock Guardrails + IAM + Detective | Sensitive Data Protection + Cloud Armor + Security Command Center | **Out** (sibling concern; ExecutionGate handles inline enforcement) |
| **4. Agent development** | Frameworks, SDKs, protocols | Microsoft Agent Framework + Foundry SDK + MCP + A2A | Bedrock Agents SDK + AgentCore + AWS SDK | Agent Builder + Vertex AI ADK + Agentspace + MCP | **Out** — UNS is callable from any framework |

This is the *governance stack*. UNS does not compete with any of these layers.

**The missing fifth layer**, present in zero of the cloud-vendor stacks: a runtime primitive for `REQUIRE_APPROVAL → notification → human ACK → resume callback`.

Every cloud vendor's stack assumes either:
1. Policy decision is binary (ALLOW/DENY) — handled by Layer 3, no human needed for that specific action
2. Human review is asynchronous, after-the-fact, and lives in observability (Layer 2)
3. Approval is bespoke per-deployment, built by the customer's engineering team using framework HITL primitives + messaging tools

That's the gap.

---

## Vendor-by-vendor map

### Microsoft Agent 365 + Agent Governance Toolkit (AGT)

**What Microsoft has shipped (as of Q2 2026):**
- **Agent 365** — agent inventory, observability, hero metrics, agent map, audit
- **Microsoft Entra Agent ID** — centralized agent identity
- **Agent Governance Toolkit (AGT)** — MIT-licensed: PolicyEvaluator, MerkleAuditChain, KernelSpace runtime governance, contributor reputation, MCP security scanner, shadow AI discovery, agent SRE
- **Microsoft Purview** — data governance and compliance
- **Microsoft Defender for Cloud** — AI threat protection
- **Microsoft Foundry** — agent development platform with native AGT integration
- **Copilot Studio** — low-code agent authoring with built-in governance and (notably) approval flows
- **Microsoft Agent Framework + tool-approval flow** — adjacent product with HITL approval semantics

**What Microsoft does *not* ship (verified by reading AGT codebase + Cloud Adoption Framework doc):**
- A standalone runtime HITL approval primitive at the Layer-5 / cloud-vendor-agnostic level
- A first-class `Approval Audit` stream distinct from policy decision audit
- Cross-cloud bridge plugins (AGT is Microsoft-stack-coupled even where MIT-licensed)
- Three-stream correlated forensic audit specifically engineered for the "who knew what, when" forensic question

**Microsoft's HITL story is real but Microsoft-locked:** Copilot Studio approvals + Agent Framework tool-approval flow. These work beautifully *within* Microsoft. They don't help a team running LangGraph on AWS that needs HITL approval flows interoperable with their Bedrock AgentCore deployment.

### AWS Bedrock AgentCore

**What AWS has shipped:**
- **Bedrock AgentCore** — agent runtime with policy/permissions evaluation
- **Cedar policy language** for fine-grained authorization (notable: UNS evaluated Cedar in ADR-002 and chose custom DSL for v1; convergence with Cedar via plugin is plausible v2+)
- **AWS IAM** for agent identity (managed-identity pattern via IRSA / IAM Roles for Service Accounts)
- **Amazon Bedrock Guardrails** for input/output filtering
- **AWS Verified Permissions** for managed Cedar evaluation
- **Step Functions** + custom workflow patterns for human-in-the-loop (callback token pattern)

**What AWS does *not* ship as a discrete product:**
- A standalone HITL approval control plane SKU
- A neutral, framework-agnostic runtime approval primitive
- Cross-cloud audit federation

**AWS's HITL story is the Step Functions callback-token pattern** — referenced in UNS ADR-001 as Pattern B. It's well-documented and proven, but it's a workflow primitive, not a governance-native HITL layer. AWS-native customers building HITL approval typically wire up Step Functions + Lambda + EventBridge + custom UI. **UNS as a Step-Functions-callback-compatible layer compresses that to a single primitive.**

### Google Cloud Vertex AI

**What Google has shipped:**
- **Vertex AI Agent Builder** — agent development platform
- **Agentspace** — enterprise agent management and discovery
- **Vertex AI Tool Governance** — centralized tool registry, evaluation, controls (2025 enhancements)
- **Cloud API Registry** — governance-relevant API gateway with policy evaluation
- **Vertex AI evaluation services** — model and agent evaluation pipelines
- **Cloud Audit Logs** — comprehensive audit infrastructure (admin activity, data access, system events)

**What Google does *not* ship:**
- A first-class HITL approval workflow primitive
- Standalone runtime approval product
- Cross-cloud governance federation

**Google's posture is "governance through platform"** — strong on tool governance, evaluation, and centralized control, but no clear public product for the runtime HITL approval primitive specifically.

### Framework-native HITL (LangGraph, AutoGen, CrewAI)

These frameworks ship HITL primitives at the *framework-developer* layer, not the *enterprise-governance* layer:

- **LangGraph** — `interrupt()` + checkpointing + durable state; available in OSS core; LangSmith Deployment provides hosted infrastructure
- **AutoGen** — `human_input_mode` parameter on agents; built into the orchestration loop
- **CrewAI** — task-level human verification patterns

These are essential for developer ergonomics. They don't substitute for an enterprise-grade governance HITL layer because:
- They're framework-locked (LangGraph code doesn't compose with AutoGen-only HITL)
- They lack first-class identity verification of approvers
- They lack the three-stream forensic audit substrate
- They lack the policy/audit/notification integration that enterprise compliance demands
- They emit framework-specific events, not portable governance signals

**UNS calls into these frameworks' HITL primitives, not the other way around.** The `WorkflowOrchestrator` Protocol (5-method contract per ADR-004) provides a portable abstraction over Temporal signals, Step Functions callback tokens, Restate awakeables, Airflow HITL operators, and framework-native interrupts.

### Workflow vendors (Temporal, Restate, Orkes Conductor, Step Functions)

These are durable workflow engines with HITL patterns:

- **Temporal signals + `wait_condition`** — well-documented HITL pattern
- **Restate awakeables** — durable suspended invocation
- **Orkes Conductor** — workflow-native human approval steps
- **AWS Step Functions** — callback token pattern

Same gap as framework HITL: workflow-primitive, not governance-native. UNS v1.0 OSS core ships a lightweight built-in WorkflowOrchestrator (in-memory, non-durable across restart) for non-regulated deployments; commercial DurableWorkflow plugin maps to Temporal or Restate when durability matters.

### Specialized HITL / approval-workflow products

Two adjacent product categories worth noting:

- **HumanSignal** (formerly Label Studio Enterprise) — production-grade HITL for *data labeling and LLM evaluation*. Different problem space from runtime agent-action approval. Brand-adjacent name; clarify in marketing.
- **Approval-as-a-feature** in workflow tools (Zapier approvals, Slack workflow builder, etc.) — useful for business-process approvals, not governance-grade for AI agent actions.

---

## What everyone has covered

Across the cloud-vendor stacks, every governance layer has a credible commercial or OSS-with-managed-tier solution:

- ✅ Agent identity (Microsoft Entra Agent ID, AWS IAM, Google Cloud IAM)
- ✅ Policy enforcement (AGT, AgentCore, Vertex AI Tool Governance)
- ✅ Observability + inventory (Agent 365, CloudWatch, Cloud Monitoring)
- ✅ Threat protection (Defender, GuardDuty, Cloud Armor)
- ✅ Audit infrastructure (Defender, CloudTrail, Cloud Audit Logs)
- ✅ Sandboxing / execution gates (AGT KernelSpace, AgentCore execution boundaries, Vertex AI restrictions)
- ✅ Compliance documentation pipelines (Purview, Audit Manager, Compliance Reports)

These are the layers UNS does not need to build. Each cloud-vendor stack is good enough at its own layer; the value UNS provides is *not* re-implementing them.

---

## What everyone is missing

Single shared blind spot:

> **A neutral, durable, runtime primitive for `REQUIRE_APPROVAL → notification → human ACK → resume callback`.**

Concrete observable form of the gap:
1. **No standalone product** — every "approval" feature is bundled into a broader stack (workflow, framework, observability, platform)
2. **No cross-vendor portability** — Microsoft approvals don't compose with AWS, AWS callbacks don't compose with Google, none of them compose with framework-native HITL
3. **No first-class `Approval Audit` stream** — every existing audit treats human ACK as a sub-field of policy decision logs, not a semantically distinct event
4. **No three-stream forensic correlation** — auditor cannot trivially answer "what did the policy decide, what did the human decide, what did the transport layer do" with cross-stream correlation keys
5. **No "approval completion ≠ policy correctness" distinction** in the audit substrate — most existing audits conflate them

Production teams working around this gap (per Stage 2 research):
- Slack approval buttons + custom callback handlers
- Email links + webhook receivers
- Temporal workflows + custom UIs
- LangGraph interrupts + manual state management
- Cloud-vendor SDKs + glue code

This is the UNS market.

---

## UNS's exact niche

| Layer | Cloud-vendor responsibility | UNS responsibility |
|---|---|---|
| 1. Data governance & compliance | Purview / Macie / DLP | Article 14 + GDPR 22 commercial Compliance Templates plugin |
| 2. Agent observability | Agent 365 / CloudWatch / Cloud Monitoring | Three-stream audit emitted into vendor stack via AuditHook plugins |
| 3. Agent security | Defender / GuardDuty / Cloud Armor | Out of scope (ExecutionGate handles inline enforcement; commercial Break-Glass adds dual-key emergency override) |
| 4. Agent development | Agent Framework / Bedrock SDK / Vertex Builder | UNS SDKs (Python, TypeScript) + MCP governance tools |
| **5. Runtime HITL approval (NEW)** | **Not provided** | **UNS core: REQUIRE_APPROVAL → notification → ACK → resume + three-stream audit** |

---

## Concrete integration patterns

### With Microsoft

Customer running Agent 365 + AGT + Foundry. Wants HITL approval primitive for high-stakes agent actions:

```
agent.tool_call(args)
   │
   ▼
AGT PolicyEvaluator.evaluate(args)  ─── ALLOW ──► proceed
   │
   ▼ DENY-with-approval-possible (custom AGT outcome) OR REQUIRE_APPROVAL via UNS MCP tool
uns.governance.evaluate(policy, context)
   │
   ▼ REQUIRE_APPROVAL
uns Approval Workflow ──► Slack notification (or Teams via Microsoft Stack Bridge plugin)
   │
   ▼ Human ACK
UNS callback ──► agent resume

Audit trail emitted to:
   ├─ Defender for Cloud (via UNS AuditHook → Microsoft Stack Bridge plugin)
   ├─ Sentinel
   └─ UNS Decision/Approval/Delivery streams (preserved as authoritative HITL forensic record)
```

The Microsoft Stack Bridge plugin (commercial) consumes Entra Agent ID for `IdentityProvider` hook and emits to Defender + Sentinel via `AuditHook` Protocol. **UNS becomes a first-class citizen of the Microsoft governance stack without forcing the customer to abandon their existing Microsoft investments.**

### With AWS

Customer running Bedrock AgentCore + Cedar policy:

- UNS core emits Decision/Approval/Delivery audit to CloudTrail via AWS Stack Bridge plugin
- IdentityProvider hook resolves identity from AWS IAM (or AWS Verified Permissions)
- Approval callback registered as Step Functions task token; human approval via Slack/Email/PagerDuty channel adapters
- Cedar policy evaluation continues in AgentCore; UNS handles the HITL approval layer that AgentCore doesn't ship

### With Google

Customer running Vertex AI + Agentspace:

- UNS emits to Cloud Audit Logs via GCP Stack Bridge plugin
- IdentityProvider hook resolves identity from Google Cloud IAM
- Tool governance handled by Vertex; HITL approval handled by UNS
- Channel adapters route notifications to Google Chat in addition to Slack/Email/PagerDuty

### With framework-only (LangGraph + Temporal, no cloud governance stack)

Customer running LangGraph agents on Temporal, no major cloud governance stack:

- UNS core's lightweight built-in WorkflowOrchestrator (in-memory) sufficient for v0.4–v0.5 prototyping
- Commercial DurableWorkflow plugin swaps in Temporal as the orchestrator backend for production
- LangGraph `interrupt()` calls UNS MCP tools (`request_approval`, `check_policy`, `log_decision_reasoning`)
- UNS handles the audit, callback, and identity primitives the framework alone doesn't provide

---

## Differentiation summary

| | Cloud-vendor stacks (Microsoft / AWS / Google) | Framework HITL (LangGraph / AutoGen / CrewAI) | Workflow tools (Temporal / Restate / Step Functions) | **UNS** |
|---|---|---|---|---|
| Cloud-agnostic | No | N/A | Yes | **Yes** |
| Framework-agnostic | Adapter-only | Framework-locked | Yes | **Yes** |
| First-class HITL approval primitive | Partial / Microsoft-stack-locked / AWS callback-token / GCP absent | Developer ergonomics | Workflow primitive (not governance-native) | **Yes (core)** |
| Three-stream forensic audit | Single audit stream | Framework-dependent | Workflow history only | **Yes (Decision + Approval + Delivery)** |
| OSS + commercial plugins | All-OSS (Microsoft AGT) or all-managed (AWS / GCP) | OSS + paid SaaS tier | OSS + commercial workflow platform | **Apache 2.0 core + à la carte plugins** |
| Approval-as-policy-correctness distinction | Conflated | Not modeled | Workflow-state only | **Explicit, audit-substrate-level** |
| HITL approver identity verification | Cloud-vendor-locked | Framework-dependent | Workflow-tool-dependent | **Pluggable via IdentityProvider hook** |
| Regulatory templates for HITL specifically | Annex IV documentation only | None | None | **Commercial plugin: Article 14 + GDPR 22 + FINRA 3110 + DORA Article 17** |

---

## Risks to the positioning

Honest enumeration:

1. **Microsoft adds runtime HITL.** The most likely competitive response. AGT is iterating fast; community contributors are pushing PRs to harden enforcement (per the LangChain Reddit thread). Mitigation: ship faster on the cloud-agnostic complementary positioning. Once UNS is the de facto neutral primitive, even Microsoft customers may prefer it for cross-cloud or framework-agnostic deployments.

2. **AWS or Google ships a Bedrock-AgentCore-Approval / Vertex-Approval product.** Plausible. Same mitigation: cloud-agnostic neutrality is the moat. Customers running multi-cloud agent fleets need a layer that doesn't lock them in.

3. **A framework vendor (LangChain via LangSmith, or a startup) adds enterprise HITL approval.** Possible but harder to do cleanly across frameworks. Same neutrality argument.

4. **HumanSignal expands into runtime agent governance.** Adjacent but unlikely; their core is data-labeling-and-evaluation, not runtime control plane. Worth monitoring; brand disambiguation matters in the meantime.

5. **The category itself doesn't materialize fast enough for UNS v1.0 to find buyers.** Real risk. Mitigation: regulatory tailwind (EU AI Act August 2026 deadline) creates urgency; design partners in regulated domains are highest-priority go-to-market.

---

## Strategic implication for UNS v1.0

Three actionable changes vs Vision B+ as originally drafted:

1. **Promote Microsoft / AWS / GCP Stack Bridge plugins** to commercial-priority — these are the validation that "complementary" is real. First commercial plugin to ship should be Microsoft Stack Bridge, since Microsoft has the most aggressive agent-governance posture.

2. **Lead Compliance Templates plugin with EU AI Act Article 14** (operational human oversight) and **GDPR Article 22** (meaningful human intervention) — not Annex IV documentation (Microsoft AGT already automates Annex IV).

3. **Adopt CloudEvents native event schema in v1.0** (revise ADR-002) — AGT uses CloudEvents; for the "complement Microsoft's stack" pitch to be credible at every integration point, UNS needs to speak the same envelope format.

---

## Source artifacts

- PRD v2.0 at `_UNS/agent_governance_control_plane_prd.md` (gitignored)
- 9 architecture decision records at `_UNS/docs/decisions/`
- Vision B+ scope sketch at `_UNS/docs/internal/superpowers/specs/2026-05-08-vision-b-plus-design.md`
- Stage 2 production-pattern matrix research at same location
- Stage 2 pre-vs-post execution research at same location
- Stage 2 competitive landscape (Perplexity Deep Research, May 2026)

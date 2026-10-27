> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Executive Summary

**UNS — Neutral Approval Control Plane for AI Agents**

---

## The Market Moment

Autonomous AI agents are crossing the line from *recommend* to *act*. They commit financial transactions, mutate records, call external APIs, send communications — actions with real-world consequences and no easy "undo."

Cloud vendors are responding. As of 2026:

- **Microsoft** has shipped Agent 365, the Agent Governance Toolkit (MIT-licensed), and an Azure Cloud Adoption Framework for AI agent governance. Four-layer stack covering identity, policy, security, observability.
- **AWS** has Bedrock AgentCore with Cedar-based policy and fine-grained authorization for tool actions.
- **Google Cloud** has Vertex AI agent governance, an enterprise tool registry, and centralized agent management.

**Every major cloud platform is becoming an agent governance stack.**

## The Gap That Persists

Across the entire cloud-vendor landscape — and throughout framework-native HITL features (LangGraph interrupts, AutoGen human-input modes, CrewAI patterns) — one capability is consistently *partial, framework-locked, or absent*:

> **A neutral, durable, runtime primitive for `REQUIRE_APPROVAL → notification → human ACK → resume`.**

This is the human-in-the-loop control plane. It's distinct from policy enforcement (which says yes/no), distinct from observability (which records what happened), and distinct from sandboxing (which constrains execution). It answers: *"Should this specific action proceed, and which human authorized it?"*

Production teams need this primitive but don't have it as a standalone product. They build it themselves from:

- Slack approval buttons + custom callback handlers
- Email links + webhook receivers
- Temporal workflows + custom UIs
- LangGraph interrupts + manual state management

Every team rebuilds it. Every team gets the audit semantics, retry logic, identity verification, and cross-system correlation slightly different. None of these solutions composes cleanly with the cloud-vendor governance stacks emerging around them.

## Why It Matters

Three regulatory regimes, all active in 2026, **mandate runtime human-in-the-loop** for high-risk automated decisions — not just documented oversight, but operational mechanisms:

| Regulation | Requirement |
|---|---|
| **EU AI Act Article 14** (high-risk system effective Aug 2026) | Appropriate human oversight measures *operationalized at runtime* |
| **GDPR Article 22** | Meaningful human intervention in automated decisions affecting individuals |
| **FINRA Rule 3110** + **SEC Rule 15c3-5** | Supervision of automated systems with human override capability |
| **DORA Article 17** | Major ICT incident reporting requires evidence of decision-making chain |

The cloud-vendor governance stacks ship the documentation pipelines (e.g., Microsoft AGT's Annex IV evidence pipeline). They don't ship the runtime mechanism. That's the gap.

## The Solution: UNS

UNS is the **neutral approval control plane** for AI agents. It plugs into the cloud-vendor governance stacks and framework-native runtimes; it doesn't compete with them.

**Core primitive (Apache 2.0 OSS):**

- `evaluate(policy, context) → DecisionRecord` returning `ALLOW | REQUIRE_APPROVAL | DENY`
- On `REQUIRE_APPROVAL`: notification to human reviewers via durable channels (Slack, Email, WebSocket, PagerDuty), with approval workflow that survives across restart, retry, and timeout
- On human ACK: callback resume or polling-fetch with cryptographically attestable approval evidence
- Three correlated audit streams (Decision + Approval + Delivery) — the forensic substrate for "who knew what, and when"

**Plugin ecosystem (commercial, à la carte):**

- Cloud-stack bridges: Microsoft (Entra Agent ID + Defender + Sentinel), AWS (IAM + CloudTrail + GuardDuty), GCP equivalents
- Identity / non-repudiation: JWS, SPIFFE, hardware-token-based signing
- Tamper-evident audit: Merkle-tree chained ledger with external attestation
- Durable workflow: Temporal / Restate adapter
- Compliance templates: EU AI Act Article 14 + GDPR 22 + FINRA 3110 + SOC 2 + HIPAA

**No "Enterprise Edition."** Plugins are independently licensed and independently versioned.

## Three Buyer Segments

Demand is concentrated in three places, each with budget today:

1. **Regulated and high-stakes automation** — financial services, healthcare, legal, infrastructure. Money movement, sensitive-data access, externally visible changes. Risk is obvious; budget exists.
2. **Agent platform teams** operationalizing tool approval and runtime governance — already deploying Microsoft AGT, AWS AgentCore, or Google Vertex AI. Need the missing HITL layer that composes with their existing platform.
3. **Custom-agent builder teams** stitching approval flows from frameworks + Slack + webhooks. Need a neutral, durable primitive they can drop in.

## Strategic Differentiation

| | Microsoft AGT / Agent 365 | AWS Bedrock AgentCore | Google Vertex AI Governance | LangGraph / AutoGen / CrewAI HITL | **UNS** |
|---|---|---|---|---|---|
| Cloud-agnostic | No (Azure-coupled) | No (AWS-coupled) | No (GCP-coupled) | N/A | **Yes** |
| Framework-agnostic | Adapters | AWS-runtime | Vertex-runtime | Framework-locked | **Yes** |
| First-class HITL approval primitive | Partial (Copilot Studio adjacent) | No | No | Framework-native (developer ergonomics) | **Yes (core primitive)** |
| Three-stream forensic audit (Decision + Approval + Delivery) | Single audit stream | Single audit stream | Single audit stream | Framework-dependent | **Yes** |
| OSS core + commercial plugins | All MIT (no commercial layer) | Managed service only | Managed service only | OSS + paid tiers | **Apache 2.0 core; plugins per capability** |

The wedge is precise: **neutral approval primitive, runtime-grade, audit-complete, vendor-portable**. UNS sells *the primitive every team is reinventing*, productized.

## Status

- v0.2 OSS core in extraction from MIP — notification & signaling layer (Slack/Email/WebSocket/PagerDuty channel adapters), declarative YAML policies, ACK lifecycle, deduplication, rate limiting, DLQ, delivery audit
- 1823 tests passing; ruff clean; smoke-deployed
- 9 architecture decision records committed at `_UNS/docs/decisions/`
- Roadmap v0.3 (Phase 5 cleanup) → v0.4 (Decision Engine) → v0.5 (Approval Workflow) → v0.6 (Why Layer / DecisionRecord polish) → v1.0 (OSS GA) → v2.0+ (commercial plugin ecosystem)
- Trading-domain reference integration via MIP-AG-Trading (illustrative; not load-bearing for UNS positioning)

## The Ask

- Validate that the three buyer segments resonate with your network
- Pressure-test the neutral-approval-control-plane positioning against the cloud-vendor stacks emerging around it
- Identify candidate design partners — agent platform teams or regulated-domain operators willing to pilot v0.4–v0.5
- Help prioritize among the seven commercial plugins (Microsoft / AWS / GCP stack bridges, JWS-Identity, SPIFFE-Auth, Merkle-Audit, Break-Glass, DurableWorkflow, Compliance Templates, Enterprise Dashboards)

## Brand Disambiguation

UNS (Apache 2.0 OSS, runtime agent-action approval) is distinct from **HumanSignal** (commercial data-labeling and LLM-evaluation HITL, formerly Label Studio). Different problem spaces; different audiences; no relationship.

---

*Source artifacts: PRD at `_UNS/agent_governance_control_plane_prd.md`; ADRs at `_UNS/docs/decisions/`; Vision B+ scope sketch and Stage 2 research at `_UNS/docs/internal/superpowers/specs/`.*

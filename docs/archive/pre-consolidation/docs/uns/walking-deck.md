> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Walking Deck

**AGSignal — Neutral Approval Control Plane for AI Agents**

*(Slide-by-slide narrative)*

---

## Slide 1 — Title

**AGSignal**
**The Neutral Approval Control Plane for AI Agents**

The runtime human-in-the-loop primitive every team is rebuilding — productized, vendor-portable, audit-grade.

---

## Slide 2 — The Market Moment

AI agents are crossing the line from *recommend* to *act*:

- Money movements, record mutations, irreversible API calls
- Decisions faster than humans can synchronously supervise
- Failures rare but high-impact and externally visible

Cloud vendors are responding with full agent-governance stacks (2026):

- **Microsoft**: Agent 365 + Agent Governance Toolkit + Azure Cloud Adoption Framework
- **AWS**: Bedrock AgentCore + Cedar policy
- **Google**: Vertex AI governance + Agentspace + tool registry

**Every major cloud platform is becoming an agent governance stack.**

---

## Slide 3 — The Persistent Gap

Across all three cloud-vendor stacks. Across all major frameworks (LangGraph, AutoGen, CrewAI). One capability is consistently partial, framework-locked, or absent:

> **Neutral, durable, runtime `REQUIRE_APPROVAL → notification → human ACK → resume`.**

Distinct from:
- Policy enforcement (yes/no decisions)
- Observability (recording what happened)
- Sandboxing (constraining execution)

Answers: ***"Should this specific action proceed, and which human authorized it?"***

---

## Slide 4 — The Hack-Together Problem

Production teams need this primitive but don't have it.

Today's reality: every team builds it themselves from:

- Slack approval buttons + custom callback handlers
- Email links + webhook receivers
- Temporal workflows + custom UIs
- LangGraph interrupts + manual state management
- Cloud-vendor SDKs + glue code

Every team gets the audit semantics, retry logic, identity verification, and cross-system correlation slightly different.

**Reinvented every project. Composed cleanly with nothing.**

---

## Slide 5 — Regulatory Tailwind

Three regulatory regimes, all active in 2026, **mandate runtime human-in-the-loop** for high-risk automated decisions:

| Regulation | Requirement |
|---|---|
| **EU AI Act Article 14** | Operational human oversight (effective Aug 2026 for high-risk systems) |
| **GDPR Article 22** | Meaningful human intervention in automated decisions |
| **FINRA Rule 3110** + **SEC Rule 15c3-5** | Supervision with human override capability |
| **DORA Article 17** | Major ICT incident reporting requires decision-chain evidence |

Cloud-vendor governance stacks ship the documentation pipelines.
**They don't ship the runtime mechanism.** That's the gap.

---

## Slide 6 — Three Buyer Segments

Demand is concentrated in three places, each with budget today:

1. **Regulated / high-stakes automation** — financial services, healthcare, legal, critical infrastructure. Risk is obvious; budget exists.
2. **Agent platform teams** — already deploying Microsoft AGT, AWS AgentCore, Google Vertex AI; need the missing HITL layer.
3. **Custom-agent builders** — stitching approval flows from frameworks + Slack + webhooks; need a neutral primitive.

---

## Slide 7 — Introducing AGSignal

**The neutral approval control plane.** Plugs into cloud-vendor stacks and framework-native runtimes; doesn't compete with them.

Apache 2.0 OSS core. Commercial plugins for crypto, identity, durability, compliance.

```
[Agent decision]
     │
     ▼
evaluate(policy, context) ──► DecisionRecord
     │
     ├─ ALLOW ──────► proceed (auto-audit)
     ├─ DENY ───────► block (auto-audit)
     └─ REQUIRE_APPROVAL ──► notification ──► human ACK ──► resume callback
                                  │              │
                                  ▼              ▼
                              Delivery       Approval
                              Audit          Audit
                                            (with approver identity)

                            All three streams correlated by:
                            correlation_id + decision_id
```

---

## Slide 8 — Audit: Three Correlated Streams

The forensic substrate for "who knew what, and when":

- **Decision Audit** — every policy evaluation. *What did the engine decide.*
- **Approval Audit** — every human ACK / DISMISS / TIMED_OUT. *What did the human decide.*
- **Delivery Audit** — every notification routed/delivered/failed. *What did the transport layer do.*

All three correlated by `correlation_id` + `decision_id`. Hash-chain integrity in OSS core; cryptographic Merkle attestation in commercial plugin.

**Approval completion is *not* proof of policy correctness.** AGSignal is the only product that explicitly carves this distinction in the audit substrate.

---

## Slide 9 — Architectural Commitments

Five load-bearing commitments shape every decision:

1. **Core never participates in execution.** AGSignal is control plane; ExecutionGate and runtime sandboxing are sibling concerns.
2. **Domain-specific governance lives in plugins, not core.** Trading, healthcare, legal each get their own adapter.
3. **Crypto, identity, durability, compliance live in commercial plugins.** No "enterprise edition" — à la carte instead.
4. **Approval Workflow is async, callback-driven by default.** Engine never blocks waiting internally.
5. **Decision Engine is two-layer.** Pure `decide()` for testability; impure `evaluate()` wrapper for audit + side effects.

---

## Slide 10 — Plugin Ecosystem

**3 stable Protocols + 1 callable hook** in OSS core:

- `OverrideAuthority` — emergency overrides (commercial Break-Glass plugin uses dual-key)
- `AuditHook` — extended audit destinations (commercial Merkle-Audit ships tamper-evident chain)
- `WorkflowOrchestrator` — durable execution (5-method portable contract; commercial DurableWorkflow swaps in Temporal/Restate)
- `IdentityProvider` (hook) — identity backends (commercial JWS-Identity, SPIFFE-Auth)

**Cloud-stack bridge plugins** (commercial): Microsoft (consume Entra Agent ID, emit to Defender + Sentinel); AWS (consume IAM, emit to CloudTrail + GuardDuty); GCP (consume Cloud IAM, emit to Cloud Logging + Security Command Center).

---

## Slide 11 — The Complementary Stance

AGSignal is **with** the cloud vendors, not against:

| Cloud-vendor stack provides | AGSignal complements with |
|---|---|
| Agent identity (Entra / IAM / Cloud IAM) | Identity-resolved approvers via IdentityProvider hook |
| Policy enforcement (AGT / AgentCore / Vertex governance) | Runtime HITL primitive that policy engines can invoke |
| Audit infrastructure (Defender / CloudTrail / Cloud Logging) | Three-stream HITL-specific audit emitted to host stack via AuditHook |
| Sandboxing / runtime (rings / IAM service control / VPC SC) | Out of AGSignal scope by design |
| Annex IV / compliance docs | Article 14 + GDPR 22 templates that augment vendor templates |

The pitch: ***"AGSignal adds what your governance stack doesn't have, without forcing you to leave it."***

---

## Slide 12 — Differentiation

| | Cloud-vendor stacks | Framework HITL | Workflow tools | **AGSignal** |
|---|---|---|---|---|
| Cloud-agnostic | No | N/A | Yes | **Yes** |
| Framework-agnostic | Adapter-only | No | Yes | **Yes** |
| First-class HITL approval primitive | Partial / framework-locked | Developer ergonomics only | Workflow primitive (not governance-native) | **Yes (core)** |
| Three-stream forensic audit | Single stream | Framework-dependent | Workflow history only | **Yes** |
| OSS + commercial plugins | All-OSS or all-managed | OSS + paid tier | OSS + paid tier | **Apache 2.0 + à la carte plugins** |

---

## Slide 13 — Roadmap

| Version | Scope | Status |
|---|---|---|
| v0.2 | Notification & signaling layer (existing) | Shipped (1823 tests passing) |
| v0.3 | Phase 5 cleanup + post-v0.2 follow-ups | Planned |
| v0.4 | Decision Engine + Policy DSL + ContextSchema | ADRs landed; implementation queued |
| v0.5 | Approval Workflow + callback semantics | ADRs landed |
| v0.6 | Why Layer / DecisionRecord polish | ADRs landed |
| v1.0 | OSS GA — Python + TypeScript SDK | All 9 ADRs committed |
| v2.0+ | Commercial plugins, multi-tenant control plane | Roadmap |

9 architecture decision records committed; PRD locked at v2.0; v0.4 implementation pending strategic-positioning ratification.

---

## Slide 14 — The Ask

We're looking for:

- **Validation**: do the three buyer segments resonate with your network?
- **Pressure-test**: is the neutral-approval-control-plane positioning defensible against Microsoft / AWS / Google's stacks?
- **Design partners**: agent platform teams or regulated-domain operators willing to pilot v0.4–v0.5
- **Plugin priorities**: which of the seven commercial plugins (3 cloud-stack bridges + JWS-Identity + SPIFFE-Auth + Merkle-Audit + Break-Glass + DurableWorkflow + Compliance Templates + Enterprise Dashboards) ships first

---

## Slide 15 — Brand Disambiguation

**AGSignal** (Apache 2.0 OSS, runtime agent-action approval) is distinct from:

- **HumanSignal** — commercial data-labeling + LLM-evaluation HITL (formerly Label Studio). Different problem space.
- **Microsoft Agent 365** — commercial agent platform with policy/identity/observability. Complementary; AGSignal plugs in.
- **AWS Bedrock AgentCore** — agent runtime with Cedar policy. Complementary.
- **Google Vertex AI Agent Governance** — platform governance + tool registry. Complementary.
- **LangGraph/AutoGen/CrewAI HITL** — framework-native developer ergonomics. Different layer; AGSignal is the runtime control plane those frameworks call into.

---

## Slide 16 — Closing

> **Cloud vendors built the agent governance stack.**
> **They forgot the runtime human-in-the-loop primitive.**
> **AGSignal is what every team has been rebuilding — productized.**

Vendor-portable. Framework-agnostic. Audit-grade.

The neutral approval control plane.

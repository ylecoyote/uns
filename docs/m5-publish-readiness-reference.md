# M5 Publish Readiness Reference

Date: 2026-05-06

Status: Working reference

Linear milestone: [M5 - UNS parity backlog](https://linear.app/awiley-personal/project/agsignal-migration-45e0671d2a4c)

Landing page reference: `/Users/awiley/Downloads/AGSignal-screencapture-60ff106d-b864-43fc-ae59-1696facb81cb-claudeusercontent-v1-design-projects-60ff106d-b864-43fc-ae59-1696facb81cb-serve-AGSignal-v4-html-2026-05-06-11_56_57.png`

## Purpose

This document is the standing M5 reference for keeping the AGSignal landing page,
publish-readiness plan, and MIP UNS parity backlog aligned.

The landing page is the product narrative. M5 is the implementation and
documentation work required to make that narrative true enough to publish without
overstating what the current extraction branch already ships.

## Current Implementation Reading

The current branch supports the AGSignal foundation:

- AGSignal-first product terminology and `agsignal.*` public aliases.
- Standalone HTTP runtime for sending and simulating governance signals.
- Basic acknowledgment, dismissal, and notification status routes.
- YAML policy loading plus database-backed notification policy persistence.
- WebSocket replay and optional Redis fanout.
- Basic channel health and DLQ visibility.
- Generic host-application adapter boundary.

The branch should not be described as full MIP UNS parity. M5 captures the
remaining work needed for MIP sample policies, MIP embedding, richer HTTP/admin
parity, operational runtime parity, policy engine migration, and publish-ready
documentation.

## Landing Page Mapping

### Hero: missing control plane for accountable autonomy

Implementation status: supported by the current product direction.

This maps to AGSignal's core positioning: governance signaling for autonomous
agents, with durable notification, acknowledgment, timeout, delivery, and policy
state. This is safe as a top-level product claim.

Supporting work:

- AGSignal README and docs taxonomy.
- Public `agsignal.*` aliases.
- Generic app adapter boundary.

### Three gaps every autonomous system inherits

Implementation status: partially shipped, with M5 parity work required.

Landing page claims:

- Logs show what happened, not why.
- Alerts notify, but acknowledgments teach.
- Enforcement blocks, but does not explain decisions.

Implementation mapping:

- Audit/read model and notification history are M5 parity work.
- Acknowledgment flows exist now, but need richer API/docs parity.
- Enforcement explanation depends on host-app integration and the policy engine.

Linear:

- [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)
- [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)
- [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

### Infrastructure primitives

Implementation status: mixed.

| Landing page primitive | Current status | M5 owner |
|---|---|---|
| Durable notification state | Partially present through audit, policy, and replay stores | MIP-253 |
| Explicit ACK semantics | Core behavior present | MIP-252, MIP-255 |
| Autonomy-aware routing | Basic routing and autonomy context present | MIP-250, MIP-254 |
| Non-blocking governance | Generic boundary present; host integration remains | MIP-251 |

### Not another alerting tool

Implementation status: directionally correct, but needs careful wording.

The "delivery -> telemetry -> enforcement" framing is useful. Today AGSignal is
strongest on delivery, signaling, policy routing, replay, and acknowledgment.
Full enforcement defensibility requires host-app integration and the policy
engine work.

Linear:

- [MIP-251](https://linear.app/awiley-personal/issue/MIP-251/add-mip-embedding-adapter-package-for-uns-parity)
- [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

### Market/category claim

Implementation status: strong product narrative.

Landing page claim:

> The market is building enforcement. AGSignal builds the layer that makes
> enforcement defensible.

This is the strongest category statement. It should remain, provided the docs
clearly separate:

- Shipped core signaling and runtime behavior.
- MIP UNS sample policies.
- Planned policy engine and operational parity work.
- MIP-specific adapter behavior that is not part of AGSignal Core.

Linear:

- [MIP-255](https://linear.app/awiley-personal/issue/MIP-255/prepare-agsignal-for-publish-with-full-documentation-set)

### Built, not just proposed

Implementation status: true for the extraction foundation, not for full parity.

This section should distinguish status labels such as:

- Active: implemented and verified in the current branch.
- In progress: implemented partially or needs docs/API cleanup.
- Parity backlog: planned M5 work.

Do not imply full MIP UNS parity is already shipped until MIP-250 through
MIP-255 have been resolved or explicitly descoped.

### How AGSignal works

Implementation status: good workflow model.

| Landing page step | Implementation mapping |
|---|---|
| Agent emits intent | `agsignal.*` SDK and generic app adapter |
| Policy router determines action | Current policy registry/store, MIP sample policies, future policy engine |
| Signal emits durable event | Current runtime, replay store, and future operational parity |
| Human reviews and ACKs | Current ACK routes plus richer API/docs parity |
| Record becomes governance memory | Future audit/read model and policy learning work |

Linear:

- [MIP-250](https://linear.app/awiley-personal/issue/MIP-250/publish-mip-uns-policies-as-agsignal-sample-policy-set)
- [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)
- [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)
- [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

### Production-oriented implementation

Implementation status: should become the public publish checklist.

This section should be generated from real implementation status, not marketing
intent. MIP-255 owns the publish checklist and should keep each row tied to
evidence: code, tests, smoke docs, examples, or explicit known limitations.

## M5 Backlog

| Issue | Purpose | Publish impact |
|---|---|---|
| [MIP-250](https://linear.app/awiley-personal/issue/MIP-250/publish-mip-uns-policies-as-agsignal-sample-policy-set) | Publish MIP UNS policies as AGSignal sample policies | Creates `examples/policies/mip-uns/` as the canonical sample policy pack path |
| [MIP-251](https://linear.app/awiley-personal/issue/MIP-251/add-mip-embedding-adapter-package-for-uns-parity) | Add MIP embedding adapter package | Adds optional MIP-shaped adapter templates outside AGSignal Core |
| [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns) | Close HTTP/admin API parity gaps | Completed slices add producer idempotency, richer simulation, audit-backed delivery status, and DLQ entry removal; list/read-model, invalidation lifecycle, and DLQ retry/bulk ops remain |
| [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity) | Decide and implement worker, adapter, audit, and DLQ parity | Delivery, ACK, and timeout audit slices are implemented; worker/retry/DLQ replay are host-owned or future operations-package concerns |
| [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package) | Port reusable policy engine concepts | Slices now add ACTIVE-only runtime policy loading, PREVIEW-only shadow loading, immutable delta transition history, shadow evaluation models, and guard result primitives; repository and policy-envelope work remains |
| [MIP-255](https://linear.app/awiley-personal/issue/MIP-255/prepare-agsignal-for-publish-with-full-documentation-set) | Prepare full docs and publish checklist | Makes the landing page publishable and supportable |

## Donor Parity Protocol

Every M5 implementation issue must include a donor parity checkpoint before it
is marked done in Linear.

Required fields:

- Donor files reviewed.
- Behavior ported into AGSignal.
- Behavior adapted to AGSignal's product boundary.
- Behavior intentionally excluded from AGSignal Core.
- Tests proving adapted AGSignal behavior.
- Remaining validation that must happen in the MIP host repo.

The checkpoint belongs in the issue spec or implementation note, and the Linear
completion update must summarize the same `Ported`, `Adapted`, `Excluded`,
`Verification`, and `Remaining host-repo validation` sections.

## Truth-in-Publishing Rules

Use these rules when editing the landing page, README, docs, or examples:

1. Lead with AGSignal, not UNS.
2. Use UNS as historical provenance or compatibility language only.
3. Use MIP policies as sample content, not default product behavior.
4. Keep MIP/ATP integration outside AGSignal Core unless explicitly optional.
5. Do not describe full MIP UNS parity as shipped until M5 says so.
6. Separate shipped behavior, sample behavior, and planned behavior.
7. Public examples should prefer `agsignal.*` imports.
8. Compatibility docs may mention `notification.*` imports explicitly.

## Publish Readiness Definition

AGSignal is ready to publish when:

- The landing page claims map to shipped behavior, sample assets, or explicit
  documented limitations.
- Full docs route readers by task: evaluate, quickstart, integrate, operate,
  and extend.
- Sample MIP policies are loadable, tested, and documented as examples.
- Host-app integration has a clear generic boundary and a MIP proving adapter.
- HTTP/admin API parity is either implemented or documented as intentionally
  excluded.
- Operational runtime guarantees are documented and tested.
- Policy engine concepts required for defensible governance are ported or
  explicitly scoped into a later release.
- Release checklist includes package metadata, smoke commands, known
  limitations, and verification evidence.

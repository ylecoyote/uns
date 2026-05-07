# M5 Publish Readiness Reference

Date: 2026-05-06

Status: Completed M5 reference

Linear milestone: [M5 - UNS parity backlog](https://linear.app/awiley-personal/project/agsignal-migration-45e0671d2a4c)

Landing page reference: `/Users/awiley/Downloads/AGSignal-screencapture-60ff106d-b864-43fc-ae59-1696facb81cb-claudeusercontent-v1-design-projects-60ff106d-b864-43fc-ae59-1696facb81cb-serve-AGSignal-v4-html-2026-05-06-11_56_57.png`

## Purpose

This document is the standing M5 reference for keeping the AGSignal landing page,
publish-readiness plan, and completed MIP UNS parity work aligned.

The landing page is the product narrative. M5 closed the implementation and
documentation work required to make that narrative true enough to publish without
overstating what AGSignal currently ships.

## Current Implementation Reading

The current main branch supports the AGSignal foundation:

- AGSignal-first product terminology and `agsignal.*` public aliases.
- Standalone HTTP runtime for sending and simulating governance signals.
- Acknowledgment, dismissal, notification status, and ACK status routes.
- Producer idempotency, richer simulation, audit-backed delivery status, DLQ
  inspection/removal, channel health, and policy reload APIs.
- YAML policy loading plus database-backed notification policy persistence,
  ACTIVE-only runtime loading, PREVIEW-only shadow loading, policy delta history,
  shadow/guard primitives, policy learning store, policy config hashes, and
  evaluation records.
- WebSocket replay and optional Redis fanout.
- Generic host-application adapter boundary.
- MIP UNS sample policies under `examples/policies/mip-uns`.
- Optional MIP-shaped adapter templates outside the AGSignal Core public facade.
- Local stdio MCP server exposing AGSignal governance tools; HTTP/SSE MCP
  transport remains deferred.
- Apache-2.0 publish metadata and repository `LICENSE`.

The branch should not be described as a verbatim copy of MIP UNS. M5 completed
the reusable AGSignal Core parity work and explicitly scoped host-owned MIP
behavior, worker topology, DLQ replay, and MIP-specific callback side effects
outside AGSignal Core.

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

Implementation status: supported, with explicit host-owned boundaries.

Landing page claims:

- Logs show what happened, not why.
- Alerts notify, but acknowledgments teach.
- Enforcement blocks, but does not explain decisions.

Implementation mapping:

- Audit/read models and notification history are implemented for the AGSignal
  runtime and console surfaces.
- Acknowledgment, dismissal, timeout audit, and delivery audit flows are
  implemented and documented.
- Enforcement explanation depends on host-app integration; AGSignal provides
  policy/config/evaluation primitives and sample MIP policy content, not a
  host-specific execution governor.

Linear:

- [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)
- [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)
- [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

### Infrastructure primitives

Implementation status: implemented with scoped limitations.

| Landing page primitive | Current status | Evidence |
|---|---|---|
| Durable notification state | Delivery, ACK, timeout, policy, replay, and read-model storage implemented | MIP-252, MIP-253 |
| Explicit ACK semantics | ACK, dismiss, timeout, status, and audit records implemented | MIP-252, MIP-253 |
| Autonomy-aware routing | Autonomy context, mode-aware policy routing, sample policies, and shadow/guard primitives implemented | MIP-250, MIP-254 |
| Non-blocking governance | Generic host boundary and optional MIP-shaped adapter implemented; host execution remains outside Core | MIP-251 |

### Not another alerting tool

Implementation status: correct with careful wording.

The "delivery -> telemetry -> enforcement" framing is useful. Today AGSignal is
strongest on delivery, signaling, policy routing, replay, acknowledgment, audit,
and policy evaluation evidence. Full enforcement defensibility still requires
host-app integration because AGSignal does not own agent execution loops,
decision models, or host-specific governors.

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

- Shipped core signaling, runtime, MCP stdio, and policy behavior.
- MIP UNS sample policies.
- Host-owned behavior and intentionally deferred operational surfaces.
- MIP-specific adapter behavior that is not part of AGSignal Core.

Linear:

- [MIP-255](https://linear.app/awiley-personal/issue/MIP-255/prepare-agsignal-for-publish-with-full-documentation-set)

### Built, not just proposed

Implementation status: true for AGSignal Core M5.

This section should distinguish status labels such as:

- Active: implemented and verified on current `main`.
- Deferred: intentionally out of v1 or host-owned.
- Sample: MIP-specific proving content, not Core defaults.

Do not imply AGSignal owns MIP runtime services, ATP callbacks, trading
execution, worker topology, hosted MCP transport, public website hosting, or
commercial support channels until those surfaces are explicitly implemented or
documented.

### How AGSignal works

Implementation status: good workflow model.

| Landing page step | Implementation mapping |
|---|---|
| Agent emits intent | `agsignal.*` SDK and generic app adapter |
| Policy router determines action | Policy registry/store, ACTIVE-only runtime loading, sample policies, config hashes, evaluation records |
| Signal emits durable event | Runtime delivery, audit store, replay store, DLQ visibility, MCP stdio tools |
| Human reviews and ACKs | ACK, dismiss, status, timeout, and audit routes |
| Record becomes governance memory | Audit/read models and policy learning primitives |

Linear:

- [MIP-250](https://linear.app/awiley-personal/issue/MIP-250/publish-mip-uns-policies-as-agsignal-sample-policy-set)
- [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)
- [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)
- [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

### Production-oriented implementation

Implementation status: public publish checklist.

This section should be generated from real implementation status, not marketing
intent. MIP-255 closed the publish checklist and each row should stay tied to
evidence: code, tests, smoke docs, examples, or explicit known limitations.

## M5 Completion Summary

| Issue | Purpose | Publish impact |
|---|---|---|
| [MIP-250](https://linear.app/awiley-personal/issue/MIP-250/publish-mip-uns-policies-as-agsignal-sample-policy-set) | Publish MIP UNS policies as AGSignal sample policies | Completed: `examples/policies/mip-uns/` is the canonical sample policy pack path |
| [MIP-251](https://linear.app/awiley-personal/issue/MIP-251/add-mip-embedding-adapter-package-for-uns-parity) | Add MIP embedding adapter package | Completed: optional MIP-shaped adapter templates exist outside AGSignal Core |
| [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns) | Close HTTP/admin API parity gaps | Completed: producer idempotency, richer simulation, audit-backed delivery status, DLQ inspection/removal, read-model routes, channel health, and policy reload are implemented; DLQ retry/bulk ops remain intentionally excluded |
| [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity) | Decide and implement worker, adapter, audit, and DLQ parity | Completed: delivery, ACK, dismiss, and timeout audit slices are implemented; worker/retry/DLQ replay are host-owned or future operations-package concerns |
| [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package) | Port reusable policy engine concepts | Completed: ACTIVE-only runtime policy loading, PREVIEW-only shadow loading, immutable delta transition history, shadow/guard primitives, persisted delta/shadow repositories, config hashes, evaluation records, and approved-delta config application |
| [MIP-255](https://linear.app/awiley-personal/issue/MIP-255/prepare-agsignal-for-publish-with-full-documentation-set) | Prepare full docs and publish checklist | Completed: docs taxonomy, publish identity, sample-policy boundaries, runnable verification references, and known limitations are documented |

## Post-M5 Follow-Ups

These are not M5 blockers:

- Decide whether the landing page screenshot is an external design artifact or a
  site implemented in this repo.
- Create public URL, contact, blog, discussions, and spec/RFC documentation
  issues after the distribution path is decided.
- Add HTTP/Streamable HTTP MCP transport only when there is a named remote
  consumer and an auth/session model.
- Evaluate MCP Tasks for long-running governance workflows.
- Position A2A only when AGSignal has a real peer-agent delegation use case.
- Build host-owned retry/replay runbooks or an optional operations package if
  AGSignal needs durable DLQ replay beyond visibility/removal.

## Donor Parity Protocol

Every M5 implementation issue included a donor parity checkpoint before it was
marked done in Linear.

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
   The AGSignal public integration facade exports only the generic host-app
   boundary; MIP-shaped adapters stay in `notification.integrations.mip_adapter`
   as optional sample/proving code.
5. Describe M5 as reusable AGSignal Core parity, not a verbatim copy of MIP UNS
   runtime infrastructure.
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

As of M5 completion, AGSignal satisfies this definition for a public
source-level publish. Distribution-specific assets such as the landing page
implementation, public domain, contact routes, blog, discussions, and hosted MCP
transport are post-M5 publication/distribution decisions, not evidence gaps in
AGSignal Core.

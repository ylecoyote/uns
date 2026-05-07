# AGSignal Documentation

This directory contains the technical documentation for AGSignal, the governance
signaling control plane for autonomous agents.

AGSignal turns notifications, acknowledgments, timeouts, and delivery failures
into durable governance signals. The current Python runtime is still exposed
through the historical `notification.*` package and UNS-compatible terminology
while the public product API stabilizes.

## Task Navigation

Start from the task you need to complete, not from the implementation package
name. Public docs lead with AGSignal terminology; `notification.*`, `UNS_*`, and
UNS/MIP names appear only where they describe compatibility, provenance, or
sample content.

| Task | Start Here | Then Read |
|------|------------|-----------|
| **Evaluate AGSignal** | [Root README](../README.md) | [Architecture](ARCHITECTURE.md), [M5 Publish Readiness Reference](m5-publish-readiness-reference.md) |
| **Quickstart: send a signal** | [Root README Quick Start](../README.md#quick-start) | [API Reference](API.md), [Running the Service](../README.md#running-the-service) |
| **Configure policies** | [Policy Lifecycle](sections/policy-lifecycle.md) | [MIP UNS Sample Policy Pack](../examples/policies/mip-uns/README.md), [Delivery Semantics](sections/delivery-semantics.md) |
| **Integrate an app** | [Integration Modes](sections/integration-modes.md) | [API Host App Boundary](API.md#host-app-boundary), [App Adapter Proving Smoke](testing/app-adapter-proving-smoke.md) |
| **Operate and audit** | [Observability](sections/observability.md) | [Delivery Semantics](sections/delivery-semantics.md), [WebSocket Replay Smoke](testing/websocket-replay-smoke.md), [WebSocket Redis Fanout Smoke](testing/websocket-redis-fanout-smoke.md) |
| **Extend AGSignal** | [Architecture](ARCHITECTURE.md) | [API Reference](API.md), [Architecture Decisions](#architecture-decisions) |
| **Verify publish readiness** | [M5 Publish Readiness Reference](m5-publish-readiness-reference.md) | [Testing Guides](#testing-guides), [UNS Provenance](uns/README.md) |

## Document Inventory

| Document | Description |
|----------|-------------|
| [../README.md](../README.md) | AGSignal product overview, boundary, terminology, and quick start |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Core runtime architecture, components, and data flow |
| [API.md](API.md) | API reference for the current SDK, models, and interfaces |
| [M5 Publish Readiness Reference](m5-publish-readiness-reference.md) | Landing page, MIP UNS parity backlog, and publish-readiness alignment |
| [uns/README.md](uns/README.md) | Historical UNS extraction materials and AGSignal terminology mapping |

### Architecture Decisions

| Decision | Description |
|----------|-------------|
| [Generic App Adapter Boundary](decisions/2026-05-06-app-adapter-boundary.md) | Host-application integration facade without MIP coupling |
| [UNS Taxonomy](decisions/2026-05-06-uns-taxonomy.md) | Keeps `docs/uns/` as provenance while AGSignal remains the public product identity |
| [WebSocket Redis Fanout](decisions/2026-05-06-websocket-redis-fanout.md) | Optional Redis pub/sub fanout, per-agent channels, and MIP donor comparison |
| [WebSocket Replay Read Model](decisions/2026-05-06-websocket-replay-read-model.md) | Reconnect replay payload persistence and Redis boundary |
| [MIP Adapter Design](superpowers/specs/2026-05-06-mip-251-mip-adapter-design.md) | Optional MIP-shaped adapter templates built on the generic app boundary |
| [HTTP Idempotency and Simulation Design](superpowers/specs/2026-05-06-mip-252a-http-idempotency-simulate-design.md) | First MIP-252 HTTP parity slice for producer retry safety and simulation detail |
| [Delivery Status Design](superpowers/specs/2026-05-06-mip-252b-delivery-status-design.md) | MIP-252 HTTP parity slice for audit-backed delivery readback |
| [DLQ Remove Design](superpowers/specs/2026-05-06-mip-252c-dlq-remove-design.md) | MIP-252 admin parity slice for removing visible DLQ entries |
| [Standalone Audit Persistence Design](superpowers/specs/2026-05-06-mip-253a-standalone-audit-persistence-design.md) | MIP-253 operational parity slice for audit-backed standalone sends |
| [ACK Audit Persistence Design](superpowers/specs/2026-05-06-mip-253b-ack-audit-persistence-design.md) | MIP-253 operational parity slice for ACK and dismiss audit records |
| [Timeout Audit Callback Design](superpowers/specs/2026-05-06-mip-253c-timeout-audit-callback-design.md) | MIP-253 operational parity slice for host-scheduled ACK timeout audits |
| [Operational Parity Contract](superpowers/specs/2026-05-06-mip-253-operational-parity-contract.md) | MIP-253 Core-versus-host runtime ownership decision |
| [Policy Lifecycle Runtime Boundary](superpowers/specs/2026-05-06-mip-254a-policy-lifecycle-runtime-boundary-design.md) | MIP-254 policy engine slice for ACTIVE-only runtime loads and PREVIEW-only shadow loads |
| [Policy Delta Core](superpowers/specs/2026-05-06-mip-254b-policy-delta-core-design.md) | MIP-254 policy engine slice for immutable delta transitions and auditable history |
| [Shadow And Guard Core](superpowers/specs/2026-05-06-mip-254c-shadow-guard-core-design.md) | MIP-254 policy engine slice for shadow evaluation and guard result primitives |
| [Policy Learning Store](superpowers/specs/2026-05-06-mip-254d-policy-learning-store-design.md) | MIP-254 policy engine slice for persisted deltas, shadow results, aggregates, and approval gates |
| [Policy Config Envelope](superpowers/specs/2026-05-06-mip-254e-policy-config-envelope-design.md) | MIP-254 policy engine slice for config hashes, evaluation records, and applying approved deltas |

### Topic Sections

Detailed documentation for specific subsystems:

| Section | Description |
|---------|-------------|
| [Delivery Semantics](sections/delivery-semantics.md) | GUARANTEED vs BEST_EFFORT modes, truth tables, failure handling |
| [Integration Modes](sections/integration-modes.md) | Standalone, context provider, and full integration configurations |
| [Observability](sections/observability.md) | Health states, metrics, DLQ visibility, monitoring |
| [Policy Lifecycle](sections/policy-lifecycle.md) | Policy states, loading, versioning, and resolution |

### Testing Guides

| Guide | Description |
|-------|-------------|
| [App Adapter Proving Smoke](testing/app-adapter-proving-smoke.md) | AGSignal-native smoke for host app evidence integration |
| [WebSocket Redis Fanout Smoke](testing/websocket-redis-fanout-smoke.md) | Real Redis smoke for cross-instance WebSocket fanout |
| [WebSocket Replay Smoke](testing/websocket-replay-smoke.md) | Reconnect replay smoke for missed WebSocket notifications |

### Examples

| Example | Description |
|---------|-------------|
| [MIP UNS Sample Policy Pack](../examples/policies/mip-uns/README.md) | Realistic MIP-derived sample policies for safety, governance, and operational signaling |

## Document Map

```
docs/
├── README.md           ← You are here
├── ARCHITECTURE.md     ← System architecture overview
├── API.md              ← API reference
├── m5-publish-readiness-reference.md ← Landing page and M5 backlog alignment
├── decisions/          ← Accepted architecture decisions
├── sections/
│   ├── delivery-semantics.md   ← Delivery behavior truth tables
│   ├── integration-modes.md    ← Integration configuration options
│   ├── observability.md        ← Health, metrics, and monitoring
│   └── policy-lifecycle.md     ← Policy management
├── testing/           ← Reusable smoke-test guides
└── uns/               ← Historical UNS extraction materials, not public product docs
```

Sample policy packs live outside `docs/` under `examples/policies/`.

## Reading Guide

**New to AGSignal?** Use the **Evaluate AGSignal** and **Quickstart: send a
signal** rows above.

**Implementing delivery logic or policies?** Use **Configure policies** first,
then follow the delivery semantics links for reliability behavior.

**Integrating with external systems?** Use **Integrate an app** for the generic
host boundary. MIP-shaped adapters are optional proving/sample code, not the
AGSignal Core public facade.

**Setting up monitoring?** Use **Operate and audit** for health, audit, DLQ,
WebSocket replay, and fanout guidance.

**Preparing a publish checkpoint?** Use **Verify publish readiness** and keep
each public claim tied to shipped behavior, sample assets, or explicit
limitations.

## Key Concepts Summary

### Product Terms

| Term | Meaning |
|------|---------|
| AGSignal | The product and repository identity. |
| AGS | Agent Governance Signaling, the product category. |
| Governance signal | A durable, auditable state transition created from a notification, acknowledgment, timeout, or delivery failure. |
| AGSignal Core | The runtime that routes, delivers, acknowledges, deduplicates, rate-limits, and audits governance signals. |
| UNS Core | Historical extraction name for the notification runtime from MIP; use for provenance or compatibility only. |

### Notification Intents

| Intent | Purpose | Delivery Mode | Default Ack (LIVE) |
|--------|---------|---------------|---------------------|
| SAFETY | Critical safety issues | GUARANTEED | Required (15 min) |
| GOVERNANCE | Policy/compliance notifications | GUARANTEED | Not required* |
| OPERATIONAL | Operational alerts | BEST_EFFORT | Not required |
| INFORMATIONAL | Informational messages | BEST_EFFORT | Not required |

*GOVERNANCE acknowledgment timeout (30 min) applies only if explicitly enabled via policy.

### Autonomy Modes

| Mode | Channel Routing |
|------|-----------------|
| PREVIEW | WebSocket only (all intents) |
| SHADOW | Limited routing (elevated intents add Slack) |
| LIVE | Full production routing |

### Delivery Modes

| Mode | Behavior | On Failure |
|------|----------|------------|
| GUARANTEED | Sequential fallback (Slack → Email → PagerDuty) | Raises `DeliveryError` |
| BEST_EFFORT | Concurrent delivery to all channels | Returns `FAILED` status, no exception |

For complete details, see [Delivery Semantics](sections/delivery-semantics.md).

## Cross-Reference Index

### By Topic

| Topic | Primary Document | Related Sections |
|-------|-----------------|------------------|
| Acknowledgments | [ARCHITECTURE.md](ARCHITECTURE.md#acknowledgment-engine) | [Delivery Semantics](sections/delivery-semantics.md#acknowledgment-requirements) |
| Channel Adapters | [ARCHITECTURE.md](ARCHITECTURE.md#channel-adapters) | [API.md](API.md#adapters), [Observability](sections/observability.md#per-adapter-health-check-behavior) |
| DLQ/Escalation | [Delivery Semantics](sections/delivery-semantics.md#dlq-dead-letter-queue-visibility) | [Observability](sections/observability.md#dlq-dead-letter-queue-visibility) |
| Health Checks | [Observability](sections/observability.md#health-states) | [API.md](API.md#healthcheckresult) |
| Policy Resolution | [Policy Lifecycle](sections/policy-lifecycle.md#policy-application) | [ARCHITECTURE.md](ARCHITECTURE.md#policy-system) |
| Rate Limiting | [ARCHITECTURE.md](ARCHITECTURE.md#rate-limiter) | [API.md](API.md#rate-limiting), [Observability](sections/observability.md#6-rate-limiting-events) |
| WebSocket Integration | [Integration Modes](sections/integration-modes.md#websocket-considerations) | [ARCHITECTURE.md](ARCHITECTURE.md#integration-points) |

### By Component

| Component | API Reference | Architecture | Configuration |
|-----------|---------------|--------------|---------------|
| NotificationSDK | [API.md#sdk](API.md#sdk) | [ARCHITECTURE.md#sdk-layer](ARCHITECTURE.md#sdk-layer) | [Integration Modes](sections/integration-modes.md#mode-1-standalone-no-external-integration) |
| PolicyRegistry | [API.md#policies](API.md#policies) | [ARCHITECTURE.md#policy-system](ARCHITECTURE.md#policy-system) | [Policy Lifecycle](sections/policy-lifecycle.md) |
| DeliveryService | [API.md#error-handling](API.md#error-handling) | [ARCHITECTURE.md#delivery-service](ARCHITECTURE.md#delivery-service) | [Delivery Semantics](sections/delivery-semantics.md) |
| AcknowledgmentEngine | [API.md#acknowledgment](API.md#acknowledgment) | [ARCHITECTURE.md#acknowledgment-engine](ARCHITECTURE.md#acknowledgment-engine) | [Delivery Semantics](sections/delivery-semantics.md#acknowledgment-requirements) |

## Contributing to Documentation

When adding or updating documentation:

1. **Avoid duplication** - Reference existing sections instead of repeating content
2. **Add cross-references** - Link to related documentation sections
3. **Update this README** - Add new sections to the navigation tables
4. **Maintain consistency** - Use the same terminology across documents

### Terminology Standards

| Term | Meaning |
|------|---------|
| AGSignal | Top-level product and repository identity |
| UNS | Historical extraction/runtime name; avoid as the public product lead |
| ATP | Autonomous Trading Platform (external system) |
| Intent | Notification classification (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL) |
| Autonomy Mode | Agent operating mode (PREVIEW, SHADOW, LIVE) |
| Delivery Mode | Reliability semantics (GUARANTEED, BEST_EFFORT) |
| DLQ | Dead Letter Queue (via escalation callback) |

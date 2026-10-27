> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Generic App Adapter Boundary

Date: 2026-05-06

Status: Accepted

Linear: MIP-246

## Context

The UNS migration project needs an embedding surface for applications that
own governor hooks, circuit-breaker state, execution/slippage evidence, and
domain-specific audit identifiers. The original extraction source was MIP, but
UNS is the shipped product and must not ship MIP-specific application
logic.

The existing `NotificationSDK` is already sufficient for direct producers, but
larger applications benefit from a small facade that standardizes how app-owned
evidence references are carried into `AutonomyContext` and
`Notification.metadata`.

## Decision

UNS ships a generic host-application boundary under
`notification.integrations`:

- `AppEvidenceContext` carries optional app-owned evidence identifiers:
  `plan_id`, `decision_snapshot_id`, `execution_snapshot_id`, and
  `skip_snapshot_id`.
- `AppSignalRequest` represents a host application's signal request without
  importing host domain models.
- `AppSignalContextProvider` is the protocol for resolving UNS
  `AutonomyContext`.
- `DefaultAppSignalContextProvider` supports simple single-agent/default-mode
  integrations.
- `AppSignalAdapter` translates `AppSignalRequest` into a `NotificationSDK`
  call.

This is a stub boundary, not an implementation of any host application's
governor or execution system. MIP or another application can implement its own
hooks outside UNS and call this boundary.

## Rejected

### Ship a MIP-specific adapter inside UNS

Rejected because the user is not shipping MIP. That would leak donor concepts
into the public UNS product and recreate the coupling the extraction is
trying to remove.

### Keep this docs-only

Rejected because application integrators need importable contracts and tests,
not only prose.

## Consequences

- UNS can document and test the app integration contract without owning
  application-specific behavior.
- MIP-246 can be satisfied as an UNS-side boundary stub.
- MIP-247 can later build a proving flow against this boundary, but that flow
  remains a separate integration exercise.

# MIP-251 MIP Adapter Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-251](https://linear.app/awiley-personal/issue/MIP-251/add-mip-embedding-adapter-package-for-uns-parity)

## Goal

Add a MIP-shaped adapter layer on top of AGSignal's generic host-application
boundary so the MIP integration pattern is concrete, testable, and reusable
without importing MIP or ATP code into AGSignal Core.

## Context

MIP's donor UNS implementation has integration hooks for governor approvals,
circuit breaker events, execution alerts, autonomy changes, and acknowledgment
callbacks. AGSignal already has the generic `AppSignalAdapter` boundary that
accepts app-owned evidence references and translates them into SDK sends.

MIP-251 fills the gap between those two layers: it provides a small optional
adapter with MIP-style method names and metadata conventions while keeping all
host domain behavior outside AGSignal.

## Design

Create `notification.integrations.mip_adapter` with:

- `MIPSignalAdapter`: a thin class that delegates to `AppSignalAdapter`.
- `MIPExecutionAlert`: typed alert input for execution alert migration.
- `MIPExecutionSummary`: typed summary input for execution alert metadata.
- helper functions for severity-to-intent and metric-to-notification-type mapping.

Expose the adapter through:

- `notification.integrations.__init__`
- `agsignal.integrations`

The adapter methods are synchronous because `AppSignalAdapter.send()` and
`NotificationSDK.send()` are synchronous today.

## Adapter Methods

| Method | Notification type | Intent | Source |
|---|---|---|---|
| `approval_required()` | `governance.approval_required` | GOVERNANCE | `agent_governor` |
| `contract_approved()` | `governance.approved` | GOVERNANCE | `agent_governor` |
| `contract_rejected()` | `governance.rejected` | GOVERNANCE | `agent_governor` |
| `autonomy_changed()` | `governance.autonomy_change` | GOVERNANCE | `agent_governor` |
| `circuit_breaker_engaged()` | `safety.circuit_breaker_engaged` | SAFETY | `circuit_breaker` |
| `circuit_breaker_recovered()` | `safety.circuit_breaker_recovered` | SAFETY | `circuit_breaker` |
| `execution_alert()` | metric-derived `execution.*` type | severity-derived | `execution_alerts` |

## Boundary Rules

- Do not import from MIP, ATP, or `src.services.*`.
- Do not own DecisionSnapshot, ExecutionSnapshot, SkipSnapshot, or trading data
  models.
- Carry host IDs through `AppEvidenceContext`, `AutonomyContext`, metadata,
  correlation IDs, and dedup keys.
- Keep channel routing policy-driven; producer methods may set intent,
  acknowledgement requirements, metadata, and irreversible flags.

## Tests

Tests should use a fake `AppSignalAdapter` that records `AppSignalRequest`
objects. They should assert the adapter builds the right request shape without
calling real delivery adapters.

## Donor Parity Checkpoint

MIP-251 is an adapter-template port, not a verbatim code port. The donor code
depends on MIP services, logging, runtime context, telemetry, database sessions,
and governor implementations that must remain outside AGSignal Core.

| Donor file | AGSignal mapping | Status |
|---|---|---|
| `src/notification/integrations/governor_hooks.py` | `MIPSignalAdapter.approval_required()`, `contract_approved()`, `contract_rejected()`, `autonomy_changed()` | Adapted |
| `src/notification/integrations/circuit_breaker_hooks.py` | `MIPSignalAdapter.circuit_breaker_engaged()`, `circuit_breaker_recovered()` | Adapted |
| `src/notification/integrations/execution_alerts.py` | `MIPSignalAdapter.execution_alert()`, `MIPExecutionAlert`, `MIPExecutionSummary` | Adapted |
| `src/notification/integrations/atp_context.py` | `AppSignalRequest.autonomy_context` plus `AppEvidenceContext`; host app resolves context | Excluded from Core |
| `src/notification/integrations/atp_callbacks.py` | Host-repo acknowledgment callback implementation; AGSignal carries metadata/evidence only | Excluded from Core |
| `src/notification/integrations/__init__.py` | `notification.integrations` and `agsignal.integrations` exports | Adapted |

### Ported

- MIP-style event names, source labels, notification type strings, metadata
  conventions, correlation IDs, and dedup key shapes.
- Governor approval, approval result, autonomy change, circuit breaker, and
  execution alert request construction.
- Severity-to-intent and metric-to-notification-type mapping for execution
  alerts.

### Adapted

- Donor async hook functions became synchronous adapter methods because
  `AppSignalAdapter.send()` and `NotificationSDK.send()` are synchronous today.
- Donor `get_atp_sdk()` factory became explicit dependency injection through an
  `AppSignalAdapter` instance.
- Donor runtime context lookup became explicit `AutonomyContext` and
  `AppEvidenceContext` input.

### Excluded

- MIP service imports such as `src.services.agent_governor_service`.
- ATP runtime context discovery from thread-local or request state.
- Acknowledgment side effects that update MIP audit records, telemetry,
  governor contracts, or learning services.
- Real channel delivery, queueing, and MIP database behavior.

### Remaining Host-Repo Validation

- Wire `MIPSignalAdapter` into the actual MIP host repo and confirm each donor
  hook call site can pass explicit context/evidence without importing AGSignal
  Core internals.
- Implement or adapt MIP-side acknowledgment callbacks if the host still needs
  ACK-driven governor/learning side effects.
- Run one end-to-end MIP host smoke for approval required, circuit breaker
  engaged, and execution alert flows.

## Acceptance Criteria

- MIP-shaped methods generate the expected `AppSignalRequest` values.
- Evidence IDs are carried through `AppEvidenceContext`.
- Circuit breaker engagement sets safety intent, irreversible flag, ack
  override, and stable dedup key.
- Execution alert severity mapping is documented and tested.
- Public aliases expose the adapter without breaking existing integration exports.

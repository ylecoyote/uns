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

## Acceptance Criteria

- MIP-shaped methods generate the expected `AppSignalRequest` values.
- Evidence IDs are carried through `AppEvidenceContext`.
- Circuit breaker engagement sets safety intent, irreversible flag, ack
  override, and stable dedup key.
- Execution alert severity mapping is documented and tested.
- Public aliases expose the adapter without breaking existing integration exports.


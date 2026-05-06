# MIP-253 Operational Parity Contract

Date: 2026-05-06

Status: Approved

Linear: [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)

## Goal

Define the runtime boundary between AGSignal Core and host applications for the
operational behavior inherited from MIP UNS.

## Decision

AGSignal Core ships reusable governance runtime contracts. It does not ship the
MIP worker topology as product behavior.

Core owns:

- notification and ACK state machines;
- delivery result and channel adapter interfaces;
- audit-store abstractions and audit record creation;
- channel health state;
- DLQ record visibility and removal;
- ACK timeout detection and callback hooks;
- examples and smoke guides for host integration.

Host applications own:

- queue backend selection;
- worker process lifecycle;
- retry cadence, retry limits, and replay safety;
- durable ACK storage binding;
- durable audit-store binding;
- Slack/PagerDuty/email credentials and deployment-specific adapters;
- escalation runbooks and operator authorization.

## Implemented In MIP-253

| Slice | Commit | Behavior |
|---|---|---|
| MIP-253A | `7365bef` | Standalone HTTP sends persist delivery audits through `AuditStore` |
| MIP-253B | `9bd192e` | ACK and dismiss routes persist ACK audit records when mounted with an `AuditStore` |
| MIP-253C | `8808705` | Host-scheduled ACK timeout checks can persist `TIMED_OUT` audits through `PersistentAcknowledgmentAuditCallback` |

## Donor Parity Matrix

| Donor behavior | AGSignal Core mapping | Status |
|---|---|---|
| RQ worker executes delivery jobs | `NotificationSDK` + `DeliveryService` contracts; host chooses scheduler | Adapted |
| Worker persists delivery audit | Standalone send route and `PersistentAuditLogger` write through `AuditStore` | Ported |
| ACK/DISMISS audit trail | Routes persist `AckAuditRecord` when audit store is configured | Ported |
| ACK timeout audit and escalation | `AcknowledgmentEngine.check_all_timeouts(...)`, `PersistentAcknowledgmentAuditCallback`, `EscalationHandler` | Ported/adapted |
| Channel health tracking | `ChannelHealthTracker` and `/api/v1/channels/health` | Ported/adapted |
| DLQ visibility | `/api/v1/dlq` plus `DLQService` | Ported/adapted |
| DLQ removal after remediation | `DELETE /api/v1/dlq/{entry_id}` | Ported |
| DLQ retry/replay | Excluded until retry context and idempotency guarantees are host-defined | Excluded |
| Bulk DLQ retry/clear and alert checks | Host runbook or future operations package | Excluded |
| MIP PostgreSQL schema and ATP imports | `AuditStore`, `PolicyStore`, and host adapters | Replaced |
| Slack interactivity webhook | Channel adapter or host app surface, not AGSignal Core | Excluded |

## DLQ Retry Decision

AGSignal Core should not implement DLQ retry yet.

Current `DLQEntry` records enough information for visibility and remediation:
notification id, type, intent, source, reason, created time, and metadata. It
does not preserve the full notification payload, resolved policy, delivery
attempt context, idempotency key, or adapter-specific retry metadata needed to
replay safely.

Retry is therefore a host-owned operation until AGSignal either:

1. introduces a durable notification read model that can reconstruct the exact
   original signal, or
2. defines a dedicated retry envelope with replay-safe payload, policy version,
   idempotency key, and adapter context.

MIP can implement host-owned retry sooner because it knows its worker backend,
database schema, and operational runbook.

## Worker Decision

AGSignal Core should not include a production worker daemon in M5.

The reusable contract is:

1. producers call `NotificationSDK` or the standalone HTTP route;
2. delivery execution uses `DeliveryService` and channel adapters;
3. delivery, ACK, dismiss, and timeout transitions write audit records through
   `AuditStore`;
4. host schedulers call `AcknowledgmentEngine.check_all_timeouts(...)`;
5. host retry workers may inspect DLQ entries and reconstruct signals through
   host-owned state.

MIP can wrap this with RQ or any later worker backend without making AGSignal
Core depend on that backend.

## Remaining Host-Repo Validation

- Bind MIP's durable audit table to AGSignal `AuditStore`.
- Bind MIP's durable ACK state to `AckStorageProtocol`.
- Configure `PersistentAcknowledgmentAuditCallback` for timeout audits.
- Decide whether MIP keeps RQ for `check_all_timeouts(...)` or moves to a
  different scheduler.
- Confirm Slack interactivity stays in MIP/channel-adapter space.

## Tests

MIP-253 behavior is covered by:

- standalone HTTP tests for delivery audit persistence;
- standalone HTTP tests for ACK and dismiss audit persistence;
- audit tests for timeout callback persistence;
- existing route tests proving no-audit-store MCP behavior remains compatible;
- docs cross-reference tests for the standing design notes.

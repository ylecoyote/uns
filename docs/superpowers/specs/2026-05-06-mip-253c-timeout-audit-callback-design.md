# MIP-253C Timeout Audit Callback Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)

## Goal

Close the reusable ACK-timeout audit gap without pulling a worker queue into
AGSignal Core.

## Runtime Decision

AGSignal Core owns the timeout state machine and audit callback. Host apps own
when and where timeout checks run.

The core engine already exposes `check_ack_timeout(...)` and
`check_all_timeouts(...)`. A host can call those from RQ, Celery, cron,
APScheduler, a background task, or an application-specific worker. AGSignal Core
should not choose that scheduler for every embedding.

## Scope

This slice covers:

- `PersistentAcknowledgmentAuditCallback`, an `AcknowledgmentCallback`
  implementation that persists ACK lifecycle state changes to `AuditStore`.
- Timeout audit persistence when a host runs `check_all_timeouts(...)`.
- Public package export for the callback.

This slice does not add a built-in scheduler, queue worker, retry runner, or
host-specific escalation adapter.

## Donor Parity Checkpoint

| Donor behavior | AGSignal mapping | Status |
|---|---|---|
| RQ worker checks ACK timeout jobs | Host calls `AcknowledgmentEngine.check_all_timeouts(...)` | Adapted |
| Timed-out ACKs become audit-visible | `PersistentAcknowledgmentAuditCallback` persists `TIMED_OUT` transition | Ported |
| SAFETY LIVE timeout escalation | Existing `EscalationHandler` hook remains core contract | Ported |
| Queue backend and scheduling cadence | Host-owned worker/runtime concern | Excluded |
| Retry/DLQ replay orchestration | Later MIP-253 slice after retry context decision | Excluded |

## Runtime Design

The callback persists from `on_status_change(...)` so it receives both the old
and new ACK status. It intentionally no-ops for `on_ack`, `on_dismiss`, and
`on_timeout`, which do not include the previous status.

When a host configures:

```python
configure_ack_engine(
    storage=durable_ack_storage,
    callback=PersistentAcknowledgmentAuditCallback(store=durable_audit_store),
)
```

any call to `check_all_timeouts(...)` records `PENDING -> TIMED_OUT` transitions.
The same callback can be used for ACK/DISMISS audit persistence in host-owned
routes, but the standalone HTTP routes currently persist ACK/DISMISS audits at
the route layer to preserve actor fields from request bodies.

## Tests

Tests assert:

- an expired pending notification processed by `check_all_timeouts(...)` writes
  one ACK audit;
- the audit records `PENDING -> TIMED_OUT`;
- timeout metadata is preserved.

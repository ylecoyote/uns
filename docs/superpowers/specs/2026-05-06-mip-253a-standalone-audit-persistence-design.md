# MIP-253A Standalone Audit Persistence Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)

## Goal

Close the first MIP-253 operational parity gap by making standalone HTTP sends
persist delivery audits through AGSignal's configured audit-store boundary.

## Runtime Decision

AGSignal Core should own the operational contract boundaries, not a full MIP
worker stack:

- Core owns: adapter interface, delivery result shape, audit-store persistence,
  channel-health state, acknowledgment timeout model, and DLQ record format.
- Host apps own: queue backend selection, worker lifecycle, retry scheduling,
  deployment runbooks, and host-specific Slack/PagerDuty/email wiring.
- AGSignal examples may provide host adapters, but MIP/ATP-specific runtime
  dependencies must stay outside Core.

This slice implements the audit persistence part of that contract.

## Scope

This slice covers:

- Persisting a delivery audit after `POST /api/v1/notifications` resolves the
  notification and delivery result.
- Reusing `create_app(audit_store=...)` from MIP-252B.
- Making the delivery-status route useful for notifications produced by the
  standalone HTTP route without manually seeding audit state.

This slice does not add queued worker execution, durable retry, DLQ replay, or
host adapter configuration.

## Donor Parity Checkpoint

| Donor behavior | AGSignal mapping | Status |
|---|---|---|
| Worker persists notification audit after delivery | Standalone HTTP route saves a delivery audit through `AuditStore` | Ported |
| Audit includes delivery status and channel outcomes | Existing `create_audit_record(notification, result, ...)` | Ported |
| MIP PostgreSQL audit model and retry counts | Existing AGSignal `AuditStore` abstraction, DB implementation optional | Adapted |
| RQ worker retry semantics | Host-owned runtime contract, later slice if needed | Excluded |
| Ack-timeout queue scheduling | Existing ACK timeout model; durable scheduling decision deferred | Excluded |
| DLQ retry/replay | MIP-253 later slice after retry context decision | Excluded |

## Runtime Design

The standalone send route already resolves a `Notification` and
`NotificationResult`. After ACK registration, it checks `app.state.audit_store`.
When the store implements `AuditStore`, the route saves a delivery audit with
`runtime=standalone_http` metadata.

If audit persistence raises `AuditPersistenceError`, the route returns
`audit_persistence_failed` with HTTP 503. This keeps the production-oriented
contract honest: a governance signal should not appear accepted when the audit
trail cannot be written.

Idempotent replay does not write another audit record because the replay path
returns the cached response before resolving or delivering a new notification.

## Tests

Tests assert:

- sending through the standalone HTTP route persists a delivery audit;
- `GET /api/v1/notifications/{notification_id}/delivery` can read that audit
  without manual seeding;
- existing standalone send, simulation, delivery-status, DLQ, policy reload, and
  WebSocket behavior remains green.

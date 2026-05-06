# MIP-253B ACK Audit Persistence Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-253](https://linear.app/awiley-personal/issue/MIP-253/decide-and-implement-workeradapterauditdlq-operational-parity)

## Goal

Extend the MIP-253 audit contract so ACK and dismiss actions write audit records
when the host app provides an AGSignal `AuditStore`.

## Scope

This slice covers:

- Persisting ACK audits from `POST /api/v1/notifications/{notification_id}/ack`
  when that shared route is mounted by the standalone AGSignal app.
- Persisting DISMISSED audits from
  `POST /api/v1/notifications/{notification_id}/dismiss`.
- Preserving existing MCP route behavior when no audit store is configured.

This slice does not add durable ACK timeout scheduling or host-specific operator
identity enforcement.

## Donor Parity Checkpoint

| Donor behavior | AGSignal mapping | Status |
|---|---|---|
| ACK/DISMISS events are audit-visible | Shared routes save `AckAuditRecord` through configured `AuditStore` | Ported |
| Audit record tracks old/new ACK status | Existing `create_ack_audit_record(...)` | Ported |
| MIP DB-backed audit table | Existing AGSignal `AuditStore`; DB binding remains optional | Adapted |
| Durable ACK timeout queue | Later operational slice or host-owned worker | Excluded |
| Operator identity/authorization policy | Host-app concern outside AGSignal Core | Excluded |

## Runtime Design

The shared ACK routes now accept `Request` so they can inspect
`request.app.state.audit_store`. If the app does not configure an `AuditStore`,
the routes behave as before.

When an ACK or dismiss request changes state, the route saves an `AckAuditRecord`
with the previous status, new status, actor, timestamp, and metadata. Idempotent
requests where old and new status already match do not write another state-change
audit.

If audit persistence fails, the route returns `ack_audit_persistence_failed`
with HTTP 503. The ACK state may already have changed, so durable deployments
should use a reliable audit store.

## Tests

Tests assert:

- ACK through the standalone-mounted route persists one ACK audit;
- dismiss through the standalone-mounted route persists one ACK audit;
- existing MCP route behavior remains green when no audit store is configured.

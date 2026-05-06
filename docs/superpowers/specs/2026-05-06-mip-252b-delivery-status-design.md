# MIP-252B Delivery Status Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)

## Goal

Close the next safe MIP UNS HTTP parity slice by exposing per-notification
delivery status from AGSignal's existing audit-store boundary.

## Scope

This slice covers:

- `GET /api/v1/notifications/{notification_id}/delivery`.
- Optional audit-store injection into the standalone AGSignal app.
- A latest-status response with channel results and persisted audit history.
- A deterministic 404 when no delivery audit exists for the notification.

This slice does not add global notification listing, automatic send-route audit
persistence, invalidation, or DLQ retry/admin mutations.

## Donor Parity Checkpoint

| Donor route behavior | AGSignal mapping | Status |
|---|---|---|
| Per-notification delivery readback | `GET /api/v1/notifications/{notification_id}/delivery` | Ported |
| Delivery status derived from persisted audit records | Existing `AuditStore.get_delivery_audits_for_notification` boundary | Adapted |
| Full notification list with filters/pagination | Excluded until AGSignal has a durable notification read model | Excluded |
| MIP DB/job identifiers and retry metadata | Excluded from AGSignal Core response shape | Excluded |
| Automatic send-route audit persistence | Later MIP-253 operational parity slice | Excluded |

## Runtime Design

`create_app()` accepts an optional `AuditStore`. When no store is provided, the
standalone app uses `InMemoryAuditStore` so the route exists in local operation
without requiring host infrastructure.

The route reads delivery audits by notification id. If audits exist, the newest
record is summarized as the current delivery status and the full audit list is
returned newest first. If no audit exists, the route returns
`delivery_audit_not_found`.

## Tests

Tests assert:

- a seeded `InMemoryAuditStore` produces delivery status readback with channel
  outcomes and audit history;
- an unknown notification id returns `delivery_audit_not_found`;
- existing standalone HTTP routes still pass with the new default audit store.

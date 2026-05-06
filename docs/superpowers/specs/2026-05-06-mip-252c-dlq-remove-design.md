# MIP-252C DLQ Remove Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)

## Goal

Close a safe DLQ admin parity slice by exposing entry removal for visible
dead-lettered notifications.

## Scope

This slice covers:

- `DELETE /api/v1/dlq/{entry_id}`.
- Removal through the existing `DLQService.remove()` boundary.
- A 404 response when the entry is not present.

This slice does not add DLQ retry, bulk clear, alerting thresholds, or automatic
replay. Those require operational decisions covered by MIP-253.

## Donor Parity Checkpoint

| Donor route behavior | AGSignal mapping | Status |
|---|---|---|
| DLQ admin removal | `DELETE /api/v1/dlq/{entry_id}` | Ported |
| DLQ storage abstraction | Existing Redis-list compatible `DLQService` | Adapted |
| DLQ retry/replay | Excluded until AGSignal stores enough delivery context to retry safely | Excluded |
| DLQ bulk clear/depth alerts | MIP-253 operational parity | Excluded |
| Notification invalidation | Excluded from this slice because AGSignal has no native `INVALIDATED` lifecycle state | Excluded |

## Runtime Design

The route calls the configured app `DLQService`. Successful removal returns the
removed entry id, `removed=true`, and the remaining DLQ depth. Missing entries
return `dlq_entry_not_found`.

Invalidation is intentionally not implemented here. The donor UNS behavior
requires canceling pending acknowledgments and preserving audit history with an
`INVALIDATED` state. AGSignal currently models acknowledgment terminal states as
`ACKED`, `DISMISSED`, and `TIMED_OUT`; mapping invalidation to `DISMISSED` would
lose producer intent and pollute human-feedback semantics.

## Tests

Tests assert:

- a seeded DLQ entry can be removed through the HTTP route;
- removed entries are no longer listed by the service;
- unknown entries return `dlq_entry_not_found`.

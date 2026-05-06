# MIP-252A HTTP Idempotency and Simulation Design

Date: 2026-05-06

Status: Approved

Linear: [MIP-252](https://linear.app/awiley-personal/issue/MIP-252/close-agsignal-httpadmin-api-parity-gaps-with-mip-uns)

## Goal

Close the first safe slice of MIP UNS HTTP parity by adding producer
`idempotency_key` support and a richer simulation response to the standalone
AGSignal HTTP app.

## Scope

This slice covers:

- `idempotency_key` on `POST /api/v1/notifications`.
- Idempotent retries returning the original notification id instead of creating
  a new notification.
- A richer `POST /api/v1/notifications/simulate` response that exposes resolved
  delivery mode, channels, ACK requirement, dedup key/window, policy source, and
  warnings.

This slice does not cover notification list/detail/delivery status,
invalidation, or DLQ admin parity. Those remain later MIP-252/MIP-253 slices.

## Donor Parity Checkpoint

| Donor route behavior | AGSignal mapping | Status |
|---|---|---|
| `SendNotificationRequest.idempotency_key` | Add optional `idempotency_key` to AGSignal send request | Ported |
| Producer retry safety by `source + idempotency_key` | App-local HTTP idempotency cache for standalone runtime | Adapted |
| Rich `/simulate` result with routing and warnings | Expanded `SimulateNotificationResponse` | Adapted |
| Queued job id replay | Excluded because current standalone AGSignal route is synchronous and returns notification id only | Excluded |
| Notification list/detail/delivery status | Later slice | Excluded |
| Invalidate endpoint | Later slice | Excluded |
| DLQ retry/depth/clear/admin operations | Later MIP-252/MIP-253 slice | Excluded |

## Runtime Design

The standalone app stores HTTP idempotency records in `app.state` by
`source:idempotency_key`. This is intentionally scoped to the current in-process
standalone runtime. A durable Redis/DB-backed variant belongs with the broader
operational parity work.

The first request is processed normally and the response is cached. A retry with
the same producer source and idempotency key returns the cached response with
`idempotent_replay=true`.

Simulation continues to use the SDK capture path, but returns more of the
resolved notification state so producers can understand what would happen.

## Tests

Tests assert:

- repeated sends with the same source and idempotency key return the same
  notification id and mark the retry as idempotent;
- idempotency is scoped by source;
- simulation includes resolved delivery mode, dedup key, dedup window, policy
  source, and warnings.


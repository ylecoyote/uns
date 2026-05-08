# Post-v0.2 Architectural Followups

**Purpose:** Track architectural-debt items that surface during the v0.2
cleanup but cannot be absorbed into Phases 1-5 without scope creep. Each
item below is real, has a known cause, and should be picked up after
Phase 5 ships.

This file is appended to as new items surface; do not delete entries
until they are resolved. Resolved entries move to a "Done" section at
the bottom with the resolving commit SHA.

---

## Open

### F-1. Unify the accept-only and dispatch send paths; wire DLQ-on-send-failure

**Surfaced during:** Phase 3 Task 8 (2026-05-08).

**Observation:** `agsignal.signaling.send_signal` (the canonical
service-layer write function established in Phase 2) does not perform
actual channel delivery. It uses
`NotificationSDK(delivery_handler=_capture_delivery)` where the handler
always returns `NotificationResult(status=DeliveryStatus.SUCCESS,
channels_succeeded=[], channels_failed=[])`. The function only accepts,
registers with the ack engine, and persists the delivery audit row.

The actual channel dispatch (Slack, PagerDuty, email) and
DLQ-on-failure wiring live in the legacy
`notification.service.dispatch_notification` path
(`src/notification/service.py:335-336`).

**Why this is debt:** the new service layer's name (`send_signal`)
implies it sends. The legacy path's name (`dispatch_notification`) is
internal. External callers reach for `agsignal.signaling.send_signal`
expecting full delivery; they get accept-only behavior. The transport
surface (HTTP `/api/v1/notifications/send`, MCP `send_signal` tool)
papers over this — those routes/tools today only need accept-only — but
when a caller wants delivery confirmation, they'll be surprised.

**Fix shape (when picked up):**

1. Decide whether to unify in-place (move `dispatch_notification`
   logic into `agsignal.signaling.send_signal`) or to keep the layered
   shape (have `send_signal` call into `dispatch_notification` with the
   right channel and DLQ wiring threaded through).
2. Re-introduce the `dlq_service` parameter on `send_signal` with real
   behavior: on `GUARANTEED`-mode delivery failure, push to DLQ.
3. Add a `delivery_handler` parameter so callers can opt out of channel
   dispatch (the simulate path needs this).
4. Update the existing `tests/agsignal/test_signaling.py` to cover
   delivery-failure → DLQ-push, mirroring the legacy
   `tests/notification/test_service.py` coverage.
5. Update the HTTP route and MCP tool to thread `dlq_service` through.
6. Delete `notification.service.send_signal_v2` once the new path
   covers everything.

**Estimated effort:** 1 week for a focused engineer. **Risk:** medium —
this is a behavior change for any consumer that today gets accept-only
back; consumers may have grown to expect that. Audit consumer
expectations before merging.

**Pre-req:** v0.2 Phase 5 (`notification/` reshape) — that phase moves
delivery code into a stable home, making this unification land cleanly.

---

### F-2. `list_invariants` swallows broad `Exception` and silently returns empty; transport-coupled error reporting

**Surfaced during:** Phase 3 final review (2026-05-08).

**Observation:** `agsignal.queries.list_invariants` at
`src/agsignal/queries.py:571-591` catches `Exception` and falls through
to an empty `InvariantListResponse(items=[], ...)` response with HTTP
status 200, after recording an error metric against the
`/ui/invariants` endpoint string.

Two problems:

1. **Silent failure on malformed input.** A malformed `invariants.yml`,
   a `pydantic.ValidationError`, or any other exception during invariant
   loading returns an empty dashboard with no operator-visible signal.
   Pre-Phase-3 the legacy route had the same behavior (Phase 3 verbatim-
   relocated the function), so this is not a Phase 3 regression — but
   Phase 3 made `list_invariants` the canonical implementation that the
   MCP tool also calls. Silent failure on the MCP transport is worse
   than on HTTP because there's no observability middleware to record
   the failure.

2. **Transport coupling.** The hard-coded `endpoint="/ui/invariants"`
   string in the service layer leaks HTTP-route detail into a function
   that two transports call. The MCP tool's `list_invariants` records
   errors against the `/ui/invariants` HTTP endpoint string, which is
   misleading.

**Fix shape (when picked up):**

1. Decide on the failure-mode contract: should `list_invariants` raise
   a typed domain error (e.g., `InvariantsLoadError`) that the route
   layer translates to a 5xx, or continue to return empty with a
   structured warning the caller can detect?
2. If raising a typed error, drop the `record_endpoint_error` call
   from the service layer and let the route adapter record the metric
   with its actual endpoint string. The MCP transport records its own
   way.
3. If keeping the empty fallback, surface a structured warning in the
   response (e.g., a `loader_status` field) so consumers can
   distinguish "no invariants configured" from "loader failed."
4. The trailing `else: logger.warning("Invariants file not found")`
   branch (`queries.py:566-591`) flows past the `try`/`except` and
   hits the empty fallback — the logic flow is non-obvious. Either
   return from the `else` branch directly or hoist the empty response
   above the `if`.

**Estimated effort:** half a day. **Risk:** low — this is an
error-path behavior change. **Pre-req:** none; can land any time
post-v0.2.

---

## Done

(none yet)

# TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay

## 1. Symptoms & Alerts
- `GET /readyz` reports `"dlq_depth": N` where $N > 0$.
- `GET /api/v1/runtime/dead-letters` (or MCP `list_dlq`) returns one or more notifications with `"status": "FAILED"` and `"dead_letter": true`.
- Downstream operators or alerts report that a `GUARANTEED` notification (`SAFETY` or `GOVERNANCE`) failed all configured fallback channels across all `max_attempts` (default `3`).

---

## 2. Root Cause & Component Mechanics

In `src/uns/runtime.py`, when a `GUARANTEED` leader notification fails delivery on all configured fallback channels (`Slack` $\rightarrow$ `Email` $\rightarrow$ `PagerDuty`) and `cycle_attempts >= max_attempts`:
1. The row in `uns_notifications` is updated to `status = "FAILED"`, `dead_letter = True`.
2. A `DELIVERY_RESULT` event is appended to `uns_events` with `"dead_letter": true` and the per-channel error map in `outcome`.
3. `Runtime._settle_followers(session, row, succeeded=False)` promotes the first pending follower (`DEDUP_OWNER_PROMOTED`) to become the new leader (`dedup_owner_id = NULL`, `dedup_generation + 1`) and records `dedup_successor_id` + an `OBLIGATION_HANDED_OFF` event on the failed leader so that coalesced obligations get their own retry budget and durable successor lineage is preserved.

---

## 3. Diagnostic Commands

### Step 3.1: List all active dead-letter entries (including replay blockers)
```sh
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/api/v1/runtime/dead-letters" | jq .
```
Each entry includes:
- `notification_id`, `status`, `attempts`, `cycle`, `cycle_attempts`, `outcome`
- `replay_blocked_by`: UUID of the successor or active owner blocking replay (`null` if unblocked)
- `replay_block_reason`: `"PENDING"`, `"DELIVERED"`, `"DEDUPLICATED"`, or `"UNRESOLVED_LINEAGE"` (`null` if unblocked)

### Step 3.2: Inspect the full state and event timeline of a dead-lettered notification
```sh
NOTIF_ID="<notification_id>"
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID" | jq .
```

Examine:
- `outcome.channels_failed` and `outcome.error_message` to identify the failing provider (e.g., invalid `UNS_SLACK_BOT_TOKEN`, unreachable `UNS_SMTP_HOST`, or `5xx` from PagerDuty).
- `events` array:
  - Check for `CHANNEL_ATTEMPT_RESULT` or `LEASE_LOST` events after `CHANNEL_ATTEMPT_STARTED` (see [TSG-02](TSG-02-LEASES-AND-PROVIDER-EFFECTS.md)).
  - Check whether `OBLIGATION_HANDED_OFF` or `DEDUP_OWNER_PROMOTED` transferred the obligation to a successor.

### Step 3.3: Inspect deduplication lineage in SQLite
```sh
sqlite3 "$UNS_DB_FILE" "
  SELECT id, status, dead_letter, cycle, attempts, dedup_owner_id, dedup_generation, dedup_successor_id, delivered_at
  FROM uns_notifications
  WHERE dedup_key = (SELECT dedup_key FROM uns_notifications WHERE id = '$NOTIF_ID')
  ORDER BY next_attempt ASC;
"
```

---

## 4. Safe Remediation Steps

### Scenario A: External provider issue is resolved AND `replay_blocked_by` is `null`
If the downstream channel (Slack/SMTP/PagerDuty) has been restored and `replay_blocked_by` is `null` (meaning either there was no successor or the entire successor chain also exhausted and failed), trigger an attributable replay:

```sh
curl -sS -X POST -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID/replay" | jq .
```
- **Effect:** Sets `status = "PENDING"`, `dead_letter = False`, increments `cycle = cycle + 1`, resets `cycle_attempts = 0` (preserving cumulative `attempts`), reassigns any failed successor lineage to this replayed owner, and records a `REPLAY_REQUESTED` event attributed to `UNS_API_PRINCIPAL`.
- The background worker (`runtime.worker()`) will claim and dispatch the notification within ~1 second.

### Scenario B: `replay_blocked_by` is non-null (`DELIVERED`, `DEDUPLICATED`, `PENDING`, or `UNRESOLVED_LINEAGE`)
If a promoted follower (`DEDUP_OWNER_PROMOTED`) or current owner is `PENDING` or already `DELIVERED`, `POST /api/v1/runtime/notifications/{id}/replay` automatically raises `409 Conflict` to prevent duplicate delivery. Once the obligation is satisfied (or resolved out-of-band), clear the dead-letter flag via `DELETE /api/v1/dlq/{entry_id}` (where in canonical `uns.Runtime` / `RuntimeDLQ` mode, `entry_id === notification_id`, whereas in legacy non-runtime `DLQService` fixtures, `entry_id` is the DLQ entry UUID from `GET /api/v1/dlq`):

```sh
ENTRY_ID="$NOTIF_ID" # In RuntimeDLQ, entry_id === notification_id
curl -sS -X DELETE -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/api/v1/dlq/$ENTRY_ID" | jq .
```
- **Effect:** Invokes `Runtime.resolve_failure`, setting `dead_letter = False` while keeping `status = "FAILED"` and recording a `FAILURE_RESOLVED` audit event with the operator's principal.

---

## 5. Runtime Guardrails (`F-01` & `F-02` Disposition)

> [!NOTE]
> **Guarded Replay & Durable Successor Lineage (`F-02`):**
> `Runtime.replay()` enforces atomic lineage verification (`_replay_blocker` in `src/uns/runtime.py`). If a successor in `dedup_successor_id` (or the current `uns_dedup` owner) is `PENDING`, `DELIVERED`, `DEDUPLICATED`, or has `UNRESOLVED_LINEAGE` (such as a missing/cyclic migration target), `replay()` rejects the call with `409 Conflict`. There is no force-send bypass.

> [!NOTE]
> **Pending Ownership Across Deduplication TTL (`F-01`):**
> Pending owner exclusivity survives `uns_dedup.until` expiration: incoming identical notifications continue to coalesce behind an in-flight `PENDING` owner rather than electing a competing parallel owner. Follower promotion transfers ownership of the existing window without resetting `uns_dedup.until`.

## Related Documentation

- [TSG-02: Expired Worker Leases & Uncertain Provider Effects](TSG-02-LEASES-AND-PROVIDER-EFFECTS.md)
- [Support Reference: State Machines & Schema](../support/STATE-MACHINE-AND-SCHEMA.md)
- [Delivery Semantics](../sections/delivery-semantics.md)

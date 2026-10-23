# TSG-03: Acknowledgment Timeouts, Escalations, & Callback Failures

## 1. Symptoms & Alerts
- An operator or agent attempts `POST /api/v1/notifications/{id}/ack` (or `/dismiss`) and receives `409 Conflict` (`"Notification is not awaiting this response or its deadline elapsed"` or `"Terminal response belongs to another actor"`).
- Notifications with `require_ack: true` transition to `ack_status: "TIMED_OUT"` with `actor: "uns-timeout-worker"`.
- Downstream systems registered via `Runtime(..., callback=...)` stop receiving terminal `ACKED`, `DISMISSED`, or `TIMED_OUT` events, or `uns_events` rows show `callback_pending = 1` and `callback_error IS NOT NULL`.

---

## 2. Root Cause & Component Mechanics

### 2.1 Acknowledgment Deadline & Timeout Sweep (`Runtime.expire`)
1. When a notification with `require_ack = true` reaches `status = "DELIVERED"`, `Runtime.dispatch()` sets:
   - `ack_status = "PENDING"`
   - `deadline = delivered_at + 60 * (ack_timeout_minutes or 15)` (default `15` minutes for `SAFETY`, `30` minutes for `GOVERNANCE`).
2. Every 1 second, `Runtime.worker()` runs `timeout_loop()`, which calls `Runtime.expire()` (`src/uns/runtime.py`).
3. Up to 100 rows ordered by `(deadline, id)` with `ack_status == "PENDING"` and `deadline <= now` are atomically updated to:
   - `ack_status = "TIMED_OUT"`
   - `actor = "uns-timeout-worker"`
   - `response_metadata = {"escalation_required": True}`
4. Once `ack_status` transitions out of `"PENDING"`, terminal state is immutable: subsequent `acknowledge` or `dismiss` calls fail with `409 Conflict` (unless the exact same `actor` repeats the exact same terminal state).

### 2.2 Terminal Event Callback Delivery (`Runtime.deliver_callbacks`)
When `Runtime(..., callback=...)` is configured in embedded Python mode:
1. Terminal transitions (`ACKED`, `DISMISSED`, `TIMED_OUT`) insert an `uns_events` row with `callback_pending = True` and `callback_until = self.clock()`.
2. `callback_loop()` calls `Runtime.deliver_callbacks()` (`src/uns/runtime.py`) every 1 second.
3. It selects up to 100 rows where `callback_pending == True`, `callback_until <= now`, and `callback_attempts < 3`, ordered by `(callback_until, at, id)` via `ix_uns_callbacks`.
4. Each callback is claimed under a 30-second lease (`callback_token`) and awaited (`await asyncio.wait_for(self.callback(event), timeout=10)`). On failure, `callback_error` is recorded and `callback_until` is backed off by `2 ** callback_attempts` seconds. After 3 failed attempts (`callback_attempts == 3`), the callback is no longer retried automatically.

---

## 3. Diagnostic Commands

### Step 3.1: Inspect ACK state, deadline, and actor via HTTP
```sh
NOTIF_ID="<notification_id>"
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID" \
  | jq '{id, status, ack_status, actor, delivered_at, deadline, responded_at, response_metadata}'
```

### Step 3.2: Inspect stuck or exhausted callbacks in SQLite
```sh
sqlite3 "$UNS_DB_FILE" "
  SELECT id, notification_id, kind, at, callback_pending, callback_attempts, callback_until, callback_error
  FROM uns_events
  WHERE callback_pending = 1 OR callback_error IS NOT NULL
  ORDER BY callback_until ASC, at ASC
  LIMIT 50;
"
```

---

## 4. Safe Remediation Steps

### Scenario A: Operator received `409 Conflict` when acknowledging
1. Run Step 3.1 to check `ack_status` and `actor`:
   - **`ack_status: "TIMED_OUT"` (`actor: "uns-timeout-worker"`):** The `ack_timeout_minutes` window elapsed before the operator responded. Because `TIMED_OUT` is a terminal audit record, the expired notification cannot be retroactively changed to `ACKED`. If an active policy requires a longer response window, update `ack_timeout_minutes` in the YAML policy and reload via `POST /api/v1/policies/reload`.
   - **`ack_status: "ACKED"` or `"DISMISSED"` by another `actor`:** Another principal already settled the notification.
   - **`status: "PENDING"` and `ack_status: null`:** The notification has not yet been delivered (`DELIVERED`). Acknowledgment is only valid after `status` reaches `DELIVERED`.

### Scenario B: Operator received `403 Forbidden` (`principal_override_forbidden`)
- When calling `POST /api/v1/notifications/{id}/ack` or `/dismiss`, either omit `acked_by` / `dismissed_by` from the JSON body or set it to the exact value of `UNS_API_PRINCIPAL`. Supplying any other string returns `403 Forbidden`.

### Scenario C: Re-enabling exhausted callbacks (`callback_attempts >= 3`)
If an external callback endpoint was down and `uns_events` rows reached `callback_attempts = 3` (with `callback_pending = 1`), reset their attempt counter in SQLite after restoring the callback receiver:

```sh
sqlite3 "$UNS_DB_FILE" "
  UPDATE uns_events
  SET callback_attempts = 0,
      callback_until = at,
      callback_token = NULL
  WHERE callback_pending = 1 AND callback_attempts >= 3;
"
```

---

## 5. Runtime Guardrails (`F-06` Disposition)

> [!NOTE]
> **Due-Time Ordering & Retry Backoff (`F-06`):**
> `deliver_callbacks()` orders batches by `(callback_until, at, id)` and initializes `callback_until` to the event timestamp (`self.clock()`), ensuring backed-off retries do not starve newly due callbacks behind older failed events. Because each claimed callback allows up to a `10s` timeout inside the batch loop, keep custom `Runtime.callback` handlers fast and idempotent by `event["id"]`.

## Related Documentation

- [Support Reference: State Machines & Schema](../support/STATE-MACHINE-AND-SCHEMA.md)
- [API Reference](../API.md)

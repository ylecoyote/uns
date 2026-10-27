# TSG-02: Expired Worker Leases & Uncertain Provider Effects

## 1. Symptoms & Alerts
- Downstream recipients report receiving duplicate emails, Slack messages, or PagerDuty incidents for a single `notification_id`.
- `GET /api/v1/runtime/notifications/{id}` shows `"kind": "CHANNEL_ATTEMPT_STARTED"`, optionally `"kind": "CHANNEL_ATTEMPT_RESULT"`, and `"kind": "LEASE_LOST"` with `"provider_effect_may_have_occurred": true`.
- An email attempt records `metadata.provider_outcome = "UNKNOWN"` on timeout, or a notification ultimately fails with `"error_message": "Provider outcome unknown: recovery exhausted the attempt budget"`.

---

## 2. Root Cause & Component Mechanics

`uns.Runtime` executes external network calls outside database transactions under a fenced 60-second lease (`self.lease_seconds = 60.0` in `src/uns/runtime.py`):

1. **Lease Acquisition (`dispatch`):** Worker 1 claims a `PENDING` leader row by setting `lease_token = <uuid>` and `lease_until = now + 60.0`, incrementing `attempts` and `cycle_attempts`, and recording `ATTEMPT_STARTED`.
2. **Pre-Channel Fence (`_before_attempt`):** Immediately before invoking each channel adapter, Worker 1 verifies `lease_token` and `lease_until > now`, then commits `CHANNEL_ATTEMPT_STARTED` with `"provider_effect_may_have_occurred": true`.
3. **Append-Only Per-Channel Observation (`_channel_result` / `F-03`):**
   - As soon as a channel adapter returns a `DeliveryResult`, `Runtime._channel_result()` persists an append-only `CHANNEL_ATTEMPT_RESULT` event attributed to the worker's `lease_token` (`channel`, `success`, `message_id`, `error`, `metadata`).
   - Even if Worker 1's lease expired while the channel call was in flight, `CHANNEL_ATTEMPT_RESULT` is preserved in `uns_events` without overwriting a replacement worker's aggregate state.
4. **SMTP Deadline & Ambiguous Timeout Handling (`F-04a` & `F-04b`):**
   - `EmailAdapter` checks lease validity before SMTP send preparation without emitting a duplicate start event (`check_lease`), budgets socket timeouts against the remaining deadline, and does **not** locally retry an ambiguous post-admission SMTP timeout (recording `provider_outcome: "UNKNOWN"` instead).
   - When Worker 1 tries to commit final aggregate settlement after `lease_until <= now`, the fencing check fails and records `LEASE_LOST`.

---

## 3. Diagnostic Commands

### Step 3.1: Inspect the notification's event sequence
```sh
NOTIF_ID="<notification_id>"
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID" \
  | jq '.events[] | {at, kind, payload}'
```

Look for `CHANNEL_ATTEMPT_STARTED`, `CHANNEL_ATTEMPT_RESULT`, and `LEASE_LOST` events:
```json
{
  "at": 1761192000.1,
  "kind": "CHANNEL_ATTEMPT_STARTED",
  "payload": {
    "attempt": 1,
    "channel": "EMAIL",
    "cycle": 1,
    "cycle_attempt": 1,
    "lease_token": "...",
    "provider_effect_may_have_occurred": true
  }
}
{
  "at": 1761192060.5,
  "kind": "CHANNEL_ATTEMPT_RESULT",
  "payload": {
    "attempt": 1,
    "channel": "EMAIL",
    "cycle": 1,
    "cycle_attempt": 1,
    "lease_token": "...",
    "message_id": "email-...",
    "success": true
  }
}
{
  "at": 1761192060.6,
  "kind": "LEASE_LOST",
  "payload": {
    "attempt": 1,
    "lease_token": "...",
    "provider_effect_may_have_occurred": true
  }
}
```

### Step 3.2: Find all notifications with `LEASE_LOST` or `CHANNEL_ATTEMPT_RESULT` events in SQLite
```sh
sqlite3 "$UNS_DB_FILE" "
  SELECT n.id, n.status, n.dead_letter, n.attempts, n.cycle, e.kind, e.at, e.payload
  FROM uns_events e
  JOIN uns_notifications n ON n.id = e.notification_id
  WHERE e.kind IN ('LEASE_LOST', 'CHANNEL_ATTEMPT_RESULT')
  ORDER BY e.at DESC
  LIMIT 25;
"
```

---

## 4. Safe Remediation Steps

### Step 4.1: When a notification with `LEASE_LOST` lands in the DLQ
1. **Inspect `CHANNEL_ATTEMPT_RESULT` events and provider logs first** before calling `/replay` (3-way decision branch):
   - **Branch 1 (`"success": true` with `message_id`):** The external provider accepted the message even though the worker lost its lease before aggregate settlement. Do **not** replay — resolve the DLQ entry via `DELETE /api/v1/dlq/$ENTRY_ID`:
     ```sh
     ENTRY_ID="$NOTIF_ID" # In RuntimeDLQ, entry_id === notification_id
     curl -sS -X DELETE -H "Authorization: Bearer $UNS_API_KEY" \
       "$UNS_BASE_URL/api/v1/dlq/$ENTRY_ID"
     ```
   - **Branch 2 (`metadata.provider_outcome == "UNKNOWN"`):** An in-flight SMTP operation timed out after admission (`success` is `false`) and may or may not have completed at the relay. **Verify out-of-band first** (inspect SMTP relay logs or recipient mailbox) before choosing **Resolve** (if the email arrived) vs. **Replay** (if the message was dropped; replaying without verification risks duplicate email delivery).
   - **Branch 3 (`"success": false` and `provider_outcome != "UNKNOWN"`):** The provider rejected or dropped the connection before acceptance. Fix the underlying network/provider latency issue, then trigger replay via `POST /api/v1/runtime/notifications/$NOTIF_ID/replay`.

### Step 4.2: Mitigating Slow SMTP / Provider Calls
- Ensure your SMTP relay (`UNS_SMTP_HOST`) is local or low-latency so that connection + `STARTTLS` + `login` + `sendmail` completes well under `lease_seconds` (`60.0s`).
- Avoid running redundant external worker processes against the same SQLite database unless required; the unified `uns` server already runs `runtime.worker()` in-process.

---

## 5. Runtime Guardrails (`F-03`, `F-04a`, & `F-04b` Disposition)

> [!IMPORTANT]
> **Why `LEASE_LOST` Cannot Roll Back External Side Effects:**
> External providers (SMTP, Slack Web API, PagerDuty) do not participate in two-phase commit with SQLite. `uns.Runtime` guarantees **at-least-once** channel execution under lease failure while preserving late worker observations in `CHANNEL_ATTEMPT_RESULT` (`F-03`) and preventing internal adapter retry of ambiguous post-admission SMTP timeouts (`F-04b`).

## Related Documentation

- [TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay](TSG-01-DLQ-AND-REPLAY.md)
- [Support Reference: State Machines & Schema](../support/STATE-MACHINE-AND-SCHEMA.md)

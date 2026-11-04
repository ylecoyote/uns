# TSG-06: Database Maintenance, Retention, & Archive Recovery

## 1. Symptoms & Alerts
- Running `uns-maintain --apply --archive /path/to/archive.json` fails with `FileExistsError: [Errno 17] File exists`.
- `uns-maintain` output reports non-empty `"oversized_notification_ids": [...]` and leaves those notifications in the database.
- An operator runs `uns-maintain --apply` (without `--archive`) expecting the SQLite database file size on disk or row counts in `uns_events` / `notification_audit_records` to shrink, and observes that audit/event rows remain and a `RETENTION_APPLIED` receipt is inserted.
- Live HTTP requests experience brief write latency during `uns-maintain --apply`.

---

## 2. Root Cause & Component Mechanics

Implemented in `src/uns/maintenance.py`:

1. **Eligibility Rules (`_eligible`):**
   A notification is eligible for retention only when ALL of the following hold:
   - `effective_cutoff = min(cutoff, now - idempotency_seconds)`
   - `status IN ('DELIVERED', 'SUCCESS', 'DEDUPLICATED', 'FAILED')`
   - `ack_status IS NULL OR ack_status IN ('ACKED', 'DISMISSED', 'TIMED_OUT')`
   - `dead_letter == False`, `lease_token IS NULL`, and `lease_until <= now`
   - `next_attempt < effective_cutoff`, `delivered_at < effective_cutoff`, and `responded_at < effective_cutoff`
   - At least one `uns_events` row exists for the notification, and **no** `uns_events`, `notification_audit_records`, or `ack_audit_records` row has a timestamp $\ge$ `effective_cutoff` (with naive SQLite UTC datetimes normalized to UTC, `F-08b`)
   - No `uns_events` row has `callback_pending = True`, `callback_token IS NOT NULL`, or `callback_until > now`
   - The notification is not an active `uns_dedup` owner and has no retained followers (`dedup_owner_id`) or predecessors (`dedup_successor_id`) referencing it.

2. **Two Operating Modes (`--archive` vs. Non-Archive):**
   - **Without `--archive` (Operational-Record Expiration Only, `F-08a` by design):**
     - Deletes eligible rows from `uns_notifications` and expired ownerless rows from `uns_dedup`.
     - **Preserves** all rows in `uns_events`, `notification_audit_records`, and `ack_audit_records`.
     - Inserts a `RETENTION_APPLIED` receipt into `uns_events` whose `payload["removed"]` embeds a full copy of the deleted `uns_notifications` and `uns_dedup` rows.
   - **With `--archive /path/to/new-file.json` (Full Group Export & Prune):**
     - Counts the total row cost of each notification group (`1 + count(uns_events) + count(notification_audit_records) + count(ack_audit_records)`).
     - Writes all removed rows from all 5 tables (`uns_notifications`, `uns_dedup`, `uns_events`, `notification_audit_records`, `ack_audit_records`) to the new archive file using `os.O_WRONLY | os.O_CREAT | os.O_EXCL` (mode `0600`), `fsync`s the file and parent directory, verifies the SHA-256 readback digest, deletes the rows from all 5 tables, and writes a compact metadata-only `RETENTION_APPLIED` receipt (`archive: {path, sha256, bytes}`).

---

## 3. Diagnostic Commands

### Step 3.1: Run a dry-run preview (no `--apply`)
```sh
.venv/bin/uns-maintain \
  --database-url "$UNS_DATABASE_URL" \
  --cutoff "2026-10-01T00:00:00Z" \
  --idempotency-seconds 86400 \
  --batch-size 100 | jq .
```

### Step 3.2: Inspect why a specific notification was skipped or marked oversized
```sh
NOTIF_ID="<notification_id>"
sqlite3 "$UNS_DB_FILE" "
  SELECT
    (SELECT COUNT(*) FROM uns_events WHERE notification_id = '$NOTIF_ID') AS event_rows,
    (SELECT COUNT(*) FROM notification_audit_records WHERE notification_id = replace('$NOTIF_ID', '-', '')) AS delivery_audit_rows,
    (SELECT COUNT(*) FROM ack_audit_records WHERE notification_id = replace('$NOTIF_ID', '-', '')) AS ack_audit_rows;
"
```

---

## 4. Safe Remediation Steps

### Scenario A: `FileExistsError` when running with `--archive`
- **Cause:** `_write_archive()` opens the target path with `O_CREAT | O_EXCL` so it never overwrites an existing archive file, partial file from an aborted run, or symlink.
- **Remediation:**
  1. Never reuse a static filename across batches or cron runs.
  2. Include a high-resolution timestamp, batch cursor, or `uuidgen` suffix in the archive filename:
     ```sh
     ARCHIVE_FILE="/var/backups/uns/archive-$(date -u +%Y%m%dT%H%M%SZ)-$(uuidgen | tr '[:upper:]' '[:lower:]').json"
     .venv/bin/uns-maintain \
       --database-url "$UNS_DATABASE_URL" \
       --cutoff "2026-10-01T00:00:00Z" \
       --idempotency-seconds 86400 \
       --batch-size 500 \
       --apply \
       --operator "oncall-operator" \
       --archive "$ARCHIVE_FILE"

     BACKUP_FILE="/var/backups/uns/uns-$(date -u +%Y%m%dT%H%M%SZ).db"
     sqlite3 -cmd ".timeout 5000" "${UNS_DB_FILE:?Set UNS_DB_FILE}" ".backup $BACKUP_FILE"
     sqlite3 "$BACKUP_FILE" "PRAGMA quick_check;"
     ```
  3. If a previous run failed mid-transaction, inspect any leftover partial file at the old path, verify whether its SHA-256 appears in `SELECT payload FROM uns_events WHERE kind = 'RETENTION_APPLIED'`, and remove the unreferenced partial file.

### Scenario B: Handling `oversized_notification_ids` in `--archive` mode
- **Cause:** In `--archive` mode, a notification's group cost is `1 + events + delivery_audits + ack_audits`. If that total exceeds `--batch-size` (default `100`), it is reported in `oversized_notification_ids` and skipped.
- **Remediation:** Increase `--batch-size` up to the maximum allowed value (`1000`):
  ```sh
  .venv/bin/uns-maintain \
    --database-url "$UNS_DATABASE_URL" \
    --cutoff "2026-10-01T00:00:00Z" \
    --idempotency-seconds 86400 \
    --batch-size 1000 \
    --apply \
    --operator "oncall-operator" \
    --archive "/var/backups/uns/archive-oversized-$(uuidgen).json"
  ```

### Scenario C: Paginating through a large backlog with `--after-id`
When `next_after_id` in the JSON output is non-null, pass it to the next invocation's `--after-id` flag (with a fresh `--archive` path for each batch) until `next_after_id` is `null`:

```sh
AFTER_ID=""
while :; do
  ARCHIVE="/var/backups/uns/archive-$(date -u +%Y%m%dT%H%M%SZ)-$(uuidgen).json"
  ARGS=(--database-url "$UNS_DATABASE_URL" --cutoff "$CUTOFF" --idempotency-seconds 86400 --batch-size 500 --apply --operator "ops-cron" --archive "$ARCHIVE")
  if [ -n "$AFTER_ID" ]; then
    ARGS+=(--after-id "$AFTER_ID")
  fi
  REPORT=$(.venv/bin/uns-maintain "${ARGS[@]}")
  echo "$REPORT" | jq '{deleted_rows, next_after_id, receipt_id}'
  AFTER_ID=$(echo "$REPORT" | jq -r '.next_after_id // empty')
  [ -z "$AFTER_ID" ] && break
done
```

---

## 5. Runtime Guardrails (`F-08a` & `F-08b` Disposition)

> [!IMPORTANT]
> **Non-Archive Mode Expires Operational & Idempotency Records Without Erasing History (`F-08a`):**
> By documented contract (`src/uns/maintenance.py`), running `uns-maintain --apply` **without** `--archive` expires active operational and idempotency rows from `uns_notifications` and `uns_dedup` while preserving full removed payloads inside the `RETENTION_APPLIED` receipt in `uns_events`.
> - **To prune rows across `uns_events` and audit tables**, supply `--archive <new-path.json>`.
> - **To reclaim physical disk space on the filesystem** after archived deletions, run SQLite `VACUUM` during a scheduled maintenance window (note that `RETENTION_APPLIED` receipts and policy history are never deleted).

> [!NOTE]
> **Runtime Clock Alignment for Audit Cutoff Checks (`F-08b`):**
> Delivery and ACK audit rows record `Runtime.clock()` timestamps, and `uns-maintain` normalizes SQLite naive UTC timestamps to UTC when comparing against `effective_cutoff`.

## Related Documentation

- [Deployment Guide - Explicit Retention](../DEPLOYMENT.md)
- [Support Reference: State Machines & Schema](../support/STATE-MACHINE-AND-SCHEMA.md)

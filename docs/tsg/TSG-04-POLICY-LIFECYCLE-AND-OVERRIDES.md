# TSG-04: Policy Lifecycle, Shadow Promotion, & Override Rejections

## 1. Symptoms & Alerts
- Producer calls to `POST /api/v1/notifications` or `/simulate` fail with `422 Unprocessable Entity` (`PolicyOverrideError` or `ValidationError`).
- Operator calls to `POST /api/v1/policies/reload` fail with `404 Not Found`, `409 Conflict`, or `422 Unprocessable Entity`.
- An operator wonders why a policy updated in a YAML file is not yet active, or how multi-process `uns` / `uns-mcp` instances synchronize policy changes.

---

## 2. Root Cause & Component Mechanics

### 2.1 Revision-Locked Durable Policy Authority (`PolicyRuntime`)
In `src/uns/policy_runtime.py` and `src/db/policy_store.py`:
1. All `ACTIVE` policies are stored in an immutable, revision-numbered JSON snapshot table (`notification_policy_snapshots`) coordinated by `notification_policy_revisions`.
2. **Canonical Intake (`Runtime.accept`):** Acquires the revision lock (`UPDATE notification_policy_revisions SET revision = revision WHERE singleton = 1`) inside its acceptance transaction so policy activation and accepted obligations linearize together.
3. **Steady-State Simulation & Inspection (`F-05`):** Warm `simulate()` and `/ui/policies/effective` calls read the current revision and immutable snapshot in a single consistent `SELECT` without acquiring a SQLite write lock.
4. Because policy resolution checks the database revision on every call, **separate `uns` and `uns-mcp` processes automatically pick up newly persisted `ACTIVE` snapshots** as soon as `POST /api/v1/policies/reload` commits.

### 2.2 Producer Override Enforcement & Reserved Metadata
1. **No Producer Weakening of `ACTIVE` Policy:** When an `ACTIVE` policy matches `notification_type`, producer-supplied overrides on `SendNotificationRequest` (`delivery_mode`, `require_ack`, `priority`, or `intent` if `policy.intent` is configured) that differ from the resolved `ACTIVE` policy raise `PolicyOverrideError` (`HTTP 422`).
2. **Reserved Adapter-Control Metadata:** `PolicyRuntime.resolve()` rejects requests whose `metadata` dictionary contains any adapter-steering key:
   - `slack_channel`
   - `email_to`
   - `pagerduty_severity`
   - `websocket_user_id` (plus any custom `target_user_metadata_key`)
3. **Persistent Channel Requirement for `GUARANTEED` Mode:** If a notification resolves to `delivery_mode = "GUARANTEED"` but its resolved `channels` list contains only `["WEBSOCKET"]` (or is empty), `PolicyRuntime.resolve()` raises `ValueError` (`HTTP 422`: `"GUARANTEED requires a persistent channel; choose BEST_EFFORT for WebSocket-only preview"`).

---

## 3. Diagnostic Commands

### Step 3.1: Inspect effective policy resolution for a signal shape
```sh
curl -sS -G -H "Authorization: Bearer $UNS_API_KEY" \
  "$UNS_BASE_URL/ui/policies/effective" \
  --data-urlencode "notification_type=system.alert" \
  --data-urlencode "intent=SAFETY" \
  --data-urlencode "autonomy_mode=LIVE" \
  --data-urlencode "irreversible=true" | jq .
```

### Step 3.2: Preview a producer request without side effects
```sh
curl -sS -X POST -H "Authorization: Bearer $UNS_API_KEY" \
  -H "Content-Type: application/json" \
  "$UNS_BASE_URL/api/v1/notifications/simulate" \
  -d '{
    "notification_type": "system.alert",
    "intent": "SAFETY",
    "title": "Test",
    "message": "Simulation check",
    "source": "diagnostics",
    "autonomy_context": {"autonomy_mode": "LIVE", "agent_id": "00000000-0000-0000-0000-000000000001"}
  }' | jq .
```

### Step 3.3: Inspect persisted policy snapshots and revisions in SQLite
```sh
sqlite3 "$UNS_DB_FILE" "
  SELECT r.revision, s.content_hash, s.created_at
  FROM notification_policy_revisions r
  JOIN notification_policy_snapshots s ON s.revision = r.revision
  WHERE r.singleton = 1;
"
```

---

## 4. Safe Remediation Steps

### Scenario A: `POST /api/v1/policies/reload` returns `409 Conflict`
- **Cause 1 — Re-activating a `RETIRED` policy content hash:** `SQLAlchemyPolicyStore._save_policy` blocks reactivating an identical content hash that was previously marked `RETIRED` (`"A retired policy version cannot be reactivated; publish a new version"`).
  - **Fix:** Increment the `version` field in the YAML policy file so its canonical content hash is new, then re-run `/api/v1/policies/reload`.
- **Cause 2 — Duplicate `(notification_type, status)` in directory:** Multiple YAML files define the same `notification_type` and `status`.
  - **Fix:** Ensure at most one `ACTIVE` and one `PREVIEW` definition exist per `notification_type`.

### Scenario B: `POST /api/v1/policies/reload` returns `422 Unprocessable Entity`
- **Cause:** YAML syntax error, invalid enum (`channels`, `delivery_mode`, `status`), or invalid policy field (`ack_timeout_minutes <= 0`, `dedup_window_seconds < 0`).
- **Fix:** Inspect the `detail` message in the `422` response, correct the YAML file in your policy directory, and retry:
  ```sh
  curl -sS -X POST -H "Authorization: Bearer $UNS_API_KEY" \
    -H "Content-Type: application/json" \
    "$UNS_BASE_URL/api/v1/policies/reload" \
    -d '{"policy_dir": "examples/policies/mip-uns"}' | jq .
  ```

### Scenario C: Producer receives `422` on `POST /api/v1/notifications`
1. **If error mentions `Producer metadata cannot control adapter routing or urgency`:** Remove `slack_channel`, `email_to`, `pagerduty_severity`, or `websocket_user_id` from `request.metadata`. Channel routing is controlled exclusively by server-side environment variables and policy configuration.
2. **If error mentions `PolicyOverrideError`:** Remove explicit `delivery_mode`, `require_ack`, or `priority` overrides from the producer payload (or align `intent` with the policy's configured `intent`) so the `ACTIVE` policy governs delivery.

---

## 5. Runtime Guardrails (`F-05` Disposition)

> [!NOTE]
> **Cross-Process Policy Consistency & Lock-Free Warm Reads (`F-05`):**
> Only policies with `status: ACTIVE` are written into `notification_policy_snapshots` and enforced by `PolicyRuntime`. Policies with `status: PREVIEW` are persisted in `notification_policies` for shadow comparison (`load_shadow_registry()`) and do **not** alter runtime delivery until promoted to `status: ACTIVE` with a bumped `version`. Warm simulation and effective-policy reads execute a single `SELECT` join without blocking concurrent SQLite writers.

## Related Documentation

- [Policy Lifecycle](../sections/policy-lifecycle.md)
- [Support Reference: State Machines & Schema](../support/STATE-MACHINE-AND-SCHEMA.md)
- [API Reference](../API.md)

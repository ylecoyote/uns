# Operator Console Guide (UNS Console)

This manual explains how human operators and support engineers use the **UNS Console** (`apps/ui`) to inspect notification deliveries, policy resolution provenance, system invariants, and the compliance audit stream.

---

## 1. Core Principles & Safety Boundaries (`INV-UI-001`)

- **Flight Instruments Only (`READ-ONLY`):** The UNS Console is strictly read-only (`INV-UI-001`). It calls only `GET /ui/*` endpoints and cannot send notifications, acknowledge/dismiss alerts, modify policies, or replay dead letters. All mutations must be performed via authenticated HTTP API calls (`/api/v1/*`) or `uns-mcp --enable-writes`.
- **Backend Authority:** The console displays durable state committed by `uns.Runtime`. If a response fails runtime schema validation or returns degraded state, the console surfaces a degraded banner rather than silently assuming delivery succeeded.

---

## 2. Signing In & Session Lifecycle

1. Open the UNS Console in your browser (`http://localhost:5173` in local development, or your production HTTPS origin).
2. At the **Sign In** prompt (`ConsoleSignIn`), enter the configured operator credential (`UNS_API_KEY`).
3. **Validation Probe:** Before mounting any console views, the app sends an authenticated `GET /ui/audit` request (`Authorization: Bearer <key>`) to verify the credential.
4. **Tab-Memory Storage:**
   - Your API key is stored **exclusively in JavaScript memory** for the current browser tab (`apps/ui/src/auth/session.ts`).
   - It is **never** written to `localStorage`, `sessionStorage`, cookies, or URL query parameters.
   - Reloading the browser tab, closing the tab, or clicking **Sign out** in the top navigation bar immediately clears the key from memory and returns to the sign-in screen.
5. **Session Expiration & Error Handling:**
   - **`401 Unauthorized`:** Immediately invalidates the current in-memory session and displays the sign-in screen with an expired-session notice (e.g., after `UNS_API_KEY` rotation).
   - **`403 Forbidden`:** Surfaces an inline authorization error without destroying an otherwise valid session.

---

## 3. Navigating the Five Console Views

Once signed in, the top navigation bar displays the **`READ-ONLY`** badge and links to four primary views (plus the drill-down Delivery Detail view):

### 3.1 Deliveries Explorer (`/deliveries`)
- **Purpose:** Browse and filter recent notification obligations (`GET /ui/deliveries`).
- **Available Filters:**
  - **Delivery Status:** `PENDING`, `DELIVERED`, `SUCCESS`, `FAILED`, `DEDUPLICATED`
  - **Intent:** `SAFETY`, `GOVERNANCE`, `OPERATIONAL`, `INFORMATIONAL`
  - **Delivery Mode:** `GUARANTEED`, `BEST_EFFORT`
  - **Autonomy Mode:** `LIVE`, `SHADOW`, `PREVIEW`, `SUPERVISED`, `AUTONOMOUS`
  - **Channel:** `SLACK`, `EMAIL`, `PAGERDUTY`, `WEBSOCKET`
  - **Notification Type & Agent ID**
- **Reading Status Badges:**
  | Badge | Meaning |
  | :--- | :--- |
  | `DELIVERED` / `SUCCESS` | At least one configured channel adapter succeeded and committed before lease expiration. |
  | `PENDING` | Queued for initial delivery, waiting for retry backoff (`next_attempt`), or coalesced behind an in-flight leader. |
  | `DEDUPLICATED` | Coalesced into an active deduplication window whose leader satisfied the obligation. |
  | `FAILED` | Exhausted all channels (`BEST_EFFORT`) or entered the Dead-Letter Queue (`GUARANTEED`, `dead_letter = true`). |

### 3.2 Delivery Detail & Timeline (`/deliveries/:notification_id`)
- **Purpose:** Inspect the end-to-end lifecycle of a single notification (`GET /ui/deliveries/{notification_id}`).
- **What You See:**
  1. **Header & Identity:** Notification UUID, `notification_type`, `intent`, `source`, `correlation_id`, and `created_at`.
  2. **Autonomy Context:** `agent_id`, `autonomy_mode`, and optional `plan_id` / `decision_snapshot_id`.
  3. **Acknowledgment Panel:** Whether `require_ack` is true, current `ack_status` (`PENDING`, `ACKED`, `DISMISSED`, `TIMED_OUT`), response `deadline`, `acked_by` actor, and `acked_at` timestamp.
  4. **Policy Evidence (`ResolutionContext`):** Which `policy_config_id` and `policy_config_hash` governed routing, and whether defaults or an `ACTIVE` policy applied.
  5. **Channel Attempt Timeline:** Ordered list of delivery attempts (`channel`, `status`, `error_message`, `timestamp`).

### 3.3 Effective Policy Inspector (`/policy`)
- **Purpose:** Test and inspect how UNS resolves routing rules for any combination of signal attributes (`GET /ui/policies/effective`).
- **How to Use:**
  1. Enter a `notification_type` (e.g., `system.alert` or `trading.risk_breach`).
  2. Select `intent` (`SAFETY`, `GOVERNANCE`, `OPERATIONAL`, `INFORMATIONAL`), `autonomy_mode` (`LIVE`, `SHADOW`, `PREVIEW`), and toggle `irreversible`.
  3. Inspect the resulting **Effective Policy Values**:
     - Resolved `channels` order (e.g., `["SLACK", "PAGERDUTY"]`)
     - `delivery_mode` (`GUARANTEED` vs `BEST_EFFORT`)
     - `require_ack` and `ack_timeout_minutes`
     - `dedup_window_seconds`
     - Step-by-step **Resolution Trace** showing whether values came from an `ACTIVE` policy, `mode_overrides`, `irreversible` safety escalation, or built-in intent defaults.

### 3.4 Invariants Viewer (`/invariants`)
- **Purpose:** Review the system's architectural and safety invariants registered in [`docs/verification/invariants.yml`](../verification/invariants.yml) (`GET /ui/invariants` and `GET /ui/invariants/summary`).
- **How to Use:**
  - View aggregate counts at the top (Total, Passing, Failing, By Severity).
  - Filter invariants by **Severity** (`CRITICAL`, `HIGH`, `MEDIUM`), **Enforcement Type** (`RUNTIME`, `STATIC_ANALYSIS`, `TEST`, `SCHEMA`), **Status**, or full-text search (e.g., `INV-UI-001`).
  - Expand an invariant row to inspect its verification evidence links (test files and source modules).

### 3.5 Audit Timeline (`/audit`)
- **Purpose:** Search the immutable compliance audit stream (`GET /ui/audit`).
- **How to Use:**
  - Filter by `event_type` (`DELIVERY_SUCCEEDED`, `DELIVERY_FAILED`, `NOTIFICATION_DEDUPLICATED`, `ACK_RECEIVED`, `ACK_DISMISSED`, `ACK_TIMED_OUT`), `notification_id`, `agent_id`, `autonomy_mode`, `correlation_id`, or time window (`start_time` / `end_time`).
  - Use cursor pagination (**Next Page**) to traverse historical audit records.

---

## 4. Acting on Console Findings

Because the UNS Console is read-only (`INV-UI-001`), when you identify an incident in the console:
- **Failed / Dead-Lettered Delivery:** Follow [TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay](../tsg/TSG-01-DLQ-AND-REPLAY.md).
- **Timed-Out Acknowledgment:** Follow [TSG-03: Acknowledgment Timeouts, Escalations, & Callback Failures](../tsg/TSG-03-ACK-TIMEOUTS-AND-CALLBACKS.md).
- **Unexpected Policy Routing:** Follow [TSG-04: Policy Lifecycle, Shadow Promotion, & Override Rejections](../tsg/TSG-04-POLICY-LIFECYCLE-AND-OVERRIDES.md).

## Related Documentation

- [Console Developer README](../../apps/ui/README.md)
- [UI Data Contracts](../ui/ui-data-contracts.md)
- [UI Scope](../ui/ui-scope.md)
- [Deployment Guide](../DEPLOYMENT.md)

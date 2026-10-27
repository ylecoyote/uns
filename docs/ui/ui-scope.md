# AGSignal Console Scope — Responder & Operator Console

## Design Philosophy

AGSignal Console (UNS Console) began in v1 as a **read-first "flight instruments" dashboard**, not an unconstrained control cockpit, establishing observability and audit trust before introducing operational mutations. It has since evolved into a capability-gated **Responder & Operator Console** that pairs read-first flight-instrument telemetry with strictly scoped, backend-enforced responder, producer, and operator actions across five primary surfaces.

## v1 Constraints (Historical Baseline & Permanent Boundaries)

| Capability | v1 Status | Current Responder & Operator Console Status |
|------------|-----------|---------------------------------------------|
| Read-only dashboards | Included | Included (`observer` scope across `/ui/*`) |
| Metrics & health monitoring | Included | Included (`/operations`, `GET /readyz`, `GET /api/v1/channels/health`) |
| Notification authoring | **Not included** | Synthetic `[TEST]` dispatch only in `/policy` (`producer`/`admin`); arbitrary ad-hoc notification authoring remains **Not included** |
| Policy editing | **Not included** | Arbitrary inline YAML policy editing remains **Not included**; atomic disk-to-runtime reload (`POST /api/v1/policies/reload`) is gated by `admin` scope |
| Obligation response & triage | **Not included** | Inline Acknowledge / Dismiss (`responder`/`admin`) on `/deliveries/:notificationId` |
| Dead-letter recovery | **Not included** | Inline Replay / Resolve (`admin`) on `/operations` and `/deliveries/:notificationId` |

## Primary Console Surfaces

### 1. Session Capability Introspection & Auth (`GET /ui/session`)

- **Server-Verified Capability Introspection:** On sign-in, the console authenticates against `GET /ui/session` (`ConsoleSessionResponse`), which returns the authenticated principal `subject`, granted `scopes` (`observer`, `responder`, `producer`, `admin`), and runtime `persistence_mode`.
- **Non-Lossy Capability Pills:** The top navigation bar renders non-lossy capability pills mapped directly from server-verified scopes:
  - `OPERATOR` (`admin` scope)
  - `RESPONDER` (`responder` or `admin` scope)
  - `PRODUCER` (`producer` or `admin` scope)
  - `READ-ONLY` (when only `observer` scope is held)
  Multi-role principals (e.g., `["observer", "responder", "producer"]`) display all applicable capability pills simultaneously without hiding lower-ranked capabilities.
- **Tab-Memory Credential Storage & Multi-Tab Handshake:** API credentials are held exclusively in JavaScript tab memory (`apps/ui/src/auth/session.ts`) and never persisted to `localStorage`, `sessionStorage`, or cookies. New browser tabs synchronize active credentials and sign-out events in-memory via `BroadcastChannel('uns_console_session')` (`SESSION_REQUEST`, `SESSION_SHARE`, `SESSION_CLEAR` handshake).

### 2. Deliveries & Obligation Triage (`/deliveries` and `/deliveries/:notificationId`)

- **Delivery Timelines:** Queries `GET /ui/deliveries` and `GET /ui/deliveries/{notification_id}` for channel delivery attempts, autonomy context, and durable runtime obligation state (`RuntimeDeliveryState`).
- **Canonical Owner vs. Deduplicated Follower Lineage:** Surfaces `obligation_owner_id`, `ack_inherited`, `effective_ack_status`, `obligation_resolution_status`, and `obligation_resolution_error`. When a notification is deduplicated (`obligation_owner_id !== notification_id`), the console links directly to the canonical owner notification and routes response actions to the owner.
- **Bounded Runtime Obligation Events:** Displays the chronological runtime obligation ledger (`events`, `events_total_count`, `events_truncated`) capped at the most recent 100 events with an explicit truncation notice when `events_truncated` is `true`.
- **Inline Responder Workflows:** Principals with `responder` or `admin` scope can execute inline **Acknowledge** (`POST /api/v1/notifications/{id}/ack`) and **Dismiss** (`POST /api/v1/notifications/{id}/dismiss`) transitions with optional responder notes (`metadata.note`).
- **Inline Dead-Letter Recovery & `409 Conflict` Auto-Refresh:** Principals with `admin` scope can trigger inline **Replay** (`POST /api/v1/runtime/notifications/{id}/replay`) and **Resolve** (`DELETE /api/v1/dlq/{entry_id}`) directly from dead-lettered delivery details. If a concurrent transition produces `409 Conflict`, the view automatically refreshes the delivery timeline and surfaces a concurrency banner.

### 3. Policy Workspace (`/policy`)

- **Active Policies Catalog (`GET /ui/policies/active`):** Loads the live catalog of registered notification routing policies (`ActivePolicyListResponse` / `ActivePolicySummary`) with clickable rows that populate the inspector and synchronize `?notification_type=` URL deep-links.
- **Policy Revision History & Governance (`GET /ui/policies/revisions`):** Surfaces the durable revision ledger (`PolicyRevisionListResponse` / `PolicyRevisionSummary`) across `ACTIVE`, `DRAFT`, `PREVIEW`, and `RETIRED` revisions with status filter pills, selection-scoped revision filtering, `policy_revision_id` / `supersedes_revision_id` lineage chains, `content_hash`, actor attribution (`created_by`, `published_by`), and timestamps.
- **Two-Column Split Layout for Effective Policy Resolution (`GET /ui/policies/effective`):** Displays resolved effective policy values (`delivery_mode`, `channels`, `require_ack`, `ack_timeout_minutes`, `dedup_window_seconds`) alongside the step-by-step field resolution trace (`explicit_override`, `mode_override`, `policy_base`, `sdk_default`).
- **Dry-Run Simulation (`POST /api/v1/notifications/simulate`):** Gated by `producer` or `admin` scope; previews resolved routing channels, deduplication keys, and simulation warnings without dispatching to external providers.
- **Synthetically Tagged `[TEST]` Live Dispatch (`POST /api/v1/notifications`):** Gated by `producer` or `admin` scope; dispatches a live verification notification prefixed with `[TEST]` and tagged with `source: "uns-console-policy-test"` and `metadata.source = "uns_console_policy_test"`, linking directly to the resulting `/deliveries/:notificationId` timeline.
- **Atomic Two-Phase Policy Reload (`POST /api/v1/policies/reload`):** Gated by `admin` scope; validates YAML policies on disk and atomically swaps the active policy registry while refreshing the catalog.

### 4. Operations & Dead-Letter Recovery (`/operations`)

- **Fault-Isolated Polling:** Polls four operational endpoints independently via `Promise.allSettled` so a failure or `503` on one panel never blocks the others:
  - `GET /readyz` (`503`-tolerant JSON decoding for degraded readiness inspection)
  - `GET /api/v1/channels/health` (per-channel health status, consecutive failures, and last failure reasons)
  - `GET /api/v1/dlq` (visible DLQ entries and queue depth)
  - `GET /api/v1/runtime/dead-letters` (durable runtime dead-letter obligations)
- **Inline Dead-Letter Recovery:** Principals with `admin` scope can execute inline **Replay** (`POST /api/v1/runtime/notifications/{id}/replay`) and **Resolve** (`DELETE /api/v1/dlq/{entry_id}`) actions with confirmation guards on irreversible DLQ removal.

### 5. System Invariants (`/invariants`) & Audit Timeline (`/audit`)

- **System Invariants (`/invariants`):** Read-only verification surface backed by `GET /ui/invariants` and `GET /ui/invariants/summary`, exposing invariant severity, enforcement mechanisms, and repository evidence links.
- **Dual-Mode Audit Timeline (`/audit`):** Queries `GET /ui/audit` and defaults to **By notification (`1e`)** lifecycle grouping (`NOTIFICATION | STARTED | DELIVERED | RESPONSE | TIME TO RESPOND`), which correlates all audit events for each `notification_id` into an expandable lifecycle row computing elapsed response time (`ack.received` / `ack.dismissed` / `ack.timed_out` minus `notification.created`), with a segmented toggle to the chronological **All events (`1d`)** stream.

## Modernist Design System Specification

The UNS Console implements a high-craft light-mode **Modernist** (Swiss-grid Neo-Brutalist) visual system in `apps/ui/src/App.css`:

- **Typography:** `Archivo` (`400` regular body, `600` semi-bold labels/headers, `800` extra-bold display headings) paired with `ui-monospace` (`font-variant-numeric: tabular-nums`) for UUIDs, timestamps, durations, and hashes.
- **Color Tokens:**
  - Warm paper canvas background: `#f3f2f2` (`--color-bg`)
  - Stone secondary surface: `#eae9e9` (`--color-surface`)
  - Warm charcoal ink: `#201e1d` (`--color-text`)
  - Signal vermilion accent: `#ec3013` (`--color-accent`)
  - Structural grid divider rules: `color-mix(in srgb, #201e1d 40%, transparent)` (`--color-divider`)
- **Geometry & Modular Grid Rules:** Strict `0px` border radius (`--radius-sm/md/lg: 0px`), no drop shadows, `2px solid #201e1d` primary structural rules, and `1px solid` modular grid cell dividers.
- **Badge Visual Grammar (Filled Delivery vs. Outlined Response):**
  - **Filled Badges (Delivery State):** Solid fills communicate machine delivery states (`DELIVERED` / `SUCCESS` in solid `#201e1d` charcoal ink; `FAILED` / `DEAD-LETTER` in solid `#ec3013` signal vermilion).
  - **Outlined Badges (Human Response State):** `1.5px`–`2px` stroked transparent badges communicate human obligation states (`ACKED`, `DISMISSED`, `PENDING`, `TIMED_OUT`), preventing visual conflation between transport delivery and human acknowledgment.

## Invariant Integrity

**The UI must not bypass system invariants.**

All business rules, RBAC scope checks (`observer`, `responder`, `producer`, `admin`), state-machine transitions, and safety constraints enforced by the backend remain authoritative. Read-only `/ui/*` endpoints remain strictly non-mutating (`INV-UI-001`), while responder and operator mutations invoke the canonical `/api/v1/*` endpoints under full backend invariant and audit enforcement.

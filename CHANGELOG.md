# Changelog

All notable changes to the Unified Notification Service (UNS) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Policy Authority, Obligation Lineage, Webhook Idempotency & Scoped Read Hardening (`F16`-`F24`):**
  - **Policy Activation Authority & Shadow Accuracy Gate (`F16`, `F21`, `F22`):** Verified `GuardStage.APPLY` baseline freshness, matched `APPROVED` `PolicyDelta` records, and transitioned matched proposals to `DeltaState.APPLIED` across all `ShadowPolicyEvaluator.activate_draft()` invocation paths (`delta_id`, `policy_id`, and `notification_type`); marked `ShadowEvaluationAggregate` as `FAILED` whenever `degraded_decisions > 0` once `min_samples` is reached; pushed shadow result counting into SQL via `SQLAlchemyPolicyLearningStore.get_shadow_result_counts(delta_id)` and used `persisted_preview` directly when evaluating auto-bound `PREVIEW` policy revisions; reconstructed multi-field `PREVIEW` policy diffs across all 19 `ALLOWED_POLICY_FIELD_PATHS`; allowed retired unactivated `PREVIEW`/`DRAFT` candidates (`activated_at is None`) to be re-proposed while preserving the reactivation tombstone for retired `ACTIVE` policies.
  - **Canonical Obligation Owner Settlement & Inherited Projection (`F17`):** Resolved `_resolve_obligation_owner()` inside `Runtime._respond()` and `Runtime.sync_pagerduty_incident()` so acknowledging, dismissing, or timing out a deduplicated follower or failed replay predecessor settles the canonical owner obligation and propagates `actor`, `responded_at`, and `response_metadata` across `Runtime.get()`.
  - **PagerDuty & Slack Webhook Settlement Semantics (`F18`, `F23`):** Mapped PagerDuty `incident.resolved` on unacknowledged `PENDING` obligations to `DISMISSED` (`ApprovalStatus.REJECTED`) rather than `ACKED` (`ApprovalStatus.APPROVED`), treated already-`DISMISSED` obligations as `already_settled=True` (`HTTP 200`), resolved `uns-pd-<uuid>` incident keys in O(1), made Slack interactivity button clicks idempotent after settlement (`HTTP 200` with settled blocks), and moved outbound PagerDuty sync in the Slack webhook onto FastAPI `BackgroundTasks`.
  - **Governance Approval Bridge Pre-Dispatch, Timeout & Deterministic Recovery (`F19`):** Allowed `Runtime._respond()` to settle pre-dispatch `PENDING` obligations with `require_ack=True` (without `Runtime.dispatch()` overwriting `ack_status` back to `PENDING`), persisted `ApprovalStatus.TIMED_OUT` transitions to `Runtime`, and bound `sign_approval_callback()` to `int(resolved_at.timestamp())` so recovered approval records produce deterministic `X-UNS-Timestamp` and `X-UNS-Signature` headers across restarts.
  - **Scoped SQL Pushdown Pagination, Proposal Sample Filtering & PostgreSQL Shared Snapshot Reads (`F20`, `F23`, `F24`):** Pushed `allowed_sources` and `allowed_namespaces` scope pattern predicates directly into SQL `WHERE` clauses inside `SQLAlchemyReadModelAdapter.get_deliveries()` and `get_audit_events()` (and `InMemoryReadModelAdapter`) so `/ui/deliveries`, `/ui/audit`, and `uns-mcp` `list_deliveries`/`list_audit_events` paginate natively at the database level without 10,000-row Python scans; enforced `extra="forbid"` on `PaginationInfo`; filtered `shadow_results` by `principal.allows_source` in `GET /ui/policies/proposals/{delta_id}`; switched `SQLAlchemyPolicyStore.lock_snapshot(for_write=False)` to `SELECT ... FOR SHARE` on PostgreSQL; protected followers of active owners in `uns-maintain`; and cleared replayed `UNKNOWN` attempts in `compute_slo_report()`.
  - **Core Positioning & Boundary Alignment:** Refined repository headlines and documentation across `README.md`, `docs/README.md`, `pyproject.toml`, and `mkdocs.yml` around durable human-response coordination for agent workflows and high-trust backend operations, explicitly documenting producer routing-metadata isolation and `uns.governance` as an opt-in host callback helper.

## [0.6.1] - 2026-11-03

### Added
- **UNS Brand System (Variant `4a`) & Complete Console Screenshot Gallery:**
  - Added clean SVG brand marks (`docs/assets/logo/uns-mark.svg`, `uns-mark-on-dark.svg`, `uns-mark-mono.svg`, `uns-lockup.svg`, `uns-lockup-dark.svg`, `apps/ui/public/favicon.svg`) and GitHub social preview card (`docs/assets/logo/uns-social-preview.png`).
  - Integrated `UnsLogoMark` (`apps/ui/src/components/UnsLogoMark.tsx`) into the UNS Console top navigation bar and sign-in header, configured MkDocs theme logo/favicon (`mkdocs.yml`), and expanded the documentation screenshot gallery to 8 high-DPI views including `console-policy-inspector.png` and `console-docs.png`.

### Fixed
- **Security & Functionality Audit Remediations (`F01`-`F15`):**
  - **`F01` (Scoped Read & MCP Tenant Isolation):** Enforced fail-closed record-level and collection-level `allowed_sources` + `allowed_namespaces` bounds across `/api/v1/runtime/notifications/{id}`, `/api/v1/runtime/dead-letters`, `/api/v1/notifications/{id}/delivery`, `/api/v1/notifications/{id}/audit`, `/api/v1/dlq*`, `/ui/deliveries*`, `/ui/audit`, and all registered `uns-mcp` read/list tools before pagination and counts.
  - **`F02` & `F09` (Governance Approval Identity & Durable Settlement Callbacks):** Included `tenant_id`, `resource_type`, and `resource_id` in `_deterministic_decision_id()`, enforced bound-content fingerprint matching (`ApprovalConflictError`) in `GovernanceApprovalBridge.request_approval()`, and decoupled terminal approval status from `on_settled` callback completion so failed resume callbacks retry across subsequent resolution and runtime sync calls.
  - **`F03`, `F07`, `F08`, `F10` (Policy Evolution Atomicity, Exact Draft Binding & Shared-DB Cache):** Bound exact `draft_policy_id` and `candidate_hash` to `APPROVE_DRAFT` evidence and verified/materialized the exact approved candidate in `activate_draft()`; made `promote_to_shadow()`, `approve_to_draft()`, and `activate_draft()` rollback-safe across policy and learning stores; removed the process-local negative candidate cache so warm workers immediately evaluate peer-created `SHADOW`/`PREVIEW` candidates; preserved explicit `dedup_window_seconds=0` in `config_dict_to_policy()`.
  - **`F04` (PagerDuty Provider Incident Key Isolation):** Scoped PagerDuty `dedup_key` generation and webhook target resolution to the obligation's isolated runtime `dedup_key` (`uns_obligation_dedup_key`) and persisted `CHANNEL_ATTEMPT_RESULT` `message_id`, rejecting ambiguous raw producer keys across isolated tenants.
  - **`F05` (Bounded Unmatched Route Metric Cardinality):** Mapped unmatched HTTP 404 paths to `"__unmatched__"` and normalized HTTP methods in `src/notification/metrics.py` and `src/uns/api/observability.py`.
  - **`F06` (Admin Gate on `promote_to_shadow` Proposal Creation):** Required `admin` scope when `promote_to_shadow: true` is passed to `POST /api/v1/policies/proposals`.
  - **`F11`, `F12`, `F13`, `F14`, `F15` (SLO Stalled-Backlog Gate, Shared Channel Health, `/readyz` HTTP 503, Lifespan Reload Worker & Docs Contracts):** Added `zero_stalled_pending_backlog` gate to `compute_slo_report()`, wired `Runtime._channel_result()` into the shared `ChannelHealthTracker` across HTTP and MCP, returned HTTP `503` on `/readyz` failure, started a background policy reload worker in `app.py:lifespan`, and resolved all 39 MkDocs link diagnostics (`validation.links.not_found: warn`).

## [0.6.0] - 2026-11-03

### Added
- **In-Tree Pre-Execution Governance Engine & Approval Obligation Bridge (`uns.governance`, `#49`):**
  - Completed `src/uns/governance/context_schema.py` (`ContextSchema`, `parse_field_path()`, `validate_policy_against_schema()`, `validate_context_capsule()`, `resolve_field_path()`, and RFC 8785-style canonical JSON `compute_context_hash()`).
  - Completed `src/uns/governance/decision_engine.py` with pure, deterministic `decide()` (`DENY > REQUIRE_APPROVAL > ALLOW` precedence, full rule evaluation without short-circuiting, and default-`DENY` fallback) and impure `DecisionEngine` supporting hot-reload last-known-good quarantine, bounded audit ledger (`max_audit_entries`), and per-intent fail-mode semantics (`SAFETY` / `GOVERNANCE` / `OPERATIONAL` fail-closed `DENY`; `INFORMATIONAL` fail-open `ALLOW` with operational alert emission).
  - Added `src/uns/governance/approval_workflow.py` (`GovernanceApprovalBridge`, `ApprovalRequestRecord`, `ApprovalStatus`, `sign_approval_callback()`, `verify_approval_callback()`) wiring `REQUIRE_APPROVAL` decisions to durable `uns.Runtime` notification obligations (`idempotency_key="gov-approval:{decision_id}"`), cross-restart obligation recovery (`_recover_from_runtime()`), and HMAC-SHA256 signed resume callbacks (`X-UNS-Signature`, `X-UNS-Timestamp` with `±300s` replay guard).
- **SLO Telemetry & Certification CLI Harness (`uns-slo-certify` / `src/uns/slo.py`, `#48`):**
  - Added `compute_slo_report()`, `format_slo_markdown()`, and the `uns-slo-certify` console script entry point to compute SHA-256 hash-verifiable operational SLO receipts (`receipt_sha256` / `receipt_hash`), human response latency percentiles (`p50`, `p95`, `max`), persistent external provider error rates, `recording_only` vs. live external provider classification (`observed_live_span_days`), and 6-gate `v1.0` certification checks.

### Fixed
- **Post-Milestone 4 Security & Lifecycle Hardening:**
  - Enforced upfront `Content-Length` check and streaming `MAX_WEBHOOK_BODY_BYTES` (`262,144`) cap in `src/uns/api/routes_webhooks.py:_read_bounded_body()`.
  - Added `SQLAlchemyPolicyStore.retire_candidate_revisions()` and wired `ShadowPolicyEvaluator.reject_delta()` to retire `PREVIEW`/`DRAFT` revisions on rejection so rejected proposals cannot resurrect on subsequent intakes.
  - Replaced deprecated `HTTP_422_UNPROCESSABLE_ENTITY` status constant with `HTTP_422_UNPROCESSABLE_CONTENT` in `src/notification/routes.py`.

## [0.5.0] - 2026-11-03

### Added
- **Automated `PREVIEW` Shadow Evaluation Runner (`uns.shadow_evaluator.ShadowPolicyEvaluator`, `#46`):**
  - Added `ShadowPolicyEvaluator` (`src/uns/shadow_evaluator.py`) wired into `Runtime.accept()` (`src/uns/runtime.py`) and `create_app()` (`src/uns/app.py`) to asynchronously evaluate `SHADOW` policy deltas and `PREVIEW` policy revisions (`_ensure_shadow_deltas_for_preview_policies`) against live notification intake without external channel sends or live obligation mutation.
  - Added deterministic candidate vs. baseline policy routing comparison (`policy_to_envelope`, `envelope_to_policy`, `_candidate_policy`), allow-listed policy field-path validation (`ALLOWED_POLICY_FIELD_PATHS`), O(1) `_write_seq` fast-path skipping when no `PREVIEW`/`SHADOW` candidates exist, and automatic `ShadowEvaluationResult` + `ShadowEvaluationAggregate` persistence in `SQLAlchemyPolicyLearningStore` (`UNS_SHADOW_EVALUATION_ENABLED`, `UNS_SHADOW_MIN_SAMPLES`, `UNS_SHADOW_ACCURACY_THRESHOLD`).
- **Console `/policy` Promotion Workflow & Governed Policy Delta API (`#47`):**
  - Added read endpoints (`GET /ui/policies/proposals`, `GET /ui/policies/proposals/{delta_id}`, `GET /api/v1/policies/proposals`, `GET /api/v1/policies/proposals/{delta_id}`) and operator-authenticated promotion endpoints (`POST /api/v1/policies/proposals`, `POST /api/v1/policies/proposals/{delta_id}/shadow`, `/approve`, `/activate`, `/reject`, and `POST /api/v1/policies/revisions/{policy_id}/activate`) in `src/uns/api/routes_ui.py` and `src/notification/routes.py`.
  - Enforced `PolicyChangeProposalService.evaluate_guards()` (`BOUNDS`, `CONFLICT`, `INVARIANTS`), baseline config hash (`baseline_config_hash`) drift checks (`409 policy_baseline_drift`), and shadow sample/accuracy threshold gates (`409 policy_promotion_conflict`) before promoting `SHADOW` deltas into `DRAFT` revisions (`notification_policy_revisions`) and explicitly activating `DRAFT -> ACTIVE` (retiring prior `ACTIVE`/`PREVIEW` revisions and broadcasting cross-process reload notifications).
  - Updated `apps/ui/src/pages/PolicyInspectorPage.tsx` with the `Proposals & Shadow Evidence` workspace tab, interactive `PolicyDelta` proposal builder, shadow sample/accuracy progress pills, baseline-hash/guard status badges, one-click `Promote to SHADOW` / `Approve to DRAFT` / `Activate DRAFT -> ACTIVE` actions, and the `Shadow Evidence & Guard Ledger` inspection drawer.

## [0.4.0] - 2026-11-03

### Added
- **PostgreSQL Retention & Archive-Before-Prune (`uns-maintain`, `#43`):**
  - Extended `uns-maintain` (`src/uns/maintenance.py`) to support `postgresql+psycopg://` databases alongside SQLite.
  - Added PostgreSQL native UUID casting in `_eligible()` (`sa_cast(work.c.id, Uuid)`), `SET LOCAL lock_timeout = '30s'`, transactional advisory locking (`SELECT pg_advisory_xact_lock(758392014)`), and `FOR UPDATE` candidate row locking before exporting mode-`0600` SHA-256 verified JSON archives and pruning settled notification groups.
- **Cross-Process Policy Reload Broadcast (`LISTEN/NOTIFY` & Redis Pub/Sub, `#44`):**
  - Added `PolicyReloadEnvelope`, `RedisPolicyReloadBroadcaster`, `RedisPolicyReloadSubscriber` (`uns:policies:reload` / `UNS_POLICY_REDIS_CHANNEL`), and `PostgresPolicyReloadListener` (`LISTEN uns_policy_reload`) in `src/uns/policy_runtime.py` and `src/db/policy_store.py`.
  - Added parsed `NotificationPolicy` caching on `PolicySnapshot` and warm snapshot caching + activation listeners on `SQLAlchemyPolicyStore` and `PolicyRuntime` so `save_policy()`, `bootstrap_policies()`, and `POST /api/v1/policies/reload` broadcast revision changes immediately across multi-worker deployments.
- **Source- & Namespace-Scoped Credentials Across HTTP, WebSocket, & `uns-mcp` (`#45`):**
  - Extended `WritePrincipal` (`src/uns/api/auth.py`) with `allowed_sources` and `allowed_namespaces` wildcard/prefix patterns (`*`, `ci-*`, `deploy.*`), configured via `UNS_PRODUCER_ALLOWED_SOURCES`, `UNS_PRODUCER_ALLOWED_NAMESPACES`, `UNS_RESPONDER_ALLOWED_SOURCES`, `UNS_RESPONDER_ALLOWED_NAMESPACES`, `UNS_OBSERVER_ALLOWED_SOURCES`, `UNS_OBSERVER_ALLOWED_NAMESPACES`, and multi-team JSON credentials (`UNS_SCOPED_API_KEYS`).
  - Enforced source and namespace scopes (`403 namespace_or_source_forbidden`) across `POST /api/v1/notifications`, `/simulate`, `/ack`, `/dismiss`, `GET /api/v1/notifications/{id}`, `/ack-status`, `/api/v1/runtime/notifications/{id}`, `/ui/deliveries`, `/ui/deliveries/{id}`, `/ui/policies/effective`, `/ui/policies/active`, `/ui/policies/revisions`, WebSocket `/ws/agents/{agent_id}` live push + replay + ack frames, and `uns-mcp` (`UNS_MCP_ALLOWED_SOURCES`, `UNS_MCP_ALLOWED_NAMESPACES`).

## [0.3.0] - 2026-11-03

### Added
- **Inbound Signed Slack Interactivity Webhook (`POST /api/v1/webhooks/slack`, `#40`):**
  - Added HMAC-SHA256 request verification (`X-Slack-Signature` `v0=<hex>` and `X-Slack-Request-Timestamp` `±300s` replay guard with `UNS_SLACK_SIGNING_SECRET`, constant-time `hmac.compare_digest`, 256 KB body size limit, and fail-closed `503 slack_webhook_not_configured` when unset).
  - Wired `SlackAdapter._build_blocks()` `Acknowledge` (`ack_<id>`) and `Dismiss` (`dismiss_<id>`) buttons to settle the canonical `obligation_owner_id` directly from Slack as actor `slack:<team_id>:<user_id>` and return an in-place Block Kit message update (`replace_original: true`).
- **Inbound Signed PagerDuty v3 Webhook & Bi-Directional Sync (`POST /api/v1/webhooks/pagerduty`, `#41`):**
  - Added PagerDuty v3 Generic Webhook verification (`X-PagerDuty-Signature` `v1=<hex>` supporting comma-separated rotation signatures with `UNS_PAGERDUTY_WEBHOOK_SECRET`, constant-time `hmac.compare_digest`, 256 KB body limit, and fail-closed `503 pagerduty_webhook_not_configured` when unset).
  - Added `Runtime.resolve_pagerduty_target()` and `Runtime.sync_pagerduty_incident()` (`PAGERDUTY_OUTBOUND_SYNC`) so inbound `incident.acknowledged` / `incident.resolved` webhooks settle `uns-<dedup_key>` / `uns-<notification_id>` obligations as `pagerduty:<agent_id>`, while HTTP/Slack `ACK` and `DISMISS` propagate outbound `acknowledge_incident` / `resolve_incident` calls to PagerDuty Events API v2.
- **Automated PyPI & Multi-Arch GHCR Release Publishing Workflow (`.github/workflows/release.yml`, `#42`):**
  - Added release automation triggered on `release: [published]` and `workflow_dispatch` to build, smoke-test, and attach Python wheels/sdists, publish multi-arch (`linux/amd64`, `linux/arm64`) images to `ghcr.io/ylecoyote/uns` with `actions/attest-build-provenance@v2`, and publish to PyPI via OIDC Trusted Publishing (`vars.PYPI_TRUSTED_PUBLISHING == 'true'`) or `secrets.PYPI_API_TOKEN`.

## [0.2.0] - 2026-11-02

### Added
- **Durable Transactional Outbox Runtime (`uns.Runtime` & `uns.Client`):**
  - Atomic SQLite/SQLAlchemy intake (`uns_notifications`, `uns_events`, `uns_dedup`) combining policy provenance resolution, idempotency verification (`principal + source + idempotency_key`), and deduplication window claiming (`LEADER` / `FOLLOWER` generations).
  - Fenced 60-second delivery leases (`lease_token`, `lease_until`) with pre-channel fencing (`CHANNEL_ATTEMPT_STARTED`), append-only per-channel attempt observations (`CHANNEL_ATTEMPT_RESULT`), `LEASE_LOST` recording, exponential retry backoff, and automatic follower settlement (`DEDUP_SATISFIED` on leader delivery; `OBLIGATION_HANDED_OFF`, `DEDUP_OWNER_PROMOTED`, and `DEDUP_RELINKED` on leader exhaustion).
  - Durable successor lineage (`dedup_successor_id`) and guarded replay (`replay_blocked_by`, `replay_block_reason`) preventing duplicate delivery when a successor obligation is pending or already satisfied (`F-01`, `F-02`).
  - Deadline/cancellation-aware SMTP admission and `UNKNOWN` provider outcome recording for timed-out in-flight sends (`F-04a`, `F-04b`).
  - Durable acknowledgment deadline sweeps (`TIMED_OUT`) and due-time ordered (`callback_until, at, id`) at-least-once terminal callback delivery (`deliver_callbacks`, `F-06`).
  - Operator dead-letter inspection (`GET /api/v1/runtime/dead-letters`), attributable cycle replay (`POST /api/v1/runtime/notifications/{id}/replay`), and non-replay failure resolution (`DELETE /api/v1/dlq/{id}`).
- **Revision-Locked Policy Authority (`uns.policy_runtime.PolicyRuntime`):**
  - Immutable `ACTIVE` policy snapshots (`notification_policy_revisions`, `notification_policy_snapshots`) locked at intake and read in a single lock-free `SELECT` during warm simulation/inspection (`F-05`).
  - Strict enforcement blocking producer overrides from weakening `ACTIVE` policies and blocking reserved adapter-steering metadata keys (`slack_channel`, `email_to`, `pagerduty_severity`, `websocket_user_id`).
- **Unified HTTP, Console Read-Model, & WebSocket Service (`uns` / `uns.app:create_app`):**
  - Consolidated FastAPI service mounting `/api/v1/notifications/*`, `/api/v1/runtime/*`, `/api/v1/policies/reload`, `/ui/*`, `/ws/agents/{agent_id}`, public `/healthz`, and authenticated `/readyz` and `/metrics`.
  - Pre-accept WebSocket authentication supporting native `Authorization: Bearer` headers and browser `uns.v1` + `bearer.<base64url>` subprotocols with closed-list `Origin` validation.
- **Trusted-Local MCP Server (`uns-mcp`):**
  - Read-only default mode (`stdio-local`) and explicit `--enable-writes` mode (`stdio-persistent`) requiring `UNS_DATABASE_URL`, `UNS_API_PRINCIPAL`, and `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` with an owned lifespan recovery worker and runtime-bound read helpers (`F-07`).
- **Explicit Database Maintenance & Archival CLI (`uns-maintain` & `uns-migrate`):**
  - `uns-migrate` for idempotent additive schema bootstrap, successor-lineage reconstruction, and callback due-time normalization.
  - `uns-maintain` for bounded operational pruning, cursor continuation (`--after-id`), and `O_EXCL` mode-`0600` SHA-256 verified JSON group archival (`--archive`).
- **Responder & Operator Console (`apps/ui`) & Local Recording Stack:**
  - React 19 + TypeScript 5.9 + ESLint 9 flat config + Vite SPA styled in the **Modernist** Swiss-grid design system (`Archivo` 800/600/400, warm paper `#f3f2f2` / stone `#eae9e9` / charcoal `#201e1d` / signal vermilion `#ec3013`, `0px` corners, filled-delivery vs. outlined-response badge grammar) across six primary surfaces: `/deliveries` (with `/deliveries/:id` detail), `/policy`, `/operations`, `/invariants`, `/audit`, and `/docs`.
  - Server-verified session capability introspection (`GET /ui/session`), non-lossy capability pills (`OPERATOR`, `RESPONDER`, `PRODUCER`, `READ-ONLY`), tab-memory credential isolation, and multi-tab `BroadcastChannel('uns_console_session')` synchronization (`UNS_SESSION_REQUEST`, `UNS_SESSION_GRANT`, `UNS_SESSION_SYNC`, `UNS_SESSION_EXPIRE`, `UNS_SESSION_CLEAR`).
  - Responder obligation workflows (inline `Acknowledge` / `Dismiss` with responder notes, canonical owner vs. deduplicated follower lineage, automatic `409 Conflict` recovery), operator dead-letter recovery (`/operations` full outer join of `/api/v1/dlq` + `/api/v1/runtime/dead-letters`, inline `Replay` / `Resolve`), Policy Workspace (`GET /ui/policies/active`, `GET /ui/policies/revisions` across `ACTIVE`/`PREVIEW`/`DRAFT`/`RETIRED`, dry-run simulator, tagged `[TEST]` live dispatch, atomic policy reload), dual-mode Audit Timeline (`1e` "By notification" lifecycle correlation with `TIME TO RESPOND` vs. `1d` "All events" stream), and in-portal Documentation & Runbooks (`/docs`).
  - Persistent localhost recording deployment (`deploy/local/`, `docs/LOCAL_DEPLOYMENT.md`, `docs/DEPLOYMENT_SMOKE.md`) plus runnable first-party producer integration demo (`examples/mip_producer_demo.py`) and opt-in external channel smoke verifier (`scripts/opt_in_channel_smoke.py`).
- **Live PostgreSQL 16 Operational Acceptance & Sustained Load Validation (`tests/uns/test_postgres_and_load.py`):**
  - Out-of-the-box PostgreSQL driver support (`psycopg[binary]>=3.2.0` in `uns[sql]` / `uns[full]`) verified in CI against `postgres:16-alpine` across schema migrations (`uns-migrate`), policy snapshot revision locking, deduplication leader/follower promotion, lease-fenced delivery, ACK/timeout callbacks, and `SQLAlchemyReadModelAdapter` queries.
  - Sustained concurrency and load suite validating 100-request burst intake and deduplication storm coalescing, 4-worker racing `Runtime.dispatch(limit=...)` lease contention with zero duplicate external sends, and concurrent policy reload interleaved with active intake.
  - Optional `delivery_service` and `dlq_service` dispatch integration on `uns.signaling.send_signal()`.
- **Comprehensive Documentation Suite (`docs/`):**
  - Production Deployment reference (`docs/DEPLOYMENT.md`), complete API reference (`docs/API.md`), Support State Machine & Schema guide (`docs/support/STATE-MACHINE-AND-SCHEMA.md`), Troubleshooting Guides (`docs/tsg/TSG-01` through `TSG-06`), User/Integrator Manuals (`docs/user-guides/`), and MkDocs Material GitHub Pages configuration (`mkdocs.yml`, `.github/workflows/docs.yml`).

### Fixed & Hardened
- **Same-Window Dedup Replacement & Callback Retention (`uns.Runtime`, `uns.maintenance`):**
  - Linked `dedup_successor_id` and emitted `OBLIGATION_HANDED_OFF` when a new request replaces a failed solo leader within the same deduplication window, and preserved `uns_dedup` generation state while any retained notification shares `dedup_key`.
  - Refreshed per-callback lease timestamps (`self.clock()`) inside `deliver_callbacks()` and cleared `callback_pending` on 3rd-attempt exhaustion so exhausted callbacks do not block `uns-maintain` retention pruning.
- **Email, Rate-Limiter, Policy Reload, & Audit Query Hardening:**
  - Escaped HTML entities (`html.escape`) in `EmailAdapter._build_html_body()` and sanitized CR/LF characters from MIME header fields.
  - Keyed HTTP rate-limiter buckets by SHA-256 digests of verified API keys only, falling back to client IP for unauthenticated or invalid headers.
  - Constrained `POST /api/v1/policies/reload` to reject path traversal (`..`), enforce `UNS_POLICY_DIR` root boundaries when configured, and reject empty policy directories (`loaded_count == 0`).
  - Pushed `event_type` filtering and `total_count` computation into SQL `WHERE` / `COUNT(*)` clauses in `SQLAlchemyReadModelAdapter.get_audit_events()`.
  - Bounded `MetricsCollector` sample storage with ring buffers (`deque(maxlen=10_000)`), validated `X-Request-ID` headers, capped serialized request `metadata` at 64 KiB, isolated `RedisWebSocketSubscriber` onto a dedicated thread pool, and hardened `.github/workflows/python-tests.yml` with strict `mypy` verification.

## [0.1.0] - 2025-01-23

### Added

#### Core Models
- `NotificationIntent` enum: SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL
- `DeliveryMode` enum: GUARANTEED, BEST_EFFORT
- `AutonomyMode` enum: PREVIEW, SHADOW, LIVE
- `AckStatus` enum: PENDING, ACKED, DISMISSED, TIMED_OUT
- `Channel` enum: SLACK, EMAIL, WEBSOCKET, PAGERDUTY
- `Priority` enum: HIGH, NORMAL, LOW
- `DeliveryStatus` enum: PENDING, DELIVERED, SUCCESS, FAILED, DEDUPLICATED, RATE_LIMITED
- `AutonomyContext` model with hard guard validation
- `Notification` model with derived field resolution
- `NotificationResult` model for delivery outcomes
- `AckEvent` model for acknowledgment events

#### SDK
- `NotificationSDK` class as primary producer interface
- `send()` method for generic notification sending
- `send_safety()` convenience method for SAFETY intent
- `send_governance()` convenience method for GOVERNANCE intent
- `send_operational()` convenience method for OPERATIONAL intent
- `send_info()` convenience method for INFORMATIONAL intent
- Factory functions: `create_sdk()`, `get_sdk()`, `configure_sdk()`
- Hard validation guards for autonomy_context

#### Policy System
- `NotificationPolicy` model for per-notification-type rules
- `ModeOverride` model for mode-specific overrides
- `PolicyRegistry` for policy management
- Default routing logic by intent and autonomy mode
- Factory functions: `get_policy_registry()`, `configure_policy_registry()`

#### Delivery Service
- `DeliveryService` for orchestrating delivery pipeline
- Deduplication check integration
- Rate limit check integration
- WebSocket fire-and-forget delivery
- GUARANTEED sequential fallback (Slack → Email → PagerDuty)
- BEST_EFFORT concurrent delivery
- Audit logging integration

#### Channel Adapters
- `BaseAdapter` abstract base class
- `SlackAdapter` with Block Kit formatting
- `EmailAdapter` for SMTP delivery
- `WebSocketAdapter` for real-time delivery
- `PagerDutyAdapter` for incident creation
- `DeliveryResult` and `HealthCheckResult` models
- Exception hierarchy: `AdapterError`, `AdapterConfigurationError`, `AdapterDeliveryError`, `AdapterTimeoutError`

#### Deduplication
- `DeduplicationStore` abstract base class
- `InMemoryDeduplicationStore` for testing
- `RedisDeduplicationStore` for production
- `DeduplicationEngine` with configurable window
- SHA256-based key generation

#### Rate Limiting
- `RateLimitConfig` model
- `TokenBucket` implementation
- `RateLimiter` with per-channel limits
- Default limits for all channels
- Factory functions: `get_rate_limiter()`, `configure_rate_limiter()`

#### Acknowledgment
- `AckState` for internal state tracking
- `AcknowledgmentEngine` for lifecycle management
- Timeout detection and escalation
- Support for ACKED, DISMISSED, TIMED_OUT transitions
- Factory functions: `get_ack_engine()`, `configure_ack_engine()`

#### Interfaces
- `NotificationContextProvider` protocol
- `AcknowledgmentCallback` protocol
- `DefaultContextProvider` implementation
- `NoOpAcknowledgmentCallback` implementation
- `LoggingAcknowledgmentCallback` implementation
- `CompositeAcknowledgmentCallback` implementation

#### Audit
- `AuditRecord` model
- `AckAuditRecord` model
- `AuditStore` abstract base class
- `InMemoryAuditStore` for testing
- `PersistentAuditLogger` implementation

#### Database
- SQLAlchemy models for audit persistence
- `NotificationAuditRecord` table
- `AckAuditRecord` table

#### Testing
- Comprehensive test suite with 90% coverage
- Unit tests for all modules
- Integration tests for delivery pipeline
- Contract tests for invariants

#### Documentation
- README.md with quick start guide
- API reference documentation
- Architecture documentation
- Contributing guidelines

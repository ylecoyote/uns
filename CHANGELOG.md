# Changelog

All notable changes to the Unified Notification Service (UNS) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- **Unified HTTP, Console Read-Model, & WebSocket Service (`uns` / `agsignal.app:create_app`):**
  - Consolidated FastAPI service mounting `/api/v1/notifications/*`, `/api/v1/runtime/*`, `/api/v1/policies/reload`, `/ui/*`, `/ws/agents/{agent_id}`, public `/healthz`, and authenticated `/readyz` and `/metrics`.
  - Pre-accept WebSocket authentication supporting native `Authorization: Bearer` headers and browser `agsignal.v1` + `bearer.<base64url>` subprotocols with closed-list `Origin` validation.
- **Trusted-Local MCP Server (`uns-mcp`):**
  - Read-only default mode (`stdio-local`) and explicit `--enable-writes` mode (`stdio-persistent`) requiring `UNS_DATABASE_URL`, `UNS_API_PRINCIPAL`, and `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` with an owned lifespan recovery worker and runtime-bound read helpers (`F-07`).
- **Explicit Database Maintenance & Archival CLI (`uns-maintain` & `uns-migrate`):**
  - `uns-migrate` for idempotent additive schema bootstrap, successor-lineage reconstruction, and callback due-time normalization.
  - `uns-maintain` for bounded operational pruning, cursor continuation (`--after-id`), and `O_EXCL` mode-`0600` SHA-256 verified JSON group archival (`--archive`).
- **Read-Only UNS Console (`apps/ui`) & Local Recording Stack:**
  - React 18 + TypeScript + Vite SPA enforcing `INV-UI-001` (`GET /ui/*` only) with tab-memory API key authentication across `/deliveries`, `/deliveries/:id`, `/policy`, `/invariants`, and `/audit`.
  - Persistent localhost recording deployment (`scripts/deploy/local_stack.py`, `docs/LOCAL_DEPLOYMENT.md`, `docs/DEPLOYMENT_SMOKE.md`).
- **Comprehensive Documentation Suite (`docs/`):**
  - Production Deployment reference (`docs/DEPLOYMENT.md`), complete API reference (`docs/API.md`), Support State Machine & Schema guide (`docs/support/STATE-MACHINE-AND-SCHEMA.md`), Troubleshooting Guides (`docs/tsg/TSG-01` through `TSG-06`), User/Integrator Manuals (`docs/user-guides/`), and MkDocs Material GitHub Pages configuration (`mkdocs.yml`, `.github/workflows/docs.yml`).

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

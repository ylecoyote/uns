# Changelog

All notable changes to the Unified Notification Service (UNS) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Technical Details

- Python 3.10+ compatibility
- Pydantic v2 for data validation
- Redis for distributed deduplication/rate limiting
- SQLAlchemy 2.0 for database ORM
- FastAPI for HTTP API
- pytest for testing with asyncio support
- ruff for linting and formatting
- mypy for type checking

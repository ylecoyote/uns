> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Unified Notification Service (UNS)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/coverage-90%25-brightgreen.svg)](tests/)

A standalone control-plane service for autonomous agent systems, providing policy-driven notification delivery, governance decision-making, and policy management. UNS is being extracted from the [Market Insights Platform (MIP)](https://github.com/your-org/market-insights-platform) into an independent, reusable service.

## Roadmap: MIP Extraction

This repository is the target for extracting three tightly coupled subsystems from MIP into a single standalone product:

| Subsystem | Status | Description |
|-----------|--------|-------------|
| **Unified Notification Service** | Extracted | Multi-channel, policy-driven notification delivery with intent-based routing and delivery guarantees |
| **Policy Engine** | Planned | Notification policy lifecycle (DRAFT → PREVIEW → ACTIVE → RETIRED), YAML-based policy definitions, versioning, persistence, and hot-reload |
| **Agent Governance** | Planned | Autonomy-level management, decision policies, governor hooks, and circuit-breaker integration |

### Why Extract?

- **Reusability** — Governance + notifications are general-purpose capabilities, not trading-specific
- **Independent Deployment** — Decouple release cycles from the trading platform
- **Clear Domain Boundaries** — Notification delivery, policy management, and governance form a cohesive control-plane domain
- **Simplified Testing** — Standalone test suite without trading-platform dependencies

### Extraction Phases

1. **Phase 1 (Complete):** Core UNS — SDK, delivery pipeline, adapters, deduplication, rate limiting, acknowledgment tracking, audit trail
2. **Phase 2 (In Progress):** Policy Engine Stabilization — Lifecycle transitions, YAML loader, versioning, DB persistence, hot-reload, MIP-225 compliance (completed in MIP, pending port to this repo)
3. **Phase 3 (Planned):** Governance Extraction — Agent Governor, decision policies, autonomy-level state machine, governor hooks, circuit-breaker hooks
4. **Phase 4 (Planned):** Integration Consolidation — Unified API surface, shared DB schema, cross-subsystem contract tests

## Features

### Notification Service (Extracted)

- **Multi-Channel Delivery**: Slack, Email, WebSocket, PagerDuty
- **Intent-Based Routing**: SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL
- **Delivery Guarantees**: GUARANTEED and BEST_EFFORT modes
- **Mode-Aware Routing**: Different behavior for PREVIEW, SHADOW, and LIVE modes
- **Acknowledgment Tracking**: Timeout handling and escalation
- **Deduplication**: At-most-once semantics within configurable windows
- **Rate Limiting**: Per-channel token bucket rate limiting
- **Policy Registry**: Flexible per-notification-type overrides
- **Audit Trail**: Comprehensive logging for compliance

### Policy Engine (Pending Port from MIP)

- **Policy Lifecycle**: DRAFT → PREVIEW → ACTIVE → RETIRED state machine
- **YAML Policy Definitions**: File-based policy configuration with directory loading
- **Policy Versioning**: `previous_version_id` chain for version history tracking
- **Database Persistence**: `notification_policy` table with JSONB columns and content-hash dedup
- **Hot-Reload**: `POST /api/v1/policies/reload` for runtime policy refresh without restart
- **MIP-225 Compliance**: Producers cannot specify channels — policy engine owns routing decisions

### Agent Governance (Planned)

- **Autonomy-Level Management**: PREVIEW → SHADOW → LIVE state transitions
- **Decision Policies**: Configurable rules for agent autonomy boundaries
- **Governor Hooks**: Integration points for autonomy-level change notifications
- **Circuit-Breaker Hooks**: Safety circuit-breaker engage/recover notification integration

## Quick Start

### Installation

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Install with adapter dependencies
pip install -e ".[adapters]"

# Install everything
pip install -e ".[all]"
```

### Basic Usage

```python
from uuid import uuid4

from notification.models import AutonomyContext, AutonomyMode
from notification.sdk import NotificationSDK

# Create SDK instance
sdk = NotificationSDK()

# Create autonomy context (REQUIRED for all notifications)
context = AutonomyContext(
    autonomy_mode=AutonomyMode.LIVE,
    agent_id=uuid4(),
)

# Send a safety notification
result = sdk.send_safety(
    notification_type="trading.risk_breach",
    title="Risk Limit Exceeded",
    message="Position size exceeds configured risk limits. Immediate review required.",
    source="risk_engine",
    autonomy_context=context,
)

print(f"Notification sent: {result.notification_id}")
```

### Intent-Based Notifications

```python
# SAFETY: Critical issues requiring immediate attention
# - GUARANTEED delivery
# - Requires acknowledgment in LIVE mode
# - Channels: Slack + WebSocket (+ PagerDuty if irreversible)
sdk.send_safety(
    notification_type="system.critical_error",
    title="Critical System Error",
    message="Database connection pool exhausted",
    source="health_monitor",
    autonomy_context=context,
    irreversible=True,  # Adds PagerDuty in LIVE mode
)

# GOVERNANCE: Policy/compliance notifications
# - GUARANTEED delivery
# - Channels: Slack + WebSocket
sdk.send_governance(
    notification_type="compliance.policy_violation",
    title="Policy Violation Detected",
    message="Trading activity exceeds daily limits",
    source="compliance_engine",
    autonomy_context=context,
)

# OPERATIONAL: Operational alerts
# - BEST_EFFORT delivery
# - Channels: Slack
sdk.send_operational(
    notification_type="ops.deployment_complete",
    title="Deployment Complete",
    message="Version 2.1.0 deployed successfully",
    source="deployment_service",
    autonomy_context=context,
)

# INFORMATIONAL: Informational messages
# - BEST_EFFORT delivery
# - Channels: WebSocket only
sdk.send_info(
    notification_type="info.status_update",
    title="Status Update",
    message="All systems operating normally",
    source="status_monitor",
    autonomy_context=context,
)
```

## Architecture

> **See Also:** [Full Documentation](docs/README.md) for detailed architecture, API reference, and topic guides.

### Core Concepts

#### Acknowledgment Scope

> ⚠️ **CRITICAL: Acknowledgments are for Autonomy State Transitions ONLY**
>
> Acknowledgments exist to gate **autonomy mode transitions** (PREVIEW → SHADOW → LIVE) and similar **human-in-the-loop governance decisions**. They are NOT designed to block or gate real-time operations.
>
> **Acknowledgments MAY gate:**
> - Autonomy mode transitions (e.g., approving move from SHADOW to LIVE)
> - Policy changes or configuration updates
> - Approval workflows for non-time-sensitive decisions
>
> **Acknowledgments MUST NEVER gate:**
> - Order execution or routing
> - Risk unwind operations
> - Emergency stop/halt procedures
> - Any real-time trading or execution loop
>
> **Anti-Pattern Warning:** Do NOT use acknowledgment timeouts to halt execution pipelines. If your system blocks order routing waiting for an ack, you have a critical design flaw. Execution paths must remain independent of notification acknowledgment state.

#### Notification Intent

Determines urgency and delivery guarantees:

| Intent | Delivery Mode | Default Ack (LIVE) | Priority |
|--------|---------------|---------------------|----------|
| SAFETY | GUARANTEED | Required (15 min) | HIGH |
| GOVERNANCE | GUARANTEED | Not required* | HIGH |
| OPERATIONAL | BEST_EFFORT | Not required | NORMAL |
| INFORMATIONAL | BEST_EFFORT | Not required | LOW |

*GOVERNANCE has a 30-minute timeout if acknowledgment is explicitly enabled via policy.

#### Autonomy Mode

Controls channel routing:

| Mode | Behavior |
|------|----------|
| PREVIEW | All notifications via WebSocket only |
| SHADOW | Limited routing (OPERATIONAL→WebSocket, GOVERNANCE→Slack+WebSocket) |
| LIVE | Full routing based on intent |

#### Channel Routing (LIVE Mode)

| Intent | Channels |
|--------|----------|
| SAFETY | Slack + WebSocket (+ PagerDuty if irreversible) |
| GOVERNANCE | Slack + WebSocket |
| OPERATIONAL | Slack |
| INFORMATIONAL | WebSocket |

### Delivery Pipeline

The delivery service (`DeliveryService`) executes the following pipeline steps:

1. **Deduplication Check** - Skip if duplicate within window
2. **Rate Limit Check** - Apply per-channel rate limits
3. **WebSocket Delivery** - Fire-and-forget, non-blocking
4. **Persistent Channel Delivery**:
   - GUARANTEED: Sequential fallback (Slack → Email → PagerDuty)
   - BEST_EFFORT: Concurrent delivery to all channels
5. **Ack Timeout Scheduling** - If acknowledgment required
6. **Audit Logging** - Record delivery outcome

### Failure Semantics

- **GUARANTEED**: Raises `DeliveryError` if all persistent channels fail
- **BEST_EFFORT**: Logs failure, returns FAILED status, does not raise

## Configuration

### SDK Configuration

```python
from notification.sdk import configure_sdk
from notification.policies import PolicyRegistry, NotificationPolicy
from notification.interfaces import LoggingAcknowledgmentCallback

# Configure with custom components
sdk = configure_sdk(
    policy_registry=PolicyRegistry(),
    ack_callback=LoggingAcknowledgmentCallback(),
    delivery_handler=my_delivery_handler,
)
```

### Policy Overrides

```python
from notification.policies import (
    NotificationPolicy,
    ModeOverride,
    configure_policy_registry,
)
from notification.models import Channel, DeliveryMode, AutonomyMode

# Define custom policy
policy = NotificationPolicy(
    notification_type="trading.order_placed",
    delivery_mode=DeliveryMode.GUARANTEED,
    require_ack=True,
    ack_timeout_minutes=10,
    mode_overrides={
        AutonomyMode.PREVIEW: ModeOverride(
            channels=[Channel.WEBSOCKET],
            require_ack=False,
        ),
        AutonomyMode.LIVE: ModeOverride(
            channels=[Channel.SLACK, Channel.EMAIL, Channel.WEBSOCKET],
            require_ack=True,
        ),
    },
)

# Register policies
configure_policy_registry(policies=[policy])
```

### Adapter Configuration

```python
from notification.adapters import get_adapter, SlackConfig
from notification.models import Channel

# Configure Slack adapter
config = SlackConfig(
    bot_token="xoxb-your-token",
    default_channel="#alerts",
)
adapter = get_adapter(Channel.SLACK, config=config)
```

### Rate Limiting

```python
from notification.rate_limiting import configure_rate_limiter, RateLimitConfig
from notification.models import Channel

# Configure custom rate limits
config = {
    Channel.SLACK: RateLimitConfig(tokens_per_second=2.0, bucket_size=20),
    Channel.EMAIL: RateLimitConfig(tokens_per_second=0.5, bucket_size=10),
}
configure_rate_limiter(config)
```

### Deduplication

```python
from notification.deduplication import configure_deduplication_engine
from notification.deduplication import RedisDeduplicationStore

# Configure Redis-backed deduplication
store = RedisDeduplicationStore(redis_client)
configure_deduplication_engine(store=store, window_seconds=300)
```

## API Reference

### NotificationSDK

The primary interface for sending notifications.

#### Methods

| Method | Intent | Description |
|--------|--------|-------------|
| `send()` | Any | Generic send with full control |
| `send_safety()` | SAFETY | Critical safety issues |
| `send_governance()` | GOVERNANCE | Policy/compliance notifications |
| `send_operational()` | OPERATIONAL | Operational alerts |
| `send_info()` | INFORMATIONAL | Informational messages |

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `notification_type` | str | Yes | Namespaced type (e.g., "trading.order_placed") |
| `title` | str | Yes | Title (max 200 chars) |
| `message` | str | Yes | Body (max 4000 chars) |
| `source` | str | Yes | Producer identifier |
| `autonomy_context` | AutonomyContext | Yes | Agent context (hard guard) |
| `irreversible` | bool | No | Triggers PagerDuty for SAFETY in LIVE |
| `metadata` | dict | No | Additional JSON metadata |
| `correlation_id` | str | No | Optional correlation ID |
| `channels_override` | list[Channel] | No | Override derived channels |
| `dedup_key` | str | No | Custom deduplication key |

### Models

#### AutonomyContext

```python
from notification.models import AutonomyContext, AutonomyMode

context = AutonomyContext(
    autonomy_mode=AutonomyMode.LIVE,      # Required: PREVIEW, SHADOW, or LIVE
    agent_id=uuid4(),                      # Required: Unique agent identifier
    plan_id=uuid4(),                       # Optional: Plan identifier
    decision_snapshot_id=uuid4(),          # Optional: Decision snapshot
    execution_snapshot_id=uuid4(),         # Optional: Execution snapshot
    skip_snapshot_id=uuid4(),              # Optional: Skip snapshot
)
```

#### Notification

```python
from notification.models import (
    Notification,
    NotificationIntent,
    DeliveryMode,
    Channel,
    Priority,
)

notification = Notification(
    notification_type="trading.order_placed",
    intent=NotificationIntent.OPERATIONAL,
    autonomy_context=context,
    title="Order Placed",
    message="Buy order for 100 shares of AAPL",
    source="order_manager",
    delivery_mode=DeliveryMode.BEST_EFFORT,
    channels=[Channel.SLACK],
    priority=Priority.NORMAL,
)
```

#### NotificationResult

```python
from notification.models import NotificationResult, DeliveryStatus

result = NotificationResult(
    notification_id=notification.notification_id,
    status=DeliveryStatus.DELIVERED,
    channels_attempted=[Channel.SLACK, Channel.WEBSOCKET],
    channels_succeeded=[Channel.SLACK, Channel.WEBSOCKET],
    channels_failed=[],
)
```

### Enums

| Enum | Values |
|------|--------|
| `NotificationIntent` | SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL |
| `DeliveryMode` | GUARANTEED, BEST_EFFORT |
| `AutonomyMode` | PREVIEW, SHADOW, LIVE |
| `Channel` | SLACK, EMAIL, WEBSOCKET, PAGERDUTY |
| `Priority` | HIGH, NORMAL, LOW |
| `AckStatus` | PENDING, ACKED, DISMISSED, TIMED_OUT |
| `DeliveryStatus` | PENDING, DELIVERED, SUCCESS, FAILED, DEDUPLICATED, RATE_LIMITED |

## Running the Service

### HTTP API

UNS provides an HTTP API via FastAPI:

```bash
# Start the server
uvicorn mcp_server.app:app --host 0.0.0.0 --port 8000
```

### Health Check

The service exposes a `/health` endpoint for load balancer and orchestration health checks:

```bash
curl http://localhost:8000/health
# Response: {"status": "healthy"}
```

> **Note:** The `/health` endpoint returns a static healthy status for basic liveness checks. For detailed adapter and channel health information, see [Observability](docs/sections/observability.md).

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/notification/test_sdk.py

# Run tests matching pattern
pytest -k "test_safety"
```

## Development

### Project Structure

```
src/
├── notification/              # ── Notification Service (Extracted) ──
│   ├── __init__.py
│   ├── models.py              # Core data contracts
│   ├── interfaces.py          # Integration protocols
│   ├── policies.py            # Policy schema & registry
│   ├── policy_loader.py       # YAML policy loader (pending port)
│   ├── sdk.py                 # Producer interface
│   ├── service.py             # Delivery orchestration
│   ├── deduplication.py       # Deduplication engine
│   ├── rate_limiting.py       # Rate limiting
│   ├── acknowledgment.py      # Ack lifecycle management
│   ├── audit.py               # Audit logging
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py            # Base adapter protocol
│   │   ├── slack.py           # Slack adapter
│   │   ├── email.py           # Email adapter
│   │   ├── websocket.py       # WebSocket adapter
│   │   └── pagerduty.py       # PagerDuty adapter
│   └── integrations/          # ── Hook Integrations (pending port) ──
│       ├── governor_hooks.py  # Autonomy-level change notifications
│       └── circuit_breaker_hooks.py  # Circuit-breaker notifications
├── governance/                # ── Agent Governance (planned) ──
│   ├── governor.py            # Agent Governor state machine
│   ├── decision_policies.py   # Decision policy models
│   └── autonomy.py            # Autonomy-level management
├── db/
│   ├── models.py              # Database models
│   ├── audit_store.py         # Audit persistence
│   └── migrations/            # SQL migrations (pending port)
├── mcp_server/
│   └── routes_notification.py # HTTP API routes
└── config/
    └── notification_policies/ # YAML policy definitions (pending port)
tests/
└── notification/
    ├── test_models.py
    ├── test_interfaces.py
    ├── test_policies.py
    ├── test_policy_lifecycle.py   # (pending port)
    ├── test_policy_loader.py      # (pending port)
    ├── test_policy_persistence.py # (pending port)
    ├── test_policy_hot_reload.py  # (pending port)
    ├── test_sdk.py
    ├── test_service.py
    ├── test_deduplication.py
    ├── test_rate_limiting.py
    ├── test_adapters.py
    ├── test_acknowledgment.py
    └── test_audit.py
```

### Code Quality

```bash
# Lint code
ruff check src tests

# Format code
ruff format src tests

# Type check
mypy src
```

## Dependencies

### Core

- `pydantic>=2.0.0` - Data validation
- `redis>=5.0.0` - Distributed deduplication/rate limiting
- `rq>=1.15.0` - Job queue integration
- `fastapi>=0.100.0` - HTTP API
- `sqlalchemy>=2.0` - Database ORM

### Optional

- `httpx>=0.25.0` - HTTP client for adapters

### Development

- `pytest>=7.4.0` - Testing framework
- `pytest-asyncio>=0.23.0` - Async test support
- `pytest-cov>=4.1.0` - Coverage reporting
- `fakeredis>=2.20.0` - Redis mocking
- `ruff>=0.1.0` - Linting & formatting
- `mypy>=1.5.0` - Type checking

## License

MIT License - see [LICENSE](LICENSE) for details.

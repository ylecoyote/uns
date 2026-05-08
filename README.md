# AGSignal

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://img.shields.io/badge/coverage-90%25-brightgreen.svg)](tests/)

Open source governance infrastructure for autonomous agents.

AGSignal turns notifications, acknowledgments, and silence into durable governance
signals, so teams can prove who knew, when they knew, and how the system
responded. It is the missing control plane for accountable autonomy: agents emit
semantic events, AGSignal routes and persists them by policy, humans acknowledge
them through normal tools, and downstream governors can consume the resulting
audit-grade signal.

## Documentation

- [Quick Start](#quick-start) — install and send your first signal in under a minute
- [Deployment Guide](docs/DEPLOYMENT.md) — production hardening, env-var reference, operator runbook
- [Security Model](docs/SECURITY-MODEL.md) — threat model, trust boundaries, mitigations
- [Security Policy](SECURITY.md) — supported versions and vulnerability reporting
- [Contributing](CONTRIBUTING.md) — how to propose changes
- [Code of Conduct](CODE_OF_CONDUCT.md)

## Product Boundary

AGSignal is control-plane infrastructure. It does:

- Receive semantic governance events from autonomous systems
- Route by policy, intent, and autonomy context
- Persist signal state and delivery outcomes
- Record `ACKED`, `DISMISSED`, and `TIMED_OUT` as audit events
- Escalate safety paths and make silence or delivery failure visible
- Emit governance feedback to an external agent governor

AGSignal does not:

- Execute trades, actions, or commands
- Block execution loops or put humans in the execution path
- Replace Slack, PagerDuty, email, WebSocket, or MCP delivery surfaces
- Own agent reasoning, strategy, or decision logic

## Terminology

| Term | Meaning |
|------|---------|
| **AGSignal** | The product and repository identity. |
| **AGS** | Agent Governance Signaling, the product category. |
| **Governance signal** | A durable, auditable state transition created from a notification, acknowledgment, timeout, or delivery failure. |
| **AGSignal Core** | The runtime that routes, delivers, acknowledges, deduplicates, rate-limits, and audits governance signals. |
| **Signal API** | Public API surface for producers that emit governance events. New integrations should use `agsignal.*`; `notification.*` remains as a compatibility layer. |
| **AGSignal Console** | The read-first operator UI for delivery timelines, policy inspection, audit history, and invariants. |
| **UNS Core** | Historical extraction name for the notification runtime from MIP. Use this only for provenance or compatibility. |

## Features

### AGSignal Core Runtime

- **Multi-channel delivery:** Slack, Email, WebSocket, PagerDuty
- **Intent-based routing:** SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL
- **Delivery guarantees:** GUARANTEED and BEST_EFFORT modes
- **Autonomy-aware routing:** PREVIEW, SHADOW, and LIVE behavior
- **Acknowledgment tracking:** ACKED, DISMISSED, TIMED_OUT, timeout handling, escalation
- **Deduplication:** Cognitive at-most-once semantics within configurable windows
- **Producer idempotency:** Retry safety for event producers
- **Rate limiting:** Per-channel token bucket rate limiting
- **Policy registry:** Per-signal routing overrides, YAML loading, version/status metadata
- **Audit trail:** Delivery, acknowledgment, and failure records for accountability

### Policy-Driven Routing

- **Policy lifecycle:** DRAFT → PREVIEW → ACTIVE → RETIRED
- **YAML policy definitions:** File-based policy configuration with sample policies under `examples/policies/mip-uns`
- **Demo config compatibility:** `config/notification_policies` remains loadable for local demos and compatibility, but those MIP-derived policies are sample content and not AGSignal Core defaults
- **Policy versioning:** Version and status fields on policy definitions
- **Database persistence:** `notification_policy` storage with JSON columns and content-hash deduplication
- **Hot reload:** `POST /api/v1/policies/reload` for runtime refresh without restart
- **Producer guardrail:** Producers should emit intent and context; AGSignal owns channel routing

### Governance Feedback Integrations

- **Autonomy context:** PREVIEW, SHADOW, LIVE, agent ID, plan ID, and evidence references
- **Evidence links:** Decision, execution, and skip snapshot IDs can be attached without AGSignal owning those evidence models
- **Governor hooks:** Planned integration points for autonomy-level change notifications
- **Circuit-breaker hooks:** Planned safety event integrations for engage/recover notification flows

## MIP Provenance

AGSignal is being extracted from the Market Insights Platform (MIP), where
autonomous trading workflows made the governance problem concrete. MIP’s
decision transparency work produced external evidence artifacts such as
DecisionSnapshot, ExecutionSnapshot, SkipSnapshot, slippage attribution, Why UI
surfaces, and PREVIEW/SHADOW/LIVE autonomy workflows. AGSignal does not own
those models; it provides the signal layer that records who was notified, what
was acknowledged, and how that awareness can feed future autonomy decisions.

### Extraction Phases

1. **Phase 1 (Complete):** AGSignal Core runtime — SDK, delivery pipeline, adapters, deduplication, rate limiting, acknowledgment tracking, audit trail
2. **Phase 2 (In Progress):** Policy-driven routing — lifecycle metadata, YAML loader, versioning, DB persistence, hot reload, producer channel guardrails
3. **Phase 3 (Planned):** Governance feedback adapters — agent governor, autonomy state changes, circuit-breaker hooks
4. **Phase 4 (Planned):** Integration consolidation — unified API surface, shared DB schema, cross-subsystem contract tests

## Quick Start

### Installation

AGSignal ships a tiered install so producers consuming only the SDK do not
pull in the FastAPI / SQL / Redis runtime stack.

```bash
# Producer SDK only (pydantic + pyyaml).
pip install agsignal

# Self-host both AGSignal Core and Console (HTTP server + persistence + Redis + MCP + adapters).
pip install 'agsignal[full]'

# Pick-and-mix individual extras.
pip install 'agsignal[server]'    # FastAPI + uvicorn + slowapi + prometheus-client
pip install 'agsignal[redis]'     # Redis-backed idempotency / dedup / DLQ / rate limit
pip install 'agsignal[sql]'       # SQLAlchemy-backed audit and policy stores
pip install 'agsignal[mcp]'       # MCP stdio server transport
pip install 'agsignal[adapters]'  # HTTP-based channel adapters (httpx)

# Local development (test infra + every runtime extra).
pip install -e '.[dev]'
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for which extras a given
deployment posture requires.

### MCP Server

AGSignal includes a local stdio MCP server for agent clients:

```bash
uv run python -m agsignal_mcp.transports.stdio
```

The v1 server is stdio-only. HTTP/SSE transport is a deferred option until a
hosted integration requires it.

### Basic Usage

AGSignal Core now provides AGSignal-branded imports while preserving the
historical runtime package. `notification.*` imports remain supported for
existing users.

```python
from uuid import uuid4

from agsignal.models import AutonomyContext, AutonomyMode
from agsignal.models import GovernanceSignal, SignalIntent
from agsignal.sdk import SignalClient

# Create SDK instance
sdk = SignalClient()

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

`GovernanceSignal` is an AGSignal-branded alias for the current notification
model, and `SignalIntent` is an alias for `NotificationIntent`. Existing code
can continue to import `NotificationSDK`, `Notification`, and
`NotificationIntent` from `notification.*`.

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

### Signal Client Configuration

```python
from agsignal import (
    LoggingAcknowledgmentCallback,
    PolicyRegistry,
    configure_signal_client,
)

# Configure with custom components
client = configure_signal_client(
    policy_registry=PolicyRegistry(),
    ack_callback=LoggingAcknowledgmentCallback(),
    delivery_handler=my_delivery_handler,
)
```

`notification.*` imports remain supported for existing integrations; new public
examples should prefer the AGSignal-branded aliases.

### Policy Overrides

```python
from agsignal.models import AutonomyMode, Channel, DeliveryMode
from agsignal.policies import (
    ModeOverride,
    SignalPolicy,
    configure_policy_registry,
)

# Define custom policy
policy = SignalPolicy(
    notification_type="agent.order_placed",
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
from agsignal.adapters import SlackConfig, get_adapter
from agsignal.models import Channel

# Configure Slack adapter
config = SlackConfig(
    bot_token="xoxb-your-workspace-token",
    default_channel="#alerts",
)
adapter = get_adapter(Channel.SLACK, config=config)
```

### Rate Limiting

```python
from agsignal.models import Channel
from agsignal.rate_limiting import RateLimitConfig, configure_rate_limiter

# Configure custom rate limits
config = {
    Channel.SLACK: RateLimitConfig(tokens_per_second=2.0, bucket_size=20),
    Channel.EMAIL: RateLimitConfig(tokens_per_second=0.5, bucket_size=10),
}
configure_rate_limiter(config)
```

### Deduplication

```python
from agsignal.deduplication import RedisDeduplicationStore, configure_deduplication_engine

# Configure Redis-backed deduplication
store = RedisDeduplicationStore(redis_client)
configure_deduplication_engine(store=store, window_seconds=300)
```

## API Reference

### SignalClient

The primary interface for sending governance signals.

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
| `notification_type` | str | Yes | Namespaced type (e.g., "agent.order_placed") |
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
from agsignal.models import AutonomyContext, AutonomyMode

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
from agsignal.models import (
    Notification,
    NotificationIntent,
    DeliveryMode,
    Channel,
    Priority,
)

notification = Notification(
    notification_type="agent.order_placed",
    intent=NotificationIntent.OPERATIONAL,
    autonomy_context=context,
    title="Order Placed",
    message="Agent completed the guarded operation",
    source="agent-runtime",
    delivery_mode=DeliveryMode.BEST_EFFORT,
    channels=[Channel.SLACK],
    priority=Priority.NORMAL,
)
```

#### NotificationResult

```python
from agsignal.models import DeliveryStatus, NotificationResult

result = NotificationResult(
    notification_id=notification.notification_id,
    status=DeliveryStatus.DELIVERED,
    channels_attempted=[Channel.SLACK, Channel.WEBSOCKET],
    channels_succeeded=[Channel.SLACK, Channel.WEBSOCKET],
    channels_failed=[],
)
```

## Support and Security

Use GitHub issues for public bugs and feature requests. Do not report security
vulnerabilities in public issues; use the private reporting process in
[`SECURITY.md`](SECURITY.md).

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

AGSignal Core provides an HTTP API via FastAPI:

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
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/notification/test_sdk.py

# Run tests matching pattern
uv run pytest -k "test_safety"
```

## Development

### Documentation Map

AGSignal documentation is task-routed from [docs/README.md](docs/README.md):

| Task | Start Here |
|------|------------|
| Evaluate AGSignal | [Product overview](#agsignal), [Architecture](docs/ARCHITECTURE.md) |
| Quickstart: send a signal | [Quick Start](#quick-start), [API Reference](docs/API.md) |
| Configure policies | [Policy Lifecycle](docs/sections/policy-lifecycle.md), [MIP UNS Sample Policy Pack](examples/policies/mip-uns/README.md) |
| Integrate an app | [Integration Modes](docs/sections/integration-modes.md), [Host App Boundary](docs/API.md#host-app-boundary) |
| Operate and audit | [Observability](docs/sections/observability.md), [Delivery Semantics](docs/sections/delivery-semantics.md) |
| Verify implementation | [Testing Guides](docs/README.md#testing-guides), [Architecture Decisions](docs/README.md#architecture-decisions) |

### Project Structure

```
src/
├── agsignal/                  # AGSignal-branded public aliases
├── notification/              # Historical runtime package, still supported
│   ├── models.py              # Core data contracts
│   ├── interfaces.py          # Integration protocols
│   ├── policies.py            # Policy schema & registry
│   ├── policy_loader.py       # YAML policy loader and reload helpers
│   ├── policy_config.py       # Hash-bearing policy config envelopes
│   ├── policy_learning.py     # Policy delta, shadow, and guard primitives
│   ├── sdk.py                 # Producer interface
│   ├── service.py             # Delivery orchestration
│   ├── deduplication.py       # Deduplication engine
│   ├── rate_limiting.py       # Rate limiting
│   ├── acknowledgment.py      # Ack lifecycle management
│   ├── audit.py               # Audit logging
│   ├── adapters/              # Slack, email, WebSocket, PagerDuty adapters
│   └── integrations/          # Generic app boundary and optional MIP adapter
├── db/
│   ├── models.py              # Database models
│   ├── audit_store.py         # Audit persistence
│   ├── policy_store.py        # Policy persistence
│   ├── policy_learning_store.py
│   └── migrations/            # SQL migrations
├── mcp_server/
│   ├── app.py                 # AGSignal Console API app
│   └── routes_ui.py           # Read-only console endpoints
apps/ui/                       # AGSignal Console frontend
docs/                          # Task-routed docs, decisions, reports
examples/policies/mip-uns/     # Canonical MIP-derived sample policy pack
config/notification_policies/  # Demo/compatibility policy config, not defaults
tests/                         # Runtime, docs, examples, DB, and UI tests
```

### Code Quality

```bash
# Lint code
uv run ruff check src tests

# Format code
uv run ruff format src tests

# Type check
uv run mypy src
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

Apache License 2.0 - see [LICENSE](LICENSE) for details.

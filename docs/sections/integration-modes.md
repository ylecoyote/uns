# Integration Modes

This document describes how UNS (and the underlying UNS Core library) operates across canonical runtime transports and low-level SDK integration modes, clarifying the separation between core notification obligations, durable outbox persistence, and optional host-platform integrations.

## Overview

UNS (`uns.Runtime` and `uns.Client`, built on **UNS Core**) is designed as an **ATP-agnostic** (Autonomous Trading Platform agnostic) notification and acknowledgment governance service. The durable runtime, HTTP/MCP transports, and core delivery pipeline function independently of any specific trading platform or external host system.

**Key Principle:** UNS Core does NOT require ATP to function. ATP integration is one of several optional integration modes.

### Canonical Transport vs. Low-Level SDK Modes

UNS provides two layers of integration:

1. **Canonical Durable Runtime (`uns.Runtime` + `uns.Client`, HTTP `/api/v1/*`, `uns-mcp`):**
   - **Recommended for all production and multi-process deployments.**
   - Persists accepted obligations, policy provenance (`uns_resolution`), deduplication claims (`uns_dedup`), leased channel attempts, and recovery events (`uns_events`) in a shared relational database (`UNS_DATABASE_URL`).
   - Background worker loops (`await runtime.worker()`) handle leased retries, acknowledgment timeout sweeps (`TIMED_OUT`), and at-least-once terminal callback delivery (`deliver_callbacks`).
2. **Low-Level In-Process Pipeline (`notification.sdk.NotificationSDK` / `uns.SignalClient`):**
   - Provides protocol-based in-process policy resolution and adapter orchestration.
   - **Important Remediation Contract:** Calling `NotificationSDK()` without configuring a `delivery_handler` only evaluates policy and returns `DeliveryStatus.PENDING`; it does **not** perform external channel delivery. For durable delivery, use `uns.Runtime` and `uns.Client`.

## Architecture Separation

### Canonical Runtime Components (`uns`)

| Component | Module | Description |
|-----------|--------|-------------|
| **Runtime** | `uns.runtime` | Transactional outbox, leased channel dispatch, deduplication, ACK state machine, DLQ, and callback worker |
| **Client** | `uns.client` | Principal-bound async client (`send`, `simulate`) sharing a `Runtime` |
| **PolicyRuntime** | `uns.policy_runtime` | Revision-checked durable ACTIVE policy resolver and override guard |
| **HTTP Service** | `uns.app` | Unified FastAPI server mounting `/api/v1/*`, `/v1/notifications/*`, `/ui/*`, and `/ws/agents/{agent_id}` |
| **MCP Server** | `uns_mcp.factory` | Trusted-local stdio MCP server (`uns-mcp`) with read-only default and write-enabled recovery worker |
| **Retention CLI** | `uns.maintenance` | Explicit, bounded operational pruning and verified JSON archival (`uns-maintain`) |

### UNS Core (ATP-Agnostic)

The following low-level pipeline components are self-contained and require no external platform dependencies:

| Component | Module | Description |
|-----------|--------|-------------|
| **NotificationSDK** | `notification.sdk` | Low-level policy/handler facade (aliased as `uns.SignalClient`) |
| **PolicyRegistry** | `notification.policies` | Routing policy management |
| **DeliveryService** | `notification.service` | Delivery service (orchestrates the channel adapter pipeline) |
| **Channel Adapters** | `notification.adapters` | Slack, Email, PagerDuty, and WebSocket delivery |
| **DeduplicationEngine** | `notification.deduplication` | At-most-once in-memory/Redis deduplication helper |
| **RateLimiter** | `notification.rate_limiting` | Per-channel token-bucket rate limiting |
| **AcknowledgmentEngine** | `notification.acknowledgment` | Low-level ACK lifecycle state helper |
| **AuditLogger** | `notification.audit` | Compliance logging protocol and SQLAlchemy/in-memory stores |

These components use **protocol-based interfaces** (`notification.interfaces`) that allow external systems to inject implementations via dependency injection without coupling UNS Core to specific platforms.

### Integration Points (Optional)

UNS Core defines protocols for optional integration with external systems:

| Protocol | Purpose | Default Implementation |
|----------|---------|------------------------|
| `NotificationContextProvider` | Provides autonomy context | `DefaultContextProvider` |
| `AcknowledgmentCallback` | Receives ack events | `NoOpAcknowledgmentCallback` |

External systems (including ATP) implement these protocols to integrate with UNS Core, or pass an async `callback` coroutine directly to `uns.Runtime(..., callback=...)` for durable at-least-once terminal event callbacks (`ACKED`, `DISMISSED`, `TIMED_OUT`).

## Integration Modes

### Canonical Mode A: Embedded Durable Python Runtime (`uns.Runtime` + `uns.Client`)

Use `uns.Runtime` and `uns.Client` when embedding UNS directly inside a Python application or service that shares a SQLite (or SQLAlchemy) database.

```python
import asyncio
from uuid import uuid4

from uns.responses import AutonomyContextRequest, SendNotificationRequest
from notification.adapters import SlackAdapter, SlackConfig
from notification.models import AutonomyMode, NotificationIntent
from notification.service import SimpleAdapterRegistry
from uns import Client, Runtime

async def main() -> None:
    registry = SimpleAdapterRegistry()
    registry.register(
        SlackAdapter(SlackConfig(bot_token="xoxb-example", default_channel="#alerts"))
    )

    runtime = Runtime(
        "sqlite:///./uns.db",
        adapters=registry,
        create_tables=True,
    )
    client = Client(runtime, principal="risk-engine-service")

    request = SendNotificationRequest(
        notification_type="system.alert",
        intent=NotificationIntent.SAFETY,
        title="Margin Threshold Breached",
        message="Account drawdown exceeded 5% intraday threshold.",
        source="risk_monitor",
        idempotency_key="margin-breach-2026-10-22-001",
        autonomy_context=AutonomyContextRequest(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
    )

    # Preview policy resolution without side effects
    preview = await client.simulate(request)

    # Accept into durable outbox and attempt immediate leased delivery
    response = await client.send(request)
    print(response.notification_id, response.status, response.ack_status)

    # Run background recovery/timeout/callback pass
    await runtime.run_once()
    runtime.engine.dispose()

asyncio.run(main())
```

### Canonical Mode B: Remote HTTP Service (`/api/v1/notifications`)

Producers in any language can integrate over HTTP using `Authorization: Bearer <UNS_API_KEY>` (or `X-UNS-API-Key`). The unified server (`uns`) owns the durable `Runtime` and runs the background recovery, timeout, and callback worker loops automatically during FastAPI lifespan.

```python
import httpx
from uuid import uuid4

with httpx.Client(
    base_url="http://127.0.0.1:8000",
    headers={"Authorization": "Bearer replace-with-your-api-key"},
) as http:
    resp = http.post(
        "/api/v1/notifications",
        json={
            "notification_type": "system.alert",
            "intent": "SAFETY",
            "title": "Position Limit Alert",
            "message": "Gross exposure reached 95% of limit.",
            "source": "execution_gateway",
            "idempotency_key": "pos-limit-001",
            "autonomy_context": {
                "autonomy_mode": "LIVE",
                "agent_id": str(uuid4()),
            },
        },
    )
    resp.raise_for_status()
    data = resp.json()
    # Note: HTTP 202 indicates intake acceptance; inspect data["status"] for DELIVERED vs PENDING/FAILED
```

### Mode 1: Standalone (No External Integration)

When using the low-level `NotificationSDK` directly without external context providers, wire a `DeliveryService` as the `delivery_handler` (otherwise `NotificationSDK()` records `PENDING` without dispatching to adapters).

**Use Cases:**
- Unit testing and local policy/adapter pipeline verification
- Simple in-process scripts without autonomous agent registries
- Microservice architectures where context is passed explicitly

**Configuration:**

```python
from uuid import uuid4

from notification.models import AutonomyContext, AutonomyMode
from notification.sdk import NotificationSDK
from notification.service import DeliveryService, SimpleAdapterRegistry

# Create low-level SDK wired to a delivery service
registry = SimpleAdapterRegistry()
service = DeliveryService(adapter_registry=registry)
sdk = NotificationSDK(delivery_handler=service.deliver)

# Provide context explicitly with each notification
context = AutonomyContext(
    autonomy_mode=AutonomyMode.LIVE,
    agent_id=uuid4(),
)

result = sdk.send_safety(
    notification_type="system.alert",
    title="System Alert",
    message="Critical system event occurred.",
    source="monitoring_service",
    autonomy_context=context,  # Explicit context
)
```

**Characteristics:**
- No imports from external platforms
- Context provided explicitly per notification
- Default policy resolution based on intent
- Default acknowledgment handling (logging or no-op)

### Mode 2: Context Provider Integration

UNS Core receives autonomy context from an external provider, while delivery and acknowledgment tracking remain internal.

**Use Cases:**
- Systems with centralized agent state management
- Multi-agent deployments with a shared context service

**Configuration:**

```python
from uuid import uuid4

from notification.interfaces import DefaultContextProvider
from notification.models import AutonomyMode
from notification.sdk import NotificationSDK, configure_sdk
from notification.service import DeliveryService, SimpleAdapterRegistry

# Configure with context provider
provider = DefaultContextProvider(
    default_mode=AutonomyMode.SHADOW,
    default_agent_id=uuid4(),
)

service = DeliveryService(adapter_registry=SimpleAdapterRegistry())
sdk = configure_sdk(
    context_provider=provider,
    delivery_handler=service.deliver,
)

# SDK auto-populates autonomy_context from the provider
result = sdk.send_operational(
    notification_type="status.update",
    title="Status Update",
    message="Operation completed.",
    source="task_runner",
)
```

### Mode 3: Full External Integration (e.g., ATP)

UNS Core integrates with an external platform that provides both context and acknowledgment handling. For durable at-least-once callbacks in `uns.Runtime`, pass an async `callback` function to `Runtime(..., callback=...)`.

**Use Cases:**
- Autonomous trading platforms (ATP)
- Enterprise workflow systems
- Custom orchestration platforms

**Configuration:**

```python
from notification.sdk import configure_sdk

# External platform provides implementations of both protocols
from atp.notifications import (
    ATPContextProvider,
    ATPAcknowledgmentCallback,
)

sdk = configure_sdk(
    context_provider=ATPContextProvider(),
    ack_callback=ATPAcknowledgmentCallback(),
)

# SDK uses platform-provided context and routes ack events to callback
result = sdk.send_safety(
    notification_type="trading.risk_breach",
    title="Risk Breach",
    message="Position exceeds limits.",
    source="risk_engine",
)
```

### Mode 4: Generic App Adapter Boundary

UNS also ships a small host-application boundary under `notification.integrations` (re-exported via `uns.integrations`) for applications that want a structured facade rather than constructing raw requests from every governor, circuit breaker, or evidence-producing component.

This boundary is generic by design. It is **not MIP-specific** and does not import host application domain models.

```python
from uuid import uuid4

from notification.integrations import (
    AppEvidenceContext,
    AppSignalAdapter,
    AppSignalRequest,
    DefaultAppSignalContextProvider,
)
from notification.models import AutonomyMode, NotificationIntent

adapter = AppSignalAdapter(
    context_provider=DefaultAppSignalContextProvider(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id=uuid4(),
    )
)

result = adapter.send(
    AppSignalRequest(
        notification_type="app.governor.circuit_breaker_engaged",
        intent=NotificationIntent.SAFETY,
        title="Circuit breaker engaged",
        message="Host application halted execution.",
        source="host-app",
        evidence=AppEvidenceContext(
            decision_snapshot_id=uuid4(),
            metadata={"reason": "risk_limit"},
        ),
    )
)
```

Use this mode when the host application owns governor hooks, circuit-breaker state, execution/slippage evidence, or audit identifiers and needs to carry those references into UNS without making UNS own the host domain.

## Component Ownership

### UNS Core Components

These components are maintained as part of UNS / UNS Core and have no external platform dependencies:

```
src/
├── uns/
│   ├── runtime.py          # Durable outbox, lease fencing, dedup, ACK & callback worker
│   ├── client.py           # Canonical principal-bound async client
│   ├── policy_runtime.py   # Durable ACTIVE policy authority & override enforcement
│   ├── maintenance.py      # Explicit retention & verified archive CLI (uns-maintain)
│   └── migrate.py          # Idempotent additive schema bootstrap (uns-migrate)
├── uns/
│   ├── app.py              # Unified FastAPI HTTP + Console + WebSocket factory
│   ├── signaling.py        # Transport-shared send/simulate/ack/dismiss service
│   └── queries.py          # Read-model queries for /ui/* and MCP
├── uns_mcp/
│   ├── factory.py          # FastMCP server factory & lifespan worker management
│   └── tools.py            # 16 MCP tool implementations
└── notification/
    ├── models.py           # Data contracts (AutonomyContext, Notification, etc.)
    ├── interfaces.py       # Protocol definitions (NOT implementations)
    ├── policies.py         # Policy registry and resolution
    ├── sdk.py              # Low-level producer interface
    ├── service.py          # Delivery service (orchestrates adapter pipeline)
    ├── deduplication.py    # In-memory/Redis dedup engine
    ├── rate_limiting.py    # Token-bucket rate limiter
    ├── acknowledgment.py   # Low-level ack engine
    ├── audit.py            # Audit logging
    └── adapters/
        ├── base.py         # Adapter protocol & DeliveryLeaseLostError
        ├── slack.py        # Slack delivery
        ├── email.py        # Email delivery
        ├── websocket.py    # WebSocket delivery
        └── pagerduty.py    # PagerDuty delivery
```

### Integration Components (External Ownership)

These components are owned by the integrating system (e.g., ATP):

| Component | Owner | Implements |
|-----------|-------|------------|
| Runtime Terminal Callback | Integrator | `Callable[[dict[str, Any]], Awaitable[None]]` on `uns.Runtime` |
| ATP Context Provider | ATP / Integrator | `NotificationContextProvider` |
| ATP Ack Handler | ATP / Integrator | `AcknowledgmentCallback` |
| Custom WebSocket Manager | ATP / Integrator | `WebSocketConnectionManager` protocol |
| Host App Signal Adapter | Integrator | `notification.integrations.AppSignalAdapter` boundary |

**Important:** In low-level library mode, UNS Core does NOT own or maintain external WebSocket connection management. The `WebSocketAdapter` in `notification.adapters` accepts a `connection_manager` injected at configuration time. When running the unified HTTP server (`uns`), `uns.app:create_app` registers `uns.websocket.WebSocketDeliveryAdapter` wired to the server's authenticated `/ws/agents/{agent_id}` endpoint.

## WebSocket Considerations

### UNS Core WebSocket Adapter

The low-level UNS Core `WebSocketAdapter` is responsible for:
- Formatting notifications for WebSocket delivery
- Sending messages through an injected connection manager
- Returning explicit failure when no active agent socket is connected (in durable `WebSocketDeliveryAdapter`)

The low-level adapter does NOT by itself:
- Manage WebSocket connections
- Handle authentication
- Implement client reconnection logic
- Maintain external connection pools

### External WebSocket Management

Systems integrating with the low-level `WebSocketAdapter` provide their own WebSocket manager:

```python
from uuid import UUID

from notification.adapters import WebSocketAdapter, WebSocketConfig

# External system provides connection manager
class MyWebSocketManager:
    async def broadcast(self, message: str) -> int:
        # Implementation owned by external system
        return 0

    async def send_to_user(self, user_id: str, message: str) -> bool:
        return False

    async def send_to_agent(self, agent_id: UUID, message: str) -> bool:
        return False

    def get_connection_count(self) -> int:
        return 0

# Inject into UNS Core adapter
adapter = WebSocketAdapter(
    config=WebSocketConfig(),
    connection_manager=MyWebSocketManager(),
)
```

### ATP WebSocket Assumptions

When low-level UNS Core is integrated with an external host such as ATP:

1. **Connection Management**: The host's WebSocket manager handles connections (or uses the unified `uns` server's `/ws/agents/{agent_id}` endpoint).
2. **Authentication**: Handled before socket acceptance (`require_websocket_principal` in unified HTTP mode).
3. **Reconnection**: Client/integrator implements reconnection and replay-cursor resumption.
4. **Message Routing**: Messages route to the target `agent_id`.

UNS Core assumes any injected connection manager implements the `WebSocketConnectionManager` protocol: `broadcast()`, `send_to_user()`, `send_to_agent()`, and `get_connection_count()`.

## Default Implementations

UNS Core provides default implementations for standalone low-level operation:

### DefaultContextProvider

```python
from notification.interfaces import DefaultContextProvider

# Minimal provider for testing/simple deployments
provider = DefaultContextProvider(
    default_mode=AutonomyMode.PREVIEW,
    default_agent_id=uuid4(),
)

# Register specific agent contexts
provider.register_context(agent_id, context)
```

### NoOpAcknowledgmentCallback

```python
from notification.interfaces import NoOpAcknowledgmentCallback

# Silent callback that accepts but ignores events
callback = NoOpAcknowledgmentCallback()
```

### LoggingAcknowledgmentCallback

```python
from notification.interfaces import LoggingAcknowledgmentCallback

# Logs all ack events for debugging/audit
callback = LoggingAcknowledgmentCallback(logger=my_logger)
```

### CompositeAcknowledgmentCallback

```python
from notification.interfaces import CompositeAcknowledgmentCallback

# Combine multiple callbacks
composite = CompositeAcknowledgmentCallback([
    LoggingAcknowledgmentCallback(),
    MyCustomCallback(),
])
```

## Dependency Injection Pattern

Both `uns.Runtime` and low-level `NotificationSDK` use dependency injection to remain platform-agnostic:

```python
# Canonical Runtime accepts database URL, adapter registry, clock, and async callback
runtime = Runtime(
    "sqlite:///./uns.db",
    adapters=my_registry,
    callback=my_async_terminal_event_callback,
)

# Low-level SDK accepts optional protocol dependencies
sdk = NotificationSDK(
    policy_registry=my_registry,        # Optional: uses global if None
    context_provider=my_provider,       # Optional: requires explicit context if None
    ack_callback=my_callback,           # Optional: uses no-op if None
    delivery_handler=my_handler,        # Required for actual dispatch in low-level mode
)
```

This pattern ensures:
- Core runtime and SDK have no hard dependencies on external platforms
- External systems inject their implementations at runtime
- Testing can use deterministic clocks and recording adapters without modifying core code
- Different integration modes can coexist in the same codebase

## Summary

| Aspect | UNS Core / UNS Runtime | External Integration |
|--------|-----------------------------|---------------------|
| **Durable Outbox & Leases** | `uns.Runtime` (UNS Core owned) | - |
| **Notification Delivery** | UNS Core owned | - |
| **Policy Resolution** | UNS Core owned (`PolicyRuntime`) | - |
| **Deduplication** | UNS Core owned (`uns_dedup`) | - |
| **Rate Limiting** | UNS Core owned | - |
| **Acknowledgment Tracking** | UNS Core owned | - |
| **Context Provider** | Protocol defined | Implementation owned by integrator |
| **Ack Callbacks** | Protocol / `Runtime.callback` defined | Implementation owned by integrator |
| **App Adapter Boundary** | Generic facade defined | Host wiring owned by integrator |
| **WebSocket Connections** | Built-in `/ws/agents/{id}` or injected | External manager owned by integrator |
| **Agent State** | - | Owned by integrator |

**UNS / UNS Core is a self-contained notification and acknowledgment service.** Integration with ATP or other platforms is achieved through `uns.Runtime` / `uns.Client`, HTTP/MCP transports, or protocol-based dependency injection, never hard platform dependencies.

## Related Documentation

- [Architecture](../ARCHITECTURE.md) - System architecture overview
- [API Reference](../API.md) - Complete API documentation
- [Policy Lifecycle](policy-lifecycle.md) - Policy management
- [Producer Integration Guide](../user-guides/PRODUCER-INTEGRATION-GUIDE.md) - End-to-end producer cookbook
- [Documentation Index](../README.md) - Documentation index

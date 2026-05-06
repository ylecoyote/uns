# Integration Modes

This document describes how the AGSignal Core operates in different integration modes, clarifying the separation between AGSignal Core functionality and optional integrations.

## Overview

AGSignal Core is designed as an **ATP-agnostic** (Autonomous Trading Platform agnostic) notification service. The core SDK and delivery pipeline function independently of any specific trading platform or external system.

**Key Principle:** AGSignal Core does NOT require ATP to function. ATP integration is one of several optional integration modes.

## Architecture Separation

### AGSignal Core (ATP-Agnostic)

The following components are fully self-contained and require no external platform dependencies:

| Component | Module | Description |
|-----------|--------|-------------|
| **NotificationSDK** | `notification.sdk` | Primary interface for sending notifications |
| **PolicyRegistry** | `notification.policies` | Routing policy management |
| **DeliveryService** | `notification.service` | Delivery service (orchestrates the delivery pipeline) |
| **Channel Adapters** | `notification.adapters` | Slack, Email, PagerDuty delivery |
| **DeduplicationEngine** | `notification.deduplication` | At-most-once delivery semantics |
| **RateLimiter** | `notification.rate_limiting` | Per-channel rate limiting |
| **AcknowledgmentEngine** | `notification.acknowledgment` | Ack lifecycle management |
| **AuditLogger** | `notification.audit` | Compliance logging |

These components use **protocol-based interfaces** (`notification.interfaces`) that allow external systems to inject implementations without coupling AGSignal Core to specific platforms.

### Integration Points (Optional)

AGSignal Core defines protocols for optional integration with external systems:

| Protocol | Purpose | Default Implementation |
|----------|---------|------------------------|
| `NotificationContextProvider` | Provides autonomy context | `DefaultContextProvider` |
| `AcknowledgmentCallback` | Receives ack events | `NoOpAcknowledgmentCallback` |

External systems (including ATP) implement these protocols to integrate with AGSignal Core.

## Integration Modes

### Mode 1: Standalone (No External Integration)

AGSignal Core operates fully independently using default implementations and explicit context.

**Use Cases:**
- Testing and development
- Simple deployments without autonomous agents
- Microservice architectures where context is passed explicitly

**Configuration:**

```python
from uuid import uuid4

from notification.models import AutonomyContext, AutonomyMode
from notification.sdk import NotificationSDK

# Create SDK with no external dependencies
sdk = NotificationSDK()

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

AGSignal Core receives autonomy context from an external provider, but acknowledgment handling remains internal.

**Use Cases:**
- Systems with centralized agent state management
- Multi-agent deployments with shared context service

**Configuration:**

```python
from notification.interfaces import DefaultContextProvider
from notification.models import AutonomyMode
from notification.sdk import NotificationSDK, configure_sdk

# Configure with context provider
provider = DefaultContextProvider(
    default_mode=AutonomyMode.SHADOW,
    default_agent_id=uuid4(),
)

sdk = configure_sdk(context_provider=provider)

# SDK can auto-populate context
result = sdk.send_operational(
    notification_type="status.update",
    title="Status Update",
    message="Operation completed.",
    source="task_runner",
    # autonomy_context auto-populated from provider
)
```

### Mode 3: Full External Integration (e.g., ATP)

AGSignal Core integrates with an external platform that provides both context and acknowledgment handling.

**Use Cases:**
- Autonomous trading platforms (ATP)
- Enterprise workflow systems
- Custom orchestration platforms

**Configuration:**

```python
from notification.sdk import configure_sdk

# ATP provides implementations of both protocols
from atp.notifications import (
    ATPContextProvider,
    ATPAcknowledgmentCallback,
)

sdk = configure_sdk(
    context_provider=ATPContextProvider(),
    ack_callback=ATPAcknowledgmentCallback(),
)

# SDK uses ATP-provided context and routes ack events to ATP
result = sdk.send_safety(
    notification_type="trading.risk_breach",
    title="Risk Breach",
    message="Position exceeds limits.",
    source="risk_engine",
)
```

## Component Ownership

### AGSignal Core Components

These components are maintained as part of AGSignal Core and have no external dependencies:

```
notification/
├── models.py           # Data contracts (AutonomyContext, Notification, etc.)
├── interfaces.py       # Protocol definitions (NOT implementations)
├── policies.py         # Policy registry and resolution
├── sdk.py              # Producer interface
├── service.py          # Delivery service (orchestrates delivery pipeline)
├── deduplication.py    # Dedup engine
├── rate_limiting.py    # Rate limiter
├── acknowledgment.py   # Ack engine
├── audit.py            # Audit logging
└── adapters/
    ├── base.py         # Adapter protocol
    ├── slack.py        # Slack delivery
    ├── email.py        # Email delivery
    ├── websocket.py    # WebSocket delivery
    └── pagerduty.py    # PagerDuty delivery
```

### Integration Components (External Ownership)

These components are owned by the integrating system (e.g., ATP):

| Component | Owner | Implements |
|-----------|-------|------------|
| ATP Context Provider | ATP | `NotificationContextProvider` |
| ATP Ack Handler | ATP | `AcknowledgmentCallback` |
| ATP WebSocket Manager | ATP | WebSocket connection management |

**Important:** AGSignal Core does NOT own or maintain WebSocket connection management. The `WebSocketAdapter` in AGSignal Core accepts a connection/manager injected at configuration time. How connections are established, authenticated, and maintained is the responsibility of the integrating system.

## WebSocket Considerations

### AGSignal Core WebSocket Adapter

The AGSignal Core `WebSocketAdapter` is responsible for:
- Formatting notifications for WebSocket delivery
- Sending messages through an injected connection
- Fire-and-forget delivery semantics (non-blocking)

The adapter does NOT:
- Manage WebSocket connections
- Handle authentication
- Implement reconnection logic
- Maintain connection pools

### External WebSocket Management

Systems integrating with AGSignal Core provide their own WebSocket manager:

```python
from notification.adapters import WebSocketAdapter

# External system provides connection manager
class MyWebSocketManager:
    async def send(self, message: str) -> None:
        # Implementation owned by external system
        ...

# Inject into AGSignal Core adapter
adapter = WebSocketAdapter(connection_manager=MyWebSocketManager())
```

### ATP WebSocket Assumptions

When AGSignal Core is integrated with ATP:

1. **Connection Management**: ATP's WebSocket manager handles connections
2. **Authentication**: ATP handles WebSocket authentication
3. **Reconnection**: ATP implements reconnection strategies
4. **Message Routing**: ATP routes messages to appropriate clients

AGSignal Core assumes only that the injected connection manager implements a `send()` method.

## Default Implementations

AGSignal Core provides default implementations for standalone operation:

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

AGSignal Core uses dependency injection to remain platform-agnostic:

```python
# SDK accepts optional dependencies
sdk = NotificationSDK(
    policy_registry=my_registry,        # Optional: uses global if None
    context_provider=my_provider,       # Optional: requires explicit context if None
    ack_callback=my_callback,           # Optional: uses no-op if None
    delivery_handler=my_handler,        # Optional: uses default service if None
)
```

This pattern ensures:
- Core SDK has no hard dependencies on external systems
- External systems inject their implementations at runtime
- Testing can use mocks/stubs without modifying core code
- Different integration modes can coexist in the same codebase

## Summary

| Aspect | AGSignal Core | External Integration |
|--------|----------|---------------------|
| **Notification Delivery** | AGSignal Core owned | - |
| **Policy Resolution** | AGSignal Core owned | - |
| **Deduplication** | AGSignal Core owned | - |
| **Rate Limiting** | AGSignal Core owned | - |
| **Acknowledgment Tracking** | AGSignal Core owned | - |
| **Context Provider** | Protocol defined | Implementation owned by integrator |
| **Ack Callbacks** | Protocol defined | Implementation owned by integrator |
| **WebSocket Connections** | - | Owned by integrator |
| **Agent State** | - | Owned by integrator |

**AGSignal Core is a self-contained notification service.** Integration with ATP or other platforms is achieved through protocol-based dependency injection, not hard dependencies.

## Related Documentation

- [Architecture](../ARCHITECTURE.md) - System architecture overview
- [API Reference](../API.md) - Complete API documentation
- [Policy Lifecycle](policy-lifecycle.md) - Policy management
- [README](../../README.md) - Quick start guide

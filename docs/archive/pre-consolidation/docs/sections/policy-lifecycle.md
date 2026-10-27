> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Policy Lifecycle

This document describes the lifecycle, loading, versioning, and application of notification policies in the UNS Core.

## Overview

Policies define routing rules for notification types, allowing customization of:

- Delivery channels
- Delivery mode (GUARANTEED vs BEST_EFFORT)
- Acknowledgment requirements
- Deduplication windows
- Mode-specific overrides (PREVIEW, SHADOW, LIVE)

## Policy States

Policies transition through defined lifecycle states:

| State | Description | Behavior |
|-------|-------------|----------|
| **DRAFT** | Policy under development | Not loaded into registry, not applied to notifications |
| **PREVIEW** | Testing in preview environments | Applied only when `autonomy_mode=PREVIEW` |
| **ACTIVE** | Production policy | Applied to all matching notifications |
| **RETIRED** | Deprecated, kept for audit | Not applied, retained for compliance history |

### Current Implementation Note

The in-memory `PolicyRegistry` remains status-agnostic for backward
compatibility: callers may register any `NotificationPolicy` object directly.
Database-backed loading now exposes explicit lifecycle boundaries:

- `SQLAlchemyPolicyStore.load_runtime_registry()` loads only **ACTIVE** policies.
- `SQLAlchemyPolicyStore.load_shadow_registry()` loads only **PREVIEW** policies.
- `SQLAlchemyPolicyStore.load_registry()` remains backward compatible and loads
  **PREVIEW** plus **ACTIVE** by default, with ACTIVE winning when both exist for
  the same notification type.

### State Lifecycle Management

The DRAFT, PREVIEW, ACTIVE, and RETIRED states are the UNS lifecycle
contract for persisted policies.

- ACTIVE policies are runtime-enforced.
- PREVIEW policies are shadow-evaluated.
- DRAFT policies are editable.
- RETIRED policies are terminal audit history.

## Policy Loading

### Registration

Policies are registered with the global `PolicyRegistry`:

```python
from notification.policies import (
    NotificationPolicy,
    ModeOverride,
    get_policy_registry,
    configure_policy_registry,
)
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    NotificationIntent,
)

# Option 1: Register individual policies
registry = get_policy_registry()
policy = NotificationPolicy(
    notification_type="trading.order.filled",
    intent=NotificationIntent.OPERATIONAL,
    delivery_mode=DeliveryMode.BEST_EFFORT,
    channels=[Channel.SLACK],
)
registry.register(policy)

# Option 2: Configure with policy list at startup
configure_policy_registry(policies=[
    {
        "notification_type": "risk.breach.detected",
        "delivery_mode": "GUARANTEED",
        "require_ack": True,
        "channels_by_mode": {
            "LIVE": ["SLACK", "WEBSOCKET", "PAGERDUTY"],
            "SHADOW": ["WEBSOCKET"],
            "PREVIEW": ["WEBSOCKET"],
        },
    },
])
```

### Loading from Configuration

Policies can be loaded from external configuration sources:

```python
import json

# Load from JSON file
with open("policies.json") as f:
    policies_data = json.load(f)

registry = get_policy_registry()
registry.load_from_dict(policies_data)
```

### Singleton Pattern

UNS Core uses a global singleton registry:

```python
from notification.policies import PolicyRegistry, get_policy_registry, set_policy_registry

# Get the global registry (creates if None)
registry = get_policy_registry()

# Replace the global registry (for testing or reconfiguration)
custom_registry = PolicyRegistry()
set_policy_registry(custom_registry)
```

## Policy Versioning

### Current Behavior

Policies are immutable once created (Pydantic `frozen=True`). To update a policy:

```python
# Unregister old version
registry.unregister("trading.order.filled")

# Register new version
new_policy = NotificationPolicy(
    notification_type="trading.order.filled",
    delivery_mode=DeliveryMode.GUARANTEED,  # Changed
    channels=[Channel.SLACK, Channel.EMAIL],  # Changed
)
registry.register(new_policy)
```

### Planned: Version Management

Future versions will support:

- **Version tracking**: Each policy carries a version identifier
- **Hash-based integrity**: SHA256 hash of policy configuration for change detection
- **Audit trail**: Policy changes recorded with timestamp and actor
- **Rollback**: Ability to revert to previous policy version

> **Note:** These features are documented as the intended contract. See [Policy States](#policy-states) for rationale on documenting planned features.

## Policy Application

### Resolution Priority

When resolving notification values (channels, delivery_mode, require_ack):

```
1. Explicit parameter override (highest priority)
   └── Values passed directly to SDK.send()

2. Policy value
   ├── Mode-specific override (preview_override, shadow_override, live_override)
   └── Base policy value

3. SDK default (lowest priority)
   └── Derived from intent + autonomy_mode
```

### Resolution Examples

**Example 1: Policy Override**

```python
# Policy registered
policy = NotificationPolicy(
    notification_type="compliance.report.generated",
    delivery_mode=DeliveryMode.GUARANTEED,  # Policy override
    channels=[Channel.EMAIL],
)
registry.register(policy)

# SDK call - policy delivery_mode used
sdk.send_governance(
    notification_type="compliance.report.generated",
    title="Compliance Report Ready",
    message="Q4 compliance report generated.",
    autonomy_context=context,
)
# Result: delivery_mode=GUARANTEED (from policy)
```

**Example 2: SDK Default**

```python
# No policy registered for this type

sdk.send_operational(
    notification_type="system.health.check",
    title="Health Check Passed",
    message="All systems operational.",
    autonomy_context=context,
)
# Result: delivery_mode=BEST_EFFORT (SDK default for OPERATIONAL)
```

**Example 3: Mode-Specific Override**

```python
policy = NotificationPolicy(
    notification_type="trading.position.opened",
    channels=[Channel.SLACK, Channel.WEBSOCKET],  # Base channels
    preview_override=ModeOverride(
        channels=[Channel.WEBSOCKET],  # PREVIEW: WebSocket only
    ),
    live_override=ModeOverride(
        channels=[Channel.SLACK, Channel.WEBSOCKET, Channel.EMAIL],  # LIVE: Add Email
    ),
)
registry.register(policy)

# In PREVIEW mode: channels=[WEBSOCKET]
# In SHADOW mode: channels=[SLACK, WEBSOCKET] (base)
# In LIVE mode: channels=[SLACK, WEBSOCKET, EMAIL]
```

### Channel Resolution by Mode

When no policy is registered, SDK defaults apply:

| Mode | SAFETY | GOVERNANCE | OPERATIONAL | INFORMATIONAL |
|------|--------|------------|-------------|---------------|
| **LIVE** | Slack, WebSocket (+PagerDuty if irreversible) | Slack, WebSocket | Slack | WebSocket |
| **SHADOW** | Slack, WebSocket | Slack, WebSocket | WebSocket | WebSocket |
| **PREVIEW** | WebSocket | WebSocket | WebSocket | WebSocket |

### Acknowledgment Resolution

```python
# Resolution order:
if policy.require_ack is not None:
    require_ack = policy.require_ack
elif intent == SAFETY and autonomy_mode == LIVE:
    require_ack = True
else:
    require_ack = False
```

## Registry Unavailability

### Safe Fallback Behavior

When the policy registry is unavailable or returns `None` for a notification type:

1. **No exception raised** - Policy lookup failure is graceful
2. **SDK defaults apply** - Intent-based routing used
3. **Delivery continues** - Notifications are never blocked by missing policies

```python
# PolicyRegistry.get_sync() returns None if not found
policy = registry.get_sync("unknown.notification.type")
if policy is None:
    # Fall back to SDK defaults based on intent + mode
    channels = get_default_channels(intent, autonomy_mode, irreversible)
    delivery_mode = get_default_delivery_mode(intent)
    require_ack = get_default_require_ack(intent, autonomy_mode)
```

### Guaranteed Delivery Path

The fallback ensures notifications are always deliverable:

```
Policy Lookup ─────► Found? ──► Yes ──► Apply policy values
                        │
                        └──► No ───► Apply SDK defaults
                                           │
                                           ▼
                               Notification delivered
                               (never fails due to missing policy)
```

### SDK Defaults Reference

When no policy exists, these defaults apply:

**Delivery Mode:**
- SAFETY, GOVERNANCE: `GUARANTEED`
- OPERATIONAL, INFORMATIONAL: `BEST_EFFORT`

**Acknowledgment:**
- SAFETY + LIVE mode: `require_ack=True` (15-minute timeout)
- GOVERNANCE (if enabled): 30-minute timeout
- All other combinations: `require_ack=False`

**Deduplication Window:**
- Default: 300 seconds (5 minutes)
- Configurable per policy

## Policy Hashing

### Deduplication Keys

UNS Core uses SHA256 hashing for deduplication keys (not policy identification):

```python
import hashlib

dedup_key = hashlib.sha256(
    f"{notification_type}{agent_id}{source}{title}".encode()
).hexdigest()
```

### Planned: Policy Content Hashing

Future versions will support policy content hashing for:

- Change detection during reloads
- Audit trail integrity verification
- Distributed cache invalidation

> **Note:** See [Policy States](#policy-states) for rationale on documenting planned features.

## Best Practices

### Policy Organization

```python
# Namespace notification types by domain
policies = [
    # Trading domain
    {"notification_type": "trading.order.filled", ...},
    {"notification_type": "trading.order.rejected", ...},

    # Risk domain
    {"notification_type": "risk.limit.breached", ...},
    {"notification_type": "risk.exposure.warning", ...},

    # System domain
    {"notification_type": "system.health.degraded", ...},
]
```

### Testing Policies

```python
import pytest
from notification.policies import PolicyRegistry, NotificationPolicy

def test_policy_resolution():
    registry = PolicyRegistry()
    policy = NotificationPolicy(
        notification_type="test.notification",
        delivery_mode=DeliveryMode.GUARANTEED,
    )
    registry.register(policy)

    # Verify policy is found
    found = registry.get_sync("test.notification")
    assert found is not None
    assert found.delivery_mode == DeliveryMode.GUARANTEED

    # Verify fallback for missing policy
    missing = registry.get_sync("unknown.type")
    assert missing is None
```

### Production Configuration

```python
# startup.py
from notification.policies import configure_policy_registry

def configure_notifications():
    # Load policies from configuration service
    policies = load_policies_from_config()

    # Configure registry
    configure_policy_registry(policies=policies)

    # Verify critical policies are present
    registry = get_policy_registry()
    required = ["risk.breach.critical", "compliance.violation.detected"]
    for notification_type in required:
        if not registry.has_policy(notification_type):
            raise ConfigurationError(f"Missing required policy: {notification_type}")
```

## API Reference

### PolicyRegistry Methods

| Method | Description |
|--------|-------------|
| `register(policy)` | Register a policy |
| `register_many(policies)` | Register multiple policies |
| `unregister(notification_type)` | Remove a policy |
| `get_sync(notification_type)` | Retrieve policy (returns None if not found) |
| `has_policy(notification_type)` | Check if policy exists |
| `list_notification_types()` | List all registered types |
| `get_all()` | Get all policies as dict |
| `clear()` | Remove all policies |
| `load_from_dict(policies_data)` | Load from list of dicts |

### NotificationPolicy Fields

| Field | Type | Description |
|-------|------|-------------|
| `notification_type` | str | Unique identifier (required) |
| `intent` | NotificationIntent | Default intent |
| `delivery_mode` | DeliveryMode | Override delivery mode |
| `channels` | list[Channel] | Default channels |
| `require_ack` | bool | Override ack requirement |
| `ack_timeout_minutes` | int | Override ack timeout |
| `dedup_window_seconds` | int | Deduplication window |
| `preview_override` | ModeOverride | PREVIEW mode overrides |
| `shadow_override` | ModeOverride | SHADOW mode overrides |
| `live_override` | ModeOverride | LIVE mode overrides |
| `mode_overrides` | dict | Alternative mode override format |

### ModeOverride Fields

| Field | Type | Description |
|-------|------|-------------|
| `channels` | list[Channel] | Override channels for mode |
| `require_ack` | bool | Override ack requirement for mode |
| `delivery_mode` | DeliveryMode | Override delivery mode for mode |

## Related Documentation

- [Architecture](../ARCHITECTURE.md) - System architecture overview
- [API Reference](../API.md) - Complete API documentation
- [README](../../README.md) - Quick start guide

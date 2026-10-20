> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Delivery Semantics

This document provides truth tables and invariants for notification delivery behavior in the AGSignal Core.

## Overview

Delivery behavior is determined by three key dimensions:
- **Intent**: Classification of notification urgency (SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL)
- **Delivery Mode**: Reliability semantics (GUARANTEED, BEST_EFFORT)
- **Autonomy Mode**: Operating mode of the agent (PREVIEW, SHADOW, LIVE)

## Intent × Delivery Mode Mapping

Intent determines the default delivery mode:

| Intent | Delivery Mode | Rationale |
|--------|---------------|-----------|
| SAFETY | GUARANTEED | Safety-critical notifications must reach operators |
| GOVERNANCE | GUARANTEED | Compliance notifications require reliable delivery |
| OPERATIONAL | BEST_EFFORT | Status updates tolerate occasional loss |
| INFORMATIONAL | BEST_EFFORT | Low-priority updates are non-critical |

**Invariant**: SAFETY and GOVERNANCE notifications always default to GUARANTEED delivery mode.

## Intent × Autonomy Mode × Channels Truth Table

Default channel routing based on intent and autonomy mode:

| Intent | PREVIEW | SHADOW | LIVE |
|--------|---------|--------|------|
| SAFETY | WebSocket | Slack, WebSocket | Slack, WebSocket (+PagerDuty if irreversible) |
| GOVERNANCE | WebSocket | Slack, WebSocket | Slack, WebSocket |
| OPERATIONAL | WebSocket | WebSocket | Slack |
| INFORMATIONAL | WebSocket | WebSocket | WebSocket |

### Channel Routing Rules

1. **PREVIEW mode**: All notifications route to WebSocket only (no external notifications)
2. **SHADOW mode**: Elevated intents (SAFETY, GOVERNANCE) add Slack; others remain WebSocket-only
3. **LIVE mode**: Full production routing with channel escalation
4. **SAFETY + irreversible + LIVE**: Automatically adds PagerDuty for immediate human response

## Acknowledgment Requirements

| Intent | PREVIEW | SHADOW | LIVE |
|--------|---------|--------|------|
| SAFETY | No | No | **Yes** (15 min timeout) |
| GOVERNANCE | No | No | No (30 min timeout if enabled) |
| OPERATIONAL | No | No | No |
| INFORMATIONAL | No | No | No |

**Invariant**: Only SAFETY intent in LIVE mode requires acknowledgment by default.

## GUARANTEED Delivery Semantics

GUARANTEED mode provides strict delivery guarantees with sequential fallback.

### Fallback Order

```
1. Slack    (primary)
2. Email    (first fallback)
3. PagerDuty (final escalation)
```

### Delivery Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    GUARANTEED DELIVERY                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  WebSocket ────► Fire-and-forget (does not affect status)       │
│                                                                 │
│  Persistent Channels (sequential):                              │
│                                                                 │
│  Slack ────► Success? ──► YES ──► DELIVERED ──► Done            │
│                  │                                              │
│                  └── NO ──► Email ────► Success? ──► YES ──► Done│
│                                              │                  │
│                                              └── NO ──► PagerDuty│
│                                                         │       │
│                                                    Success?      │
│                                                    │      │     │
│                                                   YES    NO     │
│                                                    │      │     │
│                                                   Done   FAIL   │
│                                                          │      │
│                                              ┌───────────┴──────┐
│                                              │ Escalation       │
│                                              │ + DeliveryError  │
│                                              └──────────────────┘
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### GUARANTEED Invariants

1. **Must succeed or raise**: If all persistent channels fail, `DeliveryError` is raised
2. **Sequential fallback**: Channels are tried in order; stops at first success
3. **Escalation callback**: Before raising `DeliveryError`, escalation callback is invoked (DLQ entry point)
4. **WebSocket is separate**: WebSocket failure does NOT affect GUARANTEED status
5. **At least one persistent channel**: GUARANTEED delivery requires at least one persistent channel (Slack, Email, or PagerDuty)

### Failure Handling

| Scenario | Behavior |
|----------|----------|
| Slack success | Delivery complete, subsequent channels skipped |
| Slack fails, Email success | Delivery complete |
| Slack fails, Email fails, PagerDuty success | Delivery complete |
| All persistent channels fail | `DeliveryError` raised, escalation callback invoked |
| Rate limit exceeded | Channel marked failed, try next in fallback chain |
| No adapter registered | Channel marked failed, try next in fallback chain |

## BEST_EFFORT Delivery Semantics

BEST_EFFORT mode attempts delivery without strict guarantees.

### Delivery Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    BEST_EFFORT DELIVERY                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  All channels attempted concurrently:                           │
│                                                                 │
│  ┌─────────┐  ┌─────────┐  ┌───────────┐                        │
│  │  Slack  │  │ Email   │  │ WebSocket │   (parallel)           │
│  └────┬────┘  └────┬────┘  └─────┬─────┘                        │
│       │            │             │                              │
│       ▼            ▼             ▼                              │
│    Result       Result        Result                            │
│       │            │             │                              │
│       └────────────┴─────────────┘                              │
│                    │                                            │
│                    ▼                                            │
│             Aggregate Results                                   │
│                    │                                            │
│         ┌─────────┴─────────┐                                   │
│         │                   │                                   │
│    Any Success?        All Failed?                              │
│         │                   │                                   │
│        YES                 YES                                  │
│         │                   │                                   │
│    STATUS=SUCCESS     STATUS=FAILED                             │
│         │                   │                                   │
│        Done            Log & Done                               │
│                    (no exception)                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### BEST_EFFORT Invariants

1. **No exception on failure**: Failures are logged but do not raise exceptions
2. **Concurrent delivery**: All channels attempted in parallel for lower latency
3. **Partial success allowed**: If any channel succeeds, status is SUCCESS
4. **Must log failures**: All channel failures are logged for observability

### Failure Handling

| Scenario | Behavior |
|----------|----------|
| All channels succeed | STATUS=SUCCESS |
| Some channels succeed | STATUS=SUCCESS, failures logged |
| All channels fail | STATUS=FAILED, all failures logged, no exception |
| Rate limit exceeded | Channel marked failed, logged |

## DLQ (Dead Letter Queue) Visibility

### Escalation Path

GUARANTEED delivery failures trigger the escalation callback:

```python
# Configured at service initialization
service = DeliveryService(
    adapter_registry=registry,
    escalation_callback=my_dlq_handler,  # DLQ entry point
)
```

### DLQ Invariants

1. **Only GUARANTEED failures**: BEST_EFFORT failures do NOT trigger escalation callback
2. **Pre-exception invocation**: Callback is invoked BEFORE `DeliveryError` is raised
3. **Callback isolation**: Callback failures are logged but do not prevent `DeliveryError`
4. **Full context provided**: Callback receives notification and all channel errors

### Escalation Callback Signature

```python
def escalation_callback(
    notification: Notification,
    channel_errors: dict[Channel, str],
) -> None:
    """Handle GUARANTEED delivery failure.

    Args:
        notification: The failed notification with full context
        channel_errors: Map of channel to error message
    """
```

### DLQ Entry Information

| Field | Source | Description |
|-------|--------|-------------|
| `notification_id` | Notification | Unique identifier |
| `notification_type` | Notification | Type for policy lookup |
| `intent` | Notification | SAFETY, GOVERNANCE, etc. |
| `autonomy_context` | Notification | Agent ID, mode, plan ID |
| `channel_errors` | Delivery result | Per-channel failure reasons |
| `created_at` | Notification | Original creation timestamp |

## Degradation Behavior

### Channel Unavailability

| Scenario | GUARANTEED | BEST_EFFORT |
|----------|------------|-------------|
| Primary channel down | Fallback to next channel | Log and continue |
| All channels down | Escalate + raise exception | Log, return FAILED |
| Rate limited | Try next channel | Skip channel, log |
| Adapter not registered | Try next channel | Skip channel, log |

### System Degradation Modes

| Mode | Behavior | Visibility |
|------|----------|------------|
| Normal | Full delivery flow | Standard audit logging |
| Partial outage | Fallback channels active | Elevated logging, escalation callbacks |
| Full outage | GUARANTEED fails, BEST_EFFORT logs | DLQ entries, critical alerts |

## Audit Trail

Every delivery attempt generates audit records:

| Event | Logged Data |
|-------|-------------|
| Delivery start | notification_id, channels, mode |
| Channel attempt | channel, success/failure, error |
| Delivery complete | final status, channels_succeeded, channels_failed |
| Escalation | notification_id, channel_errors |

### Audit Invariant

All deliveries (success or failure) MUST generate an audit record containing:
- Notification metadata
- Delivery outcome
- Autonomy context (agent_id, mode)
- Timestamp

## Summary Table

| Aspect | GUARANTEED | BEST_EFFORT |
|--------|------------|-------------|
| **Exception on failure** | Yes (`DeliveryError`) | No |
| **Channel strategy** | Sequential fallback | Concurrent |
| **Escalation callback** | Yes | No |
| **Partial success** | N/A (stops at first) | Allowed |
| **Logging** | All attempts | All attempts |
| **Use case** | SAFETY, GOVERNANCE | OPERATIONAL, INFORMATIONAL |

## Related Documentation

- [Integration Modes](integration-modes.md) - Autonomy mode descriptions
- [Policy Lifecycle](policy-lifecycle.md) - Policy resolution rules
- [Architecture](../ARCHITECTURE.md) - System architecture overview

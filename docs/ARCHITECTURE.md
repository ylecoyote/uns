# Architecture

This document describes the architecture of the Unified Notification Service (UNS).

## Overview

UNS is a control-plane notification and acknowledgment service designed for autonomous agent systems. It provides:

- Policy-driven, multi-channel notification delivery
- Intent-based routing with delivery guarantees
- Mode-aware behavior for different operational contexts
- Acknowledgment tracking with timeout and escalation
- Audit trail for compliance

## Design Principles

1. **Mode-Aware Routing** - Different delivery behavior based on autonomy mode (PREVIEW/SHADOW/LIVE)
2. **Intent-Based Classification** - Notification intents drive delivery guarantees
3. **Delivery Guarantees** - GUARANTEED vs BEST_EFFORT semantics
4. **Acknowledgment Tracking** - Operator acknowledgments with timeouts and escalation
5. **Policy Registry** - Flexible per-notification-type overrides
6. **Deduplication** - At-most-once delivery within configurable windows

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Producers                                  │
│    (Trading Engine, Risk Engine, Compliance, Monitoring, etc.)      │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         NotificationSDK                              │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐   │
│  │  Validation   │  │    Policy     │  │   Value Resolution    │   │
│  │    Guards     │  │    Lookup     │  │ (channels, mode, ack) │   │
│  └───────────────┘  └───────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Delivery Service                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ Deduplication│  │ Rate Limit  │  │  Channel    │  │   Audit   │  │
│  │    Check    │  │    Check    │  │  Routing    │  │  Logging  │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│    Slack     │  │    Email     │  │  WebSocket   │  │  PagerDuty   │
│   Adapter    │  │   Adapter    │  │   Adapter    │  │   Adapter    │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Acknowledgment Engine                            │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐   │
│  │  Ack State    │  │   Timeout     │  │     Escalation        │   │
│  │   Tracking    │  │   Checking    │  │      Handler          │   │
│  └───────────────┘  └───────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Audit Store                                 │
│                   (Database / Persistence Layer)                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### SDK Layer

The SDK (`notification.sdk`) is the primary producer interface. It handles:

- **Validation Guards**: Ensures `autonomy_context` with `autonomy_mode` and `agent_id`
- **Policy Lookup**: Queries the PolicyRegistry for notification-type-specific rules
- **Value Resolution**: Derives `delivery_mode`, `channels`, `require_ack`, `priority` from:
  1. Explicit overrides
  2. Policy values
  3. Intent/mode defaults

### Policy System

The policy system (`notification.policies`) provides flexible routing rules:

```python
NotificationPolicy
├── notification_type: str
├── delivery_mode: DeliveryMode (override)
├── require_ack: bool (override)
├── ack_timeout_minutes: int (override)
└── mode_overrides: {AutonomyMode: ModeOverride}
    └── ModeOverride
        ├── channels: list[Channel]
        ├── require_ack: bool
        └── delivery_mode: DeliveryMode
```

**Resolution Priority:**
1. Explicit parameter override
2. Policy value (mode-specific, then base)
3. SDK default (intent + mode based)

### Delivery Service

The delivery service (`notification.service`) orchestrates the delivery pipeline:

```
1. Deduplication Check ──────► Skip if duplicate
         │
         ▼
2. Rate Limit Check ─────────► Skip channel if rate limited
         │
         ▼
3. WebSocket Delivery ───────► Fire-and-forget (non-blocking)
         │
         ▼
4. Persistent Channels
   ├── GUARANTEED: Sequential fallback (Slack → Email → PagerDuty)
   └── BEST_EFFORT: Concurrent delivery
         │
         ▼
5. Ack Timeout Scheduling ───► If require_ack=true
         │
         ▼
6. Audit Logging ────────────► Record outcome
```

### Channel Adapters

Adapters implement channel-specific delivery:

| Adapter | Protocol | Features |
|---------|----------|----------|
| `SlackAdapter` | HTTPS (Block Kit API) | Rich formatting, emojis, actions |
| `EmailAdapter` | SMTP | HTML/text formatting |
| `WebSocketAdapter` | WS/WSS | Real-time, fire-and-forget |
| `PagerDutyAdapter` | HTTPS (Events API) | Incident creation, severity mapping |

**Adapter Contract:**
```python
class BaseAdapter(ABC):
    @property
    def channel(self) -> Channel
    async def deliver(notification) -> DeliveryResult
    async def health_check() -> HealthCheckResult
    def format_message(notification) -> str
```

### Deduplication Engine

The deduplication engine (`notification.deduplication`) ensures at-most-once delivery:

- **Key Generation**: SHA256 hash of `notification_type + agent_id + source + title`
- **Storage**: Redis SETNX + TTL for distributed operation
- **Window**: Default 300 seconds (5 minutes), configurable per policy

### Rate Limiter

The rate limiter (`notification.rate_limiting`) uses token bucket per channel:

| Channel | Tokens/Second | Bucket Size |
|---------|---------------|-------------|
| Slack | 1.0 | 10 |
| Email | 0.5 | 5 |
| WebSocket | 10.0 | 100 |
| PagerDuty | 0.1 | 3 |

### Acknowledgment Engine

The acknowledgment engine (`notification.acknowledgment`) manages ack lifecycle:

```
PENDING ─────────────────────────────────────────────────► TIMED_OUT
    │                                                          │
    ├──► ACKED (operator acknowledged)                        │
    │                                                          │
    └──► DISMISSED (operator dismissed)                       │
                                                               │
                                                               ▼
                                              SAFETY + LIVE timeout
                                                 triggers escalation
```

**Escalation Logic:**
- SAFETY intent + LIVE mode + timeout → Triggers EscalationHandler
- Other cases → Logs and notifies via callback

### Audit System

The audit system (`notification.audit`) provides compliance logging:

- **AuditRecord**: Captures notification metadata, delivery outcome, context
- **AckAuditRecord**: Captures ack state transitions
- **Storage**: Pluggable (InMemory for testing, SQLAlchemy for production)

## Data Flow

### Notification Lifecycle

```
1. Producer calls SDK.send_*()
         │
         ▼
2. SDK validates autonomy_context
   ├── FAIL: Raise ValidationError
   └── PASS: Continue
         │
         ▼
3. SDK looks up policy for notification_type
         │
         ▼
4. SDK derives values (delivery_mode, channels, etc.)
         │
         ▼
5. SDK creates Notification object
         │
         ▼
6. SDK calls delivery_handler (if configured)
         │
         ▼
7. DeliveryService.deliver() runs pipeline
   ├── Deduplication → DEDUPLICATED
   ├── Rate limit → RATE_LIMITED
   └── Channel delivery → DELIVERED/FAILED
         │
         ▼
8. If require_ack: Register with AckEngine
         │
         ▼
9. Audit record written
         │
         ▼
10. NotificationResult returned to producer
```

### Acknowledgment Lifecycle

```
1. Notification delivered with require_ack=true
         │
         ▼
2. AckEngine.register_notification()
   - Creates AckState(status=PENDING)
   - Sets timeout_at based on ack_timeout_minutes
         │
         ▼
3. Operator action (via API/UI)
   ├── ACK: AckEngine.ack(status=ACKED)
   ├── DISMISS: AckEngine.ack(status=DISMISSED)
   └── No action: Continue waiting
         │
         ▼
4. Timeout check (periodic or on-demand)
   ├── Not expired: Continue waiting
   └── Expired: Transition to TIMED_OUT
         │
         ▼
5. If SAFETY + LIVE + TIMED_OUT:
   └── Trigger EscalationHandler
         │
         ▼
6. AckAuditRecord written for state changes
```

## Routing Rules

### Delivery Mode Resolution

```python
if policy.delivery_mode is not None:
    delivery_mode = policy.delivery_mode
elif intent in [SAFETY, GOVERNANCE]:
    delivery_mode = GUARANTEED
else:
    delivery_mode = BEST_EFFORT
```

### Channel Resolution

**LIVE Mode:**

| Intent | Channels |
|--------|----------|
| SAFETY | Slack + WebSocket (+ PagerDuty if irreversible) |
| GOVERNANCE | Slack + WebSocket |
| OPERATIONAL | Slack |
| INFORMATIONAL | WebSocket |

**PREVIEW Mode:**

All intents → WebSocket only

**SHADOW Mode:**

| Intent | Channels |
|--------|----------|
| OPERATIONAL | WebSocket |
| GOVERNANCE | Slack + WebSocket |
| Others | LIVE defaults |

### Require Ack Resolution

```python
if policy.require_ack is not None:
    require_ack = policy.require_ack
elif intent == SAFETY and autonomy_mode == LIVE:
    require_ack = True
else:
    require_ack = False
```

## Failure Handling

### GUARANTEED Mode

1. Try Slack
2. If Slack fails, try Email
3. If Email fails, try PagerDuty
4. If all fail:
   - Log error
   - Trigger escalation callback
   - Raise `DeliveryError`

### BEST_EFFORT Mode

1. Attempt all channels concurrently
2. Log any failures
3. Return `NotificationResult(status=FAILED)` if all fail
4. Do NOT raise exception

## Scalability Considerations

### Horizontal Scaling

- Stateless SDK and DeliveryService
- Redis for distributed deduplication and rate limiting
- Database for audit persistence

### Reliability

- Redis for distributed state coordination
- Sequential fallback for GUARANTEED delivery
- Audit trail for debugging and compliance

### Performance

- WebSocket fire-and-forget (non-blocking)
- Concurrent delivery for BEST_EFFORT
- Token bucket rate limiting prevents thundering herd

## Security Considerations

1. **Validation**: Hard guards on autonomy_context
2. **Rate Limiting**: Prevents abuse and channel throttling
3. **Deduplication**: Prevents duplicate delivery
4. **Audit Trail**: Compliance and forensics
5. **Policy-Based Access**: Notification type policies control routing

## Integration Points

### Context Provider Protocol

```python
class NotificationContextProvider(Protocol):
    def get_current_context(self) -> AutonomyContext
    def get_context_for_agent(agent_id: UUID) -> AutonomyContext
    def get_autonomy_mode(self) -> AutonomyMode
```

### Acknowledgment Callback Protocol

```python
class AcknowledgmentCallback(Protocol):
    def on_ack(event: AckEvent) -> None
    def on_dismiss(event: AckEvent) -> None
    def on_timeout(event: AckEvent) -> None
    def on_status_change(notification_id, old, new, metadata) -> None
```

### Delivery Handler

```python
delivery_handler: Callable[[Notification], NotificationResult]
```

Can be synchronous (testing) or queue-based (RQ, Celery) for production.

## Configuration Architecture

UNS uses singleton pattern with configure functions:

```python
# Policy Registry
configure_policy_registry(policies=[...])

# Deduplication Engine
configure_deduplication_engine(store=RedisStore(), window_seconds=300)

# Rate Limiter
configure_rate_limiter({Channel.SLACK: RateLimitConfig(...)})

# Delivery Service
configure_delivery_service(adapter_registry=..., audit_logger=...)

# Acknowledgment Engine
configure_ack_engine(callback=..., escalation_handler=...)

# SDK
configure_sdk(policy_registry=..., delivery_handler=...)
```

This allows:
- Testing with mocks (InMemory stores)
- Production with real implementations (Redis, Database)
- Gradual migration and A/B testing

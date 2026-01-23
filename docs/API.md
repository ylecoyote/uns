# API Reference

This document provides detailed API documentation for the Unified Notification Service (UNS).

## Table of Contents

- [SDK](#sdk)
- [Models](#models)
- [Policies](#policies)
- [Adapters](#adapters)
- [Deduplication](#deduplication)
- [Rate Limiting](#rate-limiting)
- [Acknowledgment](#acknowledgment)
- [Interfaces](#interfaces)

---

## SDK

The SDK module (`notification.sdk`) provides the primary interface for sending notifications.

### NotificationSDK

```python
class NotificationSDK:
    def __init__(
        self,
        policy_registry: PolicyRegistry | None = None,
        context_provider: NotificationContextProvider | None = None,
        ack_callback: AcknowledgmentCallback | None = None,
        delivery_handler: Callable[[Notification], NotificationResult] | None = None,
    ) -> None
```

Main SDK class for sending notifications through UNS.

#### Constructor Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `policy_registry` | `PolicyRegistry \| None` | Policy registry for lookups. Uses global registry if None. |
| `context_provider` | `NotificationContextProvider \| None` | Provider for autonomy context auto-population. |
| `ack_callback` | `AcknowledgmentCallback \| None` | Callback for acknowledgment events. |
| `delivery_handler` | `Callable[[Notification], NotificationResult] \| None` | Handler for delivering notifications. |

### SDK.send()

```python
def send(
    self,
    notification_type: str,
    intent: NotificationIntent,
    title: str,
    message: str,
    source: str,
    autonomy_context: AutonomyContext | None = None,
    irreversible: bool = False,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    channels_override: list[Channel] | None = None,
    delivery_mode_override: DeliveryMode | None = None,
    require_ack_override: bool | None = None,
    priority_override: Priority | None = None,
    dedup_key: str | None = None,
) -> NotificationResult
```

Generic send method with full control over all parameters.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `notification_type` | `str` | Yes | Namespaced type (e.g., "trading.order_placed") |
| `intent` | `NotificationIntent` | Yes | SAFETY, GOVERNANCE, OPERATIONAL, or INFORMATIONAL |
| `title` | `str` | Yes | Notification title (max 200 chars) |
| `message` | `str` | Yes | Notification body (max 4000 chars) |
| `source` | `str` | Yes | Producer identifier |
| `autonomy_context` | `AutonomyContext \| None` | Yes* | Agent context. Required unless context_provider configured. |
| `irreversible` | `bool` | No | If True, adds PagerDuty for SAFETY in LIVE mode |
| `metadata` | `dict[str, Any] \| None` | No | Additional JSON metadata |
| `correlation_id` | `str \| None` | No | Correlation ID for tracing |
| `channels_override` | `list[Channel] \| None` | No | Override derived channels |
| `delivery_mode_override` | `DeliveryMode \| None` | No | Override derived delivery mode |
| `require_ack_override` | `bool \| None` | No | Override derived require_ack |
| `priority_override` | `Priority \| None` | No | Override derived priority |
| `dedup_key` | `str \| None` | No | Custom deduplication key |

#### Returns

`NotificationResult` - Contains delivery outcome, channels attempted/succeeded/failed.

#### Raises

- `ValidationError` - If autonomy_context is missing or invalid

### SDK.send_safety()

```python
def send_safety(
    self,
    notification_type: str,
    title: str,
    message: str,
    source: str,
    autonomy_context: AutonomyContext | None = None,
    irreversible: bool = False,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    channels_override: list[Channel] | None = None,
    require_ack_override: bool | None = None,
    dedup_key: str | None = None,
) -> NotificationResult
```

Send a SAFETY intent notification. Implies GUARANTEED delivery and acknowledgment requirement in LIVE mode.

### SDK.send_governance()

```python
def send_governance(
    self,
    notification_type: str,
    title: str,
    message: str,
    source: str,
    autonomy_context: AutonomyContext | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    channels_override: list[Channel] | None = None,
    require_ack_override: bool | None = None,
    dedup_key: str | None = None,
) -> NotificationResult
```

Send a GOVERNANCE intent notification. Implies GUARANTEED delivery.

### SDK.send_operational()

```python
def send_operational(
    self,
    notification_type: str,
    title: str,
    message: str,
    source: str,
    autonomy_context: AutonomyContext | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    channels_override: list[Channel] | None = None,
    dedup_key: str | None = None,
) -> NotificationResult
```

Send an OPERATIONAL intent notification. Uses BEST_EFFORT delivery.

### SDK.send_info()

```python
def send_info(
    self,
    notification_type: str,
    title: str,
    message: str,
    source: str,
    autonomy_context: AutonomyContext | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    channels_override: list[Channel] | None = None,
    dedup_key: str | None = None,
) -> NotificationResult
```

Send an INFORMATIONAL intent notification. Uses BEST_EFFORT delivery, typically WebSocket only.

### Factory Functions

```python
def create_sdk(...) -> NotificationSDK
def get_sdk() -> NotificationSDK
def configure_sdk(...) -> NotificationSDK
```

| Function | Description |
|----------|-------------|
| `create_sdk()` | Factory to create a new SDK instance |
| `get_sdk()` | Get the global singleton SDK instance |
| `configure_sdk()` | Configure and return the global SDK instance |

---

## Models

The models module (`notification.models`) defines all core data types.

### Enums

#### NotificationIntent

```python
class NotificationIntent(str, Enum):
    SAFETY = "SAFETY"           # Critical safety issues
    GOVERNANCE = "GOVERNANCE"   # Policy/compliance notifications
    OPERATIONAL = "OPERATIONAL" # Operational alerts
    INFORMATIONAL = "INFORMATIONAL"  # Informational messages
```

#### DeliveryMode

```python
class DeliveryMode(str, Enum):
    GUARANTEED = "GUARANTEED"   # Must raise on all-channel failure
    BEST_EFFORT = "BEST_EFFORT" # May fail silently, must log
```

#### AutonomyMode

```python
class AutonomyMode(str, Enum):
    PREVIEW = "PREVIEW"  # WebSocket only
    SHADOW = "SHADOW"    # Limited routing
    LIVE = "LIVE"        # Full routing
```

#### Channel

```python
class Channel(str, Enum):
    SLACK = "SLACK"
    EMAIL = "EMAIL"
    WEBSOCKET = "WEBSOCKET"
    PAGERDUTY = "PAGERDUTY"
```

#### Priority

```python
class Priority(str, Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
```

#### AckStatus

```python
class AckStatus(str, Enum):
    PENDING = "PENDING"
    ACKED = "ACKED"
    DISMISSED = "DISMISSED"
    TIMED_OUT = "TIMED_OUT"
```

#### DeliveryStatus

```python
class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEDUPLICATED = "DEDUPLICATED"
    RATE_LIMITED = "RATE_LIMITED"
```

### AutonomyContext

```python
class AutonomyContext(BaseModel):
    autonomy_mode: AutonomyMode      # Required - routing key
    agent_id: UUID                    # Required - attribution
    plan_id: UUID | None = None
    decision_snapshot_id: UUID | None = None
    execution_snapshot_id: UUID | None = None
    skip_snapshot_id: UUID | None = None
```

Context about the autonomous agent. **Required for all notifications.**

### Notification

```python
class Notification(BaseModel):
    # Auto-generated
    notification_id: UUID
    created_at: datetime

    # Required
    notification_type: str           # Namespaced (domain.event)
    intent: NotificationIntent
    autonomy_context: AutonomyContext  # Hard requirement
    title: str                       # Max 200 chars
    message: str                     # Max 4000 chars
    source: str

    # Optional
    irreversible: bool = False
    metadata: dict[str, Any] = {}
    correlation_id: str | None = None

    # Derived
    delivery_mode: DeliveryMode | None
    require_ack: bool | None
    ack_timeout_minutes: int | None
    priority: Priority | None
    channels: list[Channel] = []
    dedup_key: str | None = None
```

### NotificationResult

```python
class NotificationResult(BaseModel):
    notification_id: UUID
    status: DeliveryStatus
    channels_attempted: list[Channel] = []
    channels_succeeded: list[Channel] = []
    channels_failed: list[Channel] = []
    error_message: str | None = None
    delivered_at: datetime
    deduplicated: bool = False
```

### AckEvent

```python
class AckEvent(BaseModel):
    notification_id: UUID
    status: AckStatus | None = None
    ack_status: AckStatus | None = None  # Compatibility alias
    acked_by: str | None = None
    acked_at: datetime
    metadata: dict[str, Any] = {}
```

### Constants

```python
TITLE_MAX_LENGTH = 200
MESSAGE_MAX_LENGTH = 4000

DEFAULT_ACK_TIMEOUTS = {
    NotificationIntent.SAFETY: 15,      # minutes
    NotificationIntent.GOVERNANCE: 30,  # minutes
}
```

### Helper Functions

```python
def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode
def get_default_priority(intent: NotificationIntent) -> Priority
def get_default_ack_timeout_minutes(intent: NotificationIntent) -> int | None
def get_default_require_ack(intent: NotificationIntent, autonomy_mode: AutonomyMode) -> bool
```

---

## Policies

The policies module (`notification.policies`) manages notification routing policies.

### ModeOverride

```python
class ModeOverride(BaseModel):
    channels: list[Channel] | None = None
    require_ack: bool | None = None
    delivery_mode: DeliveryMode | None = None
```

Per-mode override configuration.

### NotificationPolicy

```python
class NotificationPolicy(BaseModel):
    notification_type: str
    delivery_mode: DeliveryMode | None = None
    require_ack: bool | None = None
    ack_timeout_minutes: int | None = None
    priority_override: str | None = None
    mode_overrides: dict[AutonomyMode, ModeOverride] = {}
```

#### Methods

```python
def get_channels_for_mode(self, mode: AutonomyMode) -> list[Channel] | None
def get_require_ack_for_mode(self, mode: AutonomyMode) -> bool | None
def get_delivery_mode_for_mode(self, mode: AutonomyMode) -> DeliveryMode | None
```

### PolicyRegistry

```python
class PolicyRegistry:
    def register(self, policy: NotificationPolicy) -> None
    def get_sync(self, notification_type: str) -> NotificationPolicy | None
    async def get(self, notification_type: str) -> NotificationPolicy | None
```

### Factory Functions

```python
def get_policy_registry() -> PolicyRegistry
def configure_policy_registry(
    registry: PolicyRegistry | None = None,
    policies: list[NotificationPolicy] | None = None,
) -> PolicyRegistry
```

### Default Routing Functions

```python
def get_default_channels(
    intent: NotificationIntent,
    autonomy_mode: AutonomyMode,
    irreversible: bool = False,
) -> list[Channel]

def get_default_delivery_mode(intent: NotificationIntent) -> DeliveryMode
def get_default_require_ack(intent: NotificationIntent, autonomy_mode: AutonomyMode) -> bool
def get_default_ack_timeout(intent: NotificationIntent) -> int | None
```

---

## Adapters

The adapters module (`notification.adapters`) provides channel-specific delivery implementations.

### Base Classes

#### BaseAdapter (ABC)

```python
class BaseAdapter(ABC):
    @property
    @abstractmethod
    def channel(self) -> Channel: ...

    @abstractmethod
    async def deliver(self, notification: Notification) -> DeliveryResult: ...

    @abstractmethod
    async def health_check(self) -> HealthCheckResult: ...

    def format_message(self, notification: Notification) -> str: ...
```

#### DeliveryResult

```python
class DeliveryResult(BaseModel):
    success: bool
    channel: Channel
    message_id: str | None = None
    error: str | None = None
    timestamp: datetime
```

#### HealthCheckResult

```python
class HealthCheckResult(BaseModel):
    healthy: bool
    channel: Channel
    latency_ms: float | None = None
    error: str | None = None
```

### Adapter Implementations

- `SlackAdapter` - Slack Block Kit formatted messages
- `EmailAdapter` - SMTP email delivery
- `WebSocketAdapter` - Real-time WebSocket delivery
- `PagerDutyAdapter` - PagerDuty incident creation

### Exceptions

```python
class AdapterError(Exception): ...
class AdapterConfigurationError(AdapterError): ...
class AdapterDeliveryError(AdapterError): ...
class AdapterTimeoutError(AdapterError): ...
```

### Factory Functions

```python
def get_adapter(channel: Channel, config: Any = None) -> BaseAdapter
```

---

## Deduplication

The deduplication module (`notification.deduplication`) provides at-most-once delivery semantics.

### DeduplicationStore (ABC)

```python
class DeduplicationStore(ABC):
    @abstractmethod
    def mark_seen(self, key: str, ttl_seconds: int) -> bool: ...

    @abstractmethod
    def is_seen(self, key: str) -> bool: ...
```

### Implementations

- `InMemoryDeduplicationStore` - For testing
- `RedisDeduplicationStore` - For production

### DeduplicationEngine

```python
class DeduplicationEngine:
    def __init__(
        self,
        store: DeduplicationStore,
        default_window_seconds: int = 300,
    )

    def should_deduplicate(self, notification: Notification) -> bool
    def is_duplicate(self, notification: Notification) -> bool
```

### Factory Functions

```python
def get_deduplication_engine() -> DeduplicationEngine
def configure_deduplication_engine(
    store: DeduplicationStore | None = None,
    window_seconds: int = 300,
) -> DeduplicationEngine
```

---

## Rate Limiting

The rate limiting module (`notification.rate_limiting`) provides per-channel rate limiting.

### RateLimitConfig

```python
class RateLimitConfig(BaseModel):
    tokens_per_second: float
    bucket_size: int
```

### TokenBucket

```python
class TokenBucket:
    def __init__(self, tokens_per_second: float, bucket_size: int)
    def acquire(self) -> bool
```

### RateLimiter

```python
class RateLimiter:
    def acquire(self, channel: Channel) -> bool
    def configure(self, channel: Channel, config: RateLimitConfig) -> None
```

### Default Limits

| Channel | Tokens/Second | Bucket Size |
|---------|---------------|-------------|
| Slack | 1.0 | 10 |
| Email | 0.5 | 5 |
| WebSocket | 10.0 | 100 |
| PagerDuty | 0.1 | 3 |

### Factory Functions

```python
def get_rate_limiter() -> RateLimiter
def configure_rate_limiter(
    config: dict[Channel, RateLimitConfig] | None = None,
) -> RateLimiter
```

---

## Acknowledgment

The acknowledgment module (`notification.acknowledgment`) manages ack lifecycle.

### AckState

```python
class AckState:
    notification_id: UUID
    status: AckStatus
    require_ack: bool
    timeout_at: datetime | None
    acked_by: str | None
    acked_at: datetime | None

    @property
    def is_timed_out(self) -> bool
```

### AcknowledgmentEngine

```python
class AcknowledgmentEngine:
    def register_notification(
        self,
        notification: Notification,
    ) -> None

    def ack(
        self,
        notification_id: UUID,
        status: AckStatus,
        acked_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> AckEvent

    def check_ack_timeout(self, notification_id: UUID) -> bool
    def check_all_timeouts(self) -> list[UUID]
```

### Factory Functions

```python
def get_ack_engine() -> AcknowledgmentEngine
def configure_ack_engine(
    storage: dict | None = None,
    callback: AcknowledgmentCallback | None = None,
    escalation_handler: Callable | None = None,
) -> AcknowledgmentEngine
```

---

## Interfaces

The interfaces module (`notification.interfaces`) provides protocol-based abstractions.

### NotificationContextProvider (Protocol)

```python
class NotificationContextProvider(Protocol):
    def get_current_context(self) -> AutonomyContext: ...
    def get_context_for_agent(self, agent_id: UUID) -> AutonomyContext: ...
    def get_autonomy_mode(self) -> AutonomyMode: ...
```

### AcknowledgmentCallback (Protocol)

```python
class AcknowledgmentCallback(Protocol):
    def on_ack(self, event: AckEvent) -> None: ...
    def on_dismiss(self, event: AckEvent) -> None: ...
    def on_timeout(self, event: AckEvent) -> None: ...
    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...
```

### Default Implementations

```python
class DefaultContextProvider:
    """Minimal standalone implementation."""

class NoOpAcknowledgmentCallback:
    """Silent no-op callback."""

class LoggingAcknowledgmentCallback:
    """Logs all acknowledgment events."""

class CompositeAcknowledgmentCallback:
    """Chains multiple callbacks together."""
```

---

## Error Handling

### Exceptions

| Exception | Module | Description |
|-----------|--------|-------------|
| `ValidationError` | `sdk` | Notification validation failed |
| `DeliveryError` | `service` | GUARANTEED delivery failed |
| `AdapterError` | `adapters` | Base adapter error |
| `AdapterConfigurationError` | `adapters` | Adapter misconfiguration |
| `AdapterDeliveryError` | `adapters` | Delivery failed |
| `AdapterTimeoutError` | `adapters` | Delivery timeout |

### Error Handling Patterns

```python
from notification.sdk import NotificationSDK, ValidationError
from notification.service import DeliveryError

sdk = NotificationSDK()

try:
    result = sdk.send_safety(...)
except ValidationError as e:
    # Handle missing/invalid autonomy_context
    logger.error(f"Validation failed: {e}")
except DeliveryError as e:
    # Handle GUARANTEED delivery failure
    logger.critical(f"Delivery failed: {e}")
```

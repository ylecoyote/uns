> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# API Reference

This document provides detailed API documentation for the UNS Core.

> **Related Documentation:**
> - [Architecture](ARCHITECTURE.md) - System design and component overview
> - [Delivery Semantics](sections/delivery-semantics.md) - Delivery behavior and truth tables
> - [Integration Modes](sections/integration-modes.md) - Integration configuration options
> - [Policy Lifecycle](sections/policy-lifecycle.md) - Policy management and resolution

## Table of Contents

- [UNS Public Aliases](#uns-public-aliases)
- [SDK](#sdk)
- [Models](#models)
- [Policies](#policies)
- [Adapters](#adapters)
- [Deduplication](#deduplication)
- [Rate Limiting](#rate-limiting)
- [Acknowledgment](#acknowledgment)
- [Interfaces](#interfaces)
- [UI Endpoints](#ui-endpoints)

---

## UNS Public Aliases

UNS-branded imports are available for new applications. The current
implementation still lives in the historical `notification.*` modules, so these
aliases are intentionally non-breaking re-exports.

```python
from uns.models import GovernanceSignal, SignalIntent
from uns.sdk import SignalClient

client = SignalClient()
```

| UNS import | Backed by |
|-----------------|-----------|
| `uns.sdk.SignalClient` | `notification.sdk.NotificationSDK` |
| `uns.models.GovernanceSignal` | `notification.models.Notification` |
| `uns.models.SignalIntent` | `notification.models.NotificationIntent` |
| `uns.integrations.AppSignalAdapter` | `notification.integrations.AppSignalAdapter` |
| `uns.integrations.AppSignalRequest` | `notification.integrations.AppSignalRequest` |
| `uns.integrations.AppEvidenceContext` | `notification.integrations.AppEvidenceContext` |

Existing `notification.*` imports remain supported.

### Host App Boundary

Applications that want a generic facade can use `uns.integrations`:

```python
from uns.integrations import AppEvidenceContext, AppSignalAdapter, AppSignalRequest
```

This boundary carries app-owned evidence references into UNS without making
UNS own the host application's domain models.

MIP-shaped adapters remain available as sample/proving code at
`examples/integrations/mip/adapter.py`. They are intentionally not shipped in
the UNS wheel and not exported from the UNS-branded public
integration facade.

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

Main SDK class for sending notifications through UNS Core.

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
    intent: NotificationIntent | None = None
    delivery_mode: DeliveryMode | None = None
    channels: list[Channel] = []
    require_ack: bool | None = None
    ack_timeout_minutes: int | None = None
    dedup_window_seconds: int | None = None
    preview_override: ModeOverride | None = None
    shadow_override: ModeOverride | None = None
    live_override: ModeOverride | None = None
    mode_overrides: dict[AutonomyMode, ModeOverride] | None = None
    channels_by_mode: dict[AutonomyMode, list[Channel]] | None = None
    priority_override: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `notification_type` | `str` | Unique policy identifier (required) |
| `intent` | `NotificationIntent \| None` | Default intent if not specified in notification |
| `delivery_mode` | `DeliveryMode \| None` | Override delivery mode |
| `channels` | `list[Channel]` | Default channels for delivery |
| `require_ack` | `bool \| None` | Override acknowledgment requirement |
| `ack_timeout_minutes` | `int \| None` | Override acknowledgment timeout |
| `dedup_window_seconds` | `int \| None` | Deduplication window override |
| `preview_override` | `ModeOverride \| None` | PREVIEW mode-specific overrides |
| `shadow_override` | `ModeOverride \| None` | SHADOW mode-specific overrides |
| `live_override` | `ModeOverride \| None` | LIVE mode-specific overrides |
| `mode_overrides` | `dict \| None` | Alternative dict-based mode overrides |
| `channels_by_mode` | `dict \| None` | Per-mode channel routing (compatibility) |
| `priority_override` | `str \| None` | Priority override |

#### Methods

```python
def get_channels_for_mode(
    self, autonomy_mode: AutonomyMode, intent: NotificationIntent | None = None
) -> list[Channel] | None

def get_require_ack_for_mode(
    self, autonomy_mode: AutonomyMode, intent: NotificationIntent | None = None
) -> bool | None

def get_delivery_mode_for_mode(
    self, autonomy_mode: AutonomyMode, intent: NotificationIntent
) -> DeliveryMode

def get_ack_timeout_minutes_for_mode(
    self, autonomy_mode: AutonomyMode, intent: NotificationIntent
) -> int | None
```

### PolicyRegistry

> **See Also:** [Policy Lifecycle](sections/policy-lifecycle.md) for complete policy management documentation.

```python
class PolicyRegistry:
    def register(self, policy: NotificationPolicy) -> None
    def get_sync(self, notification_type: str) -> NotificationPolicy | None
```

**Note:** Policy lookup is synchronous via `get_sync()`. Returns `None` if no policy is registered for the notification type, triggering SDK default behavior.

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

> **See Also:** [Delivery Semantics - Acknowledgment Requirements](sections/delivery-semantics.md#acknowledgment-requirements) for the ack truth table and timeout behavior.

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

> **See Also:** [Integration Modes](sections/integration-modes.md) for detailed integration configuration options.

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

> **See Also:** [Delivery Semantics](sections/delivery-semantics.md#failure-handling) for complete failure handling documentation.

---

## UI Endpoints

The UI module (`uns.api.routes_ui`) provides read-only HTTP endpoints for the dashboard UI.

> **See Also:** [UI Data Contracts](ui/ui-data-contracts.md) for complete response shapes and filter specifications.

All UI endpoints are **read-only**. No mutating actions are permitted.

### GET /ui/deliveries

List delivery timelines with filtering.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `start_time` | string | ISO 8601, filter by created_at >= |
| `end_time` | string | ISO 8601, filter by created_at < |
| `status` | string | Filter by delivery status |
| `intent` | string | Filter by notification intent |
| `delivery_mode` | string | Filter by GUARANTEED or BEST_EFFORT |
| `agent_id` | string | Filter by agent UUID |
| `autonomy_mode` | string | Filter by PREVIEW, SHADOW, or LIVE |
| `notification_type` | string | Filter by notification type |
| `channel` | string | Filter by channel attempted |

#### Response

```python
{
    "items": [DeliveryTimelineSummary, ...],
    "pagination": {
        "next_cursor": str | None,
        "has_more": bool,
        "total_count": int | None
    }
}
```

### GET /ui/deliveries/{notification_id}

Get full delivery timeline for a specific notification.

#### Response

Returns `DeliveryTimelineResponse` with complete attempt history, channels, and autonomy context.

#### Errors

| Code | Condition |
|------|-----------|
| `not_found` | notification_id does not exist |

### GET /ui/policies/effective

Get effective policy resolution for a notification type, showing the resolution chain.

#### Query Parameters (Required)

| Parameter | Type | Description |
|-----------|------|-------------|
| `notification_type` | string | The notification type to resolve |
| `intent` | string | SAFETY, GOVERNANCE, OPERATIONAL, or INFORMATIONAL |
| `autonomy_mode` | string | PREVIEW, SHADOW, or LIVE |
| `irreversible` | bool | Whether the action is irreversible (default: false) |

#### Response

```python
{
    "notification_type": str,
    "effective": {
        "delivery_mode": "GUARANTEED" | "BEST_EFFORT",
        "channels": [Channel, ...],
        "require_ack": bool,
        "ack_timeout_minutes": int | None,
        "dedup_window_seconds": int
    },
    "resolution": {
        "delivery_mode": [ResolutionStep, ...],
        "channels": [ResolutionStep, ...],
        # ... other fields
    },
    "resolution_context": {
        "intent": str,
        "autonomy_mode": str,
        "irreversible": bool,
        "policy_found": bool,
        "policy_notification_type": str | None
    }
}
```

### GET /ui/invariants

List system invariants from the registry.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `severity` | string | Filter by HIGH, MEDIUM, or LOW |
| `enforcement_type` | string | Filter by guard, isolation, test, or exception |
| `status` | string | Filter by active or inactive |
| `search` | string | Full-text search on statement |

#### Response

```python
{
    "items": [InvariantEntry, ...],
    "pagination": {
        "next_cursor": str | None,
        "has_more": bool,
        "total_count": int | None
    }
}
```

### GET /ui/invariants/summary

Get summary statistics for system invariants.

#### Response

```python
{
    "total_count": int,
    "by_severity": {"HIGH": int, "MEDIUM": int, "LOW": int},
    "by_enforcement_type": {"guard": int, "isolation": int, "test": int, "exception": int},
    "by_status": {"active": int, "inactive": int},
    "exceptions_requiring_review": int,
    "last_updated": str  # ISO 8601
}
```

### GET /ui/audit

Query audit event stream with filtering.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `start_time` | string | ISO 8601, filter by event_time >= |
| `end_time` | string | ISO 8601, filter by event_time < |
| `event_type` | string | Filter by event type |
| `notification_id` | string | Filter by notification UUID |
| `agent_id` | string | Filter by agent UUID |
| `autonomy_mode` | string | Filter by autonomy mode |
| `correlation_id` | string | Filter by correlation ID |

#### Event Types

| Type | Description |
|------|-------------|
| `notification.created` | Notification submitted |
| `delivery.started` | Delivery attempt initiated |
| `delivery.channel_attempted` | Individual channel attempt |
| `delivery.succeeded` | Delivery completed successfully |
| `delivery.failed` | Delivery failed (all channels) |
| `delivery.deduplicated` | Notification deduplicated |
| `delivery.rate_limited` | Channel rate limited |
| `ack.pending` | Acknowledgment tracking started |
| `ack.received` | Notification acknowledged |
| `ack.dismissed` | Notification dismissed |
| `ack.timed_out` | Acknowledgment timeout |
| `escalation.triggered` | Escalation callback invoked |

#### Response

```python
{
    "items": [AuditEvent, ...],
    "pagination": {
        "next_cursor": str | None,
        "has_more": bool,
        "total_count": int | None
    }
}
```

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System design and component overview
- [Delivery Semantics](sections/delivery-semantics.md) - Delivery behavior truth tables
- [Integration Modes](sections/integration-modes.md) - Integration configuration options
- [Observability](sections/observability.md) - Health states and metrics
- [Policy Lifecycle](sections/policy-lifecycle.md) - Policy management
- [UI Data Contracts](ui/ui-data-contracts.md) - Complete UI response shapes and specifications

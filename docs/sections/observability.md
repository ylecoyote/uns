# Observability

This document describes the observability model for the Unified Notification Service (UNS), including health states, metrics, DLQ visibility, and monitoring semantics.

## Overview

UNS provides observability through:
- **Adapter health status**: Per-channel health reporting (HEALTHY, DEGRADED, UNHEALTHY)
- **Delivery metrics**: Latency, success/failure rates, retry counts
- **DLQ visibility**: Escalation callbacks for GUARANTEED delivery failures
- **Acknowledgment tracking**: Timeout counts and escalation events
- **Audit logging**: Comprehensive delivery audit trail

## Health States

### AdapterStatus Enum

Each channel adapter reports health via `AdapterStatus`:

| Status | Meaning | Operational Impact |
|--------|---------|-------------------|
| `HEALTHY` | Adapter fully operational | Normal delivery flow |
| `DEGRADED` | Partial functionality, elevated latency or intermittent failures | Delivery attempted but may require fallback |
| `UNHEALTHY` | Adapter cannot deliver | Immediate fallback to next channel |

**Definition** (from `notification/adapters/base.py`):

```python
class AdapterStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
```

### What "DEGRADED" Means for UNS

A DEGRADED adapter indicates:

1. **Elevated latency**: Response times exceed normal thresholds but delivery is possible
2. **Intermittent failures**: Some delivery attempts fail but retries may succeed
3. **Reduced reliability**: The channel is operational but not meeting SLA targets
4. **Partial service**: External dependencies (e.g., Slack API) may be experiencing issues

**Operational Guidance for DEGRADED State:**

| Scenario | Behavior | Operator Action |
|----------|----------|-----------------|
| Primary channel DEGRADED | UNS attempts delivery, may fallback faster | Monitor for transition to UNHEALTHY |
| All channels DEGRADED | Delivery continues with elevated failure risk | Investigate root cause, prepare for outage |
| Single adapter DEGRADED | Other channels unaffected | Review adapter-specific diagnostics |

**DEGRADED vs UNHEALTHY:**
- DEGRADED: "Try delivery but expect some failures" - UNS will attempt the channel
- UNHEALTHY: "Do not attempt delivery" - UNS will skip to fallback immediately

### HealthCheckResult

Health checks return diagnostic information:

```python
@dataclass
class HealthCheckResult:
    status: AdapterStatus         # HEALTHY, DEGRADED, UNHEALTHY
    message: str                  # Human-readable status
    latency_ms: float | None      # Response time in milliseconds
    metadata: dict[str, Any]      # Additional diagnostics
```

### Health Check Infrastructure

Adapters implement health checks individually:

```python
# Check all adapters via registry
from notification.adapters import AdapterRegistry

registry = AdapterRegistry()
results = await registry.health_check_all()
# Returns: dict[Channel, HealthCheckResult]
```

**Per-Adapter Health Check Behavior:**

| Adapter | Health Check Method | Notes |
|---------|---------------------|-------|
| Slack | API connectivity test | Tests auth and channel access |
| Email | SMTP connection test | Verifies SMTP server reachability |
| PagerDuty | API ping | Note: Events API has no health endpoint; returns HEALTHY if configured |
| WebSocket | Connection state | Always HEALTHY (fire-and-forget semantics) |

## /health Endpoint

### Current Implementation

The HTTP health endpoint is located at `GET /health`:

```python
# src/mcp_server/app.py
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
```

### Endpoint Semantics

**Current behavior**: The `/health` endpoint returns a static `{"status": "healthy"}` response. It does NOT currently:
- Invoke adapter health checks
- Check DLQ depth
- Verify pending acknowledgment timeouts
- Report per-channel status

**Response format**:

```json
{
  "status": "healthy"
}
```

**Important**: The current `/health` endpoint is a minimal stub for load balancer health checks. For comprehensive system health, use the adapter registry's `health_check_all()` method programmatically.

### Future Considerations

A full health endpoint could include:

| Field | Description |
|-------|-------------|
| `status` | Overall system status (healthy/degraded/unhealthy) |
| `adapters` | Per-channel health status |
| `pending_acks` | Count of pending acknowledgments |
| `ack_timeouts_last_hour` | Number of timeout events |
| `dlq_depth` | Count of failed GUARANTEED deliveries (if tracked) |

## DLQ (Dead Letter Queue) Visibility

### Escalation Callback Architecture

DLQ functionality is implemented via the **escalation callback** mechanism, not a persistent queue. When GUARANTEED delivery fails all channels, the callback is invoked:

```python
# Configure at service initialization
from notification.service import configure_delivery_service

service = configure_delivery_service(
    adapter_registry=registry,
    escalation_callback=my_dlq_handler,  # DLQ entry point
)
```

### DLQ Invariants

| Rule | Description |
|------|-------------|
| **GUARANTEED-only** | Only GUARANTEED delivery failures trigger escalation; BEST_EFFORT failures do NOT |
| **Pre-exception** | Callback invoked BEFORE `DeliveryError` is raised |
| **Isolated failures** | Callback exceptions are logged but do not prevent `DeliveryError` |
| **Full context** | Callback receives complete notification and error details |

### Escalation Callback Signature

```python
def escalation_callback(
    notification: Notification,
    channel_errors: dict[Channel, str],
) -> None:
    """Handle GUARANTEED delivery failure.

    Args:
        notification: The failed notification with full context
        channel_errors: Map of channel to error message for each failed channel
    """
```

### DLQ Entry Information

The escalation callback receives:

| Field | Source | Description |
|-------|--------|-------------|
| `notification_id` | `Notification` | Unique identifier |
| `notification_type` | `Notification` | Type for policy lookup |
| `intent` | `Notification` | SAFETY, GOVERNANCE, OPERATIONAL, INFORMATIONAL |
| `autonomy_context` | `Notification` | Agent ID, autonomy mode, plan ID |
| `title` | `Notification` | Notification title |
| `message` | `Notification` | Notification body |
| `source` | `Notification` | Originating system |
| `correlation_id` | `Notification` | Optional correlation ID |
| `created_at` | `Notification` | Original creation timestamp |
| `metadata` | `Notification` | Additional key-value pairs |
| `channel_errors` | Callback arg | Per-channel failure reasons |

### Operator Impact of DLQ

**Visibility Responsibility**: UNS does not persist DLQ entries internally. Operators must implement DLQ visibility in their escalation callback:

```python
# Example: DLQ callback with external persistence
def dlq_handler(notification: Notification, channel_errors: dict[Channel, str]) -> None:
    # Persist to external DLQ store
    dlq_store.insert({
        "notification_id": str(notification.notification_id),
        "intent": notification.intent.value,
        "channel_errors": {c.value: e for c, e in channel_errors.items()},
        "failed_at": datetime.now(UTC).isoformat(),
    })

    # Alert operations team
    alerting_service.send_alert(
        severity="critical",
        message=f"GUARANTEED delivery failed: {notification.notification_id}",
    )
```

**DLQ Metrics (Operator-Provided)**:

| Metric | Description | Owner |
|--------|-------------|-------|
| `dlq_depth` | Count of unprocessed DLQ entries | Operator's DLQ store |
| `dlq_oldest_entry_age` | Time since oldest entry was created | Operator's DLQ store |
| `dlq_processing_rate` | Rate of DLQ entries being resolved | Operator's monitoring |

## Key Metrics

### Metric Categories

UNS exposes the following metric categories through logging and callback hooks:

#### 1. Delivery Latency

| Metric | Source | Description |
|--------|--------|-------------|
| `adapter_latency_ms` | `HealthCheckResult.latency_ms` | Per-adapter response time |
| `delivery_duration_ms` | Computed from timestamps | End-to-end delivery time |
| `channel_attempt_duration_ms` | Per-channel timing | Time for individual channel attempt |

**Intent**: Identify slow channels and optimize fallback ordering.

#### 2. Delivery Success/Failure

| Metric | Source | Description |
|--------|--------|-------------|
| `channels_attempted` | `NotificationResult` | List of channels tried |
| `channels_succeeded` | `NotificationResult` | Channels that delivered |
| `channels_failed` | `NotificationResult` | Channels that failed |
| `delivery_status` | `NotificationResult.status` | SUCCESS, FAILED, DEDUPLICATED |

**Intent**: Track delivery reliability and identify failing channels.

#### 3. Retry/Fallback Counts

| Metric | Source | Description |
|--------|--------|-------------|
| `fallback_count` | Computed from `channels_attempted` | Number of fallback attempts in GUARANTEED mode |
| `fallback_triggered` | Boolean | Whether primary channel failed |

**Intent**: Monitor GUARANTEED delivery health; frequent fallbacks indicate channel instability.

**Note**: UNS does not implement automatic retries within a single channel. Fallback is sequential across channels (Slack → Email → PagerDuty).

#### 4. DLQ Depth

| Metric | Source | Description |
|--------|--------|-------------|
| `dlq_entry_count` | Escalation callback | Count of GUARANTEED failures |

**Intent**: Monitor undelivered critical notifications requiring manual intervention.

**Implementation**: DLQ depth is tracked by the operator's escalation callback implementation, not UNS core.

#### 5. Acknowledgment Timeout Counts

| Metric | Source | Description |
|--------|--------|-------------|
| `pending_acks` | `AckStorage.get_pending_notifications()` | Notifications awaiting ack |
| `timed_out_acks` | `AcknowledgmentEngine.check_all_timeouts()` | Notifications that timed out |
| `safety_escalations` | Escalation callback | SAFETY timeouts in LIVE mode |

**Intent**: Identify operator response time issues and SAFETY escalation patterns.

**Default Timeout Values**:

| Intent | Timeout | Escalation on Timeout |
|--------|---------|----------------------|
| SAFETY | 15 minutes | Yes (LIVE mode only) |
| GOVERNANCE | 30 minutes | No |
| OPERATIONAL | None | N/A |
| INFORMATIONAL | None | N/A |

#### 6. Rate Limiting Events

| Metric | Source | Description |
|--------|--------|-------------|
| `rate_limit_exceeded` | Logged event | Channel rate limit hit |
| `rate_limit_channel` | Logged event | Which channel was limited |

**Intent**: Detect notification storms and tune rate limits.

**Default Rate Limits**:

| Channel | Rate (tokens/sec) |
|---------|-------------------|
| Slack | 1.0 |
| Email | 0.5 |
| WebSocket | 10.0 |
| PagerDuty | 0.1 |

### Logging Events

Key events logged at various levels:

| Event | Level | Data |
|-------|-------|------|
| Delivery start | INFO | notification_id, channels, mode |
| Channel attempt success | INFO | notification_id, channel |
| Channel attempt failure | WARNING | notification_id, channel, error |
| GUARANTEED failure | ERROR | notification_id, channel_errors |
| Escalation callback failure | ERROR | notification_id, callback error |
| Ack timeout | WARNING | notification_id, intent, autonomy_mode |
| SAFETY escalation | CRITICAL | notification_id |
| Rate limit exceeded | WARNING | channel |

### Metric Collection Patterns

UNS uses standard Python logging. Operators can collect metrics by:

1. **Log aggregation**: Parse structured logs (JSON logging recommended)
2. **Callback hooks**: Implement `AuditLogger` and `AcknowledgmentCallback` protocols
3. **Adapter registry polling**: Periodically call `health_check_all()`

**Example: Custom Metrics via AuditLogger**:

```python
from notification.service import AuditLogger
from notification.models import Notification, NotificationResult

class MetricsAuditLogger:
    def __init__(self, metrics_client):
        self.metrics = metrics_client

    def log_delivery(
        self,
        notification: Notification,
        result: NotificationResult,
        metadata: dict | None = None,
    ) -> None:
        self.metrics.increment("delivery.total")
        self.metrics.increment(f"delivery.{result.status.value.lower()}")
        self.metrics.histogram(
            "delivery.channels_attempted",
            len(result.channels_attempted),
        )
        for channel in result.channels_failed:
            self.metrics.increment(f"delivery.failure.{channel.value}")
```

## System Degradation Modes

### Degradation Scenarios

| Scenario | GUARANTEED Behavior | BEST_EFFORT Behavior | Visibility |
|----------|---------------------|----------------------|------------|
| **Normal** | Full delivery flow | Full delivery flow | Standard logging |
| **Single channel down** | Fallback to next channel | Log and continue | Elevated logging |
| **Primary channel DEGRADED** | Attempt then fallback | Attempt with lower confidence | Health check shows DEGRADED |
| **All channels DEGRADED** | Attempt all, may fail | Attempt all, log failures | All health checks DEGRADED |
| **All channels UNHEALTHY** | Escalate + raise exception | Log FAILED, no exception | DLQ entries, critical alerts |

### Degradation Detection

Operators should monitor for:

1. **Elevated fallback rates**: More than 10% of GUARANTEED deliveries using fallback channels
2. **Increasing ack timeouts**: Rising count of SAFETY/GOVERNANCE timeouts
3. **DLQ growth**: Any entries in DLQ require investigation
4. **Adapter health transitions**: Any adapter moving to DEGRADED or UNHEALTHY

### Recovery Patterns

| State Transition | Operator Action |
|------------------|-----------------|
| HEALTHY → DEGRADED | Monitor closely, investigate external service |
| DEGRADED → UNHEALTHY | Expect delivery failures, check fallback channels |
| UNHEALTHY → DEGRADED | Tentatively resume, monitor error rates |
| DEGRADED → HEALTHY | Normal operations, review incident |

## Audit Trail

All deliveries generate audit records through the `AuditLogger` protocol:

| Event | Logged Fields |
|-------|---------------|
| Delivery start | notification_id, channels, delivery_mode |
| Channel attempt | channel, success/failure, error |
| Delivery complete | status, channels_succeeded, channels_failed |
| Escalation | notification_id, channel_errors |
| Ack registered | notification_id, intent, timeout |
| Ack received | notification_id, status, acked_by |
| Ack timeout | notification_id, intent, autonomy_mode |

### Audit Invariant

Every delivery (success or failure) MUST generate an audit record containing:
- Notification metadata
- Delivery outcome
- Autonomy context (agent_id, mode)
- Timestamp

## Summary

| Aspect | Description | Implementation Status |
|--------|-------------|----------------------|
| **Adapter health** | Per-channel HEALTHY/DEGRADED/UNHEALTHY | Implemented |
| **/health endpoint** | Returns static `{"status": "healthy"}` | Minimal stub |
| **DLQ visibility** | Via escalation callback | Operator-implemented |
| **Delivery metrics** | Via logging and audit callbacks | Implemented |
| **Ack timeout tracking** | Via AcknowledgmentEngine | Implemented |
| **Rate limit metrics** | Via logging | Implemented |
| **External metrics export** | Prometheus, StatsD, etc. | Not implemented |
| **Distributed tracing** | OpenTelemetry, Jaeger | Not implemented |

## Related Documentation

- [Delivery Semantics](delivery-semantics.md) - GUARANTEED vs BEST_EFFORT behavior
- [Integration Modes](integration-modes.md) - Context provider and callback configuration
- [Policy Lifecycle](policy-lifecycle.md) - Policy resolution and routing
- [Architecture](../ARCHITECTURE.md) - System architecture overview

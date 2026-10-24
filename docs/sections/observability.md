# Observability

This document describes the observability model for UNS (`uns.Runtime` and AGSignal Core), including health states, readiness and Prometheus metrics endpoints, durable DLQ visibility, structured audit events, and monitoring semantics.

## Overview

UNS and AGSignal Core provide observability through:
- **Process liveness and authenticated readiness probes**: Public `GET /health` (`/healthz`) and authenticated `GET /ready` (`/readyz`) checking SQLite/SQLAlchemy connectivity, configured channels, ACTIVE policy count, and durable DLQ depth
- **Prometheus and Console metrics**: Authenticated `GET /metrics` and read-model endpoints under `/ui/*`
- **Adapter health status**: Per-channel health reporting (`HEALTHY`, `DEGRADED`, `UNHEALTHY`) and `GET /api/v1/channels/health`
- **Delivery metrics**: Latency, success/failure rates, retry cycles, and fallback counts
- **DLQ visibility**: Durable `uns_notifications.dead_letter = true` persistence (`GET /api/v1/runtime/dead-letters`, `GET /api/v1/dlq`, MCP `list_dlq`) plus low-level escalation callbacks for `GUARANTEED` delivery failures
- **Acknowledgment tracking**: Durable deadline sweeps (`TIMED_OUT`), `ack_audit_records`, and at-least-once callback tracking (`callback_pending`, `callback_attempts`, `callback_error`)
- **Audit logging**: Comprehensive operational event stream (`uns_events`) and compliance audit trail (`notification_audit_records`)

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

### What "DEGRADED" Means for AGSignal Core

A `DEGRADED` adapter indicates:

1. **Elevated latency**: Response times exceed normal thresholds (`latency_ms`) but delivery is possible
2. **Intermittent failures**: Some delivery attempts fail but retries or subsequent attempts may succeed
3. **Reduced reliability**: The channel is operational but not meeting SLA targets
4. **Partial service**: External dependencies (e.g., Slack API or SMTP relay) may be experiencing issues

**Operational Guidance for DEGRADED State:**

| Scenario | Behavior | Operator Action |
|----------|----------|-----------------|
| Primary channel DEGRADED | AGSignal Core attempts delivery, may fallback faster | Monitor for transition to UNHEALTHY |
| All channels DEGRADED | Delivery continues with elevated failure risk | Investigate root cause, prepare for outage |
| Single adapter DEGRADED | Other channels unaffected | Review adapter-specific diagnostics |

**DEGRADED vs UNHEALTHY:**
- `DEGRADED`: "Try delivery but expect some failures" - AGSignal Core will attempt the channel
- `UNHEALTHY`: "Do not attempt delivery" - AGSignal Core will skip to fallback immediately

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

Adapters implement health checks individually and runtime channel health is tracked via `ChannelHealthTracker` (`GET /api/v1/channels/health` and MCP `get_channel_health`):

```python
# Check all adapters via registry
from notification.service import SimpleAdapterRegistry

registry = SimpleAdapterRegistry()
results = await registry.health_check_all()
# Returns: dict[Channel, HealthCheckResult]
```

**Per-Adapter Health Check Behavior:**

| Adapter | Health Check Method | Notes |
|---------|---------------------|-------|
| Slack | API connectivity test | Tests auth and channel access |
| Email | SMTP connection test | Verifies SMTP server reachability |
| PagerDuty | API ping | Note: Events API has no health endpoint; returns HEALTHY if configured |
| WebSocket | Connection state | Checks active agent socket availability |

## /health Endpoint

### Current Implementation

The public HTTP liveness endpoint is located at `GET /health` (also aliased to `GET /healthz`):

```python
# src/agsignal/app.py
@app.get("/health", tags=["system"])
@app.get("/healthz", tags=["system"])
async def health() -> dict[str, str]:
    return {
        "status": "alive",
        "service": "uns",
        "version": __version__,
    }
```

### Endpoint Semantics

Pre-Phase-3 the `/health` endpoint returned a static stub `{"status": "healthy"}`. In the unified UNS service it returns `{"status": "alive", "service": "uns", "version": ...}` as a lightweight liveness stub. The `/health` endpoint is intentionally unauthenticated for load-balancer liveness probes and does NOT invoke database queries or adapter health checks—those live at the authenticated `/ready` and `/readyz` endpoints.

`/health` does NOT:
- Query the database or invoke adapter health checks (use `/readyz` instead)
- Check DLQ depth (surfaced in `/readyz`)
- Verify pending acknowledgment timeouts
- Report per-channel status (use `/readyz` for `channels_configured` or `/api/v1/channels/health`)

**Response format (`GET /health` and `GET /healthz`)**:

```json
{
  "status": "alive",
  "service": "uns",
  "version": "0.1.0"
}
```

### Authenticated Readiness Probe (`GET /ready` and `GET /readyz`)

Unlike `/health`, the readiness probe requires an authenticated credential with observer scope (included in the operator key and every scoped key) and verifies both Core and Console readiness:

```json
{
  "status": "ready",
  "service": "uns",
  "version": "0.1.0",
  "persistence_mode": "persistent",
  "channels_configured": {
    "slack": true,
    "pagerduty": false,
    "email": true
  },
  "policy_count": 4,
  "dlq_depth": 0,
  "read_model_adapter": "SQLAlchemyReadModelAdapter",
  "audit_logger": "SQLAlchemyAuditStore",
  "operational_progress": {
    "pending_count": 0,
    "oldest_pending_age_seconds": null,
    "oldest_due_attempt_lateness_seconds": null,
    "overdue_ack_count": 0,
    "pending_callback_count": 0,
    "oldest_callback_retry_age_seconds": null,
    "unresolved_failure_count": 0,
    "unknown_attempt_count": 0
  }
}
```

If the SQLite/SQLAlchemy database connection fails, `/readyz` returns `"status": "not_ready"` with `"error"`.

`persistence_mode` distinguishes `persistent` storage from explicitly selected `in_memory` operation. The canonical runtime supplies `operational_progress` with these definitions:

| Field | Meaning |
| --- | --- |
| `pending_count` | Pending dispatch owners. Coalesced followers do not add another dispatch obligation. |
| `oldest_pending_age_seconds` | Time since the oldest retained `ACCEPTED` event for a pending dispatch owner, including owners waiting for a future retry. Replay does not reset original acceptance age. |
| `oldest_due_attempt_lateness_seconds` | Time since the earliest dispatch eligibility among pending owners with no live lease: the later of `next_attempt` and lease expiry. Future backoff and active delivery leases do not count as lateness. |
| `overdue_ack_count` | Notifications still awaiting acknowledgment whose deadline has elapsed. The timeout worker should settle these. |
| `pending_callback_count` | Terminal-event callbacks still pending with attempts remaining. Includes callbacks waiting for backoff or a lease. |
| `oldest_callback_retry_age_seconds` | Time since the earliest callback retry or lease expiry that is already due, among callbacks with attempts remaining. This is retry lateness, not total event age. |
| `unresolved_failure_count` | Retained unresolved dead-letter histories; also used as `dlq_depth`. |
| `unknown_attempt_count` | Retained `CHANNEL_ATTEMPT_RESULT` observations whose `metadata.provider_outcome` is `UNKNOWN`. Counts observations, not unique notifications; a later successful replay does not erase earlier uncertainty. |

Age/lateness fields are `null` when no matching timestamp exists. Unknown-attempt evidence can decrease when its history is archived and pruned; the count does not infer missing provider results from interrupted attempts. Progress uses SQL aggregates returning one summary row, and readiness reuses the failure count without loading dead-letter histories. Database work still depends on retained data and indexes.

These values report operational progress and uncertainty. They do not automatically change readiness status; operators should set alert thresholds for growing age, overdue acknowledgments, callback lateness, and unresolved failures.

### Authenticated Prometheus Metrics (`GET /metrics`)

`GET /metrics` (protected by `require_write_principal`) exports Prometheus text-format metrics for HTTP request latency, status codes, rate-limiter rejections, and notification counters.

## DLQ (Dead Letter Queue) Visibility

### Durable Runtime DLQ (`uns.Runtime`)

In the canonical durable runtime (`uns.Runtime`), `GUARANTEED` notifications that exhaust `max_attempts` (default `3` attempts in a cycle) transition to `status = "FAILED"` with `dead_letter = True` in `uns_notifications`.

Operators inspect and remediate durable dead-letter entries via:
- **HTTP Runtime Inspection**: `GET /api/v1/runtime/dead-letters` (returns `notification_id`, `status`, `attempts`, `cycle`, `cycle_attempts`, `outcome`)
- **HTTP Operations DLQ**: `GET /api/v1/dlq` (lists entries and `depth`) and `DELETE /api/v1/dlq/{entry_id}` (marks `dead_letter = False` and records a `FAILURE_RESOLVED` event)
- **HTTP Attributable Replay**: `POST /api/v1/runtime/notifications/{id}/replay` (increments `cycle`, resets `cycle_attempts = 0`, sets `status = "PENDING"`, and records `REPLAY_REQUESTED` with the authenticated `actor`)
- **MCP Tool**: `list_dlq`

### Low-Level Escalation Callback Architecture

In low-level `DeliveryService` usage, DLQ notification is also supported via the **escalation callback** mechanism (`escalation_callback`). When `GUARANTEED` delivery fails all channels in a `DeliveryService.deliver()` call, the callback is invoked:

```python
# Configure at low-level service initialization
from notification.service import configure_delivery_service

service = configure_delivery_service(
    adapter_registry=registry,
    escalation_callback=my_dlq_handler,  # Low-level DLQ hook
)
```

### DLQ Invariants

| Rule | Description |
|------|-------------|
| **GUARANTEED-only** | Only `GUARANTEED` delivery failures enter the durable DLQ or trigger `escalation_callback`; `BEST_EFFORT` failures do NOT |
| **Pre-exception** | In `DeliveryService`, `escalation_callback` is invoked BEFORE `DeliveryError` is raised |
| **Isolated failures** | Callback exceptions are logged but do not prevent `DeliveryError` or durable commit |
| **Full context** | Durable `uns_notifications.outcome` and `escalation_callback` preserve complete notification and `channel_errors` details |

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

Both durable dead-letter rows (`uns_notifications`) and `escalation_callback` preserve:

| Field | Source | Description |
|-------|--------|-------------|
| `notification_id` | `Notification` | Unique identifier |
| `notification_type` | `Notification` | Type for policy lookup |
| `intent` | `Notification` | `SAFETY`, `GOVERNANCE`, `OPERATIONAL`, `INFORMATIONAL` |
| `autonomy_context` | `Notification` | Agent ID, autonomy mode, plan ID |
| `title` | `Notification` | Notification title |
| `message` | `Notification` | Notification body |
| `source` | `Notification` | Originating system |
| `correlation_id` | `Notification` | Optional correlation ID |
| `created_at` | `Notification` | Original creation timestamp |
| `metadata` | `Notification` | Additional key-value pairs (including `uns_resolution` provenance) |
| `channel_errors` | `outcome` / Callback arg | Per-channel failure reasons |

### Operator Impact of DLQ

**Visibility Responsibility**: When running `uns.Runtime` (HTTP or write-enabled MCP), dead-letter state is persisted automatically in `uns_notifications` (`dead_letter = True`) and surfaced in `/readyz` (`dlq_depth`), `/api/v1/runtime/dead-letters`, and `/api/v1/dlq`. When running low-level `DeliveryService` without `uns.Runtime`, operators must persist DLQ entries in their `escalation_callback`:

```python
# Example: Low-level DLQ callback with external alerting
def dlq_handler(notification: Notification, channel_errors: dict[Channel, str]) -> None:
    alerting_service.send_alert(
        severity="critical",
        message=f"GUARANTEED delivery failed: {notification.notification_id}",
    )
```

**DLQ Metrics**:

| Metric | Description | Source |
|--------|-------------|--------|
| `dlq_depth` | Count of unresolved dead-letter entries | `GET /readyz`, `GET /api/v1/dlq`, `list_dlq` |
| `cycle` / `attempts` | Cumulative retry cycles and attempts per dead-lettered notification | `GET /api/v1/runtime/dead-letters` |

## Key Metrics

### Metric Categories

UNS and AGSignal Core expose the following metric categories through `/metrics`, `/readyz`, `/ui/*`, structured logs, and callback hooks:

#### 1. Delivery Latency

| Metric | Source | Description |
|--------|--------|-------------|
| `adapter_latency_ms` | `HealthCheckResult.latency_ms` | Per-adapter response time |
| `delivery_duration_ms` | Computed from `uns_events.at` timestamps | End-to-end delivery time (`ACCEPTED` to `DELIVERY_RESULT`) |
| `channel_attempt_duration_ms` | Per-channel timing | Time for individual channel attempt |

**Intent**: Identify slow channels, tune lease durations (`lease_seconds`), and optimize fallback ordering.

#### 2. Delivery Success/Failure

| Metric | Source | Description |
|--------|--------|-------------|
| `channels_attempted` | `NotificationResult` | List of channels tried |
| `channels_succeeded` | `NotificationResult` | Channels that delivered |
| `channels_failed` | `NotificationResult` | Channels that failed |
| `delivery_status` | `NotificationResult.status` | `DELIVERED`, `SUCCESS`, `FAILED`, `DEDUPLICATED`, `PENDING` |

**Intent**: Track delivery reliability and identify failing channels.

#### 3. Retry/Fallback Counts

| Metric | Source | Description |
|--------|--------|-------------|
| `fallback_count` | Computed from `channels_attempted` | Number of fallback attempts in `GUARANTEED` mode |
| `fallback_triggered` | Boolean | Whether primary channel failed |
| `attempts` / `cycle_attempts` | `uns_notifications` | Durable worker dispatch attempts across cycles |

**Intent**: Monitor `GUARANTEED` delivery health; frequent fallbacks or retry cycles indicate channel instability.

**Note**: Within a single dispatch attempt, fallback is sequential across configured channels (e.g., Slack $\rightarrow$ Email $\rightarrow$ PagerDuty). Across failed dispatch attempts, `uns.Runtime` schedules exponential backoff retries (`retry_seconds * 2 ** min(cycle_attempts - 1, 10)`) up to `max_attempts`.

#### 4. DLQ Depth

| Metric | Source | Description |
|--------|--------|-------------|
| `dlq_depth` | `Runtime.dead_letters()` / `escalation_callback` | Count of exhausted `GUARANTEED` failures |

**Intent**: Monitor undelivered critical notifications requiring operator investigation or replay.

#### 5. Acknowledgment Timeout Counts

| Metric | Source | Description |
|--------|--------|-------------|
| `pending_acks` | `uns_notifications.ack_status == 'PENDING'` / `AckStorage` | Notifications awaiting human or operator response |
| `timed_out_acks` | `Runtime.expire()` / `AcknowledgmentEngine.check_all_timeouts()` | Notifications whose `deadline` elapsed (`TIMED_OUT`) |
| `safety_escalations` | `TIMED_OUT` payload (`escalation_required: true`) | `SAFETY` timeouts requiring escalation |

**Intent**: Identify operator response time issues and `SAFETY` escalation patterns.

**Default Timeout Values**:

| Intent | Timeout | Escalation on Timeout |
|--------|---------|----------------------|
| `SAFETY` | 15 minutes | Yes (`LIVE` mode) |
| `GOVERNANCE` | 30 minutes | No |
| `OPERATIONAL` | None | N/A |
| `INFORMATIONAL` | None | N/A |

#### 6. Rate Limiting Events

| Metric | Source | Description |
|--------|--------|-------------|
| `rate_limit_exceeded` | Logged event / HTTP 429 | Channel or HTTP rate limit hit |
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
| Delivery start | INFO | `notification_id`, `channels`, `mode` |
| Channel attempt success | INFO | `notification_id`, `channel` |
| Channel attempt failure | WARNING | `notification_id`, `channel`, `error` |
| GUARANTEED failure | ERROR | `notification_id`, `channel_errors` |
| Escalation callback failure | ERROR | `notification_id`, callback error |
| Ack timeout | WARNING | `notification_id`, `intent`, `autonomy_mode` |
| SAFETY escalation | CRITICAL | `notification_id` |
| Rate limit exceeded | WARNING | `channel` |

### Metric Collection Patterns

Operators can collect metrics by:

1. **Prometheus scraping**: Scrape authenticated `GET /metrics` and `GET /readyz`
2. **Log aggregation**: Parse structured JSON logs correlated by `request_id`, `notification_id`, and `correlation_id`
3. **Callback hooks**: Implement `AuditLogger` and `AcknowledgmentCallback` protocols (or `Runtime.callback`)
4. **Adapter registry polling**: Call `GET /api/v1/channels/health` or `health_check_all()`

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
| **All channels DEGRADED** | Attempt all, may retry/fail | Attempt all, log failures | All health checks DEGRADED |
| **All channels UNHEALTHY** | Retry up to `max_attempts`, then DLQ (`dead_letter=True`) | Mark `FAILED`, no DLQ | `dlq_depth > 0`, critical alerts |

### Degradation Detection

Operators should monitor for:

1. **Elevated fallback rates**: More than 10% of `GUARANTEED` deliveries using fallback channels
2. **Increasing ack timeouts**: Rising count of `SAFETY` / `GOVERNANCE` `TIMED_OUT` events
3. **DLQ growth**: Any `dlq_depth > 0` in `/readyz` or `/api/v1/runtime/dead-letters` requires investigation (see [TSG-01](../tsg/TSG-01-DLQ-AND-REPLAY.md))
4. **Lease losses**: `LEASE_LOST` events in `uns_events` indicating slow provider sockets exceeding `lease_seconds` (see [TSG-02](../tsg/TSG-02-LEASES-AND-PROVIDER-EFFECTS.md))
5. **Adapter health transitions**: Any adapter moving to `DEGRADED` or `UNHEALTHY`

### Recovery Patterns

| State Transition | Operator Action |
|------------------|-----------------|
| HEALTHY → DEGRADED | Monitor closely, investigate external service |
| DEGRADED → UNHEALTHY | Expect delivery failures, check fallback channels |
| UNHEALTHY → DEGRADED | Tentatively resume, monitor error rates |
| DEGRADED → HEALTHY | Normal operations, review incident |

## Audit Trail

All deliveries and state transitions generate durable records in `uns_events`, `notification_audit_records`, and `ack_audit_records` (and through the `AuditLogger` protocol):

| Event | Logged Fields |
|-------|---------------|
| `ACCEPTED` / Delivery start | `notification_id`, `principal`, `uns_resolution` (policy snapshot & effective values) |
| `ATTEMPT_STARTED` / `CHANNEL_ATTEMPT_STARTED` | `channel`, `attempt`, `cycle`, `cycle_attempt`, `provider_effect_may_have_occurred` |
| `DELIVERY_RESULT` / Delivery complete | `status`, `attempt`, `cycle`, `dead_letter`, `outcome` (`channels_succeeded`, `channels_failed`) |
| `LEASE_LOST` | `lease_token`, `attempt`, `provider_effect_may_have_occurred` |
| `DEDUP_LINKED` / `DEDUP_SATISFIED` / `DEDUP_OWNER_PROMOTED` | `owner_id`, `previous_owner_id`, `generation` |
| `ACKED` / `DISMISSED` | `actor`, `metadata`, `responded_at` |
| `TIMED_OUT` | `actor` (`uns-timeout-worker`), `escalation_required` |
| `REPLAY_REQUESTED` / `FAILURE_RESOLVED` | `actor`, `cycle`, `cumulative_attempts` |
| `RETENTION_APPLIED` | `operator`, `cutoff`, `deleted_rows`, `archive` (or `removed` payload) |

### Audit Invariant

Every delivery (success or failure) MUST generate an audit record containing:
- Notification metadata and resolved policy provenance (`policy_config_id`, `policy_config_hash`)
- Delivery outcome (`channels_attempted`, `channels_succeeded`, `channels_failed`)
- Autonomy context (`agent_id`, `autonomy_mode`)
- Timestamp (`created_at`, `delivered_at`)

## Summary

| Aspect | Description | Implementation Status |
|--------|-------------|----------------------|
| **Adapter health** | Per-channel `HEALTHY`/`DEGRADED`/`UNHEALTHY` | Implemented |
| **/health endpoint** | Public liveness stub `{"status": "alive", "service": "uns", "version": ...}` | Implemented (liveness only) |
| **/readyz endpoint** | Authenticated DB, policy count, channel config, and `dlq_depth` check | Implemented |
| **/metrics endpoint** | Authenticated Prometheus metrics exporter | Implemented |
| **DLQ visibility** | Durable `uns_notifications.dead_letter` (`/api/v1/runtime/dead-letters`) + `escalation_callback` | Implemented |
| **Delivery metrics** | Via Prometheus `/metrics`, `/ui/*`, structured logs, and audit callbacks | Implemented |
| **Ack timeout tracking** | Durable `Runtime.expire()` worker + `AcknowledgmentEngine` | Implemented |
| **Rate limit metrics** | Via slowapi HTTP middleware and per-channel token buckets | Implemented |

## Related Documentation

- [Delivery Semantics](delivery-semantics.md) - GUARANTEED vs BEST_EFFORT behavior
- [Integration Modes](integration-modes.md) - Runtime, client, context provider, and callback configuration
- [Policy Lifecycle](policy-lifecycle.md) - Policy resolution and routing
- [Architecture](../ARCHITECTURE.md) - System architecture overview
- [Support State Machine & Schema](../support/STATE-MACHINE-AND-SCHEMA.md) - Database tables and event catalog
- [Troubleshooting Guides (TSGs)](../tsg/README.md) - Incident runbooks

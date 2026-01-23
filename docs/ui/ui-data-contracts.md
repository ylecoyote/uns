# UI Data Contracts

This document defines the response shapes, filters, pagination, and error semantics for all UI data endpoints in the Unified Notification Service (UNS).

## Design Principles

1. **Read-only** - All endpoints are read-only per [UI Scope v1](ui-scope.md)
2. **Consistent pagination** - All list endpoints use cursor-based pagination
3. **Consistent filtering** - Filter parameters follow a standard pattern
4. **Consistent errors** - Error responses use a uniform structure
5. **Type-safe** - All shapes are defined with explicit types for client code generation

## Common Types

### Pagination

All list endpoints use cursor-based pagination for consistent, efficient traversal.

```typescript
interface PaginationParams {
  cursor?: string;        // Opaque cursor from previous response
  limit?: number;         // Items per page (default: 25, max: 100)
}

interface PaginatedResponse<T> {
  items: T[];
  pagination: {
    next_cursor: string | null;  // null when no more pages
    has_more: boolean;
    total_count?: number;        // Optional; included when efficient to compute
  };
}
```

### Time Range Filters

Common time-based filtering for audit and event queries.

```typescript
interface TimeRangeFilter {
  start_time?: string;    // ISO 8601 timestamp (inclusive)
  end_time?: string;      // ISO 8601 timestamp (exclusive)
}
```

### Error Response

All errors follow a consistent structure.

```typescript
interface ErrorResponse {
  error: {
    code: string;         // Machine-readable error code
    message: string;      // Human-readable description
    details?: Record<string, unknown>;  // Additional context
  };
  request_id: string;     // For correlation/support
}
```

### Standard Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `not_found` | 404 | Resource does not exist |
| `invalid_parameter` | 400 | Malformed or invalid parameter value |
| `invalid_cursor` | 400 | Pagination cursor is invalid or expired |
| `rate_limited` | 429 | Too many requests |
| `internal_error` | 500 | Unexpected server error |

---

## 1. Delivery Timeline + Attempts

View notification delivery history including all channel attempts, outcomes, and timing.

### Endpoint

```
GET /api/v1/notifications/{notification_id}/delivery-timeline
```

### Response Shape

```typescript
interface DeliveryTimelineResponse {
  notification_id: string;          // UUID
  notification_type: string;
  intent: "SAFETY" | "GOVERNANCE" | "OPERATIONAL" | "INFORMATIONAL";
  delivery_mode: "GUARANTEED" | "BEST_EFFORT";

  // Summary
  status: "PENDING" | "DELIVERED" | "SUCCESS" | "FAILED" | "DEDUPLICATED" | "RATE_LIMITED";
  created_at: string;               // ISO 8601
  delivered_at: string | null;      // ISO 8601, null if not delivered

  // Channel attempts in chronological order
  attempts: DeliveryAttempt[];

  // Aggregates
  channels_attempted: Channel[];
  channels_succeeded: Channel[];
  channels_failed: Channel[];

  // Context
  autonomy_context: {
    autonomy_mode: "PREVIEW" | "SHADOW" | "LIVE";
    agent_id: string;               // UUID
    plan_id?: string;               // UUID, optional
    decision_snapshot_id?: string;  // UUID, optional
    execution_snapshot_id?: string; // UUID, optional
    skip_snapshot_id?: string;      // UUID, optional
  };
}

interface DeliveryAttempt {
  attempt_id: string;               // UUID
  channel: Channel;
  status: "SUCCESS" | "FAILED" | "RATE_LIMITED" | "SKIPPED";
  started_at: string;               // ISO 8601
  completed_at: string;             // ISO 8601
  duration_ms: number;
  error_message?: string;           // Present if failed
  error_code?: string;              // Adapter-specific error code
  metadata?: {
    message_id?: string;            // External ID (e.g., Slack ts)
    retry_count?: number;
    [key: string]: unknown;
  };
}

type Channel = "SLACK" | "EMAIL" | "WEBSOCKET" | "PAGERDUTY";
```

### List Delivery Timelines

```
GET /api/v1/delivery-timelines
```

Query multiple delivery timelines with filtering.

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
| `notification_type` | string | Filter by notification_type (prefix match supported with `*`) |
| `channel` | string | Filter by channel attempted |

#### Response

```typescript
interface DeliveryTimelineListResponse extends PaginatedResponse<DeliveryTimelineSummary> {}

interface DeliveryTimelineSummary {
  notification_id: string;
  notification_type: string;
  intent: string;
  delivery_mode: string;
  status: string;
  created_at: string;
  delivered_at: string | null;
  channels_attempted: Channel[];
  channels_succeeded: Channel[];
  autonomy_mode: string;
  agent_id: string;
}
```

### Errors

| Code | Condition |
|------|-----------|
| `not_found` | notification_id does not exist |
| `invalid_parameter` | Invalid filter value |

---

## 2. Escalations + Failures

View escalation events and delivery failures, particularly for GUARANTEED delivery mode.

### Endpoint

```
GET /api/v1/escalations
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `start_time` | string | ISO 8601, filter by escalated_at >= |
| `end_time` | string | ISO 8601, filter by escalated_at < |
| `intent` | string | Filter by notification intent |
| `agent_id` | string | Filter by agent UUID |
| `autonomy_mode` | string | Filter by autonomy mode |
| `notification_type` | string | Filter by notification_type (prefix match supported) |
| `escalation_type` | string | Filter by `delivery_failure` or `ack_timeout` |

### Response Shape

```typescript
interface EscalationListResponse extends PaginatedResponse<EscalationEvent> {}

interface EscalationEvent {
  escalation_id: string;            // UUID
  escalation_type: "delivery_failure" | "ack_timeout";
  escalated_at: string;             // ISO 8601

  // Notification context
  notification_id: string;
  notification_type: string;
  intent: "SAFETY" | "GOVERNANCE" | "OPERATIONAL" | "INFORMATIONAL";
  title: string;

  // Autonomy context
  autonomy_context: {
    autonomy_mode: "PREVIEW" | "SHADOW" | "LIVE";
    agent_id: string;
    plan_id?: string;
  };

  // Escalation details (varies by type)
  details: DeliveryFailureDetails | AckTimeoutDetails;
}

interface DeliveryFailureDetails {
  type: "delivery_failure";
  delivery_mode: "GUARANTEED";      // Only GUARANTEED triggers escalation
  channel_errors: ChannelError[];
  total_attempts: number;
  first_attempt_at: string;
  last_attempt_at: string;
}

interface ChannelError {
  channel: Channel;
  error_message: string;
  error_code?: string;
  attempted_at: string;
}

interface AckTimeoutDetails {
  type: "ack_timeout";
  timeout_minutes: number;
  created_at: string;               // Notification creation time
  timeout_at: string;               // When timeout occurred
  ack_status: "TIMED_OUT";
}
```

### Get Single Escalation

```
GET /api/v1/escalations/{escalation_id}
```

Returns full `EscalationEvent` with complete details.

### Errors

| Code | Condition |
|------|-----------|
| `not_found` | escalation_id does not exist |
| `invalid_parameter` | Invalid filter value |

---

## 3. Effective Policy Resolution Trace

View how a notification's routing was determined, showing the resolution chain from explicit override to SDK default.

### Endpoint

```
GET /api/v1/notifications/{notification_id}/policy-trace
```

### Response Shape

```typescript
interface PolicyResolutionTraceResponse {
  notification_id: string;
  notification_type: string;

  // Effective values (what was actually used)
  effective: {
    delivery_mode: "GUARANTEED" | "BEST_EFFORT";
    channels: Channel[];
    require_ack: boolean;
    ack_timeout_minutes: number | null;
    dedup_window_seconds: number;
  };

  // Resolution trace for each field
  resolution: {
    delivery_mode: ResolutionStep[];
    channels: ResolutionStep[];
    require_ack: ResolutionStep[];
    ack_timeout_minutes: ResolutionStep[];
    dedup_window_seconds: ResolutionStep[];
  };

  // Context used for resolution
  resolution_context: {
    intent: "SAFETY" | "GOVERNANCE" | "OPERATIONAL" | "INFORMATIONAL";
    autonomy_mode: "PREVIEW" | "SHADOW" | "LIVE";
    irreversible: boolean;
    policy_found: boolean;
    policy_notification_type?: string;  // Present if policy was found
  };
}

interface ResolutionStep {
  source: "explicit_override" | "mode_override" | "policy_base" | "sdk_default";
  value: unknown;                   // The value at this resolution step
  applied: boolean;                 // Whether this value was used
  reason?: string;                  // Explanation if not applied
}
```

### Resolution Order Documentation

The `resolution` field shows the full resolution chain per [Policy Lifecycle](../sections/policy-lifecycle.md):

```
1. explicit_override  - Values passed directly to SDK.send()
2. mode_override      - Policy mode-specific override (preview_override, etc.)
3. policy_base        - Policy base value
4. sdk_default        - SDK default derived from intent + autonomy_mode
```

### Simulate Policy Resolution

Preview how a hypothetical notification would be resolved.

```
POST /api/v1/policy-trace/simulate
```

#### Request Body

```typescript
interface PolicySimulationRequest {
  notification_type: string;
  intent: "SAFETY" | "GOVERNANCE" | "OPERATIONAL" | "INFORMATIONAL";
  autonomy_mode: "PREVIEW" | "SHADOW" | "LIVE";
  irreversible?: boolean;           // Default: false

  // Optional explicit overrides to test
  overrides?: {
    delivery_mode?: "GUARANTEED" | "BEST_EFFORT";
    channels?: Channel[];
    require_ack?: boolean;
  };
}
```

#### Response

Returns `PolicyResolutionTraceResponse` showing how the notification would be resolved.

### Errors

| Code | Condition |
|------|-----------|
| `not_found` | notification_id does not exist |
| `invalid_parameter` | Invalid simulation parameters |

---

## 4. Invariant Registry Rendering

View the system invariant registry for compliance and audit purposes.

### Endpoint

```
GET /api/v1/invariants
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `severity` | string | Filter by HIGH, MEDIUM, or LOW |
| `enforcement_type` | string | Filter by guard, isolation, test, or exception |
| `status` | string | Filter by active or inactive |
| `search` | string | Full-text search on statement |

### Response Shape

```typescript
interface InvariantListResponse extends PaginatedResponse<InvariantEntry> {}

interface InvariantEntry {
  id: string;                       // e.g., "INV-ACK-001"
  statement: string;                // The invariant claim
  severity: "HIGH" | "MEDIUM" | "LOW";
  status: "active" | "inactive";

  enforcement: {
    type: "guard" | "isolation" | "test" | "exception";
    description: string;
  };

  evidence: EvidenceLink[];

  owner: string;                    // Team/role responsible
  last_reviewed: string;            // ISO 8601 date

  // For exceptions only
  mitigation?: string[];
}

interface EvidenceLink {
  path: string;                     // Repo-relative path
  note: string;                     // Description of what this evidences
  line_ref?: string;                // Optional line reference
}
```

### Get Single Invariant

```
GET /api/v1/invariants/{invariant_id}
```

Returns full `InvariantEntry` with all details.

### Invariant Summary Statistics

```
GET /api/v1/invariants/summary
```

```typescript
interface InvariantSummaryResponse {
  total_count: number;
  by_severity: {
    HIGH: number;
    MEDIUM: number;
    LOW: number;
  };
  by_enforcement_type: {
    guard: number;
    isolation: number;
    test: number;
    exception: number;
  };
  by_status: {
    active: number;
    inactive: number;
  };
  exceptions_requiring_review: number;  // Exceptions past review date
  last_updated: string;                 // ISO 8601
}
```

### Errors

| Code | Condition |
|------|-----------|
| `not_found` | invariant_id does not exist |
| `invalid_parameter` | Invalid filter value |

---

## 5. Audit Event Stream

View the audit trail of all notification-related events.

### Endpoint

```
GET /api/v1/audit-events
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `start_time` | string | ISO 8601, filter by event_time >= |
| `end_time` | string | ISO 8601, filter by event_time < |
| `event_type` | string | Filter by event type (see below) |
| `notification_id` | string | Filter by notification UUID |
| `agent_id` | string | Filter by agent UUID |
| `autonomy_mode` | string | Filter by PREVIEW, SHADOW, or LIVE |
| `correlation_id` | string | Filter by correlation ID |

### Event Types

| Type | Description |
|------|-------------|
| `notification.created` | Notification submitted to UNS |
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

### Response Shape

```typescript
interface AuditEventListResponse extends PaginatedResponse<AuditEvent> {}

interface AuditEvent {
  audit_id: string;                 // UUID
  event_type: string;               // One of the event types above
  event_time: string;               // ISO 8601

  // Notification context (always present)
  notification_id: string;
  notification_type: string;

  // Autonomy context
  autonomy_context: {
    autonomy_mode: "PREVIEW" | "SHADOW" | "LIVE";
    agent_id: string;
    plan_id?: string;
    decision_snapshot_id?: string;
    execution_snapshot_id?: string;
    skip_snapshot_id?: string;
  };

  // Event-specific payload
  payload: AuditEventPayload;

  // Correlation
  correlation_id?: string;
}

// Union type for event payloads
type AuditEventPayload =
  | NotificationCreatedPayload
  | DeliveryStartedPayload
  | ChannelAttemptedPayload
  | DeliveryOutcomePayload
  | AckStatusChangePayload
  | EscalationTriggeredPayload;

interface NotificationCreatedPayload {
  type: "notification.created";
  intent: string;
  delivery_mode: string;
  channels: Channel[];
  require_ack: boolean;
  title: string;
  source: string;
}

interface DeliveryStartedPayload {
  type: "delivery.started";
  delivery_mode: string;
  channels_to_attempt: Channel[];
}

interface ChannelAttemptedPayload {
  type: "delivery.channel_attempted";
  channel: Channel;
  success: boolean;
  error_message?: string;
  duration_ms: number;
  message_id?: string;
}

interface DeliveryOutcomePayload {
  type: "delivery.succeeded" | "delivery.failed" | "delivery.deduplicated" | "delivery.rate_limited";
  status: string;
  channels_succeeded: Channel[];
  channels_failed: Channel[];
  error_message?: string;
}

interface AckStatusChangePayload {
  type: "ack.pending" | "ack.received" | "ack.dismissed" | "ack.timed_out";
  old_status: string | null;
  new_status: string;
  acked_by?: string;
  metadata?: Record<string, unknown>;
}

interface EscalationTriggeredPayload {
  type: "escalation.triggered";
  escalation_type: "delivery_failure" | "ack_timeout";
  channel_errors?: ChannelError[];
}
```

### Get Events for Notification

```
GET /api/v1/notifications/{notification_id}/audit-events
```

Returns all audit events for a specific notification in chronological order.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `cursor` | string | Pagination cursor |
| `limit` | number | Items per page (default: 25, max: 100) |
| `event_type` | string | Filter by event type |

### Audit Event Statistics

```
GET /api/v1/audit-events/statistics
```

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `start_time` | string | ISO 8601 (required) |
| `end_time` | string | ISO 8601 (required) |
| `granularity` | string | `minute`, `hour`, `day` (default: `hour`) |

```typescript
interface AuditStatisticsResponse {
  time_range: {
    start_time: string;
    end_time: string;
    granularity: string;
  };

  totals: {
    total_events: number;
    by_event_type: Record<string, number>;
    by_intent: Record<string, number>;
    by_autonomy_mode: Record<string, number>;
  };

  time_series: TimeSeriesBucket[];

  delivery_metrics: {
    total_deliveries: number;
    successful: number;
    failed: number;
    deduplicated: number;
    success_rate: number;           // 0.0 - 1.0
  };

  ack_metrics: {
    total_acks_required: number;
    acknowledged: number;
    dismissed: number;
    timed_out: number;
    ack_rate: number;               // 0.0 - 1.0
  };
}

interface TimeSeriesBucket {
  timestamp: string;                // ISO 8601, bucket start time
  event_count: number;
  by_event_type: Record<string, number>;
}
```

### Errors

| Code | Condition |
|------|-----------|
| `not_found` | notification_id does not exist |
| `invalid_parameter` | Invalid filter value or time range |
| `invalid_cursor` | Cursor expired or malformed |

---

## HTTP Status Code Summary

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 404 | Resource not found |
| 429 | Rate limited |
| 500 | Internal server error |

## Rate Limiting

All endpoints are subject to rate limiting:

- **Default**: 100 requests/minute per client
- **Burst**: Up to 10 requests/second
- Rate limit headers included in responses:
  - `X-RateLimit-Limit`: Requests allowed per window
  - `X-RateLimit-Remaining`: Requests remaining
  - `X-RateLimit-Reset`: Unix timestamp when window resets

## Cursor Semantics

- Cursors are opaque strings; clients must not parse or construct them
- Cursors expire after 1 hour of inactivity
- Expired cursors return `invalid_cursor` error
- Cursors are specific to the original query parameters; changing filters invalidates the cursor

## Related Documentation

- [UI Scope](ui-scope.md) - v1 scope and constraints
- [Delivery Semantics](../sections/delivery-semantics.md) - Delivery behavior details
- [Policy Lifecycle](../sections/policy-lifecycle.md) - Policy resolution rules
- [Invariants](../verification/invariants.md) - Invariant enforcement process

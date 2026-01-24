/**
 * API types matching ui-data-contracts.md
 *
 * These types define the response shapes for all UI API endpoints.
 * All endpoints are READ-ONLY per ui-scope.md.
 */

// Common types

export interface PaginationInfo {
  next_cursor: string | null;
  has_more: boolean;
  total_count?: number;
}

export interface ErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ErrorResponse {
  error: ErrorDetail;
  request_id: string;
}

// Enums matching backend

export type Channel = 'SLACK' | 'EMAIL' | 'WEBSOCKET' | 'PAGERDUTY';
export type NotificationIntent = 'SAFETY' | 'GOVERNANCE' | 'OPERATIONAL' | 'INFORMATIONAL';
export type DeliveryMode = 'GUARANTEED' | 'BEST_EFFORT';
export type DeliveryStatus = 'PENDING' | 'DELIVERED' | 'FAILED' | 'DEDUPLICATED' | 'RATE_LIMITED';
export type AutonomyMode = 'PREVIEW' | 'SHADOW' | 'LIVE';

// Audit Event Types

export type AuditEventType =
  | 'notification.created'
  | 'delivery.started'
  | 'delivery.channel_attempted'
  | 'delivery.succeeded'
  | 'delivery.failed'
  | 'delivery.deduplicated'
  | 'delivery.rate_limited'
  | 'ack.pending'
  | 'ack.received'
  | 'ack.dismissed'
  | 'ack.timed_out'
  | 'escalation.triggered';

// Autonomy Context

export interface AutonomyContext {
  autonomy_mode: AutonomyMode;
  agent_id: string;
  plan_id?: string;
  decision_snapshot_id?: string;
  execution_snapshot_id?: string;
  skip_snapshot_id?: string;
}

// Audit Event

export interface AuditEvent {
  audit_id: string;
  event_type: AuditEventType;
  event_time: string;
  notification_id: string;
  notification_type: string;
  autonomy_context: AutonomyContext;
  payload: Record<string, unknown>;
  correlation_id?: string;
}

export interface AuditEventListResponse {
  items: AuditEvent[];
  pagination: PaginationInfo;
}

// Audit Event Filters

export interface AuditEventFilter {
  cursor?: string;
  limit?: number;
  start_time?: string;
  end_time?: string;
  event_type?: AuditEventType;
  notification_id?: string;
  agent_id?: string;
  autonomy_mode?: AutonomyMode;
  correlation_id?: string;
}

// Delivery Timeline Types

export interface DeliveryAttempt {
  attempt_id: string;
  channel: Channel;
  status: string; // SUCCESS, FAILED, RATE_LIMITED, SKIPPED
  started_at: string;
  completed_at: string;
  duration_ms: number;
  error_message?: string | null;
  error_code?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface AutonomyContextResponse {
  autonomy_mode: AutonomyMode;
  agent_id: string;
  plan_id?: string | null;
  decision_snapshot_id?: string | null;
  execution_snapshot_id?: string | null;
  skip_snapshot_id?: string | null;
}

export interface DeliveryTimelineResponse {
  notification_id: string;
  notification_type: string;
  intent: NotificationIntent;
  delivery_mode: DeliveryMode;
  status: DeliveryStatus;
  created_at: string;
  delivered_at?: string | null;
  attempts: DeliveryAttempt[];
  channels_attempted: Channel[];
  channels_succeeded: Channel[];
  channels_failed: Channel[];
  autonomy_context: AutonomyContextResponse;
}

export interface DeliveryTimelineSummary {
  notification_id: string;
  notification_type: string;
  intent: NotificationIntent;
  delivery_mode: DeliveryMode;
  status: DeliveryStatus;
  created_at: string;
  delivered_at?: string | null;
  channels_attempted: Channel[];
  channels_succeeded: Channel[];
  autonomy_mode: AutonomyMode;
  agent_id: string;
}

export interface DeliveryTimelineListResponse {
  items: DeliveryTimelineSummary[];
  pagination: PaginationInfo;
}

export interface DeliveryFilter {
  cursor?: string;
  limit?: number;
  start_time?: string;
  end_time?: string;
  status?: DeliveryStatus;
  intent?: NotificationIntent;
  delivery_mode?: DeliveryMode;
  agent_id?: string;
  autonomy_mode?: AutonomyMode;
  notification_type?: string;
  channel?: Channel;
}

// Policy Inspector Types

export type ResolutionSource = 'explicit_override' | 'mode_override' | 'policy_base' | 'sdk_default';

export interface ResolutionStep {
  source: ResolutionSource;
  value: unknown;
  applied: boolean;
  reason: string | null;
}

export interface EffectivePolicy {
  delivery_mode: DeliveryMode;
  channels: Channel[];
  require_ack: boolean;
  ack_timeout_minutes: number | null;
  dedup_window_seconds: number;
}

export interface ResolutionContext {
  intent: NotificationIntent;
  autonomy_mode: AutonomyMode;
  irreversible: boolean;
  policy_found: boolean;
  policy_notification_type: string | null;
}

export interface EffectivePolicyResponse {
  notification_type: string;
  effective: EffectivePolicy;
  resolution: Record<string, ResolutionStep[]>;
  resolution_context: ResolutionContext;
}

export interface PolicyInspectorParams {
  notification_type: string;
  intent: NotificationIntent;
  autonomy_mode: AutonomyMode;
  irreversible?: boolean;
}

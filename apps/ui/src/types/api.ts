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

export type ConsoleScope = 'observer' | 'responder' | 'producer' | 'admin';

export interface ConsoleSessionResponse {
  subject: string;
  scopes: ConsoleScope[];
  persistence_mode?: string | null;
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

export interface RuntimeEvent {
  id: string;
  notification_id: string;
  kind: string;
  at: number;
  payload: Record<string, unknown>;
  callback_pending?: boolean;
  callback_attempts?: number;
  callback_error?: string | null;
}

export interface RuntimeDeliveryState {
  delivery_status: string;
  ack_status: string | null;
  deadline?: number | null;
  dead_letter: boolean;
  policy_config_hash?: string | null;
  policy_evaluation_id?: string | null;
  require_ack?: boolean;
  obligation_owner_id?: string | null;
  effective_status?: string;
  effective_ack_status?: string | null;
  ack_inherited?: boolean;
  obligation_resolution_status?: string;
  obligation_resolution_error?: string | null;
  actor?: string | null;
  responded_at?: number | null;
  response_metadata?: Record<string, unknown> | null;
  events?: RuntimeEvent[];
  events_total_count?: number;
  events_truncated?: boolean;
}

export interface AckRequest {
  acked_by?: string;
  metadata?: Record<string, unknown>;
}

export interface DismissRequest {
  dismissed_by?: string;
  metadata?: Record<string, unknown>;
}

export interface AckResponse {
  notification_id: string;
  ack_status: string;
  acked_by?: string | null;
  acked_at?: string | null;
}

export interface DeliveryTimelineResponse {
  runtime_state?: RuntimeDeliveryState | null;
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

// Operations & Dead-Letter Recovery Types (Surface 3)

export interface OperationalProgress {
  pending_count: number;
  oldest_pending_age_seconds: number | null;
  oldest_due_attempt_lateness_seconds: number | null;
  overdue_ack_count: number;
  pending_callback_count: number;
  oldest_callback_retry_age_seconds: number | null;
  unresolved_failure_count: number;
  unknown_attempt_count: number;
}

export interface ReadyzResponse {
  status: string;
  service?: string;
  version?: string;
  persistence_mode?: string;
  channels_configured?: Record<string, boolean>;
  policy_count?: number;
  dlq_depth?: number;
  read_model_adapter?: string;
  audit_logger?: string;
  operational_progress?: OperationalProgress | null;
  error?: string;
}

export type ChannelHealthStatus = 'HEALTHY' | 'DEGRADED' | 'UNAVAILABLE';

export interface ChannelHealthItem {
  channel: Channel;
  status: ChannelHealthStatus;
  consecutive_failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_failure_reason: string | null;
}

export interface ChannelHealthSummaryResponse {
  status: ChannelHealthStatus;
  total_channels: number;
  healthy_channels: Channel[];
  degraded_channels: Channel[];
  unavailable_channels: Channel[];
  channels: ChannelHealthItem[];
}

export interface RuntimeDeadLetterItem {
  notification_id: string;
  status: string;
  attempts: number;
  cycle: number;
  cycle_attempts: number;
  outcome?: Record<string, unknown> | null;
  replay_blocked_by: string | null;
  replay_block_reason: string | null;
}

export interface DLQEntryItem {
  entry_id: string;
  notification_id: string;
  notification_type: string;
  intent: string;
  source: string;
  reason: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface DLQListResponse {
  depth: number;
  items: DLQEntryItem[];
}

export interface DLQRemoveResponse {
  entry_id: string;
  removed: boolean;
  depth: number;
}

export interface ReplayNotificationResponse {
  notification_id: string;
  status: string;
}

// Policy Workspace Types (Surface 4)

export interface ActivePolicySummary {
  notification_type: string;
  version: string;
  status: string;
  intent: NotificationIntent | null;
  channels: Channel[];
  delivery_mode: DeliveryMode | null;
  require_ack: boolean | null;
  ack_timeout_minutes: number | null;
  ack_timeout_seconds: number | null;
  dedup_window_seconds: number;
}

export interface ActivePolicyListResponse {
  items: ActivePolicySummary[];
  total_count: number;
}

export interface SendNotificationRequestPayload {
  notification_type: string;
  intent: NotificationIntent;
  title: string;
  message: string;
  source: string;
  autonomy_context: {
    autonomy_mode: AutonomyMode;
    agent_id: string;
    plan_id?: string | null;
  };
  irreversible?: boolean;
  metadata?: Record<string, unknown>;
}

export interface SimulateNotificationResponsePayload {
  notification_id: string;
  simulated: boolean;
  status: DeliveryStatus;
  channels_attempted: Channel[];
  delivery_mode: DeliveryMode;
  require_ack: boolean;
  ack_status?: string | null;
  dedup_key: string;
  dedup_window_seconds: number | null;
  policy_source: string;
  warnings: string[];
  message: string;
}

export interface SendNotificationResponsePayload {
  notification_id: string;
  status: DeliveryStatus;
  channels_attempted: Channel[];
  channels_succeeded: Channel[];
  channels_failed: Channel[];
  require_ack: boolean;
  ack_status?: string | null;
  obligation_owner_id?: string | null;
  effective_ack_status?: string | null;
  ack_inherited?: boolean;
  created_at: string;
  message: string;
}

export interface PolicyReloadResponsePayload {
  loaded_count: number;
  persisted_count: number;
  policy_count: number;
  notification_types: string[];
}

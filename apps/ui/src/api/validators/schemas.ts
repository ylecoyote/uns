/**
 * Zod schemas for UI API contract validation.
 *
 * These schemas provide runtime validation of API responses to detect contract drift
 * between the backend and frontend. They are the SINGLE SOURCE OF TRUTH for response
 * shape validation.
 *
 * Key features:
 * - Strict enum validation to catch backend enum changes
 * - Required field validation to catch missing fields
 * - Optional field handling for degraded states
 * - Type inference for TypeScript compatibility
 *
 * @see docs/ui/ui-data-contracts.md for contract specifications
 */

import { z } from 'zod';

// ============================================================================
// Common Types
// ============================================================================

/**
 * Pagination info schema - used by all list responses
 */
export const PaginationInfoSchema = z.object({
  next_cursor: z.string().nullable(),
  has_more: z.boolean(),
  total_count: z.number().optional(),
});

/**
 * Error detail schema
 */
export const ErrorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).optional(),
});

/**
 * Error response schema
 */
export const ErrorResponseSchema = z.object({
  error: ErrorDetailSchema,
  request_id: z.string(),
});

// ============================================================================
// Enums
// ============================================================================

/**
 * Notification channel enum - strict validation
 */
export const ChannelSchema = z.enum(['SLACK', 'EMAIL', 'WEBSOCKET', 'PAGERDUTY']);

/**
 * Notification intent enum - strict validation
 */
export const NotificationIntentSchema = z.enum(['SAFETY', 'GOVERNANCE', 'OPERATIONAL', 'INFORMATIONAL']);

/**
 * Delivery mode enum - strict validation
 */
export const DeliveryModeSchema = z.enum(['GUARANTEED', 'BEST_EFFORT']);

/**
 * Delivery status enum - strict validation
 */
export const DeliveryStatusSchema = z.enum(['PENDING', 'DELIVERED', 'FAILED', 'DEDUPLICATED', 'RATE_LIMITED']);

/**
 * Autonomy mode enum - strict validation
 */
export const AutonomyModeSchema = z.enum(['PREVIEW', 'SHADOW', 'LIVE']);

/**
 * Audit event type enum - strict validation
 */
export const AuditEventTypeSchema = z.enum([
  'notification.created',
  'delivery.started',
  'delivery.channel_attempted',
  'delivery.succeeded',
  'delivery.failed',
  'delivery.deduplicated',
  'delivery.rate_limited',
  'ack.pending',
  'ack.received',
  'ack.dismissed',
  'ack.timed_out',
  'escalation.triggered',
]);

/**
 * Invariant severity enum - strict validation
 */
export const InvariantSeveritySchema = z.enum(['HIGH', 'MEDIUM', 'LOW']);

/**
 * Enforcement type enum - strict validation
 */
export const EnforcementTypeSchema = z.enum(['guard', 'isolation', 'test', 'exception']);

/**
 * Invariant status enum - strict validation
 */
export const InvariantStatusSchema = z.enum(['active', 'inactive']);

/**
 * Resolution source enum - strict validation
 */
export const ResolutionSourceSchema = z.enum(['explicit_override', 'mode_override', 'policy_base', 'sdk_default']);

// ============================================================================
// Autonomy Context
// ============================================================================

/**
 * Autonomy context schema
 */
export const AutonomyContextSchema = z.object({
  autonomy_mode: AutonomyModeSchema,
  agent_id: z.string(),
  plan_id: z.string().optional(),
  decision_snapshot_id: z.string().optional(),
  execution_snapshot_id: z.string().optional(),
  skip_snapshot_id: z.string().optional(),
});

/**
 * Autonomy context response schema (allows null for optional fields)
 */
export const AutonomyContextResponseSchema = z.object({
  autonomy_mode: AutonomyModeSchema,
  agent_id: z.string(),
  plan_id: z.string().nullable().optional(),
  decision_snapshot_id: z.string().nullable().optional(),
  execution_snapshot_id: z.string().nullable().optional(),
  skip_snapshot_id: z.string().nullable().optional(),
});

// ============================================================================
// Audit Events
// ============================================================================

/**
 * Audit event schema
 */
export const AuditEventSchema = z.object({
  audit_id: z.string(),
  event_type: AuditEventTypeSchema,
  event_time: z.string(),
  notification_id: z.string(),
  notification_type: z.string(),
  autonomy_context: AutonomyContextSchema,
  payload: z.record(z.string(), z.unknown()),
  correlation_id: z.string().optional(),
});

/**
 * Audit event list response schema
 */
export const AuditEventListResponseSchema = z.object({
  items: z.array(AuditEventSchema),
  pagination: PaginationInfoSchema,
});

// ============================================================================
// Delivery Timeline
// ============================================================================

/**
 * Delivery attempt schema
 */
export const DeliveryAttemptSchema = z.object({
  attempt_id: z.string(),
  channel: ChannelSchema,
  status: z.string(), // SUCCESS, FAILED, RATE_LIMITED, SKIPPED
  started_at: z.string(),
  completed_at: z.string(),
  duration_ms: z.number(),
  error_message: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  metadata: z.record(z.string(), z.unknown()).nullable().optional(),
});

/**
 * Delivery timeline response schema (full detail)
 */
export const RuntimeEventSchema = z.object({
  id: z.string(),
  notification_id: z.string(),
  kind: z.string(),
  at: z.number(),
  payload: z.record(z.string(), z.unknown()),
  callback_pending: z.boolean().optional(),
  callback_attempts: z.number().optional(),
  callback_error: z.string().nullable().optional(),
}).passthrough();

export const DeliveryTimelineResponseSchema = z.object({
  runtime_state: z.object({
    delivery_status: z.string(),
    ack_status: z.string().nullable(),
    deadline: z.number().nullable().optional(),
    dead_letter: z.boolean(),
    policy_config_hash: z.string().nullable().optional(),
    policy_evaluation_id: z.string().nullable().optional(),
    require_ack: z.boolean().optional(),
    obligation_owner_id: z.string().nullable().optional(),
    effective_status: z.string().optional(),
    effective_ack_status: z.string().nullable().optional(),
    ack_inherited: z.boolean().optional(),
    obligation_resolution_status: z.string().optional(),
    obligation_resolution_error: z.string().nullable().optional(),
    actor: z.string().nullable().optional(),
    responded_at: z.number().nullable().optional(),
    response_metadata: z.record(z.string(), z.unknown()).nullable().optional(),
    events: z.array(RuntimeEventSchema).optional(),
    events_total_count: z.number().optional(),
    events_truncated: z.boolean().optional(),
  }).nullable().optional(),
  notification_id: z.string(),
  notification_type: z.string(),
  intent: NotificationIntentSchema,
  delivery_mode: DeliveryModeSchema,
  status: DeliveryStatusSchema,
  created_at: z.string(),
  delivered_at: z.string().nullable().optional(),
  attempts: z.array(DeliveryAttemptSchema),
  channels_attempted: z.array(ChannelSchema),
  channels_succeeded: z.array(ChannelSchema),
  channels_failed: z.array(ChannelSchema),
  autonomy_context: AutonomyContextResponseSchema,
});

/**
 * Delivery timeline summary schema (list item)
 */
export const DeliveryTimelineSummarySchema = z.object({
  notification_id: z.string(),
  notification_type: z.string(),
  intent: NotificationIntentSchema,
  delivery_mode: DeliveryModeSchema,
  status: DeliveryStatusSchema,
  created_at: z.string(),
  delivered_at: z.string().nullable().optional(),
  channels_attempted: z.array(ChannelSchema),
  channels_succeeded: z.array(ChannelSchema),
  autonomy_mode: AutonomyModeSchema,
  agent_id: z.string(),
});

/**
 * Delivery timeline list response schema
 */
export const DeliveryTimelineListResponseSchema = z.object({
  items: z.array(DeliveryTimelineSummarySchema),
  pagination: PaginationInfoSchema,
});

// ============================================================================
// Invariants
// ============================================================================

/**
 * Evidence link schema
 */
export const EvidenceLinkSchema = z.object({
  path: z.string(),
  note: z.string(),
  line_ref: z.string().optional(),
});

/**
 * Invariant enforcement schema
 */
export const InvariantEnforcementSchema = z.object({
  type: EnforcementTypeSchema,
  description: z.string(),
});

/**
 * Invariant entry schema
 */
export const InvariantEntrySchema = z.object({
  id: z.string(),
  statement: z.string(),
  severity: InvariantSeveritySchema,
  status: InvariantStatusSchema,
  enforcement: InvariantEnforcementSchema,
  evidence: z.array(EvidenceLinkSchema),
  owner: z.string(),
  last_reviewed: z.string(),
  mitigation: z.array(z.string()).optional(),
});

/**
 * Invariant list response schema
 * Includes optional degraded flag for degraded-state handling
 */
export const InvariantListResponseSchema = z.object({
  items: z.array(InvariantEntrySchema),
  pagination: PaginationInfoSchema,
  degraded: z.boolean().optional(),
});

/**
 * Invariant summary response schema
 * Includes optional degraded flag for degraded-state handling
 */
export const InvariantSummaryResponseSchema = z.object({
  total_count: z.number(),
  by_severity: z.record(z.string(), z.number()),
  by_enforcement_type: z.record(z.string(), z.number()),
  by_status: z.record(z.string(), z.number()),
  exceptions_requiring_review: z.number(),
  last_updated: z.string(),
  degraded: z.boolean().optional(),
});

// ============================================================================
// Policy Inspector
// ============================================================================

/**
 * Resolution step schema
 */
export const ResolutionStepSchema = z.object({
  source: ResolutionSourceSchema,
  value: z.unknown(),
  applied: z.boolean(),
  reason: z.string().nullable(),
});

/**
 * Effective policy schema
 */
export const EffectivePolicySchema = z.object({
  delivery_mode: DeliveryModeSchema,
  channels: z.array(ChannelSchema),
  require_ack: z.boolean(),
  ack_timeout_minutes: z.number().nullable(),
  dedup_window_seconds: z.number(),
});

/**
 * Resolution context schema
 */
export const ResolutionContextSchema = z.object({
  intent: NotificationIntentSchema,
  autonomy_mode: AutonomyModeSchema,
  irreversible: z.boolean(),
  policy_found: z.boolean(),
  policy_notification_type: z.string().nullable(),
});

/**
 * Effective policy response schema
 */
export const EffectivePolicyResponseSchema = z.object({
  notification_type: z.string(),
  effective: EffectivePolicySchema,
  resolution: z.record(z.string(), z.array(ResolutionStepSchema)),
  resolution_context: ResolutionContextSchema,
});

/**
 * Policy lifecycle status enum - strict validation
 */
export const PolicyLifecycleStatusSchema = z.enum(['ACTIVE', 'DRAFT', 'PREVIEW', 'RETIRED']);

/**
 * Policy revision summary schema
 */
export const PolicyRevisionSummarySchema = z.object({
  policy_id: z.string().nullable().optional(),
  notification_type: z.string(),
  version: z.string(),
  status: PolicyLifecycleStatusSchema,
  config_hash: z.string().nullable().optional(),
  previous_version_id: z.string().nullable().optional(),
  intent: NotificationIntentSchema.nullable(),
  channels: z.array(ChannelSchema),
  delivery_mode: DeliveryModeSchema.nullable(),
  require_ack: z.boolean().nullable(),
  ack_timeout_minutes: z.number().nullable().optional(),
  ack_timeout_seconds: z.number().nullable().optional(),
  dedup_window_seconds: z.number(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  activated_at: z.string().nullable().optional(),
  retired_at: z.string().nullable().optional(),
});

/**
 * Policy revision list response schema
 */
export const PolicyRevisionListResponseSchema = z.object({
  items: z.array(PolicyRevisionSummarySchema),
  total_count: z.number(),
});

// ============================================================================
// Type Inference
// ============================================================================

// Export inferred types for use in decoders
export type PaginationInfo = z.infer<typeof PaginationInfoSchema>;
export type AuditEvent = z.infer<typeof AuditEventSchema>;
export type AuditEventListResponse = z.infer<typeof AuditEventListResponseSchema>;
export type DeliveryAttempt = z.infer<typeof DeliveryAttemptSchema>;
export type DeliveryTimelineResponse = z.infer<typeof DeliveryTimelineResponseSchema>;
export type DeliveryTimelineSummary = z.infer<typeof DeliveryTimelineSummarySchema>;
export type DeliveryTimelineListResponse = z.infer<typeof DeliveryTimelineListResponseSchema>;
export type InvariantEntry = z.infer<typeof InvariantEntrySchema>;
export type InvariantListResponse = z.infer<typeof InvariantListResponseSchema>;
export type InvariantSummaryResponse = z.infer<typeof InvariantSummaryResponseSchema>;
export type EffectivePolicyResponse = z.infer<typeof EffectivePolicyResponseSchema>;
export type PolicyRevisionSummary = z.infer<typeof PolicyRevisionSummarySchema>;
export type PolicyRevisionListResponse = z.infer<typeof PolicyRevisionListResponseSchema>;

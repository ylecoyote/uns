/**
 * Test mock data for audit events and deliveries.
 */

import type {
  AuditEvent,
  AuditEventListResponse,
  DeliveryTimelineSummary,
  DeliveryTimelineResponse,
  DeliveryTimelineListResponse,
  DeliveryAttempt,
} from '../types/api';

export const mockAuditEvent: AuditEvent = {
  audit_id: '123e4567-e89b-12d3-a456-426614174000',
  event_type: 'delivery.succeeded',
  event_time: '2026-01-23T12:00:00Z',
  notification_id: '123e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.order_executed',
  autonomy_context: {
    autonomy_mode: 'LIVE',
    agent_id: '123e4567-e89b-12d3-a456-426614174002',
    plan_id: '123e4567-e89b-12d3-a456-426614174003',
  },
  payload: {
    status: 'DELIVERED',
    channels_attempted: ['SLACK'],
    channels_succeeded: ['SLACK'],
    channels_failed: [],
  },
  correlation_id: 'corr-123',
};

export const mockAuditEventFailed: AuditEvent = {
  audit_id: '223e4567-e89b-12d3-a456-426614174000',
  event_type: 'delivery.failed',
  event_time: '2026-01-23T11:30:00Z',
  notification_id: '223e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.risk_alert',
  autonomy_context: {
    autonomy_mode: 'LIVE',
    agent_id: '223e4567-e89b-12d3-a456-426614174002',
  },
  payload: {
    status: 'FAILED',
    channels_attempted: ['SLACK', 'EMAIL'],
    channels_succeeded: [],
    channels_failed: ['SLACK', 'EMAIL'],
    error_message: 'All channels failed',
  },
};

export const mockAuditEventAck: AuditEvent = {
  audit_id: '323e4567-e89b-12d3-a456-426614174000',
  event_type: 'ack.received',
  event_time: '2026-01-23T12:05:00Z',
  notification_id: '123e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.order_executed',
  autonomy_context: {
    autonomy_mode: 'LIVE',
    agent_id: '123e4567-e89b-12d3-a456-426614174002',
  },
  payload: {
    old_status: 'PENDING',
    new_status: 'ACKED',
    acked_by: 'user@example.com',
    acked_at: '2026-01-23T12:05:00Z',
  },
};

export const mockAuditEventsResponse: AuditEventListResponse = {
  items: [mockAuditEvent, mockAuditEventFailed, mockAuditEventAck],
  pagination: {
    next_cursor: null,
    has_more: false,
    total_count: 3,
  },
};

export const mockEmptyResponse: AuditEventListResponse = {
  items: [],
  pagination: {
    next_cursor: null,
    has_more: false,
    total_count: 0,
  },
};

export const mockPaginatedResponse: AuditEventListResponse = {
  items: [mockAuditEvent],
  pagination: {
    next_cursor: 'cursor-123',
    has_more: true,
    total_count: 10,
  },
};

// Delivery Mock Data

export const mockDeliveryAttempt: DeliveryAttempt = {
  attempt_id: '423e4567-e89b-12d3-a456-426614174000',
  channel: 'SLACK',
  status: 'SUCCESS',
  started_at: '2026-01-23T12:00:00Z',
  completed_at: '2026-01-23T12:00:01Z',
  duration_ms: 1000,
  error_message: null,
  error_code: null,
  metadata: null,
};

export const mockDeliveryAttemptFailed: DeliveryAttempt = {
  attempt_id: '523e4567-e89b-12d3-a456-426614174000',
  channel: 'EMAIL',
  status: 'FAILED',
  started_at: '2026-01-23T12:00:02Z',
  completed_at: '2026-01-23T12:00:03Z',
  duration_ms: 1500,
  error_message: 'SMTP connection refused',
  error_code: 'SMTP_ERROR',
  metadata: null,
};

export const mockDeliverySummary: DeliveryTimelineSummary = {
  notification_id: '123e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.order_executed',
  intent: 'OPERATIONAL',
  delivery_mode: 'GUARANTEED',
  status: 'DELIVERED',
  created_at: '2026-01-23T12:00:00Z',
  delivered_at: '2026-01-23T12:00:01Z',
  channels_attempted: ['SLACK'],
  channels_succeeded: ['SLACK'],
  autonomy_mode: 'LIVE',
  agent_id: '123e4567-e89b-12d3-a456-426614174002',
};

export const mockDeliverySummaryFailed: DeliveryTimelineSummary = {
  notification_id: '223e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.risk_alert',
  intent: 'SAFETY',
  delivery_mode: 'GUARANTEED',
  status: 'FAILED',
  created_at: '2026-01-23T11:30:00Z',
  delivered_at: null,
  channels_attempted: ['SLACK', 'EMAIL'],
  channels_succeeded: [],
  autonomy_mode: 'LIVE',
  agent_id: '223e4567-e89b-12d3-a456-426614174002',
};

export const mockDeliverySummaryPending: DeliveryTimelineSummary = {
  notification_id: '323e4567-e89b-12d3-a456-426614174001',
  notification_type: 'governance.audit_required',
  intent: 'GOVERNANCE',
  delivery_mode: 'BEST_EFFORT',
  status: 'PENDING',
  created_at: '2026-01-23T12:30:00Z',
  delivered_at: null,
  channels_attempted: [],
  channels_succeeded: [],
  autonomy_mode: 'SHADOW',
  agent_id: '323e4567-e89b-12d3-a456-426614174002',
};

export const mockDeliveryTimeline: DeliveryTimelineResponse = {
  notification_id: '123e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.order_executed',
  intent: 'OPERATIONAL',
  delivery_mode: 'GUARANTEED',
  status: 'DELIVERED',
  created_at: '2026-01-23T12:00:00Z',
  delivered_at: '2026-01-23T12:00:01Z',
  attempts: [mockDeliveryAttempt],
  channels_attempted: ['SLACK'],
  channels_succeeded: ['SLACK'],
  channels_failed: [],
  autonomy_context: {
    autonomy_mode: 'LIVE',
    agent_id: '123e4567-e89b-12d3-a456-426614174002',
    plan_id: '123e4567-e89b-12d3-a456-426614174003',
    decision_snapshot_id: null,
    execution_snapshot_id: null,
    skip_snapshot_id: null,
  },
};

export const mockDeliveryTimelineFailed: DeliveryTimelineResponse = {
  notification_id: '223e4567-e89b-12d3-a456-426614174001',
  notification_type: 'trading.risk_alert',
  intent: 'SAFETY',
  delivery_mode: 'GUARANTEED',
  status: 'FAILED',
  created_at: '2026-01-23T11:30:00Z',
  delivered_at: null,
  attempts: [mockDeliveryAttempt, mockDeliveryAttemptFailed],
  channels_attempted: ['SLACK', 'EMAIL'],
  channels_succeeded: ['SLACK'],
  channels_failed: ['EMAIL'],
  autonomy_context: {
    autonomy_mode: 'LIVE',
    agent_id: '223e4567-e89b-12d3-a456-426614174002',
    plan_id: null,
    decision_snapshot_id: '223e4567-e89b-12d3-a456-426614174004',
    execution_snapshot_id: null,
    skip_snapshot_id: null,
  },
};

export const mockDeliveriesListResponse: DeliveryTimelineListResponse = {
  items: [mockDeliverySummary, mockDeliverySummaryFailed, mockDeliverySummaryPending],
  pagination: {
    next_cursor: null,
    has_more: false,
    total_count: 3,
  },
};

export const mockEmptyDeliveriesResponse: DeliveryTimelineListResponse = {
  items: [],
  pagination: {
    next_cursor: null,
    has_more: false,
    total_count: 0,
  },
};

export const mockPaginatedDeliveriesResponse: DeliveryTimelineListResponse = {
  items: [mockDeliverySummary],
  pagination: {
    next_cursor: 'delivery-cursor-123',
    has_more: true,
    total_count: 10,
  },
};

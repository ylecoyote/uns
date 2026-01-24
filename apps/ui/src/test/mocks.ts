/**
 * Test mock data for audit events.
 */

import type { AuditEvent, AuditEventListResponse } from '../types/api';

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

/**
 * Audit API client.
 *
 * Provides typed access to the audit event stream.
 * All operations are READ-ONLY.
 */

import type {
  AuditEventListResponse,
  AuditEventFilter,
} from '../types/api';
import { apiGet, type RequestOptions } from './client';

/**
 * Fetch audit events with optional filtering and pagination.
 *
 * @param filter - Filter and pagination parameters
 * @param options - Request options (requestId, signal)
 * @returns Paginated list of audit events
 */
export async function getAuditEvents(
  filter?: AuditEventFilter,
  options?: RequestOptions
): Promise<AuditEventListResponse> {
  const params: Record<string, string | number | undefined> = {};

  if (filter) {
    if (filter.cursor) params.cursor = filter.cursor;
    if (filter.limit) params.limit = filter.limit;
    if (filter.start_time) params.start_time = filter.start_time;
    if (filter.end_time) params.end_time = filter.end_time;
    if (filter.event_type) params.event_type = filter.event_type;
    if (filter.notification_id) params.notification_id = filter.notification_id;
    if (filter.agent_id) params.agent_id = filter.agent_id;
    if (filter.autonomy_mode) params.autonomy_mode = filter.autonomy_mode;
    if (filter.correlation_id) params.correlation_id = filter.correlation_id;
  }

  return apiGet<AuditEventListResponse>('/audit', params, options);
}

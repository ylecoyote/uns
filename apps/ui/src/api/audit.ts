/**
 * Audit API client.
 *
 * Provides typed access to the audit event stream.
 * All operations are READ-ONLY.
 *
 * Contract validation is applied via decoders to detect drift early.
 *
 * Endpoints:
 * - GET /ui/audit - List audit events with filtering and pagination
 */

import type {
  AuditEventListResponse,
  AuditEventFilter,
} from '../types/api';
import { apiGet, filterToParams, type RequestOptions } from './client';
import { decodeAuditEventsList, decodeWithMode } from './validators';

/**
 * Fetch audit events with optional filtering and pagination.
 *
 * @param filter - Filter and pagination parameters
 * @param options - Request options (requestId, signal)
 * @returns Paginated list of audit events
 */
export async function fetchAuditEvents(
  filter: AuditEventFilter = {},
  options?: RequestOptions
): Promise<AuditEventListResponse> {
  const params = filterToParams(filter);
  const data = await apiGet<AuditEventListResponse>('/audit', params, options);
  return decodeWithMode(decodeAuditEventsList, data, 'GET /ui/audit');
}

// Re-export with legacy name for backwards compatibility
export const getAuditEvents = fetchAuditEvents;

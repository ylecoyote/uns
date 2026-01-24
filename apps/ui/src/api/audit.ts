/**
 * Audit API client.
 *
 * Provides typed access to the audit event stream.
 * All operations are READ-ONLY.
 *
 * Endpoints:
 * - GET /ui/audit - List audit events with filtering and pagination
 */

import type {
  AuditEventListResponse,
  AuditEventFilter,
} from '../types/api';
import { apiGet, filterToParams, type RequestOptions } from './client';

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
  return apiGet<AuditEventListResponse>('/audit', filterToParams(filter), options);
}

// Re-export with legacy name for backwards compatibility
export const getAuditEvents = fetchAuditEvents;

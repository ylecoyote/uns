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
import { apiRequest, buildQueryString } from './client';

/**
 * Fetch audit events with optional filtering and pagination.
 *
 * @param filter - Filter and pagination parameters
 * @returns Paginated list of audit events
 */
export async function fetchAuditEvents(
  filter: AuditEventFilter = {}
): Promise<AuditEventListResponse> {
  const queryString = buildQueryString(filter);
  return apiRequest<AuditEventListResponse>(`/ui/audit${queryString}`);
}

// Re-export with legacy name for backwards compatibility
export const getAuditEvents = fetchAuditEvents;

/**
 * API client for invariants endpoints
 *
 * Endpoints:
 * - GET /ui/invariants - List invariants with filtering
 * - GET /ui/invariants/summary - Get summary statistics
 */

import type {
  InvariantFilters,
  InvariantListResponse,
  InvariantSummaryResponse,
} from '../types/invariants';
import { apiGet } from './client';

/**
 * Fetch invariants list with optional filters and pagination
 */
export async function fetchInvariants(
  filters: InvariantFilters = {}
): Promise<InvariantListResponse> {
  // Convert typed filters to generic query params
  const params: Record<string, string | number | boolean | undefined> = {
    severity: filters.severity,
    enforcement_type: filters.enforcement_type,
    status: filters.status,
    search: filters.search,
    cursor: filters.cursor,
    limit: filters.limit,
  };
  return apiGet<InvariantListResponse>('/invariants', params);
}

/**
 * Fetch invariants summary statistics
 */
export async function fetchInvariantsSummary(): Promise<InvariantSummaryResponse> {
  return apiGet<InvariantSummaryResponse>('/invariants/summary');
}

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
  return apiGet<InvariantListResponse>('/invariants', {
    severity: filters.severity,
    enforcement_type: filters.enforcement_type,
    status: filters.status,
    search: filters.search,
    cursor: filters.cursor,
    limit: filters.limit,
  });
}

/**
 * Fetch invariants summary statistics
 */
export async function fetchInvariantsSummary(): Promise<InvariantSummaryResponse> {
  return apiGet<InvariantSummaryResponse>('/invariants/summary');
}

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
import { apiRequest, buildQueryString } from './client';

/**
 * Fetch invariants list with optional filters and pagination
 */
export async function fetchInvariants(
  filters: InvariantFilters = {}
): Promise<InvariantListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<InvariantListResponse>(`/ui/invariants${queryString}`);
}

/**
 * Fetch invariants summary statistics
 */
export async function fetchInvariantsSummary(): Promise<InvariantSummaryResponse> {
  return apiRequest<InvariantSummaryResponse>('/ui/invariants/summary');
}

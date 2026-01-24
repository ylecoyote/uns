/**
 * Invariants API client.
 *
 * Provides typed access to the invariants endpoints.
 * All operations are READ-ONLY.
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
import { apiGet, filterToParams, type RequestOptions } from './client';

/**
 * Fetch invariants list with optional filters and pagination.
 *
 * @param filters - Filter and pagination parameters
 * @param options - Request options (requestId, signal)
 * @returns Paginated list of invariant entries
 *
 * @example
 * const response = await fetchInvariants({ severity: 'HIGH', limit: 10 });
 */
export async function fetchInvariants(
  filters: InvariantFilters = {},
  options?: RequestOptions
): Promise<InvariantListResponse> {
  const params = filterToParams(filters);
  return apiGet<InvariantListResponse>('/invariants', params, options);
}

/**
 * Fetch invariants summary statistics.
 *
 * @param options - Request options (requestId, signal)
 * @returns Summary statistics for invariants
 *
 * @example
 * const summary = await fetchInvariantsSummary();
 */
export async function fetchInvariantsSummary(
  options?: RequestOptions
): Promise<InvariantSummaryResponse> {
  return apiGet<InvariantSummaryResponse>('/invariants/summary', undefined, options);
}

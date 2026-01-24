/**
 * Standardized typed API client for UNS UI endpoints.
 *
 * This is the SINGLE SOURCE OF TRUTH for all API communication.
 * All endpoints are READ-ONLY per ui-scope.md.
 *
 * Features:
 * - Type-safe request/response handling
 * - Consistent error handling with ApiError class
 * - Request ID propagation via X-Request-ID header
 * - Query parameter building utilities
 * - AbortSignal support for request cancellation
 */

import type { ErrorResponse } from '../types/api';

/**
 * Custom error class for API errors with full metadata.
 */
export class ApiError extends Error {
  public readonly code: string;
  public readonly requestId: string;
  public readonly statusCode: number;
  public readonly details?: Record<string, unknown>;

  constructor(response: ErrorResponse, statusCode: number) {
    super(response.error.message);
    this.name = 'ApiError';
    this.code = response.error.code;
    this.requestId = response.request_id;
    this.statusCode = statusCode;
    this.details = response.error.details;
  }
}

/**
 * Request options for API calls.
 */
export interface RequestOptions {
  /** Request ID for correlation tracking */
  requestId?: string;
  /** AbortSignal for request cancellation */
  signal?: AbortSignal;
}

/**
 * Type for query parameter values that can be serialized to URL search params.
 */
export type QueryParamValue = string | number | boolean | undefined;

/**
 * Type for query parameter objects.
 */
export type QueryParams = Record<string, QueryParamValue>;

/** Base URL for all API endpoints */
const API_BASE = '/ui';

/**
 * Build a query string from a parameters object.
 * Filters out undefined values and properly encodes all parameters.
 *
 * @param params - Object containing query parameters
 * @returns Query string with leading '?' or empty string if no params
 *
 * @example
 * buildQueryString({ limit: 10, cursor: undefined, status: 'active' })
 * // Returns '?limit=10&status=active'
 */
export function buildQueryString(params: QueryParams): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      searchParams.set(key, String(value));
    }
  });

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
}

/**
 * Make a typed GET request to the API.
 *
 * @param path - API path (e.g., '/audit')
 * @param params - Query parameters (undefined values are filtered out)
 * @param options - Request options including optional requestId for correlation
 * @returns Promise resolving to the typed response
 * @throws {ApiError} When the server returns a non-OK response
 *
 * @example
 * const events = await apiGet<AuditEventListResponse>('/audit', { limit: 10 });
 */
export async function apiGet<T>(
  path: string,
  params?: QueryParams,
  options?: RequestOptions
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);

  // Add query parameters, filtering out undefined values
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const headers: HeadersInit = {
    Accept: 'application/json',
  };

  // Propagate request ID for correlation if provided
  if (options?.requestId) {
    headers['X-Request-ID'] = options.requestId;
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers,
    signal: options?.signal,
  });

  if (!response.ok) {
    const errorData = (await response.json()) as { detail: ErrorResponse } | ErrorResponse;
    // Handle FastAPI's error wrapping
    const errorResponse = 'detail' in errorData ? errorData.detail : errorData;
    throw new ApiError(errorResponse, response.status);
  }

  return response.json() as Promise<T>;
}

/**
 * Convenience wrapper for making typed API requests.
 * Uses apiGet internally but accepts a full path including the /ui prefix.
 *
 * @param fullPath - Full API path (e.g., '/ui/audit')
 * @param options - Request options
 * @returns Promise resolving to the typed response
 * @throws {ApiError} When the server returns a non-OK response
 *
 * @example
 * const summary = await apiRequest<InvariantSummaryResponse>('/ui/invariants/summary');
 */
export async function apiRequest<T>(
  fullPath: string,
  options?: RequestOptions
): Promise<T> {
  // If the path starts with /ui, strip it since apiGet adds it
  const path = fullPath.startsWith('/ui') ? fullPath.slice(3) : fullPath;
  return apiGet<T>(path, undefined, options);
}

/**
 * Convert a filter object to query parameters.
 * This utility maps filter properties to their query parameter equivalents.
 *
 * @param filter - Filter object with optional properties
 * @returns Query parameters object with undefined values preserved
 *
 * @example
 * const params = filterToParams({ severity: 'HIGH', limit: 10, unused: undefined });
 * // Returns { severity: 'HIGH', limit: 10, unused: undefined }
 */
export function filterToParams<T extends object>(filter: T): QueryParams {
  const params: QueryParams = {};
  for (const [key, value] of Object.entries(filter)) {
    if (value !== undefined && value !== null) {
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        params[key] = value;
      }
    }
  }
  return params;
}

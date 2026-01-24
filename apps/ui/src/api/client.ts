/**
 * Base API client for UNS UI endpoints.
 *
 * All endpoints are READ-ONLY per ui-scope.md.
 * Supports request_id propagation via X-Request-ID header.
 */

import type { ErrorResponse } from '../types/api';

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

  // Alias for consistency with types/common.ts interface
  get request_id(): string {
    return this.requestId;
  }
}

export interface RequestOptions {
  requestId?: string;
  signal?: AbortSignal;
}

const API_BASE = '/ui';

/**
 * Make a GET request to the API.
 *
 * @param path - API path (e.g., '/audit')
 * @param params - Query parameters
 * @param options - Request options including optional requestId for correlation
 */
export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
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
 * Build a query string from an object of parameters.
 * Filters out undefined/null values.
 *
 * @param params - Object with query parameters
 * @returns Query string including leading '?' if params exist, empty string otherwise
 */
export function buildQueryString(
  params: Record<string, string | number | boolean | undefined | null>
): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      searchParams.set(key, String(value));
    }
  });

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
}

/**
 * Make a GET request to the API using a full path (including /ui prefix if needed).
 *
 * @param path - Full API path (e.g., '/ui/audit')
 * @param options - Request options including optional requestId for correlation
 */
export async function apiRequest<T>(
  path: string,
  options?: RequestOptions
): Promise<T> {
  const url = new URL(path, window.location.origin);

  const headers: HeadersInit = {
    Accept: 'application/json',
  };

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
    const errorResponse = 'detail' in errorData ? errorData.detail : errorData;
    throw new ApiError(errorResponse, response.status);
  }

  return response.json() as Promise<T>;
}

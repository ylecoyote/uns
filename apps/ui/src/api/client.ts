/**
 * Standardized typed API client for UNS Console endpoints.
 *
 * This is the SINGLE SOURCE OF TRUTH for all API communication.
 *
 * Features:
 * - Type-safe request/response handling for GET, POST, and DELETE
 * - Consistent error handling with ApiError class
 * - Strict 401 (expire session) vs. 403/409 (keep session, surface error) separation
 * - Optional allowStatus support (e.g., 503 on /readyz)
 * - Request ID propagation via X-Request-ID header
 * - Query parameter building utilities
 * - AbortSignal support for request cancellation
 */

import type { ErrorResponse } from '../types/api';
import { expireConsoleSession, getConsoleSession } from '../auth/session';

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

  // Alias for consistency with types/common.ts interface
  get request_id(): string {
    return this.requestId;
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
  /** Transient sign-in probe credential; never establishes a session by itself. */
  credential?: string;
  /** Non-2xx HTTP status codes whose JSON body should still be parsed and returned (e.g. [503] for /readyz). */
  allowStatus?: readonly number[];
}

export interface ApiStatusResult<T> {
  readonly status: number;
  readonly ok: boolean;
  readonly data: T;
}

/**
 * Type for query parameter values that can be serialized to URL search params.
 */
export type QueryParamValue = string | number | boolean | undefined;

/**
 * Type for query parameter objects.
 */
export type QueryParams = Record<string, QueryParamValue>;

/** Base URL for /ui endpoints */
const API_BASE = '/ui';

/**
 * Build a query string from a parameters object.
 * Filters out undefined values and properly encodes all parameters.
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
 * Make a typed GET request to a /ui endpoint.
 */
export async function apiGet<T>(
  path: string,
  params?: QueryParams,
  options?: RequestOptions
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);

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
  const session = getConsoleSession();
  const credential = options?.credential ?? session.credential;
  if (credential) headers.Authorization = `Bearer ${credential}`;

  if (options?.requestId) {
    headers['X-Request-ID'] = options.requestId;
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers,
    signal: options?.signal,
    cache: 'no-store',
    redirect: 'error',
  });

  const isAllowedStatus = options?.allowStatus?.includes(response.status) ?? false;
  if (!response.ok && !isAllowedStatus) {
    if (response.status === 401 && options?.credential === undefined) {
      expireConsoleSession(session);
    }
    throw await responseError(response);
  }

  return response.json() as Promise<T>;
}

/**
 * Make a typed HTTP request to any root-relative endpoint (/ui/*, /api/v1/*, /readyz)
 * while preserving the HTTP status code.
 */
export async function apiRootRequestWithStatus<T>(
  method: 'GET' | 'POST' | 'DELETE',
  path: string,
  body?: unknown,
  options?: RequestOptions
): Promise<ApiStatusResult<T>> {
  const url = new URL(path, window.location.origin);
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  const session = getConsoleSession();
  const credential = options?.credential ?? session.credential;
  if (credential) {
    headers.Authorization = `Bearer ${credential}`;
  }
  if (options?.requestId) {
    headers['X-Request-ID'] = options.requestId;
  }

  const init: RequestInit = {
    method,
    headers,
    signal: options?.signal,
    cache: 'no-store',
    redirect: 'error',
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  const response = await fetch(url.toString(), init);
  const isAllowedStatus = options?.allowStatus?.includes(response.status) ?? false;

  if (!response.ok && !isAllowedStatus) {
    // Strictly expire session only on 401 Unauthorized, never on 403 Forbidden or 409 Conflict.
    if (response.status === 401 && options?.credential === undefined) {
      expireConsoleSession(session);
    }
    throw await responseError(response);
  }

  const data = (await response.json()) as T;
  return {
    status: response.status,
    ok: response.ok,
    data,
  };
}

/**
 * Make a typed HTTP request to any root-relative endpoint (/ui/*, /api/v1/*, /readyz).
 */
export async function apiRootRequest<T>(
  method: 'GET' | 'POST' | 'DELETE',
  path: string,
  body?: unknown,
  options?: RequestOptions
): Promise<T> {
  const result = await apiRootRequestWithStatus<T>(method, path, body, options);
  return result.data;
}

async function responseError(response: Response): Promise<ApiError> {
  // Auth middleware and gateways may return plain FastAPI errors or HTML.
  // Preserve typed API errors, but never display raw unstructured 401/5xx error bodies.
  let rawBody: unknown;
  try {
    rawBody = await response.json();
  } catch {
    /* Use the safe fallback below. */
  }
  const requestIdHeader = response.headers?.get('X-Request-ID') ?? '';

  let body: unknown = rawBody;
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detailValue = (body as { detail: unknown }).detail;
    if (typeof detailValue === 'object' && detailValue !== null) {
      body = detailValue;
    } else if (
      typeof detailValue === 'string' &&
      (response.status === 404 || response.status === 409 || response.status === 422)
    ) {
      return new ApiError(
        {
          error: { code: `http_${response.status}`, message: detailValue },
          request_id: requestIdHeader,
        },
        response.status
      );
    }
  }

  if (typeof body === 'object' && body !== null && 'error' in body) {
    const errField = (body as { error: unknown }).error;
    // Standard UIErrorResponse envelope: { error: { code, message, details? }, request_id }
    if (
      typeof errField === 'object' &&
      errField !== null &&
      'code' in errField &&
      typeof (errField as { code: unknown }).code === 'string' &&
      'message' in errField &&
      typeof (errField as { message: unknown }).message === 'string' &&
      'request_id' in body &&
      typeof (body as { request_id: unknown }).request_id === 'string'
    ) {
      return new ApiError(body as ErrorResponse, response.status);
    }
    // Write/Auth FastAPI envelope: { error: string, message: string, ... }
    if (
      typeof errField === 'string' &&
      'message' in body &&
      typeof (body as { message: unknown }).message === 'string'
    ) {
      return new ApiError(
        {
          error: {
            code: errField,
            message: (body as { message: string }).message,
            details: body as Record<string, unknown>,
          },
          request_id: requestIdHeader,
        },
        response.status
      );
    }
  }

  return new ApiError(
    {
      error: {
        code: `http_${response.status}`,
        message: `The service returned an error (HTTP ${response.status}).`,
      },
      request_id: requestIdHeader,
    },
    response.status
  );
}

/**
 * Convenience wrapper for making typed API requests.
 * Uses apiGet internally but accepts a full path including the /ui prefix.
 */
export async function apiRequest<T>(
  fullPath: string,
  options?: RequestOptions
): Promise<T> {
  const path = fullPath.startsWith('/ui') ? fullPath.slice(3) : fullPath;
  return apiGet<T>(path, undefined, options);
}

/**
 * Convert a filter object to query parameters.
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

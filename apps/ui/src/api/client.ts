/**
 * Base API client with request ID propagation and error handling
 */

import type { ApiError, ErrorResponse } from '../types/common';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

function generateRequestId(): string {
  return `ui-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const requestId = generateRequestId();

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-Request-ID': requestId,
    ...options.headers,
  };

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorBody: ErrorResponse | undefined;
    try {
      errorBody = await response.json();
    } catch {
      // Ignore JSON parse errors
    }

    const error: ApiError = new Error(
      errorBody?.error?.message || `Request failed: ${response.status}`
    ) as ApiError;
    error.code = errorBody?.error?.code || 'unknown_error';
    error.request_id = errorBody?.request_id || requestId;
    error.details = errorBody?.error?.details;
    throw error;
  }

  return response.json();
}

export function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, String(value));
    }
  }

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
}

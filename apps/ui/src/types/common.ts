/**
 * Common types shared across UI components
 */

export interface ErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ErrorResponse {
  error: ErrorDetail;
  request_id: string;
}

export interface ApiError extends Error {
  code: string;
  request_id?: string;
  details?: Record<string, unknown>;
}

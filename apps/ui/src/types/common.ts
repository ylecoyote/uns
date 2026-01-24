/**
 * Common types shared across UI components.
 *
 * Re-exports core types from api.ts for backward compatibility.
 * New code should import directly from './api' or './types'.
 */

// Re-export types from api.ts as the single source of truth
export type { ErrorDetail, ErrorResponse } from './api';

/**
 * Interface for API error instances.
 * Note: The actual ApiError class is defined in '../api/client'.
 * Both requestId and request_id are supported for backward compatibility.
 */
export interface ApiError extends Error {
  code: string;
  requestId?: string;
  request_id?: string; // Alias for backward compatibility with existing components
  statusCode?: number;
  details?: Record<string, unknown>;
}

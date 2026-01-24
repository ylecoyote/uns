/**
 * Type exports for UNS UI Dashboard.
 *
 * Export all TypeScript types and interfaces from this index.
 */

// API types (includes PaginationInfo, ErrorDetail, ErrorResponse)
export * from './api';

// Common types (ApiError interface - distinct from the class in api/client.ts)
export type { ApiError } from './common';

// Invariants types (re-export specific types to avoid PaginationInfo conflict)
export type {
  InvariantSeverity,
  EnforcementType,
  InvariantStatus,
  EvidenceLink,
  InvariantEnforcement,
  InvariantEntry,
  InvariantListResponse,
  InvariantSummaryResponse,
  InvariantFilters,
} from './invariants';

// Route types
export * from './routes';

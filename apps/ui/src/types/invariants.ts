/**
 * Invariants types matching docs/ui/ui-data-contracts.md
 *
 * These types define the response shapes for invariant-related API endpoints.
 * Uses shared PaginationInfo from api.ts for consistency.
 */

import type { PaginationInfo } from './api';

export type InvariantSeverity = 'HIGH' | 'MEDIUM' | 'LOW';
export type EnforcementType = 'guard' | 'isolation' | 'test' | 'exception';
export type InvariantStatus = 'active' | 'inactive';

export interface EvidenceLink {
  path: string;
  note: string;
  line_ref?: string;
}

export interface InvariantEnforcement {
  type: EnforcementType;
  description: string;
}

export interface InvariantEntry {
  id: string;
  statement: string;
  severity: InvariantSeverity;
  status: InvariantStatus;
  enforcement: InvariantEnforcement;
  evidence: EvidenceLink[];
  owner: string;
  last_reviewed: string;
  mitigation?: string[];
}

export interface InvariantListResponse {
  items: InvariantEntry[];
  pagination: PaginationInfo;
}

export interface InvariantSummaryResponse {
  total_count: number;
  by_severity: Record<string, number>;
  by_enforcement_type: Record<string, number>;
  by_status: Record<string, number>;
  exceptions_requiring_review: number;
  last_updated: string;
}

export interface InvariantFilters {
  severity?: InvariantSeverity;
  enforcement_type?: EnforcementType;
  status?: InvariantStatus;
  search?: string;
  cursor?: string;
  limit?: number;
}

// Re-export PaginationInfo for convenience
export type { PaginationInfo };

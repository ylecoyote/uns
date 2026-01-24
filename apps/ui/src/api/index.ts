/**
 * Central API exports for UNS UI.
 *
 * This module provides a unified interface to all API functionality.
 * The client.ts module is the SINGLE SOURCE OF TRUTH for API communication.
 *
 * @example
 * import { apiGet, getAuditEvents, fetchInvariants, ApiError } from '../api';
 */

// Core client exports - base API functions and utilities
export {
  ApiError,
  apiGet,
  apiRequest,
  buildQueryString,
  filterToParams,
  type RequestOptions,
  type QueryParams,
  type QueryParamValue,
} from './client';

// Audit API exports
export { getAuditEvents } from './audit';

// Invariants API exports
export { fetchInvariants, fetchInvariantsSummary } from './invariants';

// Deliveries API exports
export { getDeliveries, getDeliveryTimeline } from './deliveries';

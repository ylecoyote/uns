/**
 * Central API exports for AGSignal Console.
 *
 * This module provides a unified interface to all API functionality.
 * The client.ts module is the SINGLE SOURCE OF TRUTH for API communication.
 *
 * @example
 * import { apiGet, getAuditEvents, fetchInvariants, ApiError } from '../api';
 *
 * // Contract validation
 * import { setValidationMode, decodeDeliveriesList } from '../api';
 * setValidationMode('strict'); // For development
 */

// Core client exports - base API functions and utilities
export {
  ApiError,
  apiGet,
  apiRequest,
  apiRootRequest,
  apiRootRequestWithStatus,
  buildQueryString,
  filterToParams,
  type ApiStatusResult,
  type RequestOptions,
  type QueryParams,
  type QueryParamValue,
} from './client';

// Audit API exports
export { getAuditEvents, fetchAuditEvents } from './audit';

// Invariants API exports
export { fetchInvariants, fetchInvariantsSummary } from './invariants';

// Deliveries API exports
export {
  getDeliveries,
  getDeliveryTimeline,
  acknowledgeNotification,
  dismissNotification,
} from './deliveries';

// Policies API exports
export {
  fetchEffectivePolicy,
  fetchActivePolicies,
  simulateNotification,
  sendTestNotification,
  reloadPolicies,
} from './policies';

// Operations & DLQ Recovery API exports
export {
  getReadyz,
  getChannelHealth,
  getDlqEntries,
  getRuntimeDeadLetters,
  replayNotification,
  resolveDlqEntry,
} from './operations';

// Contract validators - for runtime drift detection
export {
  // Decode functions
  decodeDeliveriesList,
  decodeDeliveryTimeline,
  decodeAuditEventsList,
  decodeInvariantsList,
  decodeInvariantsSummary,
  decodeEffectivePolicy,
  // Error handling
  ContractDriftError,
  assertDecode,
  logDriftIfFailed,
  // Configuration
  getValidationMode,
  setValidationMode,
  decodeWithMode,
  // Types
  type DecodeResult,
  type ValidationMode,
} from './validators';

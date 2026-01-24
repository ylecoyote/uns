/**
 * Contract validators for UI API responses.
 *
 * This module provides runtime validation to detect contract drift between
 * the backend API and the frontend TypeScript types.
 *
 * @example
 * ```typescript
 * import { decodeDeliveriesList, setValidationMode } from './validators';
 *
 * // Configure validation mode (call once at app startup)
 * setValidationMode('strict'); // For development
 * setValidationMode('lenient'); // For production (log warnings, don't throw)
 *
 * // Use decoders
 * const result = decodeDeliveriesList(apiResponse);
 * if (!result.success) {
 *   // Handle contract drift
 * }
 * ```
 *
 * @see schemas.ts for zod schema definitions
 * @see decoders.ts for decode functions
 */

// Schemas - for advanced usage (custom decoders, testing)
export * from './schemas';

// Decoders - primary API
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
} from './decoders';

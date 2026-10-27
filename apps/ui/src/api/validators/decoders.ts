/**
 * Contract decoders for UI API responses.
 *
 * These decoders provide runtime validation of API responses using zod schemas.
 * They detect contract drift between the backend and frontend early, before
 * the data reaches components where undefined access could cause runtime errors.
 *
 * Key features:
 * - Safe decoding with explicit success/failure result type
 * - Detailed error messages for debugging contract mismatches
 * - Optional strict mode for development vs lenient mode for production
 * - Type-safe decoded values
 *
 * Usage:
 * ```typescript
 * const result = decodeDeliveriesList(data);
 * if (!result.success) {
 *   console.error('Contract drift detected:', result.error);
 *   // Handle gracefully or report to monitoring
 * }
 * const validated = result.data; // Type-safe
 * ```
 *
 * @see schemas.ts for the zod schema definitions
 * @see docs/ui/ui-data-contracts.md for contract specifications
 */

import { z, ZodError } from 'zod';
import {
  ActivePolicyListResponseSchema,
  AuditEventListResponseSchema,
  DeliveryTimelineListResponseSchema,
  DeliveryTimelineResponseSchema,
  InvariantListResponseSchema,
  InvariantSummaryResponseSchema,
  EffectivePolicyResponseSchema,
  PolicyRevisionListResponseSchema,
  type ActivePolicyListResponse,
  type AuditEventListResponse,
  type DeliveryTimelineListResponse,
  type DeliveryTimelineResponse,
  type InvariantListResponse,
  type InvariantSummaryResponse,
  type EffectivePolicyResponse,
  type PolicyRevisionListResponse,
} from './schemas';

// ============================================================================
// Types
// ============================================================================

/**
 * Result of a decode operation.
 * Either success with validated data, or failure with error details.
 */
export type DecodeResult<T> =
  | { success: true; data: T }
  | { success: false; error: ContractDriftError };

/**
 * Error representing a contract drift between expected and actual data shape.
 */
export class ContractDriftError extends Error {
  public readonly issues: ZodError['issues'];
  public readonly raw: unknown;

  constructor(zodError: ZodError, raw: unknown) {
    const message = formatZodError(zodError);
    super(message);
    this.name = 'ContractDriftError';
    this.issues = zodError.issues;
    this.raw = raw;
  }

  /**
   * Get a summary of the first few issues for logging.
   */
  getSummary(maxIssues = 3): string {
    const issues = this.issues.slice(0, maxIssues);
    const summaries = issues.map((issue) => {
      const path = issue.path.join('.');
      return `${path}: ${issue.message}`;
    });
    if (this.issues.length > maxIssues) {
      summaries.push(`... and ${this.issues.length - maxIssues} more issues`);
    }
    return summaries.join('; ');
  }
}

/**
 * Format a ZodError into a human-readable message.
 */
function formatZodError(error: ZodError): string {
  const issues = error.issues.map((issue) => {
    const path = issue.path.length > 0 ? issue.path.join('.') : '(root)';
    return `  - ${path}: ${issue.message}`;
  });
  return `Contract drift detected:\n${issues.join('\n')}`;
}

// ============================================================================
// Decode Functions
// ============================================================================

/**
 * Create a decoder function from a zod schema.
 */
function createDecoder<T>(schema: z.ZodType<T>) {
  return function decode(data: unknown): DecodeResult<T> {
    const result = schema.safeParse(data);
    if (result.success) {
      return { success: true, data: result.data };
    }
    return { success: false, error: new ContractDriftError(result.error, data) };
  };
}

/**
 * Decode and validate a deliveries list response.
 *
 * Validates:
 * - items array with proper DeliveryTimelineSummary shape
 * - pagination info with required fields
 * - enum values for intent, delivery_mode, status, autonomy_mode, channels
 */
export const decodeDeliveriesList = createDecoder<DeliveryTimelineListResponse>(
  DeliveryTimelineListResponseSchema
);

/**
 * Decode and validate a single delivery timeline response.
 *
 * Validates:
 * - Full delivery timeline with attempts
 * - autonomy_context shape
 * - All channel arrays
 */
export const decodeDeliveryTimeline = createDecoder<DeliveryTimelineResponse>(
  DeliveryTimelineResponseSchema
);

/**
 * Decode and validate an audit events list response.
 *
 * Validates:
 * - items array with proper AuditEvent shape
 * - event_type enum values
 * - autonomy_context within each event
 */
export const decodeAuditEventsList = createDecoder<AuditEventListResponse>(
  AuditEventListResponseSchema
);

/**
 * Decode and validate an invariants list response.
 *
 * Validates:
 * - items array with proper InvariantEntry shape
 * - severity, enforcement_type, status enum values
 * - evidence array structure
 * - Optional degraded flag
 */
export const decodeInvariantsList = createDecoder<InvariantListResponse>(
  InvariantListResponseSchema
);

/**
 * Decode and validate an invariants summary response.
 *
 * Validates:
 * - Required summary fields (total_count, by_severity, etc.)
 * - Optional degraded flag
 */
export const decodeInvariantsSummary = createDecoder<InvariantSummaryResponse>(
  InvariantSummaryResponseSchema
);

/**
 * Decode and validate an effective policy response.
 *
 * Validates:
 * - effective policy fields (delivery_mode, channels, require_ack, etc.)
 * - resolution trace structure
 * - resolution_context fields
 */
export const decodeEffectivePolicy = createDecoder<EffectivePolicyResponse>(
  EffectivePolicyResponseSchema
);

/**
 * Decode and validate an active policies list response.
 */
export const decodeActivePoliciesList = createDecoder<ActivePolicyListResponse>(
  ActivePolicyListResponseSchema
);

/**
 * Decode and validate a policy revisions list response.
 */
export const decodePolicyRevisionsList = createDecoder<PolicyRevisionListResponse>(
  PolicyRevisionListResponseSchema
);

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Assert that decode succeeded, throwing if not.
 * Useful for strict validation mode where contract drift should fail fast.
 *
 * @param result - The decode result to assert
 * @param context - Optional context for error message (e.g., endpoint name)
 * @throws ContractDriftError if decode failed
 */
export function assertDecode<T>(result: DecodeResult<T>, context?: string): T {
  if (!result.success) {
    if (context) {
      result.error.message = `[${context}] ${result.error.message}`;
    }
    throw result.error;
  }
  return result.data;
}

/**
 * Log contract drift without throwing.
 * Useful for lenient mode where we want to continue but track issues.
 *
 * @param result - The decode result to check
 * @param context - Context for the log message (e.g., endpoint name)
 * @returns The raw data (unvalidated) for graceful degradation
 */
export function logDriftIfFailed<T>(
  result: DecodeResult<T>,
  context: string,
  raw: unknown
): T | unknown {
  if (!result.success) {
    console.warn(`[Contract Drift] ${context}: ${result.error.getSummary()}`);
    return raw;
  }
  return result.data;
}

/**
 * Validation mode for decoders.
 */
export type ValidationMode = 'strict' | 'lenient' | 'off';

/**
 * Global validation mode configuration.
 * - 'strict': Throw on validation failure
 * - 'lenient': Log warning but continue with raw data
 * - 'off': Skip validation entirely (use with caution)
 */
let validationMode: ValidationMode = 'lenient';

/**
 * Get the current validation mode.
 */
export function getValidationMode(): ValidationMode {
  return validationMode;
}

/**
 * Set the validation mode.
 * Call this in app initialization to configure behavior.
 *
 * @param mode - The validation mode to set
 */
export function setValidationMode(mode: ValidationMode): void {
  validationMode = mode;
}

/**
 * Decode with the current validation mode.
 *
 * @param decoder - The decoder function to use
 * @param data - The raw data to decode
 * @param context - Context for error messages
 * @returns Validated data or raw data depending on mode
 */
export function decodeWithMode<T>(
  decoder: (data: unknown) => DecodeResult<T>,
  data: unknown,
  context: string
): T {
  if (validationMode === 'off') {
    return data as T;
  }

  const result = decoder(data);

  if (validationMode === 'strict') {
    return assertDecode(result, context);
  }

  // lenient mode
  return logDriftIfFailed(result, context, data) as T;
}

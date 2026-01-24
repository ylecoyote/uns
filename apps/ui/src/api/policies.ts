/**
 * API client for policy endpoints
 *
 * Contract validation is applied via decoders to detect drift early.
 *
 * Endpoints:
 * - GET /ui/policies/effective - Get effective policy with resolution trace
 */

import type { EffectivePolicyResponse, PolicyInspectorParams } from '../types/api';
import { apiGet, type RequestOptions } from './client';
import { decodeEffectivePolicy, decodeWithMode } from './validators';

/**
 * Fetch effective policy for the given parameters
 *
 * @param params - Policy resolution parameters
 * @param options - Request options including optional requestId for correlation
 */
export async function fetchEffectivePolicy(
  params: PolicyInspectorParams,
  options?: RequestOptions
): Promise<EffectivePolicyResponse> {
  const data = await apiGet<EffectivePolicyResponse>(
    '/policies/effective',
    {
      notification_type: params.notification_type,
      intent: params.intent,
      autonomy_mode: params.autonomy_mode,
      irreversible: params.irreversible,
    },
    options
  );
  // Type assertion: decodeWithMode validates at runtime,
  // we use original TypeScript types for compile-time safety
  return decodeWithMode(decodeEffectivePolicy, data, 'GET /ui/policies/effective') as EffectivePolicyResponse;
}

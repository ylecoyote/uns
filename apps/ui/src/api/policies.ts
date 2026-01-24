/**
 * API client for policy endpoints
 *
 * Endpoints:
 * - GET /ui/policies/effective - Get effective policy with resolution trace
 */

import type { EffectivePolicyResponse, PolicyInspectorParams } from '../types/api';
import { apiGet, type RequestOptions } from './client';

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
  return apiGet<EffectivePolicyResponse>(
    '/policies/effective',
    {
      notification_type: params.notification_type,
      intent: params.intent,
      autonomy_mode: params.autonomy_mode,
      irreversible: params.irreversible,
    },
    options
  );
}

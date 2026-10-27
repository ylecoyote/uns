/**
 * API client for policy endpoints
 *
 * Contract validation is applied via decoders to detect drift early.
 *
 * Endpoints:
 * - GET /ui/policies/effective - Get effective policy with resolution trace
 * - GET /ui/policies/active - List active notification routing policies
 * - POST /api/v1/notifications/simulate - Dry-run notification routing simulation
 * - POST /api/v1/notifications - Send tagged live test notification
 * - POST /api/v1/policies/reload - Reload policies atomically from server directory
 */

import type {
  ActivePolicyListResponse,
  EffectivePolicyResponse,
  PolicyInspectorParams,
  PolicyReloadResponsePayload,
  SendNotificationRequestPayload,
  SendNotificationResponsePayload,
  SimulateNotificationResponsePayload,
} from '../types/api';
import { apiGet, apiRootRequest, type RequestOptions } from './client';
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
  return decodeWithMode(
    decodeEffectivePolicy,
    data,
    'GET /ui/policies/effective'
  ) as EffectivePolicyResponse;
}

/**
 * Fetch the catalog of active notification policies.
 */
export async function fetchActivePolicies(
  options?: RequestOptions
): Promise<ActivePolicyListResponse> {
  return apiGet<ActivePolicyListResponse>('/policies/active', undefined, options);
}

/**
 * Run a side-effect-free notification routing simulation.
 * Requires producer or admin scope.
 */
export async function simulateNotification(
  payload: SendNotificationRequestPayload,
  options?: RequestOptions
): Promise<SimulateNotificationResponsePayload> {
  return apiRootRequest<SimulateNotificationResponsePayload>(
    'POST',
    '/api/v1/notifications/simulate',
    payload,
    options
  );
}

/**
 * Send a live test notification with explicit synthetic attribution metadata.
 * Requires producer or admin scope.
 */
export async function sendTestNotification(
  payload: SendNotificationRequestPayload,
  options?: RequestOptions
): Promise<SendNotificationResponsePayload> {
  return apiRootRequest<SendNotificationResponsePayload>(
    'POST',
    '/api/v1/notifications',
    payload,
    options
  );
}

/**
 * Trigger an atomic two-phase validate-then-swap reload from the server's configured policy directory.
 * Requires admin scope.
 */
export async function reloadPolicies(
  options?: RequestOptions
): Promise<PolicyReloadResponsePayload> {
  return apiRootRequest<PolicyReloadResponsePayload>(
    'POST',
    '/api/v1/policies/reload',
    {},
    options
  );
}

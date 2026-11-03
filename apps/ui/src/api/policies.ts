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
  PolicyPromotionResponse,
  PolicyProposalCreateRequest,
  PolicyProposalListResponse,
  PolicyProposalSummary,
  PolicyReloadResponsePayload,
  PolicyRevisionListResponse,
  PolicyRevisionsFilter,
  SendNotificationRequestPayload,
  SendNotificationResponsePayload,
  SimulateNotificationResponsePayload,
} from '../types/api';
import { apiGet, apiRootRequest, type RequestOptions } from './client';
import {
  decodeActivePoliciesList,
  decodeEffectivePolicy,
  decodePolicyRevisionsList,
  decodeWithMode,
} from './validators';

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
  const data = await apiGet<ActivePolicyListResponse>(
    '/policies/active',
    undefined,
    options
  );
  return decodeWithMode(
    decodeActivePoliciesList,
    data,
    'GET /ui/policies/active'
  ) as ActivePolicyListResponse;
}

export const getActivePolicies = fetchActivePolicies;

/**
 * Fetch stored notification policy revisions across lifecycle statuses (ACTIVE, DRAFT, PREVIEW, RETIRED).
 */
export async function fetchPolicyRevisions(
  filters?: PolicyRevisionsFilter,
  options?: RequestOptions
): Promise<PolicyRevisionListResponse> {
  const params: Record<string, string | undefined> = {};
  if (filters?.notification_type) {
    params.notification_type = filters.notification_type;
  }
  if (filters?.status) {
    params.status = filters.status;
  }
  const data = await apiGet<PolicyRevisionListResponse>(
    '/policies/revisions',
    Object.keys(params).length > 0 ? params : undefined,
    options
  );
  return decodeWithMode(
    decodePolicyRevisionsList,
    data,
    'GET /ui/policies/revisions'
  ) as PolicyRevisionListResponse;
}

export const getPolicyRevisions = fetchPolicyRevisions;

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

/**
 * Fetch governed PolicyDelta proposals and shadow evaluation aggregates.
 */
export async function fetchPolicyProposals(
  filters?: { policy_type?: string; state?: string },
  options?: RequestOptions
): Promise<PolicyProposalListResponse> {
  const params: Record<string, string | undefined> = {};
  if (filters?.policy_type) {
    params.policy_type = filters.policy_type;
  }
  if (filters?.state) {
    params.state = filters.state;
  }
  return apiGet<PolicyProposalListResponse>(
    '/policies/proposals',
    Object.keys(params).length > 0 ? params : undefined,
    options
  );
}

/**
 * Fetch a single PolicyDelta proposal including shadow decision samples and guard history.
 */
export async function fetchPolicyProposalDetail(
  deltaId: string,
  options?: RequestOptions
): Promise<PolicyProposalSummary> {
  return apiGet<PolicyProposalSummary>(
    `/policies/proposals/${encodeURIComponent(deltaId)}`,
    undefined,
    options
  );
}

/**
 * Create a new PolicyDelta proposal against the current ACTIVE baseline.
 * Requires producer or admin scope.
 */
export async function createPolicyProposal(
  payload: PolicyProposalCreateRequest,
  options?: RequestOptions
): Promise<PolicyProposalSummary> {
  return apiRootRequest<PolicyProposalSummary>(
    'POST',
    '/api/v1/policies/proposals',
    payload,
    options
  );
}

/**
 * Promote a PROPOSED delta to SHADOW and materialize a PREVIEW policy revision.
 * Requires admin scope.
 */
export async function promoteProposalToShadow(
  deltaId: string,
  reason?: string,
  options?: RequestOptions
): Promise<PolicyProposalSummary> {
  return apiRootRequest<PolicyProposalSummary>(
    'POST',
    `/api/v1/policies/proposals/${encodeURIComponent(deltaId)}/shadow`,
    reason ? { reason } : {},
    options
  );
}

/**
 * Approve a qualifying SHADOW delta into a DRAFT policy revision (SHADOW -> APPROVED).
 * Requires admin scope.
 */
export async function approveProposalToDraft(
  deltaId: string,
  reason?: string,
  options?: RequestOptions
): Promise<PolicyPromotionResponse> {
  return apiRootRequest<PolicyPromotionResponse>(
    'POST',
    `/api/v1/policies/proposals/${encodeURIComponent(deltaId)}/approve`,
    reason ? { reason } : {},
    options
  );
}

/**
 * Explicitly activate an APPROVED proposal's DRAFT revision into ACTIVE (DRAFT -> ACTIVE).
 * Requires admin scope.
 */
export async function activateApprovedProposal(
  deltaId: string,
  reason?: string,
  options?: RequestOptions
): Promise<PolicyPromotionResponse> {
  return apiRootRequest<PolicyPromotionResponse>(
    'POST',
    `/api/v1/policies/proposals/${encodeURIComponent(deltaId)}/activate`,
    reason ? { reason } : {},
    options
  );
}

/**
 * Reject a policy delta proposal.
 * Requires admin scope.
 */
export async function rejectPolicyProposal(
  deltaId: string,
  reason?: string,
  options?: RequestOptions
): Promise<PolicyProposalSummary> {
  return apiRootRequest<PolicyProposalSummary>(
    'POST',
    `/api/v1/policies/proposals/${encodeURIComponent(deltaId)}/reject`,
    reason ? { reason } : {},
    options
  );
}

/**
 * Explicitly promote a DRAFT policy revision to ACTIVE by policy_id.
 * Requires admin scope.
 */
export async function activateDraftRevision(
  policyId: string,
  reason?: string,
  options?: RequestOptions
): Promise<PolicyPromotionResponse> {
  return apiRootRequest<PolicyPromotionResponse>(
    'POST',
    `/api/v1/policies/revisions/${encodeURIComponent(policyId)}/activate`,
    reason ? { reason } : {},
    options
  );
}

/**
 * API functions for Operator Telemetry & Dead-Letter Recovery (Surface 3).
 */

import { apiRootRequest, apiRootRequestWithStatus } from './client';
import type {
  ChannelHealthSummaryResponse,
  DLQListResponse,
  DLQRemoveResponse,
  ReadyzResponse,
  ReplayNotificationResponse,
  RuntimeDeadLetterItem,
} from '../types/api';

/**
 * Fetch readiness & operational progress telemetry.
 * Tolerates HTTP 503 so operators can still inspect degraded readiness telemetry.
 */
export async function getReadyz(
  signal?: AbortSignal
): Promise<{ data: ReadyzResponse; statusCode: number }> {
  const res = await apiRootRequestWithStatus<ReadyzResponse>('GET', '/readyz', undefined, {
    allowStatus: [503],
    signal,
  });
  return {
    data: res.data,
    statusCode: res.status,
  };
}

/**
 * Fetch aggregate and per-channel health state.
 */
export async function getChannelHealth(
  signal?: AbortSignal
): Promise<ChannelHealthSummaryResponse> {
  return apiRootRequest<ChannelHealthSummaryResponse>(
    'GET',
    '/api/v1/channels/health',
    undefined,
    { signal }
  );
}

/**
 * List visible dead-letter queue entries.
 */
export async function getDlqEntries(signal?: AbortSignal): Promise<DLQListResponse> {
  return apiRootRequest<DLQListResponse>('GET', '/api/v1/dlq', undefined, {
    signal,
  });
}

/**
 * List runtime dead-letter obligations with replay blocker metadata.
 */
export async function getRuntimeDeadLetters(
  signal?: AbortSignal
): Promise<RuntimeDeadLetterItem[]> {
  return apiRootRequest<RuntimeDeadLetterItem[]>(
    'GET',
    '/api/v1/runtime/dead-letters',
    undefined,
    { signal }
  );
}

/**
 * Replay an exhausted notification obligation in a fresh recovery cycle.
 * Requires operator (admin) scope.
 */
export async function replayNotification(
  notificationId: string
): Promise<ReplayNotificationResponse> {
  return apiRootRequest<ReplayNotificationResponse>(
    'POST',
    `/api/v1/runtime/notifications/${encodeURIComponent(notificationId)}/replay`
  );
}

/**
 * Resolve / retire a dead-letter entry without re-dispatching.
 * Requires operator (admin) scope.
 */
export async function resolveDlqEntry(entryId: string): Promise<DLQRemoveResponse> {
  return apiRootRequest<DLQRemoveResponse>(
    'DELETE',
    `/api/v1/dlq/${encodeURIComponent(entryId)}`
  );
}

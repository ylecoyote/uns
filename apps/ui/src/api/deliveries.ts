/**
 * Deliveries API client.
 *
 * Provides typed access to delivery timeline endpoints.
 * All operations are READ-ONLY.
 */

import type {
  DeliveryTimelineListResponse,
  DeliveryTimelineResponse,
  DeliveryFilter,
} from '../types/api';
import { apiGet, type RequestOptions } from './client';

/**
 * Fetch delivery timelines with optional filtering and pagination.
 *
 * @param filter - Filter and pagination parameters
 * @param options - Request options (requestId, signal)
 * @returns Paginated list of delivery timeline summaries
 */
export async function getDeliveries(
  filter?: DeliveryFilter,
  options?: RequestOptions
): Promise<DeliveryTimelineListResponse> {
  const params: Record<string, string | number | undefined> = {};

  if (filter) {
    if (filter.cursor) params.cursor = filter.cursor;
    if (filter.limit) params.limit = filter.limit;
    if (filter.start_time) params.start_time = filter.start_time;
    if (filter.end_time) params.end_time = filter.end_time;
    if (filter.status) params.status = filter.status;
    if (filter.intent) params.intent = filter.intent;
    if (filter.delivery_mode) params.delivery_mode = filter.delivery_mode;
    if (filter.agent_id) params.agent_id = filter.agent_id;
    if (filter.autonomy_mode) params.autonomy_mode = filter.autonomy_mode;
    if (filter.notification_type) params.notification_type = filter.notification_type;
    if (filter.channel) params.channel = filter.channel;
  }

  return apiGet<DeliveryTimelineListResponse>('/deliveries', params, options);
}

/**
 * Fetch a single delivery timeline by notification ID.
 *
 * @param notificationId - The notification UUID
 * @param options - Request options (requestId, signal)
 * @returns Full delivery timeline with attempts
 */
export async function getDeliveryTimeline(
  notificationId: string,
  options?: RequestOptions
): Promise<DeliveryTimelineResponse> {
  return apiGet<DeliveryTimelineResponse>(`/deliveries/${notificationId}`, undefined, options);
}

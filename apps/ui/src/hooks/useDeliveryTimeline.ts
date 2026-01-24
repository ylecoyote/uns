/**
 * React hook for fetching a single delivery timeline by notification ID.
 */

import { useState, useEffect, useCallback } from 'react';
import type { DeliveryTimelineResponse } from '../types/api';
import { getDeliveryTimeline, ApiError } from '../api';

export interface UseDeliveryTimelineResult {
  timeline: DeliveryTimelineResponse | null;
  isLoading: boolean;
  error: ApiError | Error | null;
  refetch: () => void;
}

export function useDeliveryTimeline(notificationId: string | undefined): UseDeliveryTimelineResult {
  const [timeline, setTimeline] = useState<DeliveryTimelineResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  const fetchTimeline = useCallback(async () => {
    if (!notificationId) {
      setTimeline(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await getDeliveryTimeline(notificationId);
      setTimeline(response);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setTimeline(null);
    } finally {
      setIsLoading(false);
    }
  }, [notificationId]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  const refetch = useCallback(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  return {
    timeline,
    isLoading,
    error,
    refetch,
  };
}

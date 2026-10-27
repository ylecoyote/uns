/**
 * React hook for fetching a single delivery timeline by notification ID.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
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
  const requestIdRef = useRef(0);

  const fetchTimeline = useCallback(async () => {
    const requestId = ++requestIdRef.current;

    if (!notificationId) {
      setTimeline(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await getDeliveryTimeline(notificationId);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setTimeline(response);
    } catch (err) {
      if (requestId !== requestIdRef.current) {
        return;
      }
      setError(err instanceof Error ? err : new Error(String(err)));
      setTimeline(null);
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [notificationId]);

  useEffect(() => {
    void fetchTimeline();
    return () => {
      requestIdRef.current += 1;
    };
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

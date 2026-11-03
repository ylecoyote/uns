/**
 * React hook for fetching deliveries with filtering and pagination.
 */

import { useState, useEffect, useCallback } from 'react';
import type { DeliveryTimelineSummary, DeliveryFilter, PaginationInfo } from '../types/api';
import { getDeliveries, ApiError } from '../api';

export interface UseDeliveriesResult {
  deliveries: DeliveryTimelineSummary[];
  pagination: PaginationInfo | null;
  isLoading: boolean;
  error: ApiError | Error | null;
  refetch: () => void;
  loadMore: () => void;
}

export function useDeliveries(filter: DeliveryFilter): UseDeliveriesResult {
  const [deliveries, setDeliveries] = useState<DeliveryTimelineSummary[]>([]);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [cursor, setCursor] = useState<string | undefined>(filter.cursor);

  const fetchDeliveries = useCallback(
    async (loadingMore = false) => {
      setIsLoading(true);
      setError(null);

      try {
        const filterWithCursor: DeliveryFilter = {
          ...filter,
          cursor: loadingMore && cursor ? cursor : undefined,
        };
        const response = await getDeliveries(filterWithCursor);

        if (loadingMore) {
          setDeliveries((prev) => [...prev, ...response.items]);
        } else {
          setDeliveries(response.items);
        }
        setPagination(response.pagination);
        setCursor(response.pagination.next_cursor ?? undefined);
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        setIsLoading(false);
      }
    },
    [filter, cursor]
  );

  // Refetch when filter changes (excluding cursor changes)
  useEffect(() => {
    setCursor(undefined);
    fetchDeliveries(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    filter.start_time,
    filter.end_time,
    filter.status,
    filter.intent,
    filter.delivery_mode,
    filter.agent_id,
    filter.autonomy_mode,
    filter.notification_type,
    filter.channel,
    filter.limit,
  ]);

  const refetch = useCallback(() => {
    setCursor(undefined);
    fetchDeliveries(false);
  }, [fetchDeliveries]);

  const loadMore = useCallback(() => {
    if (pagination?.has_more && cursor) {
      fetchDeliveries(true);
    }
  }, [pagination, cursor, fetchDeliveries]);

  return {
    deliveries,
    pagination,
    isLoading,
    error,
    refetch,
    loadMore,
  };
}

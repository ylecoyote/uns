/**
 * React hooks for audit events data fetching
 *
 * Follows the same patterns as useInvariants hook for consistency.
 */

import { useCallback, useEffect, useState } from 'react';
import { getAuditEvents, ApiError } from '../api';
import type {
  AuditEvent,
  AuditEventFilter,
  PaginationInfo,
} from '../types/api';

interface UseAuditEventsResult {
  events: AuditEvent[];
  pagination: PaginationInfo | null;
  loading: boolean;
  error: ApiError | null;
  refetch: () => void;
  loadMore: () => void;
}

export function useAuditEvents(filters: AuditEventFilter): UseAuditEventsResult {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);

  const fetchData = useCallback(async (isLoadMore = false) => {
    setLoading(true);
    setError(null);

    try {
      const currentFilters: AuditEventFilter = {
        ...filters,
        cursor: isLoadMore && cursor ? cursor : undefined,
      };

      const response = await getAuditEvents(currentFilters);

      if (isLoadMore) {
        setEvents(prev => [...prev, ...response.items]);
      } else {
        setEvents(response.items);
      }

      setPagination(response.pagination);
      setCursor(response.pagination.next_cursor);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  }, [filters, cursor]);

  useEffect(() => {
    setCursor(null);
    fetchData(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    filters.start_time,
    filters.end_time,
    filters.event_type,
    filters.notification_id,
    filters.agent_id,
    filters.autonomy_mode,
    filters.correlation_id,
    filters.limit,
  ]);

  const refetch = useCallback(() => {
    setCursor(null);
    fetchData(false);
  }, [fetchData]);

  const loadMore = useCallback(() => {
    if (pagination?.has_more) {
      fetchData(true);
    }
  }, [fetchData, pagination?.has_more]);

  return {
    events,
    pagination,
    loading,
    error,
    refetch,
    loadMore,
  };
}

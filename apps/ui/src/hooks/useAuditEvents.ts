/**
 * React hook for fetching audit events with filtering and pagination.
 */

import { useState, useEffect, useCallback } from 'react';
import type { AuditEvent, AuditEventFilter, PaginationInfo } from '../types/api';
import { getAuditEvents, ApiError } from '../api';

export interface UseAuditEventsResult {
  events: AuditEvent[];
  pagination: PaginationInfo | null;
  isLoading: boolean;
  error: ApiError | Error | null;
  refetch: () => void;
  loadMore: () => void;
}

export function useAuditEvents(filter: AuditEventFilter): UseAuditEventsResult {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [cursor, setCursor] = useState<string | undefined>(filter.cursor);

  const fetchEvents = useCallback(
    async (loadingMore = false) => {
      setIsLoading(true);
      setError(null);

      try {
        const filterWithCursor = loadingMore ? { ...filter, cursor } : filter;
        const response = await getAuditEvents(filterWithCursor);

        if (loadingMore) {
          setEvents((prev) => [...prev, ...response.items]);
        } else {
          setEvents(response.items);
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
    fetchEvents(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    filter.start_time,
    filter.end_time,
    filter.event_type,
    filter.notification_id,
    filter.agent_id,
    filter.autonomy_mode,
    filter.correlation_id,
    filter.limit,
  ]);

  const refetch = useCallback(() => {
    setCursor(undefined);
    fetchEvents(false);
  }, [fetchEvents]);

  const loadMore = useCallback(() => {
    if (pagination?.has_more && cursor) {
      fetchEvents(true);
    }
  }, [pagination, cursor, fetchEvents]);

  return {
    events,
    pagination,
    isLoading,
    error,
    refetch,
    loadMore,
  };
}

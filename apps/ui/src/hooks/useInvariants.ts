/**
 * React hooks for invariants data fetching
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchInvariants, fetchInvariantsSummary } from '../api/invariants';
import type { ApiError } from '../types/common';
import type {
  InvariantEntry,
  InvariantFilters,
  InvariantSummaryResponse,
  PaginationInfo,
} from '../types/invariants';

interface UseInvariantsResult {
  invariants: InvariantEntry[];
  pagination: PaginationInfo | null;
  loading: boolean;
  error: ApiError | null;
  degraded: boolean;
  refetch: () => void;
  loadMore: () => void;
}

export function useInvariants(filters: InvariantFilters): UseInvariantsResult {
  const [invariants, setInvariants] = useState<InvariantEntry[]>([]);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [degraded, setDegraded] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);

  const fetchData = useCallback(async (isLoadMore = false, currentCursor: string | null = null) => {
    setLoading(true);
    setError(null);

    try {
      const currentFilters: InvariantFilters = {
        ...filters,
        cursor: isLoadMore && currentCursor ? currentCursor : undefined,
      };

      const response = await fetchInvariants(currentFilters);

      if (isLoadMore) {
        setInvariants(prev => [...prev, ...response.items]);
      } else {
        setInvariants(response.items);
      }

      setPagination(response.pagination);
      setCursor(response.pagination.next_cursor);
      setDegraded(response.degraded ?? false);
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      // Set degraded state for specific error codes indicating source unavailable
      if (apiError.code === 'invariants_source_unavailable') {
        setDegraded(true);
      }
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    setCursor(null);
    fetchData(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentionally only re-fetch when specific filter values change, not when fetchData reference changes
  }, [filters.severity, filters.enforcement_type, filters.status, filters.search, filters.limit]);

  const refetch = useCallback(() => {
    setCursor(null);
    fetchData(false);
  }, [fetchData]);

  const loadMore = useCallback(() => {
    if (pagination?.has_more && cursor) {
      fetchData(true, cursor);
    }
  }, [fetchData, pagination?.has_more, cursor]);

  return {
    invariants,
    pagination,
    loading,
    error,
    degraded,
    refetch,
    loadMore,
  };
}

interface UseInvariantsSummaryResult {
  summary: InvariantSummaryResponse | null;
  loading: boolean;
  error: ApiError | null;
  degraded: boolean;
  refetch: () => void;
}

export function useInvariantsSummary(): UseInvariantsSummaryResult {
  const [summary, setSummary] = useState<InvariantSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [degraded, setDegraded] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchInvariantsSummary();
      setSummary(response);
      setDegraded(response.degraded ?? false);
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      // Set degraded state for specific error codes indicating source unavailable
      if (apiError.code === 'invariants_source_unavailable') {
        setDegraded(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const refetch = useCallback(() => {
    fetchData();
  }, [fetchData]);

  return {
    summary,
    loading,
    error,
    degraded,
    refetch,
  };
}

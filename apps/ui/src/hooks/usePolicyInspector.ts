/**
 * React hook for policy inspector data fetching
 */

import { useCallback, useRef, useState } from 'react';
import { fetchEffectivePolicy } from '../api/policies';
import { ApiError } from '../api/client';
import type { EffectivePolicyResponse, PolicyInspectorParams } from '../types/api';

interface UsePolicyInspectorResult {
  result: EffectivePolicyResponse | null;
  loading: boolean;
  error: ApiError | null;
  inspect: (params: PolicyInspectorParams, requestId?: string) => Promise<void>;
  clear: () => void;
}

export function usePolicyInspector(): UsePolicyInspectorResult {
  const [result, setResult] = useState<EffectivePolicyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const requestIdRef = useRef(0);

  const inspect = useCallback(async (params: PolicyInspectorParams, requestId?: string) => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    try {
      const response = await fetchEffectivePolicy(params, { requestId });
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      setResult(response);
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      setError(err as ApiError);
      setResult(null);
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const clear = useCallback(() => {
    requestIdRef.current += 1;
    setLoading(false);
    setResult(null);
    setError(null);
  }, []);

  return {
    result,
    loading,
    error,
    inspect,
    clear,
  };
}

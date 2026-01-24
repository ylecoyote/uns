/**
 * React hook for policy inspector data fetching
 */

import { useCallback, useState } from 'react';
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

  const inspect = useCallback(async (params: PolicyInspectorParams, requestId?: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchEffectivePolicy(params, { requestId });
      setResult(response);
    } catch (err) {
      setError(err as ApiError);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
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

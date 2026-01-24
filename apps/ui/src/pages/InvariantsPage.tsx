/**
 * InvariantsPage component
 *
 * Main page for viewing system invariants.
 * Features:
 * - Summary panel showing statistics from /ui/invariants/summary
 * - Filter controls for severity, enforcement_type, status, and search
 * - Paginated list of invariants
 * - Degraded state display when API returns degraded=true or
 *   invariants_source_unavailable error occurs
 */

import { useState } from 'react';
import { InvariantsFilter, InvariantsList, InvariantsSummary } from '../components';
import { useInvariants } from '../hooks/useInvariants';
import type { InvariantFilters } from '../types/invariants';

export function InvariantsPage() {
  const [filters, setFilters] = useState<InvariantFilters>({
    limit: 25,
  });

  const { invariants, pagination, loading, error, degraded, loadMore } = useInvariants(filters);

  // Degraded state comes from:
  // 1. API response with degraded=true
  // 2. invariants_source_unavailable error code
  // 3. Other non-not_found errors (fallback for backwards compatibility)
  const isDegraded = degraded || (error !== null && error.code !== 'not_found');

  // For invariants_source_unavailable, we show degraded state but not error banner
  const showError = error !== null && error.code !== 'invariants_source_unavailable';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
          <h1 className="text-3xl font-bold text-gray-900">System Invariants</h1>
          <p className="mt-1 text-sm text-gray-500">
            View and monitor system invariants for compliance and audit purposes
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {/* Degraded State Banner - top level for visibility */}
        {isDegraded && (
          <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-center gap-3">
            <span className="text-yellow-600 text-xl" aria-hidden="true">&#9888;</span>
            <div>
              <div className="text-yellow-800 font-medium">Degraded State</div>
              <div className="text-yellow-700 text-sm">
                The invariant registry may be incomplete or outdated. Some data may be unavailable.
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Summary Panel (Sidebar) */}
          <div className="lg:col-span-1">
            <InvariantsSummary degraded={isDegraded} />
          </div>

          {/* Main List Area */}
          <div className="lg:col-span-2 space-y-6">
            {/* Filters */}
            <InvariantsFilter filters={filters} onFiltersChange={setFilters} />

            {/* Error Display - only for errors that aren't handled by degraded state */}
            {showError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-center gap-2">
                  <span className="text-red-600" aria-hidden="true">&#9888;</span>
                  <span className="text-red-800 font-medium">Error loading invariants</span>
                </div>
                <p className="text-red-600 text-sm mt-1">{error.message}</p>
                {error.request_id && (
                  <p className="text-red-500 text-xs mt-1">Request ID: {error.request_id}</p>
                )}
              </div>
            )}

            {/* Invariants List - still shows partial data in degraded state */}
            <InvariantsList
              invariants={invariants}
              pagination={pagination}
              loading={loading}
              onLoadMore={loadMore}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

export default InvariantsPage;

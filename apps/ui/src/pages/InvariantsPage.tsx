/**
 * InvariantsPage component
 *
 * Main page for viewing system invariants.
 * Features:
 * - Summary panel showing statistics from /ui/invariants/summary
 * - Filter controls for severity, enforcement_type, status, and search
 * - Paginated list of invariants
 * - Degraded state display when API returns degraded=true
 */

import { useState } from 'react';
import { InvariantsFilter, InvariantsList, InvariantsSummary } from '../components';
import { useInvariants } from '../hooks/useInvariants';
import type { InvariantFilters } from '../types/invariants';

export function InvariantsPage() {
  const [filters, setFilters] = useState<InvariantFilters>({
    limit: 25,
  });

  const { invariants, pagination, loading, error, loadMore } = useInvariants(filters);

  // Check for degraded state (would be indicated by API response)
  // For now, we detect degraded state based on error presence
  const isDegraded = error !== null && error.code !== 'not_found';

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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Summary Panel (Sidebar) */}
          <div className="lg:col-span-1">
            <InvariantsSummary degraded={isDegraded} />
          </div>

          {/* Main List Area */}
          <div className="lg:col-span-2 space-y-6">
            {/* Filters */}
            <InvariantsFilter filters={filters} onFiltersChange={setFilters} />

            {/* Error Display */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-center gap-2">
                  <span className="text-red-600">&#9888;</span>
                  <span className="text-red-800 font-medium">Error loading invariants</span>
                </div>
                <p className="text-red-600 text-sm mt-1">{error.message}</p>
                {error.request_id && (
                  <p className="text-red-500 text-xs mt-1">Request ID: {error.request_id}</p>
                )}
              </div>
            )}

            {/* Invariants List */}
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

/**
 * AuditTimeline page - displays the filtered audit event stream.
 *
 * Features:
 * - Filterable list of audit events
 * - Time range filtering
 * - Event type, notification_id, agent_id, autonomy_mode, correlation_id filters
 * - Cursor-based pagination with "Load More"
 * - Safe payload formatting with JSON viewer
 *
 * This page is READ-ONLY per ui-scope.md.
 *
 * Follows the InvariantsPage SPA patterns for consistency.
 */

import { useState } from 'react';
import type { AuditEventFilter } from '../types/api';
import { useAuditEvents } from '../hooks/useAuditEvents';
import { AuditFilters, AuditEventList } from '../components';

const DEFAULT_LIMIT = 25;

export function AuditTimeline() {
  const [filters, setFilters] = useState<AuditEventFilter>({
    limit: DEFAULT_LIMIT,
  });

  const { events, pagination, loading, error, refetch, loadMore } = useAuditEvents(filters);

  const handleFilterChange = (newFilters: AuditEventFilter) => {
    setFilters({ ...newFilters, limit: newFilters.limit ?? DEFAULT_LIMIT });
  };

  return (
    <div className="min-h-screen bg-gray-50" data-testid="audit-timeline-page">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
          <h1 className="text-3xl font-bold text-gray-900">Audit Timeline</h1>
          <p className="mt-1 text-sm text-gray-500">
            Browse the audit event stream for notification delivery and acknowledgment events.
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <div className="space-y-6">
          {/* Filters */}
          <AuditFilters filters={filters} onFiltersChange={handleFilterChange} />

          {/* Error Display */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4" data-testid="error-state">
              <div className="flex items-center gap-2">
                <span className="text-red-600">&#9888;</span>
                <span className="text-red-800 font-medium">Error loading audit events</span>
              </div>
              <p className="text-red-600 text-sm mt-1">{error.message}</p>
              {error.request_id && (
                <p className="text-red-500 text-xs mt-1">Request ID: {error.request_id}</p>
              )}
              <button
                type="button"
                onClick={refetch}
                className="mt-3 px-4 py-2 bg-red-100 text-red-800 rounded-lg hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                Retry
              </button>
            </div>
          )}

          {/* Audit Events List */}
          <AuditEventList
            events={events}
            pagination={pagination}
            loading={loading}
            onLoadMore={loadMore}
          />
        </div>
      </main>
    </div>
  );
}

export default AuditTimeline;

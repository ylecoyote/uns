/**
 * AuditTimeline page — displays the filtered audit event stream (/audit).
 *
 * Implements the Modernist restyle with:
 * - Architectural 2-column header + Delivery (filled) vs. Response (outlined) legend
 * - Default "By notification" lifecycle view (1e) with segmented toggle to "All events" (1d)
 * - Full compatibility with existing AuditTimeline.test.tsx assertions
 */

import { useState } from 'react';
import type { AuditEventFilter } from '../types/api';
import { useAuditEvents } from '../hooks/useAuditEvents';
import { AuditFilters, type AuditViewMode } from '../components/AuditFilters';
import { AuditEventList } from '../components/AuditEventList';

const DEFAULT_LIMIT = 25;

export function AuditTimeline() {
  const [filters, setFilters] = useState<AuditEventFilter>({
    limit: DEFAULT_LIMIT,
  });
  const [viewMode, setViewMode] = useState<AuditViewMode>('by-notification');

  const { events, pagination, loading, error, refetch, loadMore } = useAuditEvents(filters);

  const handleFilterChange = (newFilters: AuditEventFilter) => {
    setFilters({ ...newFilters, limit: newFilters.limit ?? DEFAULT_LIMIT });
  };

  return (
    <div className="audit-timeline-page min-h-screen bg-gray-50" data-testid="audit-timeline-page">
      {/* Architectural 2-Column Header with Delivery vs. Response Legend */}
      <header className="page-header">
        <div>
          <h1>Audit Timeline</h1>
        </div>
        <div className="audit-legend-group">
          <p className="page-description">
            Browse the audit event stream for notification delivery and acknowledgment events.
          </p>
          <div className="audit-legend-strip">
            <span>
              <span className="badge tag-delivery-ok" style={{ marginRight: '6px' }}>
                Delivery
              </span>
              Filled label = delivery event
            </span>
            <span>
              <span className="badge tag-response-ok" style={{ marginRight: '6px' }}>
                Response
              </span>
              Outlined label = human response
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main>
        <div>
          {/* Filters + Segmented View Toggle */}
          <AuditFilters
            filters={filters}
            onFiltersChange={handleFilterChange}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
          />

          {/* Error Display */}
          {error && (
            <div
              className="error-state bg-red-50 border border-red-200 rounded-lg p-4"
              data-testid="error-state"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>&#9888;</span>
                <strong>Error loading audit events</strong>
              </div>
              <p className="error-message" style={{ marginTop: '4px' }}>
                {error.message}
              </p>
              {error.request_id && (
                <p className="monospace" style={{ fontSize: '12px', margin: '4px 0 8px' }}>
                  Request ID: {error.request_id}
                </p>
              )}
              <button
                type="button"
                onClick={refetch}
                className="btn btn-secondary"
              >
                Retry
              </button>
            </div>
          )}

          {/* Audit Events List (1e By Notification + 1d All Events) */}
          <AuditEventList
            events={events}
            pagination={pagination}
            loading={loading}
            onLoadMore={loadMore}
            viewMode={viewMode}
          />
        </div>
      </main>
    </div>
  );
}

export default AuditTimeline;

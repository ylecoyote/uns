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
 */

import { useState } from 'react';
import type { AuditEventFilter } from '../types/api';
import { useAuditEvents } from '../hooks/useAuditEvents';
import { AuditEventCard, AuditFilters, Pagination } from '../components';

const DEFAULT_LIMIT = 25;

export function AuditTimeline() {
  const [filter, setFilter] = useState<AuditEventFilter>({
    limit: DEFAULT_LIMIT,
  });

  const { events, pagination, isLoading, error, refetch, loadMore } = useAuditEvents(filter);

  const handleFilterChange = (newFilter: AuditEventFilter) => {
    setFilter({ ...newFilter, limit: newFilter.limit ?? DEFAULT_LIMIT });
  };

  return (
    <div className="audit-timeline-page" data-testid="audit-timeline-page">
      <header className="page-header">
        <h1>Audit Timeline</h1>
        <p className="page-description">
          Browse the audit event stream for notification delivery and acknowledgment events.
        </p>
      </header>

      <AuditFilters filter={filter} onFilterChange={handleFilterChange} />

      <div className="audit-timeline-content">
        {isLoading && events.length === 0 && (
          <div className="loading-state" data-testid="loading-state">
            Loading audit events...
          </div>
        )}

        {error && (
          <div className="error-state" data-testid="error-state">
            <p className="error-message">Failed to load audit events: {error.message}</p>
            <button type="button" onClick={refetch} className="btn btn-secondary">
              Retry
            </button>
          </div>
        )}

        {!isLoading && !error && events.length === 0 && (
          <div className="empty-state" data-testid="empty-state">
            <p>No audit events found matching the current filters.</p>
          </div>
        )}

        {events.length > 0 && (
          <div className="audit-event-list" data-testid="audit-event-list">
            {events.map((event) => (
              <AuditEventCard key={event.audit_id} event={event} />
            ))}
          </div>
        )}

        <Pagination
          pagination={pagination}
          isLoading={isLoading}
          onLoadMore={loadMore}
          itemCount={events.length}
        />
      </div>
    </div>
  );
}

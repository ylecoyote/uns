/**
 * AuditEventList component
 *
 * Displays a list of audit events with pagination.
 * Follows the InvariantsList pattern for consistency.
 */

import { AuditEventCard } from './AuditEventCard';
import type { AuditEvent, PaginationInfo } from '../types/api';

interface AuditEventListProps {
  events: AuditEvent[];
  pagination: PaginationInfo | null;
  loading: boolean;
  onLoadMore: () => void;
}

export function AuditEventList({ events, pagination, loading, onLoadMore }: AuditEventListProps) {
  if (!loading && events.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-8 text-center" data-testid="empty-state">
        <div className="text-gray-500">No audit events found matching the current filters.</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Event Cards */}
      <div className="audit-event-list" data-testid="audit-event-list">
        {events.map((event) => (
          <AuditEventCard key={event.audit_id} event={event} />
        ))}
      </div>

      {/* Loading indicator */}
      {loading && events.length === 0 && (
        <div className="flex justify-center py-4" data-testid="loading-state">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      )}

      {/* Load More */}
      {!loading && pagination?.has_more && (
        <div className="flex justify-center py-4">
          <button
            onClick={onLoadMore}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            data-testid="load-more-btn"
          >
            Load More
          </button>
        </div>
      )}

      {/* Loading more indicator */}
      {loading && events.length > 0 && (
        <div className="flex justify-center py-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      )}

      {/* Pagination Info */}
      {pagination && (
        <div className="text-center text-sm text-gray-500 py-2" data-testid="pagination">
          Showing {events.length}
          {pagination.total_count !== undefined && ` of ${pagination.total_count}`} event{events.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}

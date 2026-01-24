/**
 * Pagination component for cursor-based pagination.
 */

import type { PaginationInfo } from '../types/api';

interface PaginationProps {
  pagination: PaginationInfo | null;
  isLoading: boolean;
  onLoadMore: () => void;
  itemCount: number;
}

export function Pagination({ pagination, isLoading, onLoadMore, itemCount }: PaginationProps) {
  if (!pagination) {
    return null;
  }

  return (
    <div className="pagination" data-testid="pagination">
      <span className="pagination-info">
        Showing {itemCount} event{itemCount !== 1 ? 's' : ''}
        {pagination.total_count !== undefined && ` of ${pagination.total_count}`}
      </span>

      {pagination.has_more && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={isLoading}
          className="btn btn-secondary"
          data-testid="load-more-btn"
        >
          {isLoading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
}

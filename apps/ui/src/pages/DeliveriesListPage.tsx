/**
 * DeliveriesListPage - displays the filtered delivery timelines list.
 *
 * Features:
 * - Filterable list of deliveries by status, intent, channel, and more
 * - Cursor-based pagination with "Load More"
 * - Links to individual delivery detail pages
 *
 * This page is READ-ONLY per ui-scope.md.
 */

import { useState } from 'react';
import type { DeliveryFilter } from '../types/api';
import { useDeliveries } from '../hooks/useDeliveries';
import { DeliveriesFilters, DeliveriesTable, Pagination } from '../components';

const DEFAULT_LIMIT = 25;

export function DeliveriesListPage() {
  const [filter, setFilter] = useState<DeliveryFilter>({
    limit: DEFAULT_LIMIT,
  });

  const { deliveries, pagination, isLoading, error, refetch, loadMore } = useDeliveries(filter);

  const handleFilterChange = (newFilter: DeliveryFilter) => {
    setFilter({ ...newFilter, limit: newFilter.limit ?? DEFAULT_LIMIT });
  };

  return (
    <div className="deliveries-list-page" data-testid="deliveries-list-page">
      <header className="page-header">
        <h1>Deliveries</h1>
        <p className="page-description">
          View delivery timelines and filter by status, intent, channel, and more.
        </p>
      </header>

      <DeliveriesFilters filter={filter} onFilterChange={handleFilterChange} />

      <div className="deliveries-content">
        {isLoading && deliveries.length === 0 && (
          <div className="loading-state" data-testid="loading-state">
            Loading deliveries...
          </div>
        )}

        {error && (
          <div className="error-state" data-testid="error-state">
            <p className="error-message">Failed to load deliveries: {error.message}</p>
            <button type="button" onClick={refetch} className="btn btn-secondary">
              Retry
            </button>
          </div>
        )}

        {!isLoading && !error && deliveries.length === 0 && (
          <div className="empty-state" data-testid="empty-state">
            <p>No deliveries found matching the current filters.</p>
          </div>
        )}

        {deliveries.length > 0 && <DeliveriesTable deliveries={deliveries} />}

        <Pagination
          pagination={pagination}
          isLoading={isLoading}
          onLoadMore={loadMore}
          itemCount={deliveries.length}
        />
      </div>
    </div>
  );
}

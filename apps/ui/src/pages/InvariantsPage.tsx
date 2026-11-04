/**
 * InvariantsPage component - System Invariants (/invariants)
 *
 * Restyled with the Modernist Swiss-grid layout (1c):
 * - Architectural 2-column page header
 * - Full-bleed modular summary grid (Oversized Total Invariants + Severity / Enforcement / Status cells)
 * - Modular filter bar + 3-column invariant specification rows
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

  const isDegraded = degraded || (error !== null && error.code !== 'not_found');
  const showError = error !== null && error.code !== 'invariants_source_unavailable';

  return (
    <div className="invariants-page min-h-screen bg-gray-50">
      {/* Architectural Page Header */}
      <header className="page-header">
        <div>
          <h1>System Invariants</h1>
        </div>
        <p className="page-description">
          View and monitor system invariants for compliance and audit purposes
        </p>
      </header>

      {/* Main Content */}
      <div>
        {/* Degraded State Banner */}
        {isDegraded && (
          <div
            style={{
              padding: '14px 24px',
              background: 'var(--color-surface)',
              borderBottom: '2px solid var(--color-divider)',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <span
              style={{
                width: '10px',
                height: '10px',
                background: 'var(--color-accent)',
                display: 'inline-block',
                flex: 'none',
              }}
              aria-hidden="true"
            />
            <div>
              <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 800 }}>
                Degraded State
              </div>
              <div style={{ fontSize: '13px', color: 'var(--color-neutral-700)' }}>
                The invariant registry may be incomplete or outdated. Some data may be unavailable.
              </div>
            </div>
          </div>
        )}

        {/* Modular Summary Grid (1c) */}
        <InvariantsSummary degraded={isDegraded} />

        {/* Modular Filter Bar */}
        <InvariantsFilter filters={filters} onFiltersChange={setFilters} />

        {/* Error Display */}
        {showError && (
          <div className="error-state">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span aria-hidden="true">&#9888;</span>
              <strong>Error loading invariants</strong>
            </div>
            <p className="error-message" style={{ marginTop: '4px' }}>
              {error.message}
            </p>
            {error.request_id && (
              <p className="monospace" style={{ fontSize: '12px', margin: 0 }}>
                Request ID: {error.request_id}
              </p>
            )}
          </div>
        )}

        {/* Invariants Specification Rows */}
        <InvariantsList
          invariants={invariants}
          pagination={pagination}
          loading={loading}
          onLoadMore={loadMore}
        />
      </div>
    </div>
  );
}

export default InvariantsPage;

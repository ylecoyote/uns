/**
 * InvariantsSummary component — Modernist Modular Summary Grid (1c)
 *
 * Displays summary statistics for system invariants using /ui/invariants/summary.
 * Shows counts by severity, enforcement type, and status.
 */

import { useInvariantsSummary } from '../hooks/useInvariants';

interface StatCellProps {
  label: string;
  value: number;
  accent?: boolean;
  muted?: boolean;
}

function StatCell({ label, value, accent = false, muted = false }: StatCellProps) {
  return (
    <div className="invariants-stat-item">
      <div
        className="invariants-stat-value"
        style={{
          color: accent
            ? 'var(--color-accent)'
            : muted
              ? 'var(--color-neutral-500)'
              : 'var(--color-text)',
        }}
      >
        {value}
      </div>
      <div className="invariants-stat-label">{label}</div>
    </div>
  );
}

interface InvariantsSummaryProps {
  degraded?: boolean;
}

export function InvariantsSummary({ degraded = false }: InvariantsSummaryProps) {
  const { summary, loading, error, degraded: summaryDegraded } = useInvariantsSummary();

  const isDegraded = degraded || summaryDegraded;
  const isSourceUnavailable = error?.code === 'invariants_source_unavailable';

  if (loading) {
    return (
      <div className="loading-state">
        <div>Loading invariants summary...</div>
      </div>
    );
  }

  if (isSourceUnavailable) {
    return (
      <div
        style={{
          padding: '24px',
          background: 'var(--color-surface)',
          borderBottom: '2px solid var(--color-divider)',
        }}
      >
        <h2 style={{ margin: '0 0 8px', fontSize: '14px', textTransform: 'uppercase' }}>
          Invariants Summary
        </h2>
        <div>
          <div style={{ fontWeight: 800 }}>Summary Unavailable</div>
          <div style={{ fontSize: '13px', color: 'var(--color-neutral-700)', marginTop: '4px' }}>
            The invariant registry is temporarily unavailable.
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <div style={{ fontWeight: 800 }}>Error loading summary</div>
        <div className="error-message">{error.message}</div>
        {error.request_id && (
          <div className="monospace" style={{ fontSize: '12px' }}>
            Request ID: {error.request_id}
          </div>
        )}
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  return (
    <section className="invariants-summary-grid" aria-label="Invariants Summary">
      <h2 className="sr-only">Invariants Summary</h2>

      {/* Left Oversized Metric Cell */}
      <div className="invariants-total-cell">
        <div className="invariants-eyebrow">Total Invariants</div>
        <div className="invariants-total-number">{summary.total_count}</div>
        <div className="timestamp" style={{ fontSize: '11px' }}>
          Last updated: {new Date(summary.last_updated).toLocaleString()}
        </div>
      </div>

      {/* Right Breakdown Cells */}
      <div className="invariants-breakdown-rows">
        <div className="invariants-breakdown-top">
          {/* By Severity */}
          <div className="invariants-breakdown-group">
            <h3 className="invariants-eyebrow" style={{ margin: 0 }}>
              By Severity
            </h3>
            <div
              className="invariants-stat-strip"
              style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}
            >
              <StatCell
                label="High"
                value={summary.by_severity.HIGH ?? 0}
                accent={(summary.by_severity.HIGH ?? 0) > 0}
              />
              <StatCell label="Medium" value={summary.by_severity.MEDIUM ?? 0} />
              <StatCell
                label="Low"
                value={summary.by_severity.LOW ?? 0}
                muted={(summary.by_severity.LOW ?? 0) === 0}
              />
            </div>
          </div>

          {/* By Enforcement Type */}
          <div className="invariants-breakdown-group">
            <h3 className="invariants-eyebrow" style={{ margin: 0 }}>
              By Enforcement Type
            </h3>
            <div
              className="invariants-stat-strip"
              style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}
            >
              <StatCell label="Guard" value={summary.by_enforcement_type.guard ?? 0} />
              <StatCell label="Isolation" value={summary.by_enforcement_type.isolation ?? 0} />
              <StatCell label="Test" value={summary.by_enforcement_type.test ?? 0} />
              <StatCell
                label="Exception"
                value={summary.by_enforcement_type.exception ?? 0}
                accent={(summary.by_enforcement_type.exception ?? 0) > 0}
                muted={(summary.by_enforcement_type.exception ?? 0) === 0}
              />
            </div>
          </div>

          {/* By Status */}
          <div className="invariants-breakdown-group">
            <h3 className="invariants-eyebrow" style={{ margin: 0 }}>
              By Status
            </h3>
            <div
              className="invariants-stat-strip"
              style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}
            >
              <StatCell label="Active" value={summary.by_status.active ?? 0} />
              <StatCell
                label="Inactive"
                value={summary.by_status.inactive ?? 0}
                muted={(summary.by_status.inactive ?? 0) === 0}
              />
            </div>
          </div>
        </div>

        {/* Bottom Status Strip */}
        <div
          style={{
            padding: '12px 24px',
            background: 'var(--color-surface)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
            flexWrap: 'wrap',
            fontSize: '12px',
          }}
        >
          <span>
            <strong>Registry Status:</strong>{' '}
            {isDegraded ? (
              <span>Data may be incomplete</span>
            ) : (
              <span>All active invariants verified against source tree</span>
            )}
          </span>

          {summary.exceptions_requiring_review > 0 ? (
            <span className="badge tag-delivery-fail">
              {summary.exceptions_requiring_review} exception(s) require review
            </span>
          ) : (
            <span className="monospace" style={{ color: 'var(--color-neutral-700)' }}>
              EXCEPTIONS REQUIRING REVIEW: 0
            </span>
          )}
        </div>
      </div>
    </section>
  );
}

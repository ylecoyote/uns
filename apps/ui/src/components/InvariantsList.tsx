/**
 * InvariantsList component — Modernist 3-Column Specification Rows (1c)
 *
 * Displays a list of invariants with details, enforcement description, and source evidence.
 */

import type { InvariantEntry, PaginationInfo } from '../types/invariants';

interface SeverityBadgeProps {
  severity: InvariantEntry['severity'];
}

function SeverityBadge({ severity }: SeverityBadgeProps) {
  const styles: Record<string, string> = {
    HIGH: 'tag-delivery-fail',
    MEDIUM: 'tag-delivery-info',
    LOW: 'badge-default',
  };

  return <span className={`badge ${styles[severity] ?? 'badge-default'}`}>{severity}</span>;
}

interface EnforcementBadgeProps {
  type: InvariantEntry['enforcement']['type'];
}

function EnforcementBadge({ type }: EnforcementBadgeProps) {
  return <span className="badge tag-response-ok">{type}</span>;
}

interface StatusBadgeProps {
  status: InvariantEntry['status'];
}

function StatusBadge({ status }: StatusBadgeProps) {
  const cls = status === 'active' ? 'tag-delivery-ok' : 'badge-default';
  return <span className={`badge ${cls}`}>{status}</span>;
}

interface InvariantCardProps {
  invariant: InvariantEntry;
}

function InvariantCard({ invariant }: InvariantCardProps) {
  return (
    <article className="invariant-row-card">
      {/* Left Column: ID & Classification Tags */}
      <div className="invariant-col-id">
        <code
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 700,
            fontSize: '14px',
          }}
        >
          {invariant.id}
        </code>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
          <StatusBadge status={invariant.status} />
          <SeverityBadge severity={invariant.severity} />
          <EnforcementBadge type={invariant.enforcement.type} />
        </div>
      </div>

      {/* Middle Column: Statement, Enforcement & Evidence */}
      <div className="invariant-col-body">
        <div
          style={{
            fontFamily: 'var(--font-heading)',
            fontWeight: 800,
            fontSize: '18px',
            letterSpacing: '-0.015em',
            marginBottom: '6px',
          }}
        >
          {invariant.statement}
        </div>

        <div style={{ fontSize: '13px', color: 'var(--color-neutral-700)', marginBottom: '12px' }}>
          <strong>Enforcement:</strong> {invariant.enforcement.description}
        </div>

        {invariant.mitigation && invariant.mitigation.length > 0 && (
          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface)',
              borderLeft: '3px solid var(--color-accent)',
              marginBottom: '12px',
            }}
          >
            <div style={{ fontSize: '11px', fontWeight: 800, textTransform: 'uppercase' }}>
              Mitigation:
            </div>
            <ul style={{ margin: '4px 0 0', paddingLeft: '18px', fontSize: '12px' }}>
              {invariant.mitigation.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        {invariant.evidence.length > 0 && (
          <div
            style={{
              borderTop: '1px solid var(--color-divider)',
              paddingTop: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              fontSize: '12px',
            }}
          >
            <span className="invariants-eyebrow">Evidence:</span>
            {invariant.evidence.map((evidence, index) => (
              <div key={index}>
                <code
                  style={{
                    background: 'var(--color-surface)',
                    padding: '2px 6px',
                    border: '1px solid var(--color-divider)',
                    fontSize: '11px',
                  }}
                >
                  {evidence.path}
                </code>
                {evidence.line_ref && (
                  <span className="monospace" style={{ color: 'var(--color-neutral-600)', marginLeft: '6px' }}>
                    ({evidence.line_ref})
                  </span>
                )}
                <span style={{ color: 'var(--color-neutral-700)', marginLeft: '8px' }}>
                  — {evidence.note}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Right Column: Ownership & Review Metadata */}
      <div className="invariant-col-meta">
        <div>
          <div className="invariants-eyebrow">Owner</div>
          <div className="monospace" style={{ color: 'var(--color-text)', marginTop: '2px' }}>
            Owner: {invariant.owner}
          </div>
        </div>
        <div style={{ marginTop: '12px' }}>
          <div className="invariants-eyebrow">Last Reviewed</div>
          <div className="monospace" style={{ color: 'var(--color-text)', marginTop: '2px' }}>
            Last reviewed: {new Date(invariant.last_reviewed).toLocaleDateString()}
          </div>
        </div>
      </div>
    </article>
  );
}

interface InvariantsListProps {
  invariants: InvariantEntry[];
  pagination: PaginationInfo | null;
  loading: boolean;
  onLoadMore: () => void;
}

export function InvariantsList({
  invariants,
  pagination,
  loading,
  onLoadMore,
}: InvariantsListProps) {
  if (!loading && invariants.length === 0) {
    return (
      <div className="empty-state">
        <div>No invariants found matching the current filters.</div>
      </div>
    );
  }

  return (
    <div>
      {invariants.map((invariant) => (
        <InvariantCard key={invariant.id} invariant={invariant} />
      ))}

      {loading && (
        <div className="loading-state">
          <div>Loading invariants...</div>
        </div>
      )}

      {pagination && (
        <div className="pagination">
          <div className="pagination-info">
            Showing {invariants.length}
            {pagination.total_count !== undefined && ` of ${pagination.total_count}`} invariants
          </div>

          {!loading && pagination.has_more && (
            <button onClick={onLoadMore} className="btn btn-secondary">
              Load More
            </button>
          )}
        </div>
      )}
    </div>
  );
}

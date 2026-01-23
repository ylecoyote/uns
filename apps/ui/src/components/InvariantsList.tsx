/**
 * InvariantsList component
 *
 * Displays a list of invariants with details.
 * Supports pagination and displays evidence links.
 */

import type { InvariantEntry, PaginationInfo } from '../types/invariants';

interface SeverityBadgeProps {
  severity: InvariantEntry['severity'];
}

function SeverityBadge({ severity }: SeverityBadgeProps) {
  const styles: Record<string, string> = {
    HIGH: 'bg-red-100 text-red-800 border-red-200',
    MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    LOW: 'bg-blue-100 text-blue-800 border-blue-200',
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[severity]}`}>
      {severity}
    </span>
  );
}

interface EnforcementBadgeProps {
  type: InvariantEntry['enforcement']['type'];
}

function EnforcementBadge({ type }: EnforcementBadgeProps) {
  const styles: Record<string, string> = {
    guard: 'bg-green-100 text-green-800',
    isolation: 'bg-purple-100 text-purple-800',
    test: 'bg-gray-100 text-gray-800',
    exception: 'bg-orange-100 text-orange-800',
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[type]}`}>
      {type}
    </span>
  );
}

interface StatusBadgeProps {
  status: InvariantEntry['status'];
}

function StatusBadge({ status }: StatusBadgeProps) {
  const styles: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    inactive: 'bg-gray-100 text-gray-500',
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[status]}`}>
      {status}
    </span>
  );
}

interface InvariantCardProps {
  invariant: InvariantEntry;
}

function InvariantCard({ invariant }: InvariantCardProps) {
  return (
    <div className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <code className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">{invariant.id}</code>
          <StatusBadge status={invariant.status} />
        </div>
        <div className="flex items-center gap-2">
          <SeverityBadge severity={invariant.severity} />
          <EnforcementBadge type={invariant.enforcement.type} />
        </div>
      </div>

      {/* Statement */}
      <p className="text-gray-900 mb-4">{invariant.statement}</p>

      {/* Enforcement Description */}
      <div className="text-sm text-gray-600 mb-4">
        <span className="font-medium">Enforcement:</span> {invariant.enforcement.description}
      </div>

      {/* Mitigation (for exceptions) */}
      {invariant.mitigation && invariant.mitigation.length > 0 && (
        <div className="bg-orange-50 rounded-lg p-3 mb-4">
          <div className="text-sm font-medium text-orange-800 mb-1">Mitigation:</div>
          <ul className="list-disc list-inside text-sm text-orange-700">
            {invariant.mitigation.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Evidence Links */}
      {invariant.evidence.length > 0 && (
        <div className="mb-4">
          <div className="text-sm font-medium text-gray-700 mb-2">Evidence:</div>
          <ul className="space-y-1">
            {invariant.evidence.map((evidence, index) => (
              <li key={index} className="text-sm">
                <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">{evidence.path}</code>
                {evidence.line_ref && (
                  <span className="text-gray-500 ml-1">({evidence.line_ref})</span>
                )}
                <span className="text-gray-600 ml-2">{evidence.note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-gray-500 pt-4 border-t border-gray-100">
        <span>Owner: {invariant.owner}</span>
        <span>Last reviewed: {new Date(invariant.last_reviewed).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

interface InvariantsListProps {
  invariants: InvariantEntry[];
  pagination: PaginationInfo | null;
  loading: boolean;
  onLoadMore: () => void;
}

export function InvariantsList({ invariants, pagination, loading, onLoadMore }: InvariantsListProps) {
  if (!loading && invariants.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-8 text-center">
        <div className="text-gray-500">No invariants found matching the current filters.</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Invariant Cards */}
      {invariants.map(invariant => (
        <InvariantCard key={invariant.id} invariant={invariant} />
      ))}

      {/* Loading indicator */}
      {loading && (
        <div className="flex justify-center py-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      )}

      {/* Load More */}
      {!loading && pagination?.has_more && (
        <div className="flex justify-center py-4">
          <button
            onClick={onLoadMore}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Load More
          </button>
        </div>
      )}

      {/* Pagination Info */}
      {pagination && (
        <div className="text-center text-sm text-gray-500 py-2">
          Showing {invariants.length}
          {pagination.total_count !== undefined && ` of ${pagination.total_count}`} invariants
        </div>
      )}
    </div>
  );
}

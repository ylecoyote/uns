/**
 * InvariantsSummary component
 *
 * Displays summary statistics for system invariants using /ui/invariants/summary.
 * Shows counts by severity, enforcement type, and status.
 * Displays degraded state warning if API indicates degraded=true.
 */

import { useInvariantsSummary } from '../hooks/useInvariants';

interface StatCardProps {
  label: string;
  value: number;
  variant?: 'default' | 'high' | 'medium' | 'low' | 'exception';
}

function StatCard({ label, value, variant = 'default' }: StatCardProps) {
  const variantStyles: Record<string, string> = {
    default: 'bg-gray-100 text-gray-800',
    high: 'bg-red-100 text-red-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-blue-100 text-blue-800',
    exception: 'bg-orange-100 text-orange-800',
  };

  return (
    <div className={`rounded-lg p-4 ${variantStyles[variant]}`}>
      <div className="text-sm font-medium opacity-75">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

interface InvariantsSummaryProps {
  degraded?: boolean;
}

export function InvariantsSummary({ degraded = false }: InvariantsSummaryProps) {
  const { summary, loading, error, degraded: summaryDegraded } = useInvariantsSummary();

  // Combine degraded state from prop and hook
  const isDegraded = degraded || summaryDegraded;

  // Show fallback UI for invariants_source_unavailable - don't show error, just degraded state
  const isSourceUnavailable = error?.code === 'invariants_source_unavailable';

  if (loading) {
    return (
      <div className="animate-pulse">
        <div className="h-24 bg-gray-200 rounded-lg"></div>
      </div>
    );
  }

  // For source unavailable, show a graceful fallback instead of error
  if (isSourceUnavailable) {
    return (
      <div className="space-y-4">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Invariants Summary</h2>
          <div className="text-gray-500 text-center py-8">
            <div className="text-4xl mb-2" aria-hidden="true">&#128203;</div>
            <div className="font-medium">Summary Unavailable</div>
            <div className="text-sm mt-1">
              The invariant registry is temporarily unavailable.
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="text-red-800 font-medium">Error loading summary</div>
        <div className="text-red-600 text-sm">{error.message}</div>
        {error.request_id && (
          <div className="text-red-500 text-xs mt-1">Request ID: {error.request_id}</div>
        )}
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg shadow p-6">
        {/* Show degraded indicator within summary card */}
        {isDegraded && (
          <div className="mb-4 text-yellow-700 text-sm flex items-center gap-2">
            <span aria-hidden="true">&#9888;</span>
            <span>Data may be incomplete</span>
          </div>
        )}
        <h2 className="text-lg font-semibold mb-4">Invariants Summary</h2>

        {/* Total Count */}
        <div className="mb-6">
          <div className="text-3xl font-bold text-gray-900">{summary.total_count}</div>
          <div className="text-sm text-gray-500">Total Invariants</div>
        </div>

        {/* By Severity */}
        <div className="mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">By Severity</h3>
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="High" value={summary.by_severity.HIGH ?? 0} variant="high" />
            <StatCard label="Medium" value={summary.by_severity.MEDIUM ?? 0} variant="medium" />
            <StatCard label="Low" value={summary.by_severity.LOW ?? 0} variant="low" />
          </div>
        </div>

        {/* By Enforcement Type */}
        <div className="mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">By Enforcement Type</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Guard" value={summary.by_enforcement_type.guard ?? 0} />
            <StatCard label="Isolation" value={summary.by_enforcement_type.isolation ?? 0} />
            <StatCard label="Test" value={summary.by_enforcement_type.test ?? 0} />
            <StatCard
              label="Exception"
              value={summary.by_enforcement_type.exception ?? 0}
              variant="exception"
            />
          </div>
        </div>

        {/* By Status */}
        <div className="mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-2">By Status</h3>
          <div className="grid grid-cols-2 gap-3">
            <StatCard label="Active" value={summary.by_status.active ?? 0} />
            <StatCard label="Inactive" value={summary.by_status.inactive ?? 0} />
          </div>
        </div>

        {/* Exceptions Requiring Review */}
        {summary.exceptions_requiring_review > 0 && (
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
            <div className="flex items-center gap-2">
              <span className="text-orange-600">&#9888;</span>
              <span className="text-orange-800 font-medium">
                {summary.exceptions_requiring_review} exception(s) require review
              </span>
            </div>
          </div>
        )}

        {/* Last Updated */}
        <div className="mt-4 text-xs text-gray-400">
          Last updated: {new Date(summary.last_updated).toLocaleString()}
        </div>
      </div>
    </div>
  );
}

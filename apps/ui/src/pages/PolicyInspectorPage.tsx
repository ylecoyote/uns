/**
 * PolicyInspectorPage component
 *
 * Main page for viewing effective policy resolution.
 * Features:
 * - Form for entering notification_type, intent, autonomy_mode, irreversible
 * - Display of effective policy values
 * - Resolution trace showing how each value was determined
 *
 * All functionality is READ-ONLY per UI Scope v1.
 */

import { PolicyInspectorForm } from '../components/PolicyInspectorForm';
import { ResolutionTraceDisplay } from '../components/ResolutionTraceDisplay';
import { usePolicyInspector } from '../hooks/usePolicyInspector';
import type { PolicyInspectorParams } from '../types/api';

export function PolicyInspectorPage() {
  const { result, loading, error, inspect, clear } = usePolicyInspector();

  const handleInspect = (params: PolicyInspectorParams) => {
    inspect(params);
  };

  const handleClear = () => {
    clear();
  };

  return (
    <div className="policy-inspector-page" data-testid="policy-inspector-page">
      {/* Page Header */}
      <div className="page-header">
        <h1>Policy Inspector</h1>
        <p className="page-description">
          View effective policy values and resolution trace for any notification type.
          All data is read-only.
        </p>
      </div>

      {/* Inspector Form */}
      <div className="inspector-form-section card">
        <PolicyInspectorForm
          onInspect={handleInspect}
          onClear={handleClear}
          loading={loading}
        />
      </div>

      {/* Loading State */}
      {loading && (
        <div className="loading-state" data-testid="loading-state">
          <p>Resolving policy...</p>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="error-state" data-testid="error-state">
          <div className="error-message">
            <strong>Error resolving policy</strong>
            <p>{error.message}</p>
            {error.code && <p className="error-code">Code: {error.code}</p>}
            {error.requestId && <p className="error-request-id">Request ID: {error.requestId}</p>}
          </div>
        </div>
      )}

      {/* Results */}
      {result && !loading && !error && (
        <ResolutionTraceDisplay response={result} />
      )}

      {/* Empty State */}
      {!result && !loading && !error && (
        <div className="empty-state" data-testid="empty-state">
          <p>Enter a notification type and click "Inspect Policy" to view resolution details.</p>
        </div>
      )}
    </div>
  );
}

export default PolicyInspectorPage;

/**
 * ResolutionTraceDisplay component shows the policy resolution trace.
 *
 * Displays:
 * - Resolution context (intent, autonomy_mode, irreversible, policy_found)
 * - Effective policy values
 * - Resolution trace showing how each value was determined
 */

import type { EffectivePolicyResponse, ResolutionSource, ResolutionStep } from '../types/api';

interface ResolutionTraceDisplayProps {
  response: EffectivePolicyResponse;
}

const FIELD_DISPLAY_NAMES: Record<string, string> = {
  delivery_mode: 'Delivery Mode',
  channels: 'Channels',
  require_ack: 'Require Acknowledgment',
  ack_timeout_minutes: 'Ack Timeout (minutes)',
  dedup_window_seconds: 'Dedup Window (seconds)',
};

const SOURCE_LABELS: Record<ResolutionSource, string> = {
  explicit_override: 'Explicit Override',
  mode_override: 'Mode Override',
  policy_base: 'Policy Base',
  sdk_default: 'SDK Default',
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return 'None';
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return '[]';
    }
    return value.join(', ');
  }
  return String(value);
}

function ResolutionStepItem({ step }: { step: ResolutionStep }) {
  const sourceLabel = SOURCE_LABELS[step.source] || step.source;
  const valueStr = formatValue(step.value);
  const statusClass = step.applied ? 'step-applied' : 'step-skipped';
  const statusLabel = step.applied ? 'APPLIED' : 'SKIPPED';

  return (
    <div className={`resolution-step ${statusClass}`} data-testid="resolution-step">
      <span className="step-source">{sourceLabel}</span>
      <span className="step-value">{valueStr}</span>
      <span className={`step-status badge ${step.applied ? 'badge-success' : 'badge-default'}`}>
        {statusLabel}
      </span>
      {step.reason && <span className="step-reason">{step.reason}</span>}
    </div>
  );
}

function FieldResolution({
  fieldName,
  effectiveValue,
  steps,
}: {
  fieldName: string;
  effectiveValue: string;
  steps: ResolutionStep[];
}) {
  const displayName = FIELD_DISPLAY_NAMES[fieldName] || fieldName;

  return (
    <div className="field-resolution" data-testid={`field-resolution-${fieldName}`}>
      <div className="field-header">
        <span className="field-name">{displayName}</span>
        <span className="field-effective-value">{effectiveValue}</span>
      </div>
      <div className="field-steps">
        {steps.map((step, idx) => (
          <ResolutionStepItem key={idx} step={step} />
        ))}
      </div>
    </div>
  );
}

export function ResolutionTraceDisplay({ response }: ResolutionTraceDisplayProps) {
  const { notification_type, effective, resolution, resolution_context } = response;

  // Prepare effective values for display
  const fieldEffectiveValues: Record<string, string> = {
    delivery_mode: effective.delivery_mode,
    channels: formatValue(effective.channels),
    require_ack: formatValue(effective.require_ack),
    ack_timeout_minutes: formatValue(effective.ack_timeout_minutes),
    dedup_window_seconds: formatValue(effective.dedup_window_seconds),
  };

  // Define field order
  const fieldOrder = ['delivery_mode', 'channels', 'require_ack', 'ack_timeout_minutes', 'dedup_window_seconds'];

  return (
    <div className="resolution-trace-display" data-testid="resolution-trace-display">
      {/* Header */}
      <div className="resolution-header">
        <h3>Policy Resolution for: <code>{notification_type}</code></h3>
      </div>

      {/* Resolution Context */}
      <div className="resolution-context card" data-testid="resolution-context">
        <h4>Resolution Context</h4>
        <div className="context-grid">
          <div className="context-item">
            <span className="context-label">Intent</span>
            <span className="context-value badge badge-info">{resolution_context.intent}</span>
          </div>
          <div className="context-item">
            <span className="context-label">Autonomy Mode</span>
            <span className={`context-value mode-badge mode-${resolution_context.autonomy_mode.toLowerCase()}`}>
              {resolution_context.autonomy_mode}
            </span>
          </div>
          <div className="context-item">
            <span className="context-label">Irreversible</span>
            <span className="context-value">{resolution_context.irreversible ? 'Yes' : 'No'}</span>
          </div>
          <div className="context-item">
            <span className="context-label">Policy Found</span>
            <span className={`context-value badge ${resolution_context.policy_found ? 'badge-success' : 'badge-warning'}`}>
              {resolution_context.policy_found ? 'Yes' : 'No'}
            </span>
          </div>
          {resolution_context.policy_notification_type && (
            <div className="context-item">
              <span className="context-label">Matched Policy Type</span>
              <span className="context-value"><code>{resolution_context.policy_notification_type}</code></span>
            </div>
          )}
        </div>
      </div>

      {/* Effective Policy Summary */}
      <div className="effective-policy card" data-testid="effective-policy">
        <h4>Effective Policy Values</h4>
        <div className="effective-grid">
          {fieldOrder.map((fieldName) => (
            <div key={fieldName} className="effective-item">
              <span className="effective-label">{FIELD_DISPLAY_NAMES[fieldName] || fieldName}</span>
              <span className="effective-value">{fieldEffectiveValues[fieldName]}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Resolution Trace */}
      <div className="resolution-trace card" data-testid="resolution-trace">
        <h4>Resolution Trace</h4>
        <p className="trace-description">
          Each field shows the resolution chain from highest to lowest priority.
          The first applicable source is applied.
        </p>
        <div className="trace-fields">
          {fieldOrder.map((fieldName) => (
            <FieldResolution
              key={fieldName}
              fieldName={fieldName}
              effectiveValue={fieldEffectiveValues[fieldName]}
              steps={resolution[fieldName] || []}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

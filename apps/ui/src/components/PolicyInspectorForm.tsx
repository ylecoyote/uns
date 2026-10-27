/**
 * PolicyInspectorForm component provides form controls for policy inspection.
 *
 * Form fields:
 * - notification_type: Text input for the notification type
 * - intent: Select dropdown for notification intent
 * - autonomy_mode: Select dropdown for autonomy mode
 * - irreversible: Checkbox for irreversible flag
 */

import { useEffect, useState } from 'react';
import type { NotificationIntent, AutonomyMode, PolicyInspectorParams } from '../types/api';

export interface PolicyExternalSelection {
  notification_type: string;
  intent?: NotificationIntent | null;
  autonomy_mode?: AutonomyMode;
  seq: number;
}

interface PolicyInspectorFormProps {
  onInspect: (params: PolicyInspectorParams) => void;
  onClear: () => void;
  loading: boolean;
  externalSelection?: PolicyExternalSelection | null;
}

const INTENT_OPTIONS: { value: NotificationIntent; label: string; description: string }[] = [
  { value: 'SAFETY', label: 'Safety', description: 'Critical safety notifications' },
  { value: 'GOVERNANCE', label: 'Governance', description: 'Compliance and approval requests' },
  { value: 'OPERATIONAL', label: 'Operational', description: 'System status updates' },
  { value: 'INFORMATIONAL', label: 'Informational', description: 'General information' },
];

const AUTONOMY_MODE_OPTIONS: { value: AutonomyMode; label: string; description: string }[] = [
  { value: 'PREVIEW', label: 'Preview', description: 'All notifications to WebSocket only' },
  { value: 'SHADOW', label: 'Shadow', description: 'Partial routing for testing' },
  { value: 'LIVE', label: 'Live', description: 'Full production routing' },
];

export function PolicyInspectorForm({
  onInspect,
  onClear,
  loading,
  externalSelection,
}: PolicyInspectorFormProps) {
  const [notificationType, setNotificationType] = useState('');
  const [intent, setIntent] = useState<NotificationIntent>('INFORMATIONAL');
  const [autonomyMode, setAutonomyMode] = useState<AutonomyMode>('PREVIEW');
  const [irreversible, setIrreversible] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (!externalSelection) return;
    setNotificationType(externalSelection.notification_type);
    if (externalSelection.intent) {
      setIntent(externalSelection.intent);
    }
    if (externalSelection.autonomy_mode) {
      setAutonomyMode(externalSelection.autonomy_mode);
    }
    setValidationError(null);
  }, [externalSelection]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    const trimmedType = notificationType.trim();
    if (!trimmedType) {
      setValidationError('Notification type is required');
      return;
    }

    onInspect({
      notification_type: trimmedType,
      intent,
      autonomy_mode: autonomyMode,
      irreversible,
    });
  };

  const handleClear = () => {
    setNotificationType('');
    setIntent('INFORMATIONAL');
    setAutonomyMode('PREVIEW');
    setIrreversible(false);
    setValidationError(null);
    onClear();
  };

  return (
    <form className="policy-inspector-form" onSubmit={handleSubmit} data-testid="policy-inspector-form">
      <div className="filter-row">
        <div className="filter-group filter-group-wide">
          <label htmlFor="notification-type-input">Notification Type</label>
          <input
            id="notification-type-input"
            type="text"
            placeholder="e.g., trading.order_placed"
            value={notificationType}
            onChange={(e) => setNotificationType(e.target.value)}
            data-testid="notification-type-input"
            aria-invalid={!!validationError}
            aria-describedby={validationError ? 'notification-type-error' : undefined}
          />
          {validationError && (
            <span id="notification-type-error" className="field-error" role="alert">
              {validationError}
            </span>
          )}
        </div>
      </div>

      <div className="filter-row">
        <div className="filter-group">
          <label htmlFor="intent-select">Intent</label>
          <select
            id="intent-select"
            value={intent}
            onChange={(e) => setIntent(e.target.value as NotificationIntent)}
            data-testid="intent-select"
          >
            {INTENT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label} - {opt.description}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="autonomy-mode-select">Autonomy Mode</label>
          <select
            id="autonomy-mode-select"
            value={autonomyMode}
            onChange={(e) => setAutonomyMode(e.target.value as AutonomyMode)}
            data-testid="autonomy-mode-select"
          >
            {AUTONOMY_MODE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label} - {opt.description}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group filter-group-checkbox">
          <label htmlFor="irreversible-checkbox" className="checkbox-label">
            <input
              id="irreversible-checkbox"
              type="checkbox"
              checked={irreversible}
              onChange={(e) => setIrreversible(e.target.checked)}
              data-testid="irreversible-checkbox"
            />
            <span>Irreversible Action</span>
          </label>
          <span className="field-hint">Mark if the action cannot be undone</span>
        </div>
      </div>

      <div className="filter-actions">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading}
          data-testid="inspect-btn"
        >
          {loading ? 'Inspecting...' : 'Inspect Policy'}
        </button>
        <button
          type="button"
          onClick={handleClear}
          className="btn btn-secondary"
          disabled={loading}
          data-testid="clear-btn"
        >
          Clear
        </button>
      </div>
    </form>
  );
}

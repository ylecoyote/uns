/**
 * AuditFilters component - Modernist 4-Column Modular Filter Grid (1d / 1e)
 *
 * Provides filter controls for the audit event stream plus the segmented
 * view toggle ("By notification" lifecycle view vs. "All events" stream).
 */

import { useCallback, useState } from 'react';
import type { AuditEventFilter, AuditEventType, AutonomyMode } from '../types/api';

export type AuditViewMode = 'by-notification' | 'all-events';

interface AuditFiltersProps {
  filters: AuditEventFilter;
  onFiltersChange: (filters: AuditEventFilter) => void;
  viewMode?: AuditViewMode;
  onViewModeChange?: (mode: AuditViewMode) => void;
}

const eventTypeOptions: Array<{ value: AuditEventType | ''; label: string }> = [
  { value: '', label: 'All Events' },
  { value: 'notification.created', label: 'Notification Created' },
  { value: 'delivery.started', label: 'Delivery Started' },
  { value: 'delivery.channel_attempted', label: 'Channel Attempted' },
  { value: 'delivery.succeeded', label: 'Delivery Succeeded' },
  { value: 'delivery.failed', label: 'Delivery Failed' },
  { value: 'delivery.deduplicated', label: 'Deduplicated' },
  { value: 'delivery.rate_limited', label: 'Rate Limited' },
  { value: 'ack.pending', label: 'Ack Pending' },
  { value: 'ack.received', label: 'Ack Received' },
  { value: 'ack.dismissed', label: 'Ack Dismissed' },
  { value: 'ack.timed_out', label: 'Ack Timed Out' },
  { value: 'escalation.triggered', label: 'Escalation Triggered' },
];

const autonomyModeOptions: Array<{ value: AutonomyMode | ''; label: string }> = [
  { value: '', label: 'All Modes' },
  { value: 'PREVIEW', label: 'Preview' },
  { value: 'SHADOW', label: 'Shadow' },
  { value: 'LIVE', label: 'Live' },
];

function parseOptionalIsoDate(raw: string): string | undefined {
  if (!raw) return undefined;
  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toISOString();
  }
  return undefined;
}

export function AuditFilters({
  filters,
  onFiltersChange,
  viewMode = 'by-notification',
  onViewModeChange,
}: AuditFiltersProps) {
  const [notificationId, setNotificationId] = useState(filters.notification_id || '');
  const [agentId, setAgentId] = useState(filters.agent_id || '');
  const [correlationId, setCorrelationId] = useState(filters.correlation_id || '');
  const [startTime, setStartTime] = useState(filters.start_time?.slice(0, 16) || '');
  const [endTime, setEndTime] = useState(filters.end_time?.slice(0, 16) || '');

  const buildCurrentFilters = useCallback(
    (overrides?: Partial<AuditEventFilter>): AuditEventFilter => ({
      ...filters,
      notification_id: notificationId || undefined,
      agent_id: agentId || undefined,
      correlation_id: correlationId || undefined,
      start_time: parseOptionalIsoDate(startTime),
      end_time: parseOptionalIsoDate(endTime),
      ...overrides,
    }),
    [filters, notificationId, agentId, correlationId, startTime, endTime]
  );

  const handleEventTypeChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as AuditEventType | '';
      onFiltersChange(
        buildCurrentFilters({
          event_type: value || undefined,
        })
      );
    },
    [buildCurrentFilters, onFiltersChange]
  );

  const handleAutonomyModeChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as AutonomyMode | '';
      onFiltersChange(
        buildCurrentFilters({
          autonomy_mode: value || undefined,
        })
      );
    },
    [buildCurrentFilters, onFiltersChange]
  );

  const handleApplyFilters = useCallback(() => {
    onFiltersChange(buildCurrentFilters());
  }, [buildCurrentFilters, onFiltersChange]);

  const handleClearFilters = useCallback(() => {
    setNotificationId('');
    setAgentId('');
    setCorrelationId('');
    setStartTime('');
    setEndTime('');
    onFiltersChange({ limit: filters.limit });
  }, [filters.limit, onFiltersChange]);

  const hasActiveFilters =
    filters.event_type ||
    filters.autonomy_mode ||
    filters.notification_id ||
    filters.agent_id ||
    filters.correlation_id ||
    filters.start_time ||
    filters.end_time;

  return (
    <div
      className="modernist-filter-panel bg-white rounded-lg shadow"
      data-testid="audit-filters"
    >
      <div className="filter-grid-4">
        {/* Cell 1: Event Type */}
        <div className="filter-cell">
          <label htmlFor="event-type-filter" className="field-label">
            Event Type
          </label>
          <select
            id="event-type-filter"
            value={filters.event_type || ''}
            onChange={handleEventTypeChange}
            className="modernist-select"
            data-testid="event-type-select"
          >
            {eventTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Cell 2: Autonomy Mode */}
        <div className="filter-cell">
          <label htmlFor="autonomy-mode-filter" className="field-label">
            Autonomy Mode
          </label>
          <select
            id="autonomy-mode-filter"
            value={filters.autonomy_mode || ''}
            onChange={handleAutonomyModeChange}
            className="modernist-select"
            data-testid="autonomy-mode-select"
          >
            {autonomyModeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Cell 3: Notification ID */}
        <div className="filter-cell">
          <label htmlFor="notification-id-filter" className="field-label">
            Notification ID
          </label>
          <input
            id="notification-id-filter"
            type="text"
            placeholder="Notification ID (UUID)"
            value={notificationId}
            onChange={(e) => setNotificationId(e.target.value)}
            className="modernist-input monospace"
            data-testid="notification-id-input"
          />
        </div>

        {/* Cell 4: Agent ID */}
        <div className="filter-cell">
          <label htmlFor="agent-id-filter" className="field-label">
            Agent ID
          </label>
          <input
            id="agent-id-filter"
            type="text"
            placeholder="Agent ID (UUID)"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            className="modernist-input monospace"
            data-testid="agent-id-input"
          />
        </div>

        {/* Cell 5: Correlation ID */}
        <div className="filter-cell">
          <label htmlFor="correlation-id-filter" className="field-label">
            Correlation ID
          </label>
          <input
            id="correlation-id-filter"
            type="text"
            placeholder="Correlation ID"
            value={correlationId}
            onChange={(e) => setCorrelationId(e.target.value)}
            className="modernist-input monospace"
            data-testid="correlation-id-input"
          />
        </div>

        {/* Cell 6: Start Time */}
        <div className="filter-cell">
          <label htmlFor="start-time-filter" className="field-label">
            Start Time
          </label>
          <input
            id="start-time-filter"
            type="datetime-local"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            className="modernist-input monospace"
            data-testid="start-time-input"
          />
        </div>

        {/* Cell 7: End Time */}
        <div className="filter-cell">
          <label htmlFor="end-time-filter" className="field-label">
            End Time
          </label>
          <input
            id="end-time-filter"
            type="datetime-local"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            className="modernist-input monospace"
            data-testid="end-time-input"
          />
        </div>

        {/* Cell 8: Segmented View Control + Actions */}
        <div className="filter-cell" style={{ justifyContent: 'space-between' }}>
          <span className="field-label">View Mode</span>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
            <div className="seg" role="group" aria-label="View mode">
              <button
                type="button"
                className={viewMode === 'by-notification' ? 'seg-opt active' : 'seg-opt'}
                onClick={() => onViewModeChange?.('by-notification')}
                data-testid="audit-view-by-notification"
              >
                By notification
              </button>
              <button
                type="button"
                className={viewMode === 'all-events' ? 'seg-opt active' : 'seg-opt'}
                onClick={() => onViewModeChange?.('all-events')}
                data-testid="audit-view-all-events"
              >
                All events
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Action buttons bar */}
      <div className="filter-actions">
        <div className="filter-actions-left">
          <button
            type="button"
            onClick={handleApplyFilters}
            className="btn btn-primary"
            data-testid="apply-filters-btn"
          >
            Apply Filters
          </button>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={handleClearFilters}
              className="btn btn-secondary"
              data-testid="clear-filters-btn"
            >
              Clear
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

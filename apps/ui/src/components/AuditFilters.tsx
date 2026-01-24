/**
 * AuditFilters component provides filter controls for the audit event stream.
 */

import { useState } from 'react';
import type { AuditEventFilter, AuditEventType, AutonomyMode } from '../types/api';

interface AuditFiltersProps {
  filter: AuditEventFilter;
  onFilterChange: (filter: AuditEventFilter) => void;
}

const EVENT_TYPES: { value: AuditEventType; label: string }[] = [
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

const AUTONOMY_MODES: { value: AutonomyMode; label: string }[] = [
  { value: 'PREVIEW', label: 'Preview' },
  { value: 'SHADOW', label: 'Shadow' },
  { value: 'LIVE', label: 'Live' },
];

export function AuditFilters({ filter, onFilterChange }: AuditFiltersProps) {
  const [localFilter, setLocalFilter] = useState<AuditEventFilter>(filter);

  const handleChange = (field: keyof AuditEventFilter, value: string | undefined) => {
    const newFilter = {
      ...localFilter,
      [field]: value || undefined,
    };
    setLocalFilter(newFilter);
  };

  const handleApply = () => {
    onFilterChange(localFilter);
  };

  const handleClear = () => {
    const clearedFilter: AuditEventFilter = { limit: filter.limit };
    setLocalFilter(clearedFilter);
    onFilterChange(clearedFilter);
  };

  return (
    <div className="audit-filters" data-testid="audit-filters">
      <div className="filter-row">
        <div className="filter-group">
          <label htmlFor="event-type-filter">Event Type</label>
          <select
            id="event-type-filter"
            value={localFilter.event_type ?? ''}
            onChange={(e) => handleChange('event_type', e.target.value as AuditEventType)}
            data-testid="event-type-select"
          >
            <option value="">All Events</option>
            {EVENT_TYPES.map((et) => (
              <option key={et.value} value={et.value}>
                {et.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="autonomy-mode-filter">Autonomy Mode</label>
          <select
            id="autonomy-mode-filter"
            value={localFilter.autonomy_mode ?? ''}
            onChange={(e) => handleChange('autonomy_mode', e.target.value as AutonomyMode)}
            data-testid="autonomy-mode-select"
          >
            <option value="">All Modes</option>
            {AUTONOMY_MODES.map((am) => (
              <option key={am.value} value={am.value}>
                {am.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="notification-id-filter">Notification ID</label>
          <input
            id="notification-id-filter"
            type="text"
            placeholder="UUID..."
            value={localFilter.notification_id ?? ''}
            onChange={(e) => handleChange('notification_id', e.target.value)}
            data-testid="notification-id-input"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="agent-id-filter">Agent ID</label>
          <input
            id="agent-id-filter"
            type="text"
            placeholder="UUID..."
            value={localFilter.agent_id ?? ''}
            onChange={(e) => handleChange('agent_id', e.target.value)}
            data-testid="agent-id-input"
          />
        </div>
      </div>

      <div className="filter-row">
        <div className="filter-group">
          <label htmlFor="correlation-id-filter">Correlation ID</label>
          <input
            id="correlation-id-filter"
            type="text"
            placeholder="Correlation ID..."
            value={localFilter.correlation_id ?? ''}
            onChange={(e) => handleChange('correlation_id', e.target.value)}
            data-testid="correlation-id-input"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="start-time-filter">Start Time</label>
          <input
            id="start-time-filter"
            type="datetime-local"
            value={localFilter.start_time?.slice(0, 16) ?? ''}
            onChange={(e) =>
              handleChange('start_time', e.target.value ? new Date(e.target.value).toISOString() : undefined)
            }
            data-testid="start-time-input"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="end-time-filter">End Time</label>
          <input
            id="end-time-filter"
            type="datetime-local"
            value={localFilter.end_time?.slice(0, 16) ?? ''}
            onChange={(e) =>
              handleChange('end_time', e.target.value ? new Date(e.target.value).toISOString() : undefined)
            }
            data-testid="end-time-input"
          />
        </div>
      </div>

      <div className="filter-actions">
        <button
          type="button"
          onClick={handleApply}
          className="btn btn-primary"
          data-testid="apply-filters-btn"
        >
          Apply Filters
        </button>
        <button
          type="button"
          onClick={handleClear}
          className="btn btn-secondary"
          data-testid="clear-filters-btn"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

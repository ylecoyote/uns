/**
 * AuditFilters component provides filter controls for the audit event stream.
 *
 * Follows the InvariantsFilter pattern for consistency.
 */

import { useCallback, useState } from 'react';
import type { AuditEventFilter, AuditEventType, AutonomyMode } from '../types/api';

interface AuditFiltersProps {
  filters: AuditEventFilter;
  onFiltersChange: (filters: AuditEventFilter) => void;
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

export function AuditFilters({ filters, onFiltersChange }: AuditFiltersProps) {
  const [notificationId, setNotificationId] = useState(filters.notification_id || '');
  const [agentId, setAgentId] = useState(filters.agent_id || '');
  const [correlationId, setCorrelationId] = useState(filters.correlation_id || '');
  const [startTime, setStartTime] = useState(filters.start_time?.slice(0, 16) || '');
  const [endTime, setEndTime] = useState(filters.end_time?.slice(0, 16) || '');

  const handleEventTypeChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as AuditEventType | '';
      onFiltersChange({
        ...filters,
        event_type: value || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  const handleAutonomyModeChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as AutonomyMode | '';
      onFiltersChange({
        ...filters,
        autonomy_mode: value || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  const handleApplyFilters = useCallback(() => {
    onFiltersChange({
      ...filters,
      notification_id: notificationId || undefined,
      agent_id: agentId || undefined,
      correlation_id: correlationId || undefined,
      start_time: startTime ? new Date(startTime).toISOString() : undefined,
      end_time: endTime ? new Date(endTime).toISOString() : undefined,
    });
  }, [filters, onFiltersChange, notificationId, agentId, correlationId, startTime, endTime]);

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
    <div className="bg-white rounded-lg shadow p-4" data-testid="audit-filters">
      {/* First row: dropdowns */}
      <div className="flex flex-col md:flex-row gap-4 mb-4">
        {/* Event Type Filter */}
        <div>
          <label htmlFor="event-type-filter" className="sr-only">
            Filter by event type
          </label>
          <select
            id="event-type-filter"
            value={filters.event_type || ''}
            onChange={handleEventTypeChange}
            className="rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="event-type-select"
          >
            {eventTypeOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Autonomy Mode Filter */}
        <div>
          <label htmlFor="autonomy-mode-filter" className="sr-only">
            Filter by autonomy mode
          </label>
          <select
            id="autonomy-mode-filter"
            value={filters.autonomy_mode || ''}
            onChange={handleAutonomyModeChange}
            className="rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="autonomy-mode-select"
          >
            {autonomyModeOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Second row: text inputs */}
      <div className="flex flex-col md:flex-row gap-4 mb-4">
        <div className="flex-1">
          <label htmlFor="notification-id-filter" className="sr-only">
            Filter by notification ID
          </label>
          <input
            id="notification-id-filter"
            type="text"
            placeholder="Notification ID (UUID)"
            value={notificationId}
            onChange={(e) => setNotificationId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="notification-id-input"
          />
        </div>

        <div className="flex-1">
          <label htmlFor="agent-id-filter" className="sr-only">
            Filter by agent ID
          </label>
          <input
            id="agent-id-filter"
            type="text"
            placeholder="Agent ID (UUID)"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="agent-id-input"
          />
        </div>

        <div className="flex-1">
          <label htmlFor="correlation-id-filter" className="sr-only">
            Filter by correlation ID
          </label>
          <input
            id="correlation-id-filter"
            type="text"
            placeholder="Correlation ID"
            value={correlationId}
            onChange={(e) => setCorrelationId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="correlation-id-input"
          />
        </div>
      </div>

      {/* Third row: time range */}
      <div className="flex flex-col md:flex-row gap-4 mb-4">
        <div className="flex-1">
          <label htmlFor="start-time-filter" className="block text-sm font-medium text-gray-700 mb-1">
            Start Time
          </label>
          <input
            id="start-time-filter"
            type="datetime-local"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="start-time-input"
          />
        </div>

        <div className="flex-1">
          <label htmlFor="end-time-filter" className="block text-sm font-medium text-gray-700 mb-1">
            End Time
          </label>
          <input
            id="end-time-filter"
            type="datetime-local"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="end-time-input"
          />
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-4">
        <button
          type="button"
          onClick={handleApplyFilters}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          data-testid="apply-filters-btn"
        >
          Apply Filters
        </button>

        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleClearFilters}
            className="px-4 py-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="clear-filters-btn"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}

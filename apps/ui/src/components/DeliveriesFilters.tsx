/**
 * DeliveriesFilters component provides filter controls for delivery timelines.
 */

import { useState } from 'react';
import type {
  DeliveryFilter,
  DeliveryStatus,
  NotificationIntent,
  DeliveryMode,
  AutonomyMode,
  Channel,
} from '../types/api';

interface DeliveriesFiltersProps {
  filter: DeliveryFilter;
  onFilterChange: (filter: DeliveryFilter) => void;
}

const STATUS_OPTIONS: { value: DeliveryStatus; label: string }[] = [
  { value: 'PENDING', label: 'Pending' },
  { value: 'DELIVERED', label: 'Delivered' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'DEDUPLICATED', label: 'Deduplicated' },
  { value: 'RATE_LIMITED', label: 'Rate Limited' },
];

const INTENT_OPTIONS: { value: NotificationIntent; label: string }[] = [
  { value: 'SAFETY', label: 'Safety' },
  { value: 'GOVERNANCE', label: 'Governance' },
  { value: 'OPERATIONAL', label: 'Operational' },
  { value: 'INFORMATIONAL', label: 'Informational' },
];

const DELIVERY_MODE_OPTIONS: { value: DeliveryMode; label: string }[] = [
  { value: 'GUARANTEED', label: 'Guaranteed' },
  { value: 'BEST_EFFORT', label: 'Best Effort' },
];

const AUTONOMY_MODE_OPTIONS: { value: AutonomyMode; label: string }[] = [
  { value: 'PREVIEW', label: 'Preview' },
  { value: 'SHADOW', label: 'Shadow' },
  { value: 'LIVE', label: 'Live' },
];

const CHANNEL_OPTIONS: { value: Channel; label: string }[] = [
  { value: 'SLACK', label: 'Slack' },
  { value: 'EMAIL', label: 'Email' },
  { value: 'WEBSOCKET', label: 'WebSocket' },
  { value: 'PAGERDUTY', label: 'PagerDuty' },
];

const LIMIT_OPTIONS = [10, 25, 50, 100];

export function DeliveriesFilters({ filter, onFilterChange }: DeliveriesFiltersProps) {
  const [localFilter, setLocalFilter] = useState<DeliveryFilter>(filter);

  const handleChange = (field: keyof DeliveryFilter, value: string | number | undefined) => {
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
    const clearedFilter: DeliveryFilter = { limit: filter.limit };
    setLocalFilter(clearedFilter);
    onFilterChange(clearedFilter);
  };

  return (
    <div className="audit-filters" data-testid="deliveries-filters">
      <div className="filter-row">
        <div className="filter-group">
          <label htmlFor="status-filter">Status</label>
          <select
            id="status-filter"
            value={localFilter.status ?? ''}
            onChange={(e) => handleChange('status', e.target.value as DeliveryStatus)}
            data-testid="status-select"
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="intent-filter">Intent</label>
          <select
            id="intent-filter"
            value={localFilter.intent ?? ''}
            onChange={(e) => handleChange('intent', e.target.value as NotificationIntent)}
            data-testid="intent-select"
          >
            <option value="">All</option>
            {INTENT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="delivery-mode-filter">Delivery Mode</label>
          <select
            id="delivery-mode-filter"
            value={localFilter.delivery_mode ?? ''}
            onChange={(e) => handleChange('delivery_mode', e.target.value as DeliveryMode)}
            data-testid="delivery-mode-select"
          >
            <option value="">All</option>
            {DELIVERY_MODE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
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
            <option value="">All</option>
            {AUTONOMY_MODE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="filter-row">
        <div className="filter-group">
          <label htmlFor="channel-filter">Channel</label>
          <select
            id="channel-filter"
            value={localFilter.channel ?? ''}
            onChange={(e) => handleChange('channel', e.target.value as Channel)}
            data-testid="channel-select"
          >
            <option value="">All</option>
            {CHANNEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="notification-type-filter">Notification Type</label>
          <input
            id="notification-type-filter"
            type="text"
            placeholder="e.g., order.placed"
            value={localFilter.notification_type ?? ''}
            onChange={(e) => handleChange('notification_type', e.target.value)}
            data-testid="notification-type-input"
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

        <div className="filter-group">
          <label htmlFor="limit-filter">Per Page</label>
          <select
            id="limit-filter"
            value={localFilter.limit ?? 25}
            onChange={(e) => handleChange('limit', parseInt(e.target.value, 10))}
            data-testid="limit-select"
          >
            {LIMIT_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
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

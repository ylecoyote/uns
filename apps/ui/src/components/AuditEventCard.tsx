/**
 * AuditEventCard component displays a single audit event with formatted payload.
 */

import type { AuditEvent, AuditEventType } from '../types/api';

interface AuditEventCardProps {
  event: AuditEvent;
}

/**
 * Format the event type for display with appropriate styling.
 */
function getEventTypeBadge(eventType: AuditEventType): {
  label: string;
  className: string;
} {
  const eventTypeConfig: Record<AuditEventType, { label: string; className: string }> = {
    'notification.created': { label: 'Created', className: 'badge-info' },
    'delivery.started': { label: 'Started', className: 'badge-info' },
    'delivery.channel_attempted': { label: 'Channel Attempt', className: 'badge-info' },
    'delivery.succeeded': { label: 'Delivered', className: 'badge-success' },
    'delivery.failed': { label: 'Failed', className: 'badge-error' },
    'delivery.deduplicated': { label: 'Deduplicated', className: 'badge-warning' },
    'delivery.rate_limited': { label: 'Rate Limited', className: 'badge-warning' },
    'ack.pending': { label: 'Ack Pending', className: 'badge-info' },
    'ack.received': { label: 'Acknowledged', className: 'badge-success' },
    'ack.dismissed': { label: 'Dismissed', className: 'badge-warning' },
    'ack.timed_out': { label: 'Ack Timeout', className: 'badge-error' },
    'escalation.triggered': { label: 'Escalated', className: 'badge-error' },
  };

  return eventTypeConfig[eventType] ?? { label: eventType, className: 'badge-default' };
}

/**
 * Format a date string to a human-readable format.
 */
function formatDateTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return isoString;
  }
}

/**
 * Safely format a JSON payload for display.
 */
function formatPayload(payload: Record<string, unknown>): string {
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

export function AuditEventCard({ event }: AuditEventCardProps) {
  const badge = getEventTypeBadge(event.event_type);

  return (
    <div className="audit-event-card" data-testid="audit-event-card">
      <div className="audit-event-header">
        <span className={`badge ${badge.className}`} data-testid="event-type-badge">
          {badge.label}
        </span>
        <span className="event-time" data-testid="event-time">
          {formatDateTime(event.event_time)}
        </span>
      </div>

      <div className="audit-event-meta">
        <div className="meta-row">
          <span className="meta-label">Notification:</span>
          <code className="meta-value" data-testid="notification-id">
            {event.notification_id}
          </code>
        </div>
        <div className="meta-row">
          <span className="meta-label">Type:</span>
          <span className="meta-value" data-testid="notification-type">
            {event.notification_type}
          </span>
        </div>
        <div className="meta-row">
          <span className="meta-label">Agent:</span>
          <code className="meta-value" data-testid="agent-id">
            {event.autonomy_context.agent_id}
          </code>
        </div>
        <div className="meta-row">
          <span className="meta-label">Mode:</span>
          <span
            className={`mode-badge mode-${event.autonomy_context.autonomy_mode.toLowerCase()}`}
            data-testid="autonomy-mode"
          >
            {event.autonomy_context.autonomy_mode}
          </span>
        </div>
        {event.correlation_id && (
          <div className="meta-row">
            <span className="meta-label">Correlation:</span>
            <code className="meta-value" data-testid="correlation-id">
              {event.correlation_id}
            </code>
          </div>
        )}
      </div>

      {Object.keys(event.payload).length > 0 && (
        <details className="audit-event-payload">
          <summary>Payload</summary>
          <pre className="payload-content" data-testid="event-payload">
            {formatPayload(event.payload)}
          </pre>
        </details>
      )}
    </div>
  );
}

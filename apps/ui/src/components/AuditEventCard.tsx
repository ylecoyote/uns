/**
 * AuditEventCard component displays a single audit event with formatted payload.
 *
 * Follows the InvariantCard pattern for consistent styling.
 */

import type { AuditEvent, AuditEventType } from '../types/api';

interface AuditEventCardProps {
  event: AuditEvent;
}

/**
 * Get styling configuration for event type badge.
 */
function getEventTypeBadgeStyles(eventType: AuditEventType): {
  label: string;
  className: string;
} {
  const config: Record<AuditEventType, { label: string; className: string }> = {
    'notification.created': { label: 'Created', className: 'bg-blue-100 text-blue-800 border-blue-200' },
    'delivery.started': { label: 'Started', className: 'bg-blue-100 text-blue-800 border-blue-200' },
    'delivery.channel_attempted': { label: 'Channel Attempt', className: 'bg-blue-100 text-blue-800 border-blue-200' },
    'delivery.succeeded': { label: 'Delivered', className: 'bg-green-100 text-green-800 border-green-200' },
    'delivery.failed': { label: 'Failed', className: 'bg-red-100 text-red-800 border-red-200' },
    'delivery.deduplicated': { label: 'Deduplicated', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
    'delivery.rate_limited': { label: 'Rate Limited', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
    'ack.pending': { label: 'Ack Pending', className: 'bg-blue-100 text-blue-800 border-blue-200' },
    'ack.received': { label: 'Acknowledged', className: 'bg-green-100 text-green-800 border-green-200' },
    'ack.dismissed': { label: 'Dismissed', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
    'ack.timed_out': { label: 'Ack Timeout', className: 'bg-red-100 text-red-800 border-red-200' },
    'escalation.triggered': { label: 'Escalated', className: 'bg-red-100 text-red-800 border-red-200' },
  };

  return config[eventType] ?? { label: eventType, className: 'bg-gray-100 text-gray-800 border-gray-200' };
}

/**
 * Get styling for autonomy mode badge.
 */
function getAutonomyModeBadgeStyles(mode: string): string {
  const styles: Record<string, string> = {
    PREVIEW: 'bg-purple-100 text-purple-800',
    SHADOW: 'bg-indigo-100 text-indigo-800',
    LIVE: 'bg-green-100 text-green-800',
  };

  return styles[mode] ?? 'bg-gray-100 text-gray-800';
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
  const badge = getEventTypeBadgeStyles(event.event_type);
  const modeBadgeStyles = getAutonomyModeBadgeStyles(event.autonomy_context.autonomy_mode);

  return (
    <div
      className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow mb-4"
      data-testid="audit-event-card"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${badge.className}`}
            data-testid="event-type-badge"
          >
            {badge.label}
          </span>
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${modeBadgeStyles}`}
            data-testid="autonomy-mode"
          >
            {event.autonomy_context.autonomy_mode}
          </span>
        </div>
        <span className="text-sm text-gray-500" data-testid="event-time">
          {formatDateTime(event.event_time)}
        </span>
      </div>

      {/* Metadata */}
      <div className="space-y-2 mb-4">
        <div className="flex items-center text-sm">
          <span className="font-medium text-gray-700 w-28">Notification:</span>
          <code className="bg-gray-100 px-2 py-0.5 rounded text-xs" data-testid="notification-id">
            {event.notification_id}
          </code>
        </div>
        <div className="flex items-center text-sm">
          <span className="font-medium text-gray-700 w-28">Type:</span>
          <span className="text-gray-600" data-testid="notification-type">
            {event.notification_type}
          </span>
        </div>
        <div className="flex items-center text-sm">
          <span className="font-medium text-gray-700 w-28">Agent:</span>
          <code className="bg-gray-100 px-2 py-0.5 rounded text-xs" data-testid="agent-id">
            {event.autonomy_context.agent_id}
          </code>
        </div>
        {event.correlation_id && (
          <div className="flex items-center text-sm">
            <span className="font-medium text-gray-700 w-28">Correlation:</span>
            <code className="bg-gray-100 px-2 py-0.5 rounded text-xs" data-testid="correlation-id">
              {event.correlation_id}
            </code>
          </div>
        )}
      </div>

      {/* Payload */}
      {Object.keys(event.payload).length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900">
            Payload
          </summary>
          <pre
            className="mt-2 bg-gray-50 rounded-lg p-4 text-xs overflow-x-auto"
            data-testid="event-payload"
          >
            {formatPayload(event.payload)}
          </pre>
        </details>
      )}
    </div>
  );
}

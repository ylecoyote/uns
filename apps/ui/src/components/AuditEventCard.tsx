/**
 * AuditEventCard component — Modernist 5-Column Event Row (1d)
 *
 * Uses the Delivery (filled) vs. Response (outlined) badge visual grammar
 * while preserving existing test class tokens and data-testids.
 */

import type { AuditEvent, AuditEventType } from '../types/api';

interface AuditEventCardProps {
  event: AuditEvent;
}

/**
 * Get styling configuration for event type badge.
 * Delivery events use filled badges (tag-delivery-*);
 * Response events use outlined badges (tag-response-*).
 */
function getEventTypeBadgeStyles(eventType: AuditEventType): {
  label: string;
  className: string;
} {
  const config: Record<AuditEventType, { label: string; className: string }> = {
    'notification.created': {
      label: 'Created',
      className: 'tag-delivery-info bg-blue-100 text-blue-800 border-blue-200',
    },
    'delivery.started': {
      label: 'Started',
      className: 'tag-delivery-info bg-blue-100 text-blue-800 border-blue-200',
    },
    'delivery.channel_attempted': {
      label: 'Channel Attempt',
      className: 'tag-delivery-info bg-blue-100 text-blue-800 border-blue-200',
    },
    'delivery.succeeded': {
      label: 'Delivered',
      className: 'tag-delivery-ok bg-green-100 text-green-800 border-green-200',
    },
    'delivery.failed': {
      label: 'Failed',
      className: 'tag-delivery-fail bg-red-100 text-red-800 border-red-200',
    },
    'delivery.deduplicated': {
      label: 'Deduplicated',
      className: 'tag-delivery-info bg-yellow-100 text-yellow-800 border-yellow-200',
    },
    'delivery.rate_limited': {
      label: 'Rate Limited',
      className: 'tag-delivery-info bg-yellow-100 text-yellow-800 border-yellow-200',
    },
    'ack.pending': {
      label: 'Ack Pending',
      className: 'tag-response-none bg-blue-100 text-blue-800 border-blue-200',
    },
    'ack.received': {
      label: 'Acknowledged',
      className: 'tag-response-ok bg-green-100 text-green-800 border-green-200',
    },
    'ack.dismissed': {
      label: 'Dismissed',
      className: 'tag-response-warn bg-yellow-100 text-yellow-800 border-yellow-200',
    },
    'ack.timed_out': {
      label: 'Ack Timeout',
      className: 'tag-response-fail bg-red-100 text-red-800 border-red-200',
    },
    'escalation.triggered': {
      label: 'Escalated',
      className: 'tag-response-fail bg-red-100 text-red-800 border-red-200',
    },
  };

  return (
    config[eventType] ?? {
      label: eventType,
      className: 'badge-default bg-gray-100 text-gray-800 border-gray-200',
    }
  );
}

/**
 * Get styling for autonomy mode badge.
 */
function getAutonomyModeBadgeStyles(mode: string): string {
  const styles: Record<string, string> = {
    PREVIEW: 'mode-preview bg-purple-100 text-purple-800',
    SHADOW: 'mode-shadow bg-indigo-100 text-indigo-800',
    LIVE: 'mode-live bg-green-100 text-green-800',
  };

  return styles[mode] ?? 'tag-mode bg-gray-100 text-gray-800';
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
      className="modernist-audit-card bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow"
      data-testid="audit-event-card"
    >
      {/* Column 1: Event Type & Mode Badges */}
      <div className="modernist-audit-cell">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          <span
            className={`badge ${badge.className}`}
            data-testid="event-type-badge"
          >
            {badge.label}
          </span>
          <span
            className={`mode-badge ${modeBadgeStyles}`}
            data-testid="autonomy-mode"
          >
            {event.autonomy_context.autonomy_mode}
          </span>
        </div>
        <div
          style={{
            marginTop: '6px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--color-neutral-600)',
          }}
        >
          {event.event_type}
        </div>
      </div>

      {/* Column 2: Timestamp */}
      <div className="modernist-audit-cell">
        <span className="timestamp" data-testid="event-time">
          {formatDateTime(event.event_time)}
        </span>
      </div>

      {/* Column 3: Notification Type & ID */}
      <div className="modernist-audit-cell">
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            fontSize: '13px',
            color: 'var(--color-text)',
          }}
          data-testid="notification-type"
        >
          {event.notification_type}
        </div>
        <div style={{ marginTop: '4px', fontSize: '12px' }}>
          <span style={{ color: 'var(--color-neutral-700)', marginRight: '6px' }}>
            Notification:
          </span>
          <code className="monospace" style={{ fontSize: '11px' }} data-testid="notification-id">
            {event.notification_id}
          </code>
        </div>
      </div>

      {/* Column 4: Agent & Correlation ID */}
      <div className="modernist-audit-cell">
        <div style={{ fontSize: '12px' }}>
          <span style={{ color: 'var(--color-neutral-700)', marginRight: '6px' }}>Agent:</span>
          <code className="monospace" style={{ fontSize: '11px' }} data-testid="agent-id">
            {event.autonomy_context.agent_id}
          </code>
        </div>
        {event.correlation_id && (
          <div style={{ marginTop: '4px', fontSize: '12px' }}>
            <span style={{ color: 'var(--color-neutral-700)', marginRight: '6px' }}>
              Correlation:
            </span>
            <code className="monospace" style={{ fontSize: '11px' }} data-testid="correlation-id">
              {event.correlation_id}
            </code>
          </div>
        )}
      </div>

      {/* Column 5: Collapsible Payload */}
      <div className="modernist-audit-cell">
        {Object.keys(event.payload).length > 0 ? (
          <details>
            <summary
              style={{
                cursor: 'pointer',
                fontFamily: 'var(--font-heading)',
                fontWeight: 800,
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              Payload
            </summary>
            <pre
              style={{
                marginTop: '8px',
                padding: '10px',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-divider)',
                fontSize: '11px',
                overflowX: 'auto',
              }}
              data-testid="event-payload"
            >
              {formatPayload(event.payload)}
            </pre>
          </details>
        ) : (
          <span className="monospace" style={{ fontSize: '11px', color: 'var(--color-neutral-500)' }}>
            —
          </span>
        )}
      </div>
    </div>
  );
}

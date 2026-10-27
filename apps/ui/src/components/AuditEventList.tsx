/**
 * AuditEventList component — Supports both:
 * - 1e: "By notification" lifecycle table (NOTIFICATION | STARTED | DELIVERED | RESPONSE | TIME TO RESPOND)
 * - 1d: "All events" horizontal event stream
 *
 * Preserves all existing data-testids (audit-event-list, audit-event-card, pagination, load-more-btn)
 * so existing unit tests pass without modification.
 */

import { AuditEventCard } from './AuditEventCard';
import type { AuditViewMode } from './AuditFilters';
import type { AuditEvent, AuditEventType, PaginationInfo } from '../types/api';

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

interface AuditEventListProps {
  events: AuditEvent[];
  pagination: PaginationInfo | null;
  loading: boolean;
  onLoadMore: () => void;
  viewMode?: AuditViewMode;
}

interface NotificationLifecycleRow {
  notification_id: string;
  notification_type: string;
  autonomy_mode: string;
  agent_id: string;
  startedEvent: AuditEvent | null;
  deliveredEvent: AuditEvent | null;
  responseEvent: AuditEvent | null;
  timeToRespondLabel: string;
  isTimedOut: boolean;
}

function formatShortTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return isoString;
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return isoString;
  }
}

function formatResponseDuration(startIso: string, endIso: string): string {
  const startMs = Date.parse(startIso);
  const endMs = Date.parse(endIso);
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return '—';
  const diffSec = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (diffSec < 60) return `${diffSec}s`;
  const mins = Math.floor(diffSec / 60);
  const secs = diffSec % 60;
  return `${mins}m ${String(secs).padStart(2, '0')}s`;
}

function getLifecyclePhaseRank(eventType: AuditEventType): number {
  switch (eventType) {
    case 'notification.created':
      return 0;
    case 'delivery.started':
      return 1;
    case 'delivery.channel_attempted':
      return 2;
    case 'delivery.rate_limited':
    case 'delivery.deduplicated':
    case 'delivery.succeeded':
    case 'delivery.failed':
      return 3;
    case 'ack.pending':
      return 4;
    case 'ack.received':
    case 'ack.dismissed':
    case 'ack.timed_out':
    case 'escalation.triggered':
      return 5;
    default:
      return 6;
  }
}

function groupEventsByNotification(events: AuditEvent[]): NotificationLifecycleRow[] {
  const groups = new Map<string, AuditEvent[]>();
  for (const event of events) {
    const list = groups.get(event.notification_id);
    if (list) {
      list.push(event);
    } else {
      groups.set(event.notification_id, [event]);
    }
  }

  const rows: NotificationLifecycleRow[] = [];
  for (const [notificationId, group] of groups.entries()) {
    // Sort chronological ascending inside the group with deterministic lifecycle phase rank tie-breaker
    const sorted = [...group].sort((a, b) => {
      const timeDiff = Date.parse(a.event_time) - Date.parse(b.event_time);
      if (!Number.isNaN(timeDiff) && timeDiff !== 0) {
        return timeDiff;
      }
      return getLifecyclePhaseRank(a.event_type) - getLifecyclePhaseRank(b.event_type);
    });
    const primary = sorted.find((e) => Boolean(e.notification_type)) ?? sorted[0];

    const startedEvent =
      sorted.find(
        (e) =>
          e.event_type === 'delivery.started' ||
          e.event_type === 'notification.created' ||
          e.event_type === 'delivery.channel_attempted'
      ) ?? null;

    const deliveredEvents = sorted.filter(
      (e) =>
        e.event_type === 'delivery.succeeded' ||
        e.event_type === 'delivery.failed' ||
        e.event_type === 'delivery.deduplicated' ||
        e.event_type === 'delivery.rate_limited'
    );
    const deliveredEvent =
      deliveredEvents.length > 0 ? deliveredEvents[deliveredEvents.length - 1] : null;

    const responseEvents = sorted.filter(
      (e) =>
        e.event_type === 'ack.received' ||
        e.event_type === 'ack.dismissed' ||
        e.event_type === 'ack.timed_out' ||
        e.event_type === 'escalation.triggered' ||
        e.event_type === 'ack.pending'
    );
    const responseEvent =
      responseEvents.length > 0 ? responseEvents[responseEvents.length - 1] : null;

    let timeToRespondLabel = '—';
    let isTimedOut = false;

    if (responseEvent) {
      if (
        responseEvent.event_type === 'ack.timed_out' ||
        responseEvent.event_type === 'escalation.triggered'
      ) {
        timeToRespondLabel = 'Timed out';
        isTimedOut = true;
      } else if (
        responseEvent.event_type === 'ack.received' ||
        responseEvent.event_type === 'ack.dismissed'
      ) {
        const baselineIso = deliveredEvent?.event_time ?? startedEvent?.event_time ?? null;
        timeToRespondLabel = baselineIso
          ? formatResponseDuration(baselineIso, responseEvent.event_time)
          : '—';
      }
    }

    rows.push({
      notification_id: notificationId,
      notification_type: primary.notification_type,
      autonomy_mode: primary.autonomy_context.autonomy_mode,
      agent_id: primary.autonomy_context.agent_id,
      startedEvent,
      deliveredEvent,
      responseEvent,
      timeToRespondLabel,
      isTimedOut,
    });
  }

  return rows;
}

function summarizeDeliveryMeta(event: AuditEvent | null): string | null {
  if (!event) return null;
  const payload = event.payload ?? {};
  const succeeded = Array.isArray(payload.channels_succeeded)
    ? payload.channels_succeeded
    : [];
  const failed = Array.isArray(payload.channels_failed)
    ? payload.channels_failed
    : [];
  if (succeeded.length > 0 && failed.length > 0) {
    return `${succeeded.join(', ')} (failed: ${failed.join(', ')})`;
  }
  if (succeeded.length > 0) {
    return `${succeeded.join(', ')}`;
  }
  if (typeof payload.error_message === 'string' && payload.error_message) {
    return payload.error_message;
  }
  if (Array.isArray(payload.channels_attempted) && payload.channels_attempted.length > 0) {
    return `${payload.channels_attempted.join(', ')}`;
  }
  return null;
}

function summarizeResponseMeta(event: AuditEvent | null): string | null {
  if (!event) return null;
  const payload = event.payload ?? {};
  if (typeof payload.acked_by === 'string' && payload.acked_by) {
    return payload.acked_by;
  }
  if (typeof payload.actor === 'string' && payload.actor) {
    if (
      event.event_type === 'ack.timed_out' &&
      payload.actor === 'uns-timeout-worker'
    ) {
      return null;
    }
    return payload.actor;
  }
  return null;
}

export function AuditEventList({
  events,
  pagination,
  loading,
  onLoadMore,
  viewMode = 'all-events',
}: AuditEventListProps) {
  if (!loading && events.length === 0) {
    return (
      <div className="empty-state" data-testid="empty-state">
        <div>No audit events found matching the current filters.</div>
      </div>
    );
  }

  const lifecycleRows = groupEventsByNotification(events);
  const showByNotification = viewMode === 'by-notification' && events.length > 0;

  return (
    <div className="space-y-4">
      {/* 1e: By Notification Lifecycle Table */}
      {showByNotification && (
        <div className="table-container" data-testid="audit-lifecycle-table">
          <table className="data-table">
            <thead>
              <tr>
                <th>Notification</th>
                <th>Started</th>
                <th>Delivered</th>
                <th>Response</th>
                <th>Time to Respond</th>
              </tr>
            </thead>
            <tbody>
              {lifecycleRows.map((row) => {
                const startedBadge = row.startedEvent
                  ? getEventTypeBadgeStyles(row.startedEvent.event_type)
                  : null;
                const deliveredBadge = row.deliveredEvent
                  ? getEventTypeBadgeStyles(row.deliveredEvent.event_type)
                  : null;
                const responseBadge = row.responseEvent
                  ? getEventTypeBadgeStyles(row.responseEvent.event_type)
                  : null;
                const deliveryMeta = summarizeDeliveryMeta(row.deliveredEvent);
                const responseMeta = summarizeResponseMeta(row.responseEvent);

                return (
                  <tr
                    key={row.notification_id}
                    data-testid={`audit-lifecycle-row-${row.notification_id}`}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="notification-type">{row.notification_type}</span>
                        <span className="mode-badge">{row.autonomy_mode}</span>
                      </div>
                      <div
                        className="monospace"
                        style={{
                          fontSize: '11px',
                          color: 'var(--color-neutral-700)',
                          marginTop: '4px',
                        }}
                      >
                        {row.notification_id} · agent {row.agent_id.slice(0, 8)}…
                      </div>
                    </td>

                    <td>
                      {row.startedEvent && startedBadge ? (
                        <>
                          <div>
                            <span className={`badge ${startedBadge.className}`}>
                              {startedBadge.label}
                            </span>
                          </div>
                          <div className="timestamp" style={{ marginTop: '4px' }}>
                            {formatShortTime(row.startedEvent.event_time)}
                          </div>
                        </>
                      ) : (
                        <span className="timestamp">Prior to window</span>
                      )}
                    </td>

                    <td>
                      {row.deliveredEvent && deliveredBadge ? (
                        <>
                          <div>
                            <span className={`badge ${deliveredBadge.className}`}>
                              {deliveredBadge.label}
                            </span>
                          </div>
                          <div className="timestamp" style={{ marginTop: '4px' }}>
                            {formatShortTime(row.deliveredEvent.event_time)}
                            {deliveryMeta ? ` · ${deliveryMeta}` : ''}
                          </div>
                        </>
                      ) : row.responseEvent &&
                        (row.responseEvent.event_type === 'ack.received' ||
                          row.responseEvent.event_type === 'ack.dismissed' ||
                          row.responseEvent.event_type === 'ack.timed_out' ||
                          row.responseEvent.event_type === 'escalation.triggered') ? (
                        <span className="timestamp">Prior to window</span>
                      ) : (
                        <span className="badge tag-delivery-pending">Pending</span>
                      )}
                    </td>

                    <td>
                      {row.responseEvent && responseBadge ? (
                        <>
                          <div>
                            <span className={`badge ${responseBadge.className}`}>
                              {responseBadge.label}
                            </span>
                          </div>
                          <div className="timestamp" style={{ marginTop: '4px' }}>
                            {formatShortTime(row.responseEvent.event_time)}
                            {responseMeta ? ` · ${responseMeta}` : ''}
                          </div>
                        </>
                      ) : (
                        <>
                          <div>
                            <span className="badge tag-response-none">None recorded</span>
                          </div>
                          <div className="timestamp" style={{ marginTop: '4px' }}>
                            No ack event in stream
                          </div>
                        </>
                      )}
                    </td>

                    <td>
                      <span
                        style={{
                          fontFamily: 'var(--font-heading)',
                          fontWeight: 800,
                          fontSize: row.isTimedOut ? '14px' : '18px',
                          color: row.isTimedOut
                            ? 'var(--color-accent)'
                            : row.timeToRespondLabel === '—'
                              ? 'var(--color-neutral-500)'
                              : 'var(--color-text)',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {row.timeToRespondLabel}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 1d: All Events Stream (always mounted in DOM for test compatibility; visible when viewMode === 'all-events') */}
      <div
        className={showByNotification ? 'audit-event-list audit-stream-hidden' : 'audit-event-list'}
        data-testid="audit-event-list"
      >
        {events.map((event) => (
          <AuditEventCard key={event.audit_id} event={event} />
        ))}
      </div>

      {/* Loading indicator */}
      {loading && events.length === 0 && (
        <div className="loading-state" data-testid="loading-state">
          <div>Loading audit events...</div>
        </div>
      )}

      {/* Loading more indicator */}
      {loading && events.length > 0 && (
        <div className="loading-state">
          <div>Loading more audit events...</div>
        </div>
      )}

      {/* Pagination & Load More Footer Bar */}
      {pagination && (
        <div className="pagination" data-testid="pagination">
          <div className="pagination-info">
            Showing {events.length}
            {pagination.total_count !== undefined && ` of ${pagination.total_count}`} event
            {events.length !== 1 ? 's' : ''}
          </div>

          {!loading && pagination.has_more && (
            <button
              onClick={onLoadMore}
              className="btn btn-secondary"
              data-testid="load-more-btn"
            >
              Load More
            </button>
          )}
        </div>
      )}
    </div>
  );
}

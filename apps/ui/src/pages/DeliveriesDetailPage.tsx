/**
 * DeliveriesDetailPage - displays the full delivery timeline for a notification.
 *
 * Features:
 * - Summary section with notification metadata
 * - Autonomy context section
 * - Channel results summary
 * - Delivery attempts table
 *
 * This page is READ-ONLY per ui-scope.md.
 */

import { Link, useParams } from 'react-router-dom';
import { useDeliveryTimeline } from '../hooks/useDeliveryTimeline';
import type { Channel, DeliveryAttempt, DeliveryStatus, NotificationIntent } from '../types/api';

function truncateUUID(uuid: string): string {
  return uuid.slice(0, 8) + '...';
}

function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '-';
  try {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
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

function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function getStatusBadgeClass(status: DeliveryStatus | string): string {
  switch (status) {
    case 'DELIVERED':
    case 'SUCCESS':
      return 'badge-success';
    case 'FAILED':
      return 'badge-error';
    case 'PENDING':
      return 'badge-warning';
    case 'DEDUPLICATED':
    case 'RATE_LIMITED':
    case 'SKIPPED':
      return 'badge-info';
    default:
      return 'badge-default';
  }
}

function getIntentBadgeClass(intent: NotificationIntent): string {
  switch (intent) {
    case 'SAFETY':
      return 'badge-error';
    case 'GOVERNANCE':
      return 'badge-warning';
    case 'OPERATIONAL':
      return 'badge-info';
    case 'INFORMATIONAL':
      return 'badge-default';
    default:
      return 'badge-default';
  }
}

function getModeClass(mode: string): string {
  switch (mode) {
    case 'PREVIEW':
      return 'mode-preview';
    case 'SHADOW':
      return 'mode-shadow';
    case 'LIVE':
      return 'mode-live';
    default:
      return '';
  }
}

interface ChannelTagProps {
  channel: Channel;
  variant?: 'default' | 'success' | 'failed';
}

function ChannelTag({ channel, variant = 'default' }: ChannelTagProps) {
  const className = variant === 'success'
    ? 'channel-tag channel-success'
    : variant === 'failed'
      ? 'channel-tag channel-failed'
      : 'channel-tag';
  return <span className={className}>{channel}</span>;
}

interface AttemptsTableProps {
  attempts: DeliveryAttempt[];
}

function AttemptsTable({ attempts }: AttemptsTableProps) {
  if (attempts.length === 0) {
    return (
      <div className="empty-state" data-testid="no-attempts">
        <p>No delivery attempts recorded.</p>
      </div>
    );
  }

  return (
    <div className="table-container" data-testid="attempts-table">
      <table className="data-table">
        <thead>
          <tr>
            <th>Attempt ID</th>
            <th>Channel</th>
            <th>Status</th>
            <th>Started</th>
            <th>Completed</th>
            <th>Duration</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map((attempt) => (
            <tr key={attempt.attempt_id} data-testid="attempt-row">
              <td className="monospace">{truncateUUID(attempt.attempt_id)}</td>
              <td>
                <ChannelTag channel={attempt.channel} />
              </td>
              <td>
                <span className={`badge ${getStatusBadgeClass(attempt.status)}`}>
                  {attempt.status}
                </span>
              </td>
              <td className="timestamp">{formatDateTime(attempt.started_at)}</td>
              <td className="timestamp">{formatDateTime(attempt.completed_at)}</td>
              <td>{formatDuration(attempt.duration_ms)}</td>
              <td className="error-cell">
                {attempt.error_message ? (
                  <div className="error-details">
                    {attempt.error_code && (
                      <span className="error-code">{attempt.error_code}</span>
                    )}
                    <span className="error-message">{attempt.error_message}</span>
                  </div>
                ) : (
                  '-'
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DeliveriesDetailPage() {
  const { notificationId } = useParams<{ notificationId: string }>();
  const { timeline, isLoading, error, refetch } = useDeliveryTimeline(notificationId);

  if (isLoading) {
    return (
      <div className="deliveries-detail-page" data-testid="deliveries-detail-page">
        <div className="loading-state" data-testid="loading-state">
          Loading delivery timeline...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="deliveries-detail-page" data-testid="deliveries-detail-page">
        <div className="error-state" data-testid="error-state">
          <p className="error-message">Failed to load delivery timeline: {error.message}</p>
          <button type="button" onClick={refetch} className="btn btn-secondary">
            Retry
          </button>
          <Link to="/deliveries" className="btn btn-secondary" style={{ marginLeft: '0.5rem' }}>
            Back to List
          </Link>
        </div>
      </div>
    );
  }

  if (!timeline) {
    return (
      <div className="deliveries-detail-page" data-testid="deliveries-detail-page">
        <div className="empty-state" data-testid="not-found">
          <p>Delivery timeline not found.</p>
          <Link to="/deliveries" className="btn btn-secondary">
            Back to List
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="deliveries-detail-page" data-testid="deliveries-detail-page">
      <header className="page-header">
        <nav className="breadcrumb" data-testid="breadcrumb">
          <Link to="/deliveries">Deliveries</Link> &raquo;
          <span>{notificationId}</span>
        </nav>
        <h1>Delivery Timeline</h1>
      </header>

      <div className="detail-grid">
        <section className="detail-section summary-section" data-testid="summary-section">
          <h2>Summary</h2>
          <dl className="detail-list">
            <div className="detail-item">
              <dt>Notification ID</dt>
              <dd className="monospace">{timeline.notification_id}</dd>
            </div>
            <div className="detail-item">
              <dt>Notification Type</dt>
              <dd>{timeline.notification_type}</dd>
            </div>
            <div className="detail-item">
              <dt>Intent</dt>
              <dd>
                <span className={`badge ${getIntentBadgeClass(timeline.intent)}`}>
                  {timeline.intent}
                </span>
              </dd>
            </div>
            <div className="detail-item">
              <dt>Status</dt>
              <dd>
                <span className={`badge ${getStatusBadgeClass(timeline.status)}`}>
                  {timeline.status}
                </span>
              </dd>
            </div>
            <div className="detail-item">
              <dt>Delivery Mode</dt>
              <dd>{timeline.delivery_mode}</dd>
            </div>
            <div className="detail-item">
              <dt>Created At</dt>
              <dd className="timestamp">{formatDateTime(timeline.created_at)}</dd>
            </div>
            <div className="detail-item">
              <dt>Delivered At</dt>
              <dd className="timestamp">{formatDateTime(timeline.delivered_at)}</dd>
            </div>
          </dl>
        </section>

        <section className="detail-section autonomy-section" data-testid="autonomy-section">
          <h2>Autonomy Context</h2>
          <dl className="detail-list">
            <div className="detail-item">
              <dt>Autonomy Mode</dt>
              <dd>
                <span className={`mode-badge ${getModeClass(timeline.autonomy_context.autonomy_mode)}`}>
                  {timeline.autonomy_context.autonomy_mode}
                </span>
              </dd>
            </div>
            <div className="detail-item">
              <dt>Agent ID</dt>
              <dd className="monospace">{timeline.autonomy_context.agent_id}</dd>
            </div>
            {timeline.autonomy_context.plan_id && (
              <div className="detail-item">
                <dt>Plan ID</dt>
                <dd className="monospace">{timeline.autonomy_context.plan_id}</dd>
              </div>
            )}
            {timeline.autonomy_context.decision_snapshot_id && (
              <div className="detail-item">
                <dt>Decision Snapshot ID</dt>
                <dd className="monospace">{timeline.autonomy_context.decision_snapshot_id}</dd>
              </div>
            )}
            {timeline.autonomy_context.execution_snapshot_id && (
              <div className="detail-item">
                <dt>Execution Snapshot ID</dt>
                <dd className="monospace">{timeline.autonomy_context.execution_snapshot_id}</dd>
              </div>
            )}
            {timeline.autonomy_context.skip_snapshot_id && (
              <div className="detail-item">
                <dt>Skip Snapshot ID</dt>
                <dd className="monospace">{timeline.autonomy_context.skip_snapshot_id}</dd>
              </div>
            )}
          </dl>
        </section>

        <section className="detail-section channels-section" data-testid="channels-section">
          <h2>Channel Results</h2>
          <div className="channel-summary">
            <div className="channel-group">
              <h3>Attempted</h3>
              <div className="channel-tags">
                {timeline.channels_attempted.length > 0 ? (
                  timeline.channels_attempted.map((ch) => (
                    <ChannelTag key={ch} channel={ch} />
                  ))
                ) : (
                  <span className="empty-state-inline">None</span>
                )}
              </div>
            </div>
            <div className="channel-group">
              <h3>Succeeded</h3>
              <div className="channel-tags">
                {timeline.channels_succeeded.length > 0 ? (
                  timeline.channels_succeeded.map((ch) => (
                    <ChannelTag key={ch} channel={ch} variant="success" />
                  ))
                ) : (
                  <span className="empty-state-inline">None</span>
                )}
              </div>
            </div>
            <div className="channel-group">
              <h3>Failed</h3>
              <div className="channel-tags">
                {timeline.channels_failed.length > 0 ? (
                  timeline.channels_failed.map((ch) => (
                    <ChannelTag key={ch} channel={ch} variant="failed" />
                  ))
                ) : (
                  <span className="empty-state-inline">None</span>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="detail-section attempts-section" data-testid="attempts-section">
        <h2>Delivery Attempts</h2>
        <AttemptsTable attempts={timeline.attempts} />
      </section>

      <div className="page-actions">
        <Link to="/deliveries" className="btn btn-secondary" data-testid="back-to-list">
          Back to List
        </Link>
      </div>
    </div>
  );
}

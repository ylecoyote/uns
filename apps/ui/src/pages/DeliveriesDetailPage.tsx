/**
 * DeliveriesDetailPage - displays the full delivery timeline, obligation lineage,
 * bounded runtime events, and capability-gated responder actions for a notification.
 */

import { useState, useSyncExternalStore } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  acknowledgeNotification,
  ApiError,
  dismissNotification,
  replayNotification,
  resolveDlqEntry,
} from '../api';
import { getConsoleSession, hasScope, subscribeConsoleSession } from '../auth/session';
import { useDeliveryTimeline } from '../hooks/useDeliveryTimeline';
import type {
  Channel,
  DeliveryAttempt,
  DeliveryStatus,
  NotificationIntent,
  RuntimeEvent,
} from '../types/api';

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

function formatEpochSeconds(epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined) return '-';
  try {
    return new Date(epochSeconds * 1000).toLocaleString();
  } catch {
    return String(epochSeconds);
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
    case 'RESOLVED':
      return 'badge-success';
    case 'FAILED':
    case 'UNRESOLVED':
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
  const className =
    variant === 'success'
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

function formatRuntimeEventSummary(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof payload.actor === 'string') parts.push(`actor=${payload.actor}`);
  if (typeof payload.channel === 'string') parts.push(`channel=${payload.channel}`);
  if (typeof payload.cycle === 'number') parts.push(`cycle=${payload.cycle}`);
  if (typeof payload.attempt === 'number') parts.push(`attempt=${payload.attempt}`);
  if (typeof payload.owner_id === 'string') parts.push(`owner=${truncateUUID(payload.owner_id)}`);
  if (typeof payload.successor_id === 'string') parts.push(`successor=${truncateUUID(payload.successor_id)}`);
  if (typeof payload.error === 'string' && payload.error) parts.push(`error=${payload.error}`);
  if (
    typeof payload.metadata === 'object' &&
    payload.metadata !== null &&
    'note' in payload.metadata &&
    typeof (payload.metadata as { note: unknown }).note === 'string'
  ) {
    parts.push(`note="${(payload.metadata as { note: string }).note}"`);
  }
  return parts.length > 0 ? parts.join(' · ') : '-';
}

function RuntimeEventsTable({
  events,
  totalCount,
  truncated,
}: {
  events: RuntimeEvent[];
  totalCount?: number;
  truncated?: boolean;
}) {
  return (
    <section className="detail-section runtime-events-section" data-testid="runtime-events-section">
      <h2>Runtime Obligation Events</h2>
      {truncated && (
        <p className="events-truncated-notice" data-testid="events-truncated-notice">
          Showing most recent 100 of {totalCount ?? events.length} runtime events.
        </p>
      )}
      <div className="table-container" data-testid="runtime-events-table">
        <table className="data-table">
          <thead>
            <tr>
              <th>Event ID</th>
              <th>Kind</th>
              <th>Observed At</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {events.map((evt) => (
              <tr key={evt.id} data-testid="runtime-event-row">
                <td className="monospace">{truncateUUID(evt.id)}</td>
                <td>
                  <span className="badge badge-default">{evt.kind}</span>
                </td>
                <td className="timestamp">{formatEpochSeconds(evt.at)}</td>
                <td>{formatRuntimeEventSummary(evt.payload ?? {})}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function DeliveriesDetailPage() {
  const { notificationId } = useParams<{ notificationId: string }>();
  const session = useSyncExternalStore(subscribeConsoleSession, getConsoleSession);
  const { timeline, isLoading, error, refetch } = useDeliveryTimeline(notificationId);

  const [responderNote, setResponderNote] = useState('');
  const [confirmingDecision, setConfirmingDecision] = useState<'ack' | 'dismiss' | null>(null);
  const [submittingDecision, setSubmittingDecision] = useState(false);
  const [confirmingRecovery, setConfirmingRecovery] = useState<'replay' | 'resolve' | null>(null);
  const [submittingRecovery, setSubmittingRecovery] = useState(false);
  const [actionFeedback, setActionFeedback] = useState<{
    kind: 'success' | 'info' | 'error';
    message: string;
  } | null>(null);

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

  const runtimeState = timeline.runtime_state;
  const ownerId = runtimeState?.obligation_owner_id ?? null;
  const isDeduplicatedFollower = Boolean(
    ownerId && ownerId !== timeline.notification_id
  );
  const canRespond = hasScope(session, 'responder');
  const isAdmin = hasScope(session, 'admin');
  const canActOnCanonicalPending =
    canRespond && !isDeduplicatedFollower && runtimeState?.ack_status === 'PENDING';
  const canRecoverDeadLetter = isAdmin && runtimeState?.dead_letter === true;

  async function submitRecoveryAction(action: 'replay' | 'resolve') {
    if (!notificationId || submittingRecovery) return;
    setSubmittingRecovery(true);
    setActionFeedback(null);

    try {
      if (action === 'replay') {
        const res = await replayNotification(notificationId);
        setConfirmingRecovery(null);
        setActionFeedback({
          kind: 'success',
          message: `Replayed exhausted delivery (${res.status}). Recovery cycle started.`,
        });
      } else {
        await resolveDlqEntry(notificationId);
        setConfirmingRecovery(null);
        setActionFeedback({
          kind: 'success',
          message: 'Exhausted delivery failure resolved and retired.',
        });
      }
      refetch();
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 409) {
        setConfirmingRecovery(null);
        setActionFeedback({
          kind: 'info',
          message: `Concurrent update detected: ${err.message}. Timeline refreshed with current state.`,
        });
        refetch();
      } else {
        const message = err instanceof Error ? err.message : 'Unable to execute recovery action.';
        setActionFeedback({ kind: 'error', message });
      }
    } finally {
      setSubmittingRecovery(false);
    }
  }

  async function submitDecision(decision: 'ack' | 'dismiss') {
    if (!notificationId || submittingDecision) return;
    setSubmittingDecision(true);
    setActionFeedback(null);
    const trimmedNote = responderNote.trim();
    const metadata = trimmedNote ? { note: trimmedNote } : undefined;

    try {
      const response =
        decision === 'ack'
          ? await acknowledgeNotification(notificationId, { metadata })
          : await dismissNotification(notificationId, { metadata });
      setConfirmingDecision(null);
      setResponderNote('');
      setActionFeedback({
        kind: 'success',
        message:
          decision === 'ack'
            ? `Notification acknowledged (${response.ack_status}).`
            : `Notification dismissed (${response.ack_status}).`,
      });
      refetch();
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 409) {
        setConfirmingDecision(null);
        setActionFeedback({
          kind: 'info',
          message: `Concurrent update detected: ${err.message}. Timeline refreshed with current state.`,
        });
        refetch();
      } else {
        const message = err instanceof Error ? err.message : 'Unable to record response.';
        setActionFeedback({ kind: 'error', message });
      }
    } finally {
      setSubmittingDecision(false);
    }
  }

  return (
    <div className="deliveries-detail-page" data-testid="deliveries-detail-page">
      <header className="page-header">
        <nav className="breadcrumb" data-testid="breadcrumb">
          <Link to="/deliveries">Deliveries</Link> &raquo;
          <span>{notificationId}</span>
        </nav>
        <div>
          <h1>Delivery Timeline</h1>
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '16px',
            flexWrap: 'wrap',
          }}
        >
          <p className="page-description">
            Inspect delivery attempts, runtime obligation lineage, and human response state.
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refetch}
            data-testid="refresh-timeline-btn"
          >
            Refresh Timeline
          </button>
        </div>
      </header>

      {isDeduplicatedFollower && ownerId && (
        <section
          className="card"
          data-testid="deduplicated-follower-banner"
          style={{
            borderBottom: '2px solid var(--color-divider)',
            borderLeft: '4px solid var(--color-accent)',
            background: 'var(--color-surface)',
          }}
        >
          <p style={{ margin: '0 0 8px' }}>
            <strong>Deduplicated Follower Obligation.</strong> This notification is governed by canonical owner{' '}
            <Link to={`/deliveries/${ownerId}`} className="monospace" data-testid="canonical-owner-link">
              {ownerId}
            </Link>
            {runtimeState?.effective_ack_status
              ? ` (Effective response: ${runtimeState.effective_ack_status})`
              : ''}
            .
          </p>
          {canRespond && runtimeState?.effective_ack_status === 'PENDING' && (
            <Link
              to={`/deliveries/${ownerId}`}
              className="btn btn-primary"
              data-testid="canonical-owner-ack-cta"
            >
              View &amp; Acknowledge Canonical Owner ({truncateUUID(ownerId)})
            </Link>
          )}
        </section>
      )}

      {runtimeState && (
        <section
          aria-labelledby="runtime-state-heading"
          className="card"
          style={{
            borderBottom: '2px solid var(--color-divider)',
            background: 'var(--color-surface)',
          }}
        >
          <h2 id="runtime-state-heading" style={{ marginTop: 0, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Delivery and human response
          </h2>
          <dl className="detail-list">
            <div className="detail-item">
              <dt>Delivery</dt>
              <dd>
                <span className={`badge ${getStatusBadgeClass(runtimeState.delivery_status)}`}>
                  {runtimeState.delivery_status}
                </span>
              </dd>
            </div>
            <div className="detail-item">
              <dt>Human response</dt>
              <dd>
                <span
                  className={`badge ${
                    runtimeState.ack_status === 'ACKED'
                      ? 'tag-response-ok'
                      : runtimeState.ack_status === 'DISMISSED'
                        ? 'tag-response-warn'
                        : runtimeState.ack_status === 'TIMED_OUT' ||
                            runtimeState.ack_status === 'ESCALATED'
                          ? 'tag-response-fail'
                          : 'tag-response-none'
                  }`}
                >
                  {runtimeState.ack_status ?? 'No response deadline started'}
                </span>
              </dd>
            </div>
            {runtimeState.ack_inherited && runtimeState.effective_ack_status && (
              <div className="detail-item">
                <dt>Inherited response</dt>
                <dd data-testid="inherited-ack-status">
                  <span className="badge tag-response-ok">{runtimeState.effective_ack_status}</span>
                </dd>
              </div>
            )}
            <div className="detail-item">
              <dt>Response deadline</dt>
              <dd className="timestamp">
                {runtimeState.deadline
                  ? new Date(runtimeState.deadline * 1000).toLocaleString()
                  : 'Not started'}
              </dd>
            </div>
            <div className="detail-item">
              <dt>Recovery</dt>
              <dd>
                {runtimeState.dead_letter
                  ? 'Delivery exhausted. Operator review required.'
                  : 'No exhausted delivery'}
              </dd>
            </div>
            {runtimeState.obligation_resolution_status && (
              <div className="detail-item">
                <dt>Obligation resolution</dt>
                <dd data-testid="obligation-resolution-status">
                  {runtimeState.obligation_resolution_status}
                  {runtimeState.obligation_resolution_error
                    ? ` (${runtimeState.obligation_resolution_error})`
                    : ''}
                </dd>
              </div>
            )}
            {ownerId && (
              <div className="detail-item">
                <dt>Obligation owner</dt>
                <dd className="monospace" data-testid="obligation-owner-id">
                  {isDeduplicatedFollower ? (
                    <Link to={`/deliveries/${ownerId}`}>{ownerId}</Link>
                  ) : (
                    ownerId
                  )}
                </dd>
              </div>
            )}
            {runtimeState.actor && (
              <div className="detail-item">
                <dt>Responded by</dt>
                <dd className="monospace" data-testid="responded-by-actor">
                  {runtimeState.actor}
                </dd>
              </div>
            )}
            {typeof runtimeState.response_metadata?.note === 'string' && (
              <div className="detail-item">
                <dt>Responder note</dt>
                <dd data-testid="responder-note-display">{runtimeState.response_metadata.note}</dd>
              </div>
            )}
            <div className="detail-item">
              <dt>Policy configuration</dt>
              <dd className="monospace" style={{ overflowWrap: 'anywhere' }}>
                {runtimeState.policy_config_hash}
              </dd>
            </div>
            <div className="detail-item">
              <dt>Evaluation</dt>
              <dd className="monospace">{runtimeState.policy_evaluation_id}</dd>
            </div>
          </dl>

          {actionFeedback && (
            <div
              role="status"
              data-testid={
                actionFeedback.kind === 'info'
                  ? 'conflict-recovered-banner'
                  : 'responder-action-feedback'
              }
              style={{
                marginTop: '12px',
                padding: '10px 14px',
                border:
                  actionFeedback.kind === 'error'
                    ? '1.5px solid var(--color-accent)'
                    : '1.5px solid var(--color-text)',
                backgroundColor:
                  actionFeedback.kind === 'error'
                    ? 'var(--color-accent-100)'
                    : 'var(--color-bg)',
              }}
            >
              {actionFeedback.message}
            </div>
          )}

          {canActOnCanonicalPending && (
            <div
              className="responder-action-bar"
              data-testid="responder-action-bar"
              style={{
                marginTop: '16px',
                paddingTop: '16px',
                borderTop: '2px solid var(--color-divider)',
              }}
            >
              <h3 style={{ marginTop: 0, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Record Human Response
              </h3>
              <div style={{ marginBottom: '12px' }}>
                <label
                  htmlFor="responder-note"
                  className="field-label"
                  style={{ display: 'block', marginBottom: '6px' }}
                >
                  Responder Note (optional)
                </label>
                <input
                  id="responder-note"
                  type="text"
                  className="modernist-input"
                  maxLength={500}
                  value={responderNote}
                  disabled={submittingDecision}
                  onChange={(e) => setResponderNote(e.target.value)}
                  placeholder="Context or remediation note (recorded in audit metadata)"
                  data-testid="responder-note-input"
                  style={{ maxWidth: '32rem' }}
                />
              </div>

              {confirmingDecision === null ? (
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => setConfirmingDecision('ack')}
                    disabled={submittingDecision}
                    data-testid="ack-btn"
                  >
                    Acknowledge
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setConfirmingDecision('dismiss')}
                    disabled={submittingDecision}
                    data-testid="dismiss-btn"
                  >
                    Dismiss
                  </button>
                </div>
              ) : (
                <div
                  data-testid="inline-response-confirmation"
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}
                >
                  <span>
                    Confirm <strong>{confirmingDecision === 'ack' ? 'Acknowledge' : 'Dismiss'}</strong> as{' '}
                    <code>{session.subject ?? 'authenticated responder'}</code>?
                  </span>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => submitDecision(confirmingDecision)}
                    disabled={submittingDecision}
                    data-testid="confirm-response-btn"
                  >
                    {submittingDecision
                      ? 'Recording…'
                      : confirmingDecision === 'ack'
                        ? 'Confirm Acknowledge'
                        : 'Confirm Dismiss'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setConfirmingDecision(null)}
                    disabled={submittingDecision}
                    data-testid="cancel-response-btn"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}

          {canRecoverDeadLetter && (
            <div
              className="operator-recovery-bar"
              data-testid="operator-recovery-bar"
              style={{
                marginTop: '16px',
                paddingTop: '16px',
                borderTop: '2px solid var(--color-divider)',
              }}
            >
              <h3 style={{ marginTop: 0, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Operator Dead-Letter Recovery
              </h3>
              {confirmingRecovery === null ? (
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => setConfirmingRecovery('replay')}
                    disabled={submittingRecovery}
                    data-testid="detail-replay-btn"
                  >
                    Replay Exhausted Delivery
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setConfirmingRecovery('resolve')}
                    disabled={submittingRecovery}
                    data-testid="detail-resolve-btn"
                  >
                    Resolve Failure
                  </button>
                </div>
              ) : (
                <div
                  data-testid="inline-recovery-confirmation"
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}
                >
                  <span>
                    {confirmingRecovery === 'replay'
                      ? 'Start a new recovery cycle under accepted policy snapshot?'
                      : 'Retire this dead-letter failure without re-sending?'}
                  </span>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void submitRecoveryAction(confirmingRecovery)}
                    disabled={submittingRecovery}
                    data-testid="confirm-recovery-btn"
                  >
                    {submittingRecovery
                      ? 'Working…'
                      : confirmingRecovery === 'replay'
                        ? 'Confirm Replay'
                        : 'Confirm Resolve'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setConfirmingRecovery(null)}
                    disabled={submittingRecovery}
                    data-testid="cancel-recovery-btn"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

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
              <dd>
                <Link
                  to={`/policy?notification_type=${encodeURIComponent(timeline.notification_type)}`}
                  data-testid="policy-deep-link"
                >
                  {timeline.notification_type}
                </Link>
              </dd>
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

      {runtimeState?.events && runtimeState.events.length > 0 && (
        <RuntimeEventsTable
          events={runtimeState.events}
          totalCount={runtimeState.events_total_count}
          truncated={runtimeState.events_truncated}
        />
      )}

      <div className="page-actions">
        <Link to="/deliveries" className="btn btn-secondary" data-testid="back-to-list">
          Back to List
        </Link>
      </div>
    </div>
  );
}

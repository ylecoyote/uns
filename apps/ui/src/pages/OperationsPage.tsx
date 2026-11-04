/**
 * OperationsPage - Operator Telemetry & Joined Dead-Letter Recovery (/operations).
 *
 * Surface 3 of the UNS Console Responder & Operator Workflows specification.
 * Coordinates fault-isolated polling across:
 * - GET /readyz (with HTTP 503 tolerance for degraded readiness inspection)
 * - GET /api/v1/channels/health
 * - GET /api/v1/dlq
 * - GET /api/v1/runtime/dead-letters
 */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  getChannelHealth,
  getDlqEntries,
  getReadyz,
  getRuntimeDeadLetters,
  replayNotification,
  resolveDlqEntry,
} from '../api';
import { getConsoleSession, hasScope, subscribeConsoleSession } from '../auth/session';
import type {
  ChannelHealthSummaryResponse,
  DLQEntryItem,
  ReadyzResponse,
  RuntimeDeadLetterItem,
} from '../types/api';

const POLL_INTERVAL_MS = 15_000;

interface JoinedDeadLetterRow {
  entry_id: string;
  notification_id: string;
  notification_type: string;
  intent: string;
  source: string;
  reason: string;
  created_at: string;
  attempts: number | null;
  cycle: number | null;
  cycle_attempts: number | null;
  outcome_summary: string | null;
  replay_blocked_by: string | null;
  replay_block_reason: string | null;
  is_legacy_dlq_entry: boolean;
}

interface ConfirmingOperatorAction {
  type: 'replay' | 'resolve';
  entryId: string;
  notificationId: string;
  purgeLegacyDlqEntry: boolean;
}

function truncateId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}...` : id;
}

function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const rem = Math.round(seconds % 60);
  return `${mins}m ${rem}s`;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function extractOutcomeSummary(
  runtimeItem: RuntimeDeadLetterItem | undefined,
  metadata: Record<string, unknown> | undefined
): string | null {
  const outcome =
    (runtimeItem?.outcome as Record<string, unknown> | undefined) ??
    (metadata?.outcome as Record<string, unknown> | undefined);
  if (!outcome) return null;
  if (typeof outcome.error_message === 'string' && outcome.error_message.trim()) {
    return outcome.error_message;
  }
  if (Array.isArray(outcome.channels_failed) && outcome.channels_failed.length > 0) {
    return `Failed channels: ${outcome.channels_failed.join(', ')}`;
  }
  return null;
}

function joinDeadLetters(
  dlqItems: DLQEntryItem[],
  runtimeDeadLetters: RuntimeDeadLetterItem[]
): JoinedDeadLetterRow[] {
  const runtimeByNotificationId = new Map<string, RuntimeDeadLetterItem>();
  for (const rt of runtimeDeadLetters) {
    runtimeByNotificationId.set(rt.notification_id, rt);
  }

  const matchedNotificationIds = new Set<string>();
  const rows: JoinedDeadLetterRow[] = dlqItems.map((entry) => {
    matchedNotificationIds.add(entry.notification_id);
    const rt = runtimeByNotificationId.get(entry.notification_id);
    const meta = entry.metadata ?? {};
    const attempts =
      rt?.attempts ?? (typeof meta.attempts === 'number' ? meta.attempts : null);
    const cycle = rt?.cycle ?? (typeof meta.cycle === 'number' ? meta.cycle : null);
    const cycleAttempts =
      rt?.cycle_attempts ??
      (typeof meta.cycle_attempts === 'number' ? meta.cycle_attempts : null);
    const replayBlockedBy =
      rt?.replay_blocked_by ??
      (typeof meta.replay_blocked_by === 'string' ? meta.replay_blocked_by : null);
    const replayBlockReason =
      rt?.replay_block_reason ??
      (typeof meta.replay_block_reason === 'string' ? meta.replay_block_reason : null);

    return {
      entry_id: entry.entry_id,
      notification_id: entry.notification_id,
      notification_type: entry.notification_type,
      intent: entry.intent,
      source: entry.source,
      reason: entry.reason,
      created_at: entry.created_at,
      attempts,
      cycle,
      cycle_attempts: cycleAttempts,
      outcome_summary: extractOutcomeSummary(rt, meta),
      replay_blocked_by: replayBlockedBy,
      replay_block_reason: replayBlockReason,
      is_legacy_dlq_entry: entry.entry_id !== entry.notification_id,
    };
  });

  for (const rt of runtimeDeadLetters) {
    if (matchedNotificationIds.has(rt.notification_id)) {
      continue;
    }
    matchedNotificationIds.add(rt.notification_id);
    const outcome = (rt.outcome ?? {}) as Record<string, unknown>;
    const rtRecord = rt as unknown as Record<string, unknown>;
    const notificationType =
      (typeof rtRecord.notification_type === 'string' && rtRecord.notification_type) ||
      (typeof outcome.notification_type === 'string' && outcome.notification_type) ||
      'runtime.dead_letter';
    const intent =
      (typeof rtRecord.intent === 'string' && rtRecord.intent) ||
      (typeof outcome.intent === 'string' && outcome.intent) ||
      'OPERATIONAL';
    const source =
      (typeof rtRecord.source === 'string' && rtRecord.source) ||
      (typeof outcome.source === 'string' && outcome.source) ||
      'runtime';
    const reason =
      (typeof rtRecord.reason === 'string' && rtRecord.reason) ||
      (typeof outcome.reason === 'string' && outcome.reason) ||
      'guaranteed_delivery_exhausted';
    const createdAt =
      (typeof rtRecord.created_at === 'string' && rtRecord.created_at) ||
      (typeof outcome.created_at === 'string' && outcome.created_at) ||
      '';

    rows.push({
      entry_id: rt.notification_id,
      notification_id: rt.notification_id,
      notification_type: notificationType,
      intent,
      source,
      reason,
      created_at: createdAt,
      attempts: rt.attempts ?? null,
      cycle: rt.cycle ?? null,
      cycle_attempts: rt.cycle_attempts ?? null,
      outcome_summary: extractOutcomeSummary(rt, outcome),
      replay_blocked_by: rt.replay_blocked_by ?? null,
      replay_block_reason: rt.replay_block_reason ?? null,
      is_legacy_dlq_entry: false,
    });
  }

  // Deterministic sort: created_at DESC, entry_id ASC
  rows.sort((a, b) => {
    const timeA = Date.parse(a.created_at);
    const timeB = Date.parse(b.created_at);
    if (!Number.isNaN(timeA) && !Number.isNaN(timeB) && timeA !== timeB) {
      return timeB - timeA;
    }
    if (a.created_at !== b.created_at) {
      return b.created_at.localeCompare(a.created_at);
    }
    return a.entry_id.localeCompare(b.entry_id);
  });

  return rows;
}

export function OperationsPage() {
  const session = useSyncExternalStore(subscribeConsoleSession, getConsoleSession);
  const isAdmin = hasScope(session, 'admin');

  const [readyzState, setReadyzState] = useState<{
    data: ReadyzResponse | null;
    statusCode: number | null;
    error: string | null;
  }>({ data: null, statusCode: null, error: null });

  const [channelHealthState, setChannelHealthState] = useState<{
    data: ChannelHealthSummaryResponse | null;
    error: string | null;
  }>({ data: null, error: null });

  const [dlqState, setDlqState] = useState<{
    rows: JoinedDeadLetterRow[];
    depth: number;
    error: string | null;
  }>({ rows: [], depth: 0, error: null });

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  // Keyed by entry_id outside the polled array so background refreshes never close confirmation
  const [confirmingAction, setConfirmingAction] = useState<ConfirmingOperatorAction | null>(
    null
  );
  const [submittingEntryId, setSubmittingEntryId] = useState<string | null>(null);
  const [operatorFeedback, setOperatorFeedback] = useState<{
    kind: 'success' | 'info' | 'error';
    message: string;
  } | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const autoRefreshRef = useRef(autoRefresh);
  const fetchSnapshotRef = useRef<(isInitial?: boolean) => Promise<void>>(() => Promise.resolve());

  useEffect(() => {
    autoRefreshRef.current = autoRefresh;
  }, [autoRefresh]);

  const fetchSnapshot = useCallback(async (isInitial = false) => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (isInitial) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    const [readyzRes, channelRes, dlqRes, runtimeDlqRes] = await Promise.allSettled([
      getReadyz(controller.signal),
      getChannelHealth(controller.signal),
      getDlqEntries(controller.signal),
      getRuntimeDeadLetters(controller.signal),
    ]);

    if (controller.signal.aborted) {
      return;
    }

    if (readyzRes.status === 'fulfilled') {
      setReadyzState({
        data: readyzRes.value.data,
        statusCode: readyzRes.value.statusCode,
        error: null,
      });
    } else {
      const err = readyzRes.reason;
      setReadyzState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Unable to fetch readiness telemetry',
      }));
    }

    if (channelRes.status === 'fulfilled') {
      setChannelHealthState({
        data: channelRes.value,
        error: null,
      });
    } else {
      const err = channelRes.reason;
      setChannelHealthState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Unable to fetch channel health',
      }));
    }

    const dlqErrors: string[] = [];
    if (dlqRes.status === 'rejected') {
      const err = dlqRes.reason;
      dlqErrors.push(
        err instanceof Error ? err.message : 'Unable to fetch dead-letter queue'
      );
    }
    if (runtimeDlqRes.status === 'rejected') {
      const err = runtimeDlqRes.reason;
      dlqErrors.push(
        err instanceof Error
          ? err.message
          : 'Unable to fetch runtime dead-letter eligibility'
      );
    }

    if (dlqRes.status === 'fulfilled' || runtimeDlqRes.status === 'fulfilled') {
      const dlqItems = dlqRes.status === 'fulfilled' ? (dlqRes.value.items ?? []) : [];
      const runtimeItems =
        runtimeDlqRes.status === 'fulfilled' ? runtimeDlqRes.value : [];
      const joined = joinDeadLetters(dlqItems, runtimeItems);
      const depth =
        dlqRes.status === 'fulfilled'
          ? Math.max(dlqRes.value.depth ?? joined.length, joined.length)
          : joined.length;
      setDlqState({
        rows: joined,
        depth,
        error: dlqErrors.length > 0 ? dlqErrors.join(' | ') : null,
      });
    } else {
      setDlqState((prev) => ({
        ...prev,
        error: dlqErrors.join(' | '),
      }));
    }

    setLastUpdated(new Date().toLocaleTimeString());
    setIsLoading(false);
    setIsRefreshing(false);

    if (mountedRef.current && autoRefreshRef.current) {
      pollTimeoutRef.current = setTimeout(() => {
        pollTimeoutRef.current = null;
        if (!mountedRef.current || !autoRefreshRef.current) return;
        if (typeof document === 'undefined' || document.visibilityState === 'visible') {
          void fetchSnapshotRef.current(false);
        }
      }, POLL_INTERVAL_MS);
    }
  }, []);

  useEffect(() => {
    fetchSnapshotRef.current = fetchSnapshot;
  }, [fetchSnapshot]);

  useEffect(() => {
    if (!autoRefresh || typeof document === 'undefined') return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && !pollTimeoutRef.current) {
        void fetchSnapshotRef.current(false);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [autoRefresh]);

  useEffect(() => {
    mountedRef.current = true;
    void fetchSnapshot(true);

    return () => {
      mountedRef.current = false;
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
      abortControllerRef.current?.abort();
    };
  }, [fetchSnapshot]);

  useEffect(() => {
    if (!autoRefresh && pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    } else if (autoRefresh && !pollTimeoutRef.current && !isLoading && !isRefreshing) {
      pollTimeoutRef.current = setTimeout(() => {
        pollTimeoutRef.current = null;
        if (!mountedRef.current || !autoRefreshRef.current) return;
        if (typeof document === 'undefined' || document.visibilityState === 'visible') {
          void fetchSnapshot(false);
        }
      }, POLL_INTERVAL_MS);
    }
  }, [autoRefresh, fetchSnapshot, isLoading, isRefreshing]);

  async function handleExecuteAction(action: ConfirmingOperatorAction) {
    if (submittingEntryId) return;
    setSubmittingEntryId(action.entryId);
    setOperatorFeedback(null);

    try {
      if (action.type === 'replay') {
        const res = await replayNotification(action.notificationId);
        if (action.purgeLegacyDlqEntry) {
          try {
            await resolveDlqEntry(action.entryId);
          } catch {
            // Best-effort cleanup of legacy non-runtime DLQ entry if applicable
          }
        }
        setConfirmingAction(null);
        setOperatorFeedback({
          kind: 'success',
          message: `Replayed notification ${action.notificationId} (${res.status}). Recovery cycle started.`,
        });
      } else {
        await resolveDlqEntry(action.entryId);
        setConfirmingAction(null);
        setOperatorFeedback({
          kind: 'success',
          message: `Resolved dead-letter entry ${action.entryId}. Failure retired.`,
        });
      }
      await fetchSnapshot(false);
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 409) {
        setConfirmingAction(null);
        setOperatorFeedback({
          kind: 'info',
          message: `Replay conflict detected: ${err.message}. Refreshed dead-letter queue state.`,
        });
        await fetchSnapshot(false);
      } else {
        setOperatorFeedback({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Operator action failed.',
        });
      }
    } finally {
      setSubmittingEntryId(null);
    }
  }

  const readyz = readyzState.data;
  const progress = readyz?.operational_progress;
  const isReadinessDegraded =
    readyzState.statusCode === 503 ||
    (readyz !== null && readyz.status !== 'ready') ||
    Boolean(readyzState.error);

  return (
    <div className="operations-page" data-testid="operations-page">
      <header className="page-header">
        <div>
          <h1>Operations &amp; Dead-Letter Recovery</h1>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'flex-start' }}>
          <p className="page-description">
            Live operational progress, channel health, and dead-letter queue recovery.
          </p>
          <div
            className="operations-refresh-bar"
            data-testid="operations-refresh-bar"
            style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}
          >
            {lastUpdated && (
              <span className="timestamp" data-testid="operations-last-updated">
                Last updated {lastUpdated}
              </span>
            )}
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                data-testid="auto-refresh-toggle"
              />
              <span>Auto-Refresh (15s)</span>
            </label>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void fetchSnapshot(false)}
              disabled={isRefreshing}
              data-testid="refresh-operations-btn"
            >
              {isRefreshing ? 'Refreshing…' : 'Refresh Now'}
            </button>
          </div>
        </div>
      </header>

      {isLoading && !readyz && !channelHealthState.data ? (
        <div className="loading-state" data-testid="operations-loading">
          Loading operational telemetry...
        </div>
      ) : (
        <>
          {/* Section 1: Operational Progress & Backlog Modular Grid */}
          <section
            data-testid="operational-progress-section"
            style={{ borderBottom: '2px solid var(--color-divider)', background: 'var(--color-bg)' }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '12px',
                flexWrap: 'wrap',
                padding: '14px 24px',
                background: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-divider)',
              }}
            >
              <h2 style={{ margin: 0, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Operational Progress &amp; Backlog
              </h2>
              {isReadinessDegraded ? (
                <span
                  className="badge tag-delivery-fail"
                  data-testid="readiness-degraded-badge"
                >
                  READINESS DEGRADED
                </span>
              ) : (
                <span className="badge tag-delivery-ok" data-testid="readiness-ready-badge">
                  READY
                </span>
              )}
            </div>

            {readyzState.error && (
              <div
                role="alert"
                data-testid="readyz-error-banner"
                style={{
                  padding: '12px 24px',
                  borderBottom: '1px solid var(--color-accent)',
                  backgroundColor: 'var(--color-accent-100)',
                  color: 'var(--color-accent-800)',
                }}
              >
                Readiness telemetry error: {readyzState.error}
              </div>
            )}

            {readyz?.error && (
              <div
                role="alert"
                data-testid="readyz-payload-error"
                style={{
                  padding: '12px 24px',
                  borderBottom: '1px solid var(--color-accent)',
                  backgroundColor: 'var(--color-accent-100)',
                  color: 'var(--color-accent-800)',
                }}
              >
                Readiness probe reported error: {readyz.error}
              </div>
            )}

            <div
              className="summary-cards"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              }}
            >
              <div
                style={{ padding: '18px 24px', borderRight: '1px solid var(--color-divider)' }}
                data-testid="metric-pending-count"
              >
                <div className="invariants-eyebrow">Pending Obligations</div>
                <div className="invariants-stat-value" style={{ marginTop: '8px', fontSize: '32px' }}>
                  {progress?.pending_count ?? 0}
                </div>
              </div>

              <div
                style={{ padding: '18px 24px', borderRight: '1px solid var(--color-divider)' }}
                data-testid="metric-oldest-pending-age"
              >
                <div className="invariants-eyebrow">Oldest Pending Age</div>
                <div className="invariants-stat-value" style={{ marginTop: '8px', fontSize: '32px' }}>
                  {formatSeconds(progress?.oldest_pending_age_seconds)}
                </div>
              </div>

              <div
                style={{ padding: '18px 24px', borderRight: '1px solid var(--color-divider)' }}
                data-testid="metric-due-lateness"
              >
                <div className="invariants-eyebrow">Oldest Due Attempt Lateness</div>
                <div className="invariants-stat-value" style={{ marginTop: '8px', fontSize: '32px' }}>
                  {formatSeconds(progress?.oldest_due_attempt_lateness_seconds)}
                </div>
              </div>

              <div
                style={{ padding: '18px 24px', borderRight: '1px solid var(--color-divider)' }}
                data-testid="metric-overdue-ack"
              >
                <div className="invariants-eyebrow">Overdue Acknowledgments</div>
                <div
                  className="invariants-stat-value"
                  style={{
                    marginTop: '8px',
                    fontSize: '32px',
                    color:
                      (progress?.overdue_ack_count ?? 0) > 0
                        ? 'var(--color-accent)'
                        : 'var(--color-text)',
                  }}
                >
                  {progress?.overdue_ack_count ?? 0}
                </div>
              </div>

              <div
                style={{ padding: '18px 24px', borderRight: '1px solid var(--color-divider)' }}
                data-testid="metric-unresolved-dlq"
              >
                <div className="invariants-eyebrow">Unresolved Dead-Letters</div>
                <div
                  className="invariants-stat-value"
                  style={{
                    marginTop: '8px',
                    fontSize: '32px',
                    color:
                      (progress?.unresolved_failure_count ?? readyz?.dlq_depth ?? dlqState.depth) > 0
                        ? 'var(--color-accent)'
                        : 'var(--color-text)',
                  }}
                >
                  {progress?.unresolved_failure_count ?? readyz?.dlq_depth ?? dlqState.depth}
                </div>
              </div>

              <div
                style={{ padding: '18px 24px', borderRight: '1px solid var(--color-divider)' }}
                data-testid="metric-unknown-attempts"
              >
                <div className="invariants-eyebrow">Unknown In-Flight Attempts</div>
                <div className="invariants-stat-value" style={{ marginTop: '8px', fontSize: '32px' }}>
                  {progress?.unknown_attempt_count ?? 0}
                </div>
              </div>

              <div
                style={{ padding: '18px 24px' }}
                data-testid="metric-pending-callbacks"
              >
                <div className="invariants-eyebrow">Pending Callbacks</div>
                <div className="invariants-stat-value" style={{ marginTop: '8px', fontSize: '32px' }}>
                  {progress?.pending_callback_count ?? 0}{' '}
                  <span style={{ fontSize: '13px', fontWeight: 400, fontFamily: 'var(--font-mono)' }}>
                    ({formatSeconds(progress?.oldest_callback_retry_age_seconds)})
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* Section 2: Channel Health & Persistence Summary */}
          <section
            data-testid="channel-health-section"
            style={{ borderBottom: '2px solid var(--color-divider)', background: 'var(--color-bg)' }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '12px',
                flexWrap: 'wrap',
                padding: '14px 24px',
                background: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-divider)',
              }}
            >
              <h2 style={{ margin: 0, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Channel Health &amp; Persistence
              </h2>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                {readyz?.persistence_mode && (
                  <span
                    className={`badge ${
                      readyz.persistence_mode === 'in_memory' ? 'badge-warning' : 'badge-info'
                    }`}
                    data-testid="persistence-mode-badge"
                  >
                    Persistence: {readyz.persistence_mode}
                  </span>
                )}
                {typeof readyz?.policy_count === 'number' && (
                  <span className="badge badge-default" data-testid="active-policy-count-badge">
                    Active Policies: {readyz.policy_count}
                  </span>
                )}
              </div>
            </div>

            {channelHealthState.error && (
              <div
                role="alert"
                data-testid="channel-health-error"
                style={{
                  padding: '12px 24px',
                  borderBottom: '1px solid var(--color-accent)',
                  backgroundColor: 'var(--color-accent-100)',
                  color: 'var(--color-accent-800)',
                }}
              >
                Channel health error: {channelHealthState.error}
              </div>
            )}

            {channelHealthState.data && (
              <div className="table-container">
                <table className="data-table" data-testid="channel-health-table">
                  <thead>
                    <tr>
                      <th>Channel</th>
                      <th>Status</th>
                      <th>Consecutive Failures</th>
                      <th>Last Success</th>
                      <th>Last Failure Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {channelHealthState.data.channels.map((ch) => (
                      <tr key={ch.channel} data-testid={`channel-row-${ch.channel}`}>
                        <td>
                          <span className="channel-tag">{ch.channel}</span>
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              ch.status === 'HEALTHY'
                                ? 'badge-success'
                                : ch.status === 'DEGRADED'
                                  ? 'badge-warning'
                                  : 'badge-error'
                            }`}
                          >
                            {ch.status}
                          </span>
                        </td>
                        <td className="monospace">{ch.consecutive_failures}</td>
                        <td className="timestamp">{formatDateTime(ch.last_success_at)}</td>
                        <td>{ch.last_failure_reason ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Section 3: Joined Dead-Letter Queue (DLQ) & Runtime Triage Table */}
          <section
            data-testid="dlq-triage-section"
            style={{ borderBottom: '2px solid var(--color-divider)', background: 'var(--color-bg)' }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '12px',
                flexWrap: 'wrap',
                padding: '14px 24px',
                background: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-divider)',
              }}
            >
              <h2 style={{ margin: 0, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Dead-Letter Queue Triage ({dlqState.rows.length})
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                {!isAdmin && (
                  <span className="badge badge-default" data-testid="dlq-readonly-notice">
                    Operator (admin) scope required for Replay / Resolve actions
                  </span>
                )}
                <Link
                  to="/docs?section=runbooks&q=TSG-01"
                  className="btn btn-secondary"
                  data-testid="dlq-runbook-link"
                >
                  Runbook: TSG-01 →
                </Link>
              </div>
            </div>

            {operatorFeedback && (
              <div
                role="status"
                data-testid="operator-action-feedback"
                style={{
                  padding: '12px 24px',
                  borderBottom: '1px solid var(--color-divider)',
                  backgroundColor:
                    operatorFeedback.kind === 'error'
                      ? 'var(--color-accent-100)'
                      : 'var(--color-surface)',
                }}
              >
                {operatorFeedback.message}
              </div>
            )}

            {dlqState.error && (
              <div
                role="alert"
                data-testid="dlq-error-banner"
                style={{
                  padding: '12px 24px',
                  borderBottom: '1px solid var(--color-accent)',
                  backgroundColor: 'var(--color-accent-100)',
                  color: 'var(--color-accent-800)',
                }}
              >
                DLQ telemetry error: {dlqState.error}
              </div>
            )}

            {dlqState.rows.length === 0 ? (
              <div className="empty-state" data-testid="dlq-empty-state">
                <p>No unresolved dead-lettered notifications.</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="data-table" data-testid="dlq-table">
                  <thead>
                    <tr>
                      <th>Notification ID</th>
                      <th>Notification Type</th>
                      <th>Reason / Outcome</th>
                      <th>Attempts (Cycle)</th>
                      <th>Replay Eligibility</th>
                      <th>Created At</th>
                      {isAdmin && <th>Operator Actions</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {dlqState.rows.map((row) => {
                      const isBlocked = Boolean(row.replay_blocked_by);
                      const isConfirmingThisRow =
                        confirmingAction?.entryId === row.entry_id;
                      const isSubmittingThisRow = submittingEntryId === row.entry_id;

                      return (
                        <tr key={row.entry_id} data-testid={`dlq-row-${row.entry_id}`}>
                          <td className="monospace">
                            <Link
                              to={`/deliveries/${row.notification_id}`}
                              data-testid={`dlq-delivery-link-${row.entry_id}`}
                            >
                              {truncateId(row.notification_id)}
                            </Link>
                          </td>
                          <td>
                            <Link
                              to={`/policy?notification_type=${encodeURIComponent(
                                row.notification_type
                              )}`}
                              data-testid={`dlq-policy-link-${row.entry_id}`}
                            >
                              {row.notification_type}
                            </Link>
                          </td>
                          <td>
                            <div>{row.reason}</div>
                            {row.outcome_summary && (
                              <div
                                style={{
                                  fontSize: '0.8rem',
                                  color: 'var(--color-text-secondary)',
                                }}
                              >
                                {row.outcome_summary}
                              </div>
                            )}
                          </td>
                          <td>
                            {row.attempts !== null
                              ? `${row.attempts} (cycle ${row.cycle ?? 1})`
                              : '-'}
                          </td>
                          <td>
                            {isBlocked ? (
                              <span
                                className="badge badge-warning"
                                data-testid={`dlq-blocked-badge-${row.entry_id}`}
                              >
                                Blocked by {truncateId(row.replay_blocked_by!)} (
                                {row.replay_block_reason ?? 'RESOLVED'})
                              </span>
                            ) : (
                              <span
                                className="badge badge-info"
                                data-testid={`dlq-eligible-badge-${row.entry_id}`}
                              >
                                Eligible
                              </span>
                            )}
                          </td>
                          <td className="timestamp">{formatDateTime(row.created_at)}</td>
                          {isAdmin && (
                            <td>
                              {isConfirmingThisRow && confirmingAction ? (
                                <div
                                  data-testid={`dlq-confirm-panel-${row.entry_id}`}
                                  style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '0.35rem',
                                  }}
                                >
                                  <span style={{ fontSize: '0.85rem' }}>
                                    {confirmingAction.type === 'replay'
                                      ? 'Start a new recovery cycle under accepted policy snapshot?'
                                      : 'Retire this dead-letter entry as resolved without re-sending?'}
                                  </span>
                                  {confirmingAction.type === 'replay' &&
                                    row.is_legacy_dlq_entry && (
                                      <label
                                        style={{
                                          display: 'inline-flex',
                                          alignItems: 'center',
                                          gap: '0.35rem',
                                          fontSize: '0.8rem',
                                        }}
                                      >
                                        <input
                                          type="checkbox"
                                          checked={confirmingAction.purgeLegacyDlqEntry}
                                          onChange={(e) =>
                                            setConfirmingAction({
                                              ...confirmingAction,
                                              purgeLegacyDlqEntry: e.target.checked,
                                            })
                                          }
                                          data-testid={`dlq-purge-checkbox-${row.entry_id}`}
                                        />
                                        Also remove legacy DLQ row after replay
                                      </label>
                                    )}
                                  <div style={{ display: 'flex', gap: '0.35rem' }}>
                                    <button
                                      type="button"
                                      className="btn btn-primary"
                                      disabled={isSubmittingThisRow}
                                      onClick={() => void handleExecuteAction(confirmingAction)}
                                      data-testid={`dlq-confirm-btn-${row.entry_id}`}
                                    >
                                      {isSubmittingThisRow
                                        ? 'Working…'
                                        : confirmingAction.type === 'replay'
                                          ? 'Confirm Replay'
                                          : 'Confirm Resolve'}
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-secondary"
                                      disabled={isSubmittingThisRow}
                                      onClick={() => setConfirmingAction(null)}
                                      data-testid={`dlq-cancel-btn-${row.entry_id}`}
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    disabled={isBlocked || isSubmittingThisRow}
                                    title={
                                      isBlocked
                                        ? `Replay blocked by ${row.replay_blocked_by} (${row.replay_block_reason})`
                                        : 'Replay notification in a new recovery cycle'
                                    }
                                    onClick={() =>
                                      setConfirmingAction({
                                        type: 'replay',
                                        entryId: row.entry_id,
                                        notificationId: row.notification_id,
                                        purgeLegacyDlqEntry: row.is_legacy_dlq_entry,
                                      })
                                    }
                                    data-testid={`dlq-replay-btn-${row.entry_id}`}
                                  >
                                    Replay
                                  </button>
                                  <button
                                    type="button"
                                    className={
                                      isBlocked ? 'btn btn-primary' : 'btn btn-secondary'
                                    }
                                    disabled={isSubmittingThisRow}
                                    onClick={() =>
                                      setConfirmingAction({
                                        type: 'resolve',
                                        entryId: row.entry_id,
                                        notificationId: row.notification_id,
                                        purgeLegacyDlqEntry: false,
                                      })
                                    }
                                    data-testid={`dlq-resolve-btn-${row.entry_id}`}
                                  >
                                    Resolve / Retire
                                  </button>
                                </div>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
export default OperationsPage;

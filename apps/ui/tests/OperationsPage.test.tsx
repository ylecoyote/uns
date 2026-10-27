/**
 * Tests for OperationsPage component (Surface 3).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OperationsPage } from '../src/pages/OperationsPage';
import { clearConsoleSession, startConsoleSession } from '../src/auth/session';

const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockReadyzPayload = {
  status: 'ready',
  service: 'uns',
  version: '0.1.0',
  persistence_mode: 'persistent',
  policy_count: 14,
  dlq_depth: 2,
  operational_progress: {
    pending_count: 3,
    oldest_pending_age_seconds: 12.5,
    oldest_due_attempt_lateness_seconds: 1.2,
    overdue_ack_count: 1,
    pending_callback_count: 2,
    oldest_callback_retry_age_seconds: 4.0,
    unresolved_failure_count: 2,
    unknown_attempt_count: 1,
  },
};

const mockChannelHealthPayload = {
  status: 'DEGRADED',
  total_channels: 2,
  healthy_channels: ['SLACK'],
  degraded_channels: ['EMAIL'],
  unavailable_channels: [],
  channels: [
    {
      channel: 'SLACK',
      status: 'HEALTHY',
      consecutive_failures: 0,
      last_success_at: '2026-01-23T04:00:00Z',
      last_failure_at: null,
      last_failure_reason: null,
    },
    {
      channel: 'EMAIL',
      status: 'DEGRADED',
      consecutive_failures: 3,
      last_success_at: null,
      last_failure_at: '2026-01-23T04:05:00Z',
      last_failure_reason: 'SMTP timeout',
    },
  ],
};

const entryEligible = '11111111-1111-4111-8111-111111111111';
const entryBlocked = '22222222-2222-4222-8222-222222222222';
const successorId = '99999999-9999-4999-8999-999999999999';

const mockDlqPayload = {
  depth: 2,
  items: [
    {
      entry_id: entryEligible,
      notification_id: entryEligible,
      notification_type: 'ops.alert',
      intent: 'OPERATIONAL',
      source: 'test-suite',
      reason: 'guaranteed_delivery_exhausted',
      created_at: '2026-01-23T04:00:00Z',
      metadata: {},
    },
    {
      entry_id: entryBlocked,
      notification_id: entryBlocked,
      notification_type: 'safety.halt',
      intent: 'SAFETY',
      source: 'test-suite',
      reason: 'guaranteed_delivery_exhausted',
      created_at: '2026-01-23T04:10:00Z',
      metadata: {},
    },
  ],
};

const mockRuntimeDeadLettersPayload = [
  {
    notification_id: entryEligible,
    status: 'FAILED',
    attempts: 3,
    cycle: 1,
    cycle_attempts: 3,
    outcome: { error_message: 'Slack webhook 502' },
    replay_blocked_by: null,
    replay_block_reason: null,
  },
  {
    notification_id: entryBlocked,
    status: 'FAILED',
    attempts: 3,
    cycle: 1,
    cycle_attempts: 3,
    outcome: { error_message: 'PagerDuty timeout' },
    replay_blocked_by: successorId,
    replay_block_reason: 'DELIVERED',
  },
];

function renderOperationsPage() {
  return render(
    <MemoryRouter initialEntries={['/operations']}>
      <OperationsPage />
    </MemoryRouter>
  );
}

describe('OperationsPage', () => {
  beforeEach(() => {
    clearConsoleSession();
    mockFetch.mockReset();
  });

  afterEach(() => {
    clearConsoleSession();
    vi.clearAllMocks();
  });

  it('parses HTTP 503 /readyz telemetry and displays READINESS DEGRADED badge without failing', async () => {
    startConsoleSession('observer-key', {
      subject: 'observer-user',
      scopes: ['observer'],
      auth_mode: 'required',
    });

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: () =>
          Promise.resolve({
            ...mockReadyzPayload,
            status: 'not_ready',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockChannelHealthPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ depth: 0, items: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve([]),
      });

    renderOperationsPage();

    await waitFor(() => {
      expect(screen.getByTestId('readiness-degraded-badge')).toBeInTheDocument();
    });

    expect(screen.getByTestId('metric-pending-count')).toHaveTextContent('3');
    expect(screen.getByTestId('metric-overdue-ack')).toHaveTextContent('1');
    expect(screen.getByTestId('metric-unresolved-dlq')).toHaveTextContent('2');
    expect(screen.getByTestId('persistence-mode-badge')).toHaveTextContent(
      'Persistence: persistent'
    );
  });

  it('isolates subsystem failures via Promise.allSettled so DLQ and readyz still render', async () => {
    startConsoleSession('observer-key', {
      subject: 'observer-user',
      scopes: ['observer'],
      auth_mode: 'required',
    });

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockReadyzPayload),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Channel health tracker offline' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockDlqPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRuntimeDeadLettersPayload),
      });

    renderOperationsPage();

    await waitFor(() => {
      expect(screen.getByTestId('channel-health-error')).toBeInTheDocument();
    });

    expect(screen.getByTestId('readiness-ready-badge')).toBeInTheDocument();
    expect(screen.getByTestId('dlq-table')).toBeInTheDocument();
  });

  it('joins DLQ and runtime dead-letters, sorts deterministically, and pre-badges blocked entries', async () => {
    startConsoleSession('admin-key', {
      subject: 'operator-admin',
      scopes: ['observer', 'admin'],
      auth_mode: 'required',
    });

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockReadyzPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockChannelHealthPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockDlqPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockRuntimeDeadLettersPayload),
      });

    renderOperationsPage();

    await waitFor(() => {
      expect(screen.getByTestId('dlq-table')).toBeInTheDocument();
    });

    // Sorted by created_at DESC: entryBlocked (04:10) comes before entryEligible (04:00)
    const rows = screen.getAllByTestId(/^dlq-row-/);
    expect(rows[0]).toHaveAttribute('data-testid', `dlq-row-${entryBlocked}`);
    expect(rows[1]).toHaveAttribute('data-testid', `dlq-row-${entryEligible}`);

    // Blocked entry shows Blocked badge and disables Replay button
    expect(screen.getByTestId(`dlq-blocked-badge-${entryBlocked}`)).toHaveTextContent(
      'Blocked by 99999999... (DELIVERED)'
    );
    expect(screen.getByTestId(`dlq-replay-btn-${entryBlocked}`)).toBeDisabled();
    expect(screen.getByTestId(`dlq-resolve-btn-${entryBlocked}`)).not.toBeDisabled();

    // Eligible entry shows Eligible badge and enables Replay button
    expect(screen.getByTestId(`dlq-eligible-badge-${entryEligible}`)).toHaveTextContent(
      'Eligible'
    );
    expect(screen.getByTestId(`dlq-replay-btn-${entryEligible}`)).not.toBeDisabled();
  });

  it('performs full outer join for runtime-only dead letters and surfaces runtime dead-letter fetch errors', async () => {
    startConsoleSession('admin-key', {
      subject: 'operator-admin',
      scopes: ['observer', 'admin'],
      auth_mode: 'required',
    });

    const runtimeOnlyId = '33333333-3333-4333-8333-333333333333';

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockReadyzPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockChannelHealthPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ depth: 0, items: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve([
            {
              notification_id: runtimeOnlyId,
              status: 'FAILED',
              attempts: 4,
              cycle: 2,
              cycle_attempts: 2,
              outcome: {
                notification_type: 'safety.kill_switch',
                error_message: 'Webhook 504',
              },
              replay_blocked_by: null,
              replay_block_reason: null,
            },
          ]),
      });

    renderOperationsPage();

    await waitFor(() => {
      expect(screen.getByTestId(`dlq-row-${runtimeOnlyId}`)).toBeInTheDocument();
    });

    expect(screen.getByTestId(`dlq-row-${runtimeOnlyId}`)).toHaveTextContent(
      'safety.kill_switch'
    );
    expect(screen.getByTestId(`dlq-row-${runtimeOnlyId}`)).toHaveTextContent(
      '4 (cycle 2)'
    );

    // Trigger manual refresh where runtime dead-letters fails -> surfaces dlq-error-banner
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockReadyzPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockChannelHealthPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockDlqPayload),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Runtime store unavailable' }),
      });

    fireEvent.click(screen.getByTestId('refresh-operations-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('dlq-error-banner')).toBeInTheDocument();
    });
    expect(screen.getByTestId('dlq-table')).toBeInTheDocument();
  });

  it('preserves open inline confirmation across background refresh and executes Replay and Resolve', async () => {
    startConsoleSession('admin-key', {
      subject: 'operator-admin',
      scopes: ['observer', 'admin'],
      auth_mode: 'required',
    });

    const queueSnapshotMocks = () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockReadyzPayload),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockChannelHealthPayload),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockDlqPayload),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockRuntimeDeadLettersPayload),
        });
    };

    queueSnapshotMocks();
    renderOperationsPage();

    await waitFor(() => {
      expect(screen.getByTestId(`dlq-replay-btn-${entryEligible}`)).toBeInTheDocument();
    });

    // Open inline Replay confirmation on entryEligible
    fireEvent.click(screen.getByTestId(`dlq-replay-btn-${entryEligible}`));
    expect(screen.getByTestId(`dlq-confirm-panel-${entryEligible}`)).toBeInTheDocument();

    // Trigger manual Refresh Now while confirmation is open -> confirmation remains open
    queueSnapshotMocks();
    fireEvent.click(screen.getByTestId('refresh-operations-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(8);
    });
    expect(screen.getByTestId(`dlq-confirm-panel-${entryEligible}`)).toBeInTheDocument();

    // Confirm Replay -> POST /api/v1/runtime/notifications/{id}/replay + snapshot refresh
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          notification_id: entryEligible,
          status: 'PENDING',
        }),
    });
    queueSnapshotMocks();

    fireEvent.click(screen.getByTestId(`dlq-confirm-btn-${entryEligible}`));

    await waitFor(() => {
      expect(screen.getByTestId('operator-action-feedback')).toHaveTextContent(
        `Replayed notification ${entryEligible} (PENDING).`
      );
    });

    // Now Resolve the blocked entry -> DELETE /api/v1/dlq/{entryBlocked}
    fireEvent.click(screen.getByTestId(`dlq-resolve-btn-${entryBlocked}`));
    expect(screen.getByTestId(`dlq-confirm-panel-${entryBlocked}`)).toBeInTheDocument();

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          entry_id: entryBlocked,
          removed: true,
          depth: 0,
        }),
    });
    queueSnapshotMocks();

    fireEvent.click(screen.getByTestId(`dlq-confirm-btn-${entryBlocked}`));

    await waitFor(() => {
      expect(screen.getByTestId('operator-action-feedback')).toHaveTextContent(
        `Resolved dead-letter entry ${entryBlocked}.`
      );
    });
  });
});

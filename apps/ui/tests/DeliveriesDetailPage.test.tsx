/**
 * Tests for DeliveriesDetailPage component.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DeliveriesDetailPage } from '../src/pages/DeliveriesDetailPage';
import { clearConsoleSession, startConsoleSession } from '../src/auth/session';
import {
  mockDeliveryTimeline,
  mockDeliveryTimelineFailed,
} from '../src/test/mocks';

// Mock the fetch function
const mockFetch = vi.fn();
global.fetch = mockFetch;

function renderWithRouter(notificationId: string) {
  return render(
    <MemoryRouter initialEntries={[`/deliveries/${notificationId}`]}>
      <Routes>
        <Route path="/deliveries/:notificationId" element={<DeliveriesDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('DeliveriesDetailPage', () => {
  beforeEach(() => {
    clearConsoleSession();
    mockFetch.mockReset();
  });

  afterEach(() => {
    clearConsoleSession();
    vi.clearAllMocks();
  });

  it('separates delivery, response and policy evidence', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...mockDeliveryTimeline, runtime_state: {
        delivery_status: 'DELIVERED', ack_status: 'ACKED', deadline: 1800000000,
        dead_letter: false, policy_config_hash: 'verified-policy-hash',
        policy_evaluation_id: 'evaluation-id',
      }}),
    });
    renderWithRouter(mockDeliveryTimeline.notification_id);
    expect(await screen.findByText('Delivery and human response')).toBeInTheDocument();
    expect(screen.getByText('ACKED')).toBeInTheDocument();
    expect(screen.getByText('verified-policy-hash')).toBeInTheDocument();
    expect(screen.getByText('evaluation-id')).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    // Never resolve to keep loading
    mockFetch.mockReturnValueOnce(new Promise(() => {}));

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    expect(screen.getByText('Loading delivery timeline...')).toBeInTheDocument();
  });

  it('shows error state on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () =>
        Promise.resolve({
          error: { code: 'internal_error', message: 'Something went wrong' },
          request_id: 'req-123',
        }),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
    });

    expect(screen.getByText(/Failed to load delivery timeline/)).toBeInTheDocument();
  });

  it('shows not found state for missing notification', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () =>
        Promise.resolve({
          error: { code: 'not_found', message: 'Notification not found' },
          request_id: 'req-123',
        }),
    });

    renderWithRouter('invalid-id');

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
    });
  });

  it('renders breadcrumb navigation', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument();
    });

    expect(screen.getByText('Deliveries')).toBeInTheDocument();
  });

  it('renders summary section with correct data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('summary-section')).toBeInTheDocument();
    });

    expect(screen.getByText('trading.order_executed')).toBeInTheDocument();
    expect(screen.getByText('OPERATIONAL')).toBeInTheDocument();
    expect(screen.getByText('DELIVERED')).toBeInTheDocument();
    expect(screen.getByText('GUARANTEED')).toBeInTheDocument();
  });

  it('renders autonomy section', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('autonomy-section')).toBeInTheDocument();
    });

    expect(screen.getByText('LIVE')).toBeInTheDocument();
  });

  it('renders channels section', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('channels-section')).toBeInTheDocument();
    });

    expect(screen.getByText('Attempted')).toBeInTheDocument();
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('renders attempts table', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('attempts-table')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('attempt-row');
    expect(rows).toHaveLength(1);
  });

  it('renders multiple attempts with different statuses', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimelineFailed),
    });

    renderWithRouter('223e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('attempts-table')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('attempt-row');
    expect(rows).toHaveLength(2);

    // Check for error details
    expect(screen.getByText('SMTP_ERROR')).toBeInTheDocument();
    expect(screen.getByText('SMTP connection refused')).toBeInTheDocument();
  });

  it('renders back to list link', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('back-to-list')).toBeInTheDocument();
    });

    expect(screen.getByTestId('back-to-list')).toHaveAttribute('href', '/deliveries');
  });

  it('makes API call with correct endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const callUrl = mockFetch.mock.calls[0][0];
    expect(callUrl).toContain('/ui/deliveries/123e4567-e89b-12d3-a456-426614174001');
  });

  it('renders optional autonomy context fields when present', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimeline),
    });

    renderWithRouter('123e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('autonomy-section')).toBeInTheDocument();
    });

    // Plan ID should be visible
    expect(screen.getByText('Plan ID')).toBeInTheDocument();
  });

  it('shows failed and succeeded channels correctly', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveryTimelineFailed),
    });

    renderWithRouter('223e4567-e89b-12d3-a456-426614174001');

    await waitFor(() => {
      expect(screen.getByTestId('channels-section')).toBeInTheDocument();
    });

    // Check for channel tags in different sections
    const channelsSection = screen.getByTestId('channels-section');
    expect(channelsSection).toHaveTextContent('SLACK');
    expect(channelsSection).toHaveTextContent('EMAIL');
  });

  it('renders obligation lineage, bounded runtime events, truncation notice, and policy deep-link for observer', async () => {
    startConsoleSession('observer-key', {
      subject: 'observer-user',
      scopes: ['observer'],
      auth_mode: 'required',
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          ...mockDeliveryTimeline,
          runtime_state: {
            delivery_status: 'DELIVERED',
            effective_status: 'DELIVERED',
            ack_status: 'PENDING',
            effective_ack_status: 'PENDING',
            require_ack: true,
            obligation_owner_id: mockDeliveryTimeline.notification_id,
            obligation_resolution_status: 'PENDING',
            deadline: 1800000000,
            dead_letter: false,
            events: [
              {
                id: 'evt-12345678-0001',
                notification_id: mockDeliveryTimeline.notification_id,
                kind: 'notification.dispatched',
                at: 1700000000,
                payload: { status: 'DELIVERED', channel: 'SLACK' },
              },
            ],
            events_total_count: 150,
            events_truncated: true,
          },
        }),
    });

    renderWithRouter(mockDeliveryTimeline.notification_id);

    await waitFor(() => {
      expect(screen.getByTestId('runtime-events-section')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('responder-action-bar')).not.toBeInTheDocument();
    expect(screen.getByTestId('events-truncated-notice')).toHaveTextContent(
      'Showing most recent 100 of 150 runtime events.'
    );
    expect(screen.getByTestId('policy-deep-link')).toHaveAttribute(
      'href',
      `/policy?notification_type=${encodeURIComponent(mockDeliveryTimeline.notification_type)}`
    );
  });

  it('enforces canonical owner navigation for deduplicated followers instead of remote ack', async () => {
    startConsoleSession('responder-key', {
      subject: 'responder-user',
      scopes: ['observer', 'responder'],
      auth_mode: 'required',
    });

    const canonicalOwnerId = '999e4567-e89b-12d3-a456-426614174999';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          ...mockDeliveryTimeline,
          status: 'DEDUPLICATED',
          runtime_state: {
            delivery_status: 'DEDUPLICATED',
            effective_status: 'DELIVERED',
            ack_status: 'PENDING',
            effective_ack_status: 'PENDING',
            require_ack: true,
            obligation_owner_id: canonicalOwnerId,
            ack_inherited: false,
            obligation_resolution_status: 'PENDING',
            dead_letter: false,
          },
        }),
    });

    renderWithRouter(mockDeliveryTimeline.notification_id);

    await waitFor(() => {
      expect(screen.getByTestId('deduplicated-follower-banner')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('responder-action-bar')).not.toBeInTheDocument();
    const ownerCta = screen.getByTestId('canonical-owner-ack-cta');
    expect(ownerCta).toHaveAttribute('href', `/deliveries/${canonicalOwnerId}`);
    expect(ownerCta).toHaveTextContent('View & Acknowledge Canonical Owner');
  });

  it('allows responder to acknowledge canonical pending notification with note and refreshes timeline', async () => {
    startConsoleSession('responder-key', {
      subject: 'responder-user',
      scopes: ['observer', 'responder'],
      auth_mode: 'required',
    });

    // Initial load: PENDING
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          ...mockDeliveryTimeline,
          runtime_state: {
            delivery_status: 'DELIVERED',
            effective_status: 'DELIVERED',
            ack_status: 'PENDING',
            effective_ack_status: 'PENDING',
            require_ack: true,
            obligation_owner_id: mockDeliveryTimeline.notification_id,
            obligation_resolution_status: 'PENDING',
            dead_letter: false,
          },
        }),
    });

    renderWithRouter(mockDeliveryTimeline.notification_id);

    await waitFor(() => {
      expect(screen.getByTestId('responder-action-bar')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('responder-note-input'), {
      target: { value: 'Investigated and mitigated' },
    });
    fireEvent.click(screen.getByTestId('ack-btn'));

    expect(screen.getByTestId('inline-response-confirmation')).toBeInTheDocument();

    // POST /api/v1/notifications/{id}/ack response + subsequent GET /ui/deliveries/{id} refetch
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            notification_id: mockDeliveryTimeline.notification_id,
            ack_status: 'ACKED',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            ...mockDeliveryTimeline,
            runtime_state: {
              delivery_status: 'DELIVERED',
              effective_status: 'DELIVERED',
              ack_status: 'ACKED',
              effective_ack_status: 'ACKED',
              require_ack: true,
              obligation_owner_id: mockDeliveryTimeline.notification_id,
              obligation_resolution_status: 'ACKED',
              actor: 'responder-user',
              responded_at: 1700000123,
              response_metadata: { note: 'Investigated and mitigated' },
              dead_letter: false,
            },
          }),
      });

    fireEvent.click(screen.getByTestId('confirm-response-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    const ackCall = mockFetch.mock.calls[1];
    expect(ackCall[0]).toContain(
      `/api/v1/notifications/${mockDeliveryTimeline.notification_id}/ack`
    );
    expect(ackCall[1].method).toBe('POST');
    expect(JSON.parse(ackCall[1].body)).toEqual({
      metadata: { note: 'Investigated and mitigated' },
    });

    await waitFor(() => {
      expect(screen.queryByTestId('responder-action-bar')).not.toBeInTheDocument();
    });
    expect(screen.getByText('responder-user')).toBeInTheDocument();
    expect(screen.getByTestId('responder-note-display')).toHaveTextContent(
      'Investigated and mitigated'
    );
  });

  it('gracefully recovers from 409 Conflict by auto-refreshing timeline and showing resolved banner', async () => {
    startConsoleSession('responder-key', {
      subject: 'responder-user',
      scopes: ['observer', 'responder'],
      auth_mode: 'required',
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          ...mockDeliveryTimeline,
          runtime_state: {
            delivery_status: 'DELIVERED',
            effective_status: 'DELIVERED',
            ack_status: 'PENDING',
            effective_ack_status: 'PENDING',
            require_ack: true,
            obligation_owner_id: mockDeliveryTimeline.notification_id,
            obligation_resolution_status: 'PENDING',
            dead_letter: false,
          },
        }),
    });

    renderWithRouter(mockDeliveryTimeline.notification_id);

    await waitFor(() => {
      expect(screen.getByTestId('responder-action-bar')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('dismiss-btn'));

    // Return 409 Conflict on dismiss, then return already-ACKED state on refetch
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: () =>
          Promise.resolve({
            detail: 'Notification already acknowledged by another responder',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            ...mockDeliveryTimeline,
            runtime_state: {
              delivery_status: 'DELIVERED',
              effective_status: 'DELIVERED',
              ack_status: 'ACKED',
              effective_ack_status: 'ACKED',
              require_ack: true,
              obligation_owner_id: mockDeliveryTimeline.notification_id,
              obligation_resolution_status: 'ACKED',
              actor: 'colleague-oncall',
              dead_letter: false,
            },
          }),
      });

    fireEvent.click(screen.getByTestId('confirm-response-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('conflict-recovered-banner')).toBeInTheDocument();
    });

    expect(screen.getByTestId('conflict-recovered-banner')).toHaveTextContent(
      'Notification already acknowledged by another responder'
    );
    expect(screen.getByText('colleague-oncall')).toBeInTheDocument();
  });

  it('allows admin operator to replay or resolve an exhausted dead-letter delivery inline', async () => {
    startConsoleSession('admin-key', {
      subject: 'operator-admin',
      scopes: ['observer', 'responder', 'producer', 'admin'],
      auth_mode: 'required',
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          ...mockDeliveryTimelineFailed,
          runtime_state: {
            delivery_status: 'FAILED',
            effective_status: 'FAILED',
            ack_status: null,
            dead_letter: true,
          },
        }),
    });

    renderWithRouter(mockDeliveryTimelineFailed.notification_id);

    await waitFor(() => {
      expect(screen.getByTestId('operator-recovery-bar')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('detail-replay-btn'));
    expect(screen.getByTestId('inline-recovery-confirmation')).toBeInTheDocument();

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            notification_id: mockDeliveryTimelineFailed.notification_id,
            status: 'PENDING',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            ...mockDeliveryTimelineFailed,
            status: 'PENDING',
            runtime_state: {
              delivery_status: 'PENDING',
              effective_status: 'PENDING',
              ack_status: null,
              dead_letter: false,
            },
          }),
      });

    fireEvent.click(screen.getByTestId('confirm-recovery-btn'));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    const replayCall = mockFetch.mock.calls[1];
    expect(replayCall[0]).toContain(
      `/api/v1/runtime/notifications/${mockDeliveryTimelineFailed.notification_id}/replay`
    );
    expect(replayCall[1].method).toBe('POST');

    await waitFor(() => {
      expect(screen.queryByTestId('operator-recovery-bar')).not.toBeInTheDocument();
    });
  });
});

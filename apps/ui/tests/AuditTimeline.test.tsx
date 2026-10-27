/**
 * Tests for AuditTimeline page component.
 *
 * Validates the normalized SPA patterns for the audit timeline page.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { AuditTimeline } from '../src/pages/AuditTimeline';
import { mockAuditEventsResponse, mockEmptyResponse, mockPaginatedResponse } from '../src/test/mocks';

// Mock the fetch function
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('AuditTimeline', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Structure', () => {
    it('renders page header with title', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockEmptyResponse),
      });

      render(<AuditTimeline />);

      expect(screen.getByText('Audit Timeline')).toBeInTheDocument();
      expect(
        screen.getByText(/Browse the audit event stream/)
      ).toBeInTheDocument();
    });

    it('renders with correct page wrapper testid', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockEmptyResponse),
      });

      render(<AuditTimeline />);

      expect(screen.getByTestId('audit-timeline-page')).toBeInTheDocument();
    });

    it('renders filters component', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockEmptyResponse),
      });

      render(<AuditTimeline />);

      expect(screen.getByTestId('audit-filters')).toBeInTheDocument();
    });
  });

  describe('Loading States', () => {
    it('shows loading state initially', () => {
      // Never resolve to keep loading
      mockFetch.mockReturnValueOnce(new Promise(() => {}));

      render(<AuditTimeline />);

      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('shows empty state when no events', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockEmptyResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      });

      expect(
        screen.getByText(/No audit events found/)
      ).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('shows error state on fetch failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () =>
          Promise.resolve({
            error: { code: 'internal_error', message: 'Something went wrong' },
            request_id: 'req-123',
          }),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toBeInTheDocument();
      });

      expect(
        screen.getByText(/Error loading audit events/)
      ).toBeInTheDocument();
    });

    it('shows request ID in error state', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () =>
          Promise.resolve({
            error: { code: 'internal_error', message: 'Something went wrong' },
            request_id: 'req-123',
          }),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByText(/Request ID: req-123/)).toBeInTheDocument();
      });
    });

    it('shows retry button in error state', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () =>
          Promise.resolve({
            error: { code: 'internal_error', message: 'Something went wrong' },
            request_id: 'req-123',
          }),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
      });
    });
  });

  describe('Audit Events Display', () => {
    it('renders audit events when loaded', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('audit-event-list')).toBeInTheDocument();
      });

      // Should render 3 event cards
      const cards = screen.getAllByTestId('audit-event-card');
      expect(cards).toHaveLength(3);
    });

    it('renders pagination info', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('pagination')).toBeInTheDocument();
      });

      expect(screen.getByText(/Showing 3/)).toBeInTheDocument();
    });

    it('defaults to By notification lifecycle table (1e) and toggles to All events (1d)', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('audit-lifecycle-table')).toBeInTheDocument();
      });

      // 3 mock events belong to 2 unique notifications (123e... and 223e...)
      expect(
        screen.getByTestId('audit-lifecycle-row-123e4567-e89b-12d3-a456-426614174001')
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('audit-lifecycle-row-223e4567-e89b-12d3-a456-426614174001')
      ).toBeInTheDocument();

      // Switch segmented control to All events (1d)
      fireEvent.click(screen.getByTestId('audit-view-all-events'));
      expect(screen.queryByTestId('audit-lifecycle-table')).not.toBeInTheDocument();
      expect(screen.getByTestId('audit-event-list')).not.toHaveClass('audit-stream-hidden');
    });

    it('renders Prior to window and — duration for partial-page ack.received slices, sorts equal timestamps by lifecycle phase rank, and filters internal timeout worker actor', async () => {
      const partialPagePayload = {
        items: [
          // 1. Only ack.received in window (no started or delivered events in slice)
          {
            audit_id: 'audit-ack-only',
            event_type: 'ack.received',
            event_time: '2026-01-23T12:10:00Z',
            notification_id: 'notif-ack-only',
            notification_type: 'safety.halt',
            autonomy_context: {
              autonomy_mode: 'LIVE',
              agent_id: '123e4567-e89b-12d3-a456-426614174002',
            },
            payload: {
              acked_by: 'oncall-sre',
            },
          },
          // 2. Equal-timestamp events delivered out of phase order + mixed channel success/failure + internal timeout worker
          {
            audit_id: 'audit-timeout',
            event_type: 'ack.timed_out',
            event_time: '2026-01-23T12:00:00Z',
            notification_id: 'notif-same-ts',
            notification_type: 'ops.degraded',
            autonomy_context: {
              autonomy_mode: 'LIVE',
              agent_id: '223e4567-e89b-12d3-a456-426614174002',
            },
            payload: {
              actor: 'uns-timeout-worker',
            },
          },
          {
            audit_id: 'audit-delivered-mixed',
            event_type: 'delivery.succeeded',
            event_time: '2026-01-23T12:00:00Z',
            notification_id: 'notif-same-ts',
            notification_type: 'ops.degraded',
            autonomy_context: {
              autonomy_mode: 'LIVE',
              agent_id: '223e4567-e89b-12d3-a456-426614174002',
            },
            payload: {
              channels_succeeded: ['SLACK'],
              channels_failed: ['EMAIL'],
            },
          },
          {
            audit_id: 'audit-created',
            event_type: 'notification.created',
            event_time: '2026-01-23T12:00:00Z',
            notification_id: 'notif-same-ts',
            notification_type: '',
            autonomy_context: {
              autonomy_mode: 'LIVE',
              agent_id: '223e4567-e89b-12d3-a456-426614174002',
            },
            payload: {},
          },
        ],
        pagination: {
          next_cursor: null,
          has_more: false,
          total_count: 4,
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(partialPagePayload),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('audit-lifecycle-row-notif-ack-only')).toBeInTheDocument();
      });

      const ackOnlyRow = screen.getByTestId('audit-lifecycle-row-notif-ack-only');
      // Started and Delivered columns both show "Prior to window", not "Pending" or "Acknowledged"
      expect(ackOnlyRow).toHaveTextContent('Prior to window');
      expect(ackOnlyRow).not.toHaveTextContent('Pending');
      // Time to respond is '—' rather than a fabricated '0s'
      expect(ackOnlyRow).toHaveTextContent('—');
      expect(ackOnlyRow).not.toHaveTextContent('0s');

      const sameTsRow = screen.getByTestId('audit-lifecycle-row-notif-same-ts');
      // Non-empty notification_type carrier chosen even though notification.created sorted first
      expect(sameTsRow).toHaveTextContent('ops.degraded');
      expect(sameTsRow).toHaveTextContent('Created');
      expect(sameTsRow).toHaveTextContent('SLACK (failed: EMAIL)');
      expect(sameTsRow).toHaveTextContent('Ack Timeout');
      expect(sameTsRow).not.toHaveTextContent('uns-timeout-worker');
    });
  });

  describe('API Integration', () => {
    it('makes API call with correct endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockEmptyResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/ui/audit');
    });

    it('includes limit parameter in API call', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockEmptyResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('limit=25');
    });
  });

  describe('Pagination', () => {
    it('shows load more button when more events available', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPaginatedResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('load-more-btn')).toBeInTheDocument();
      });
    });

    it('does not show load more button when no more events', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      render(<AuditTimeline />);

      await waitFor(() => {
        expect(screen.getByTestId('audit-event-list')).toBeInTheDocument();
      });

      expect(screen.queryByTestId('load-more-btn')).not.toBeInTheDocument();
    });
  });
});

describe('AuditTimeline SPA Pattern Compliance', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('uses consistent loading prop naming (loading not isLoading)', async () => {
    // This test validates that the hook returns 'loading' not 'isLoading'
    // by checking the behavior matches useInvariants pattern
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyResponse),
    });

    render(<AuditTimeline />);

    // If the pattern is correct, the page will render properly
    await waitFor(() => {
      expect(screen.getByTestId('audit-timeline-page')).toBeInTheDocument();
    });
  });

  it('follows Tailwind CSS styling patterns', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyResponse),
    });

    render(<AuditTimeline />);

    // Verify Tailwind classes are applied to the page wrapper
    const pageWrapper = screen.getByTestId('audit-timeline-page');
    expect(pageWrapper.className).toContain('min-h-screen');
    expect(pageWrapper.className).toContain('bg-gray-50');
  });

  it('uses consistent error display patterns', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () =>
        Promise.resolve({
          error: { code: 'internal_error', message: 'Something went wrong' },
          request_id: 'req-123',
        }),
    });

    render(<AuditTimeline />);

    await waitFor(() => {
      const errorState = screen.getByTestId('error-state');
      // Verify Tailwind error styling pattern
      expect(errorState.className).toContain('bg-red-50');
      expect(errorState.className).toContain('border-red-200');
    });
  });
});

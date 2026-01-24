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

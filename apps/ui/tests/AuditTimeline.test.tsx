/**
 * Tests for AuditTimeline page component.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuditTimeline } from '../src/pages/AuditTimeline';
import { mockAuditEventsResponse, mockEmptyResponse } from '../src/test/mocks';

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

  it('renders page header', async () => {
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

  it('renders filters', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyResponse),
    });

    render(<AuditTimeline />);

    expect(screen.getByTestId('audit-filters')).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    // Never resolve to keep loading
    mockFetch.mockReturnValueOnce(new Promise(() => {}));

    render(<AuditTimeline />);

    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

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
      screen.getByText(/Failed to load audit events/)
    ).toBeInTheDocument();
  });

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

    expect(screen.getByText(/Showing 3 events/)).toBeInTheDocument();
  });

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
});

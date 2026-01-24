/**
 * Tests for DeliveriesDetailPage component.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DeliveriesDetailPage } from '../src/pages/DeliveriesDetailPage';
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
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
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
});

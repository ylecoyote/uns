/**
 * Tests for DeliveriesListPage component.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DeliveriesListPage } from '../src/pages/DeliveriesListPage';
import {
  mockDeliveriesListResponse,
  mockEmptyDeliveriesResponse,
} from '../src/test/mocks';

// Mock the fetch function
const mockFetch = vi.fn();
global.fetch = mockFetch;

function renderWithRouter(component: React.ReactElement) {
  return render(<MemoryRouter>{component}</MemoryRouter>);
}

describe('DeliveriesListPage', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders page header', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyDeliveriesResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    expect(screen.getByText('Deliveries')).toBeInTheDocument();
    expect(screen.getByText(/View delivery timelines/)).toBeInTheDocument();
  });

  it('renders filters', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyDeliveriesResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    expect(screen.getByTestId('deliveries-filters')).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    // Never resolve to keep loading
    mockFetch.mockReturnValueOnce(new Promise(() => {}));

    renderWithRouter(<DeliveriesListPage />);

    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    expect(screen.getByText('Loading deliveries...')).toBeInTheDocument();
  });

  it('shows empty state when no deliveries', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyDeliveriesResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    expect(screen.getByText(/No deliveries found/)).toBeInTheDocument();
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

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
    });

    expect(screen.getByText(/Failed to load deliveries/)).toBeInTheDocument();
  });

  it('renders deliveries table when loaded', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveriesListResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('deliveries-table')).toBeInTheDocument();
    });

    // Should render 3 delivery rows
    const rows = screen.getAllByTestId('delivery-row');
    expect(rows).toHaveLength(3);
  });

  it('renders pagination info', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveriesListResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('pagination')).toBeInTheDocument();
    });

    expect(screen.getByText(/Showing 3/)).toBeInTheDocument();
  });

  it('makes API call with correct endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockEmptyDeliveriesResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const callUrl = mockFetch.mock.calls[0][0];
    expect(callUrl).toContain('/ui/deliveries');
  });

  it('displays correct status badges', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveriesListResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('deliveries-table')).toBeInTheDocument();
    });

    // Check for status badges
    expect(screen.getByText('DELIVERED')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
    expect(screen.getByText('PENDING')).toBeInTheDocument();
  });

  it('displays correct intent badges', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveriesListResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('deliveries-table')).toBeInTheDocument();
    });

    // Check for intent badges
    expect(screen.getByText('OPERATIONAL')).toBeInTheDocument();
    expect(screen.getByText('SAFETY')).toBeInTheDocument();
    expect(screen.getByText('GOVERNANCE')).toBeInTheDocument();
  });

  it('renders links to detail pages', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDeliveriesListResponse),
    });

    renderWithRouter(<DeliveriesListPage />);

    await waitFor(() => {
      expect(screen.getByTestId('deliveries-table')).toBeInTheDocument();
    });

    const links = screen.getAllByTestId('notification-link');
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAttribute('href', '/deliveries/123e4567-e89b-12d3-a456-426614174001');
  });
});

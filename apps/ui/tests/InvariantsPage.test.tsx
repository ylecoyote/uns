/**
 * Tests for InvariantsPage component
 *
 * These tests verify:
 * - Page renders correctly with summary and list
 * - Filters work correctly
 * - Pagination works correctly
 * - Degraded state is displayed when API indicates issues
 * - Error states are handled gracefully
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { InvariantsPage } from '../src/pages/InvariantsPage';
import * as api from '../src/api/invariants';

// Mock the API module
vi.mock('../src/api/invariants');

// Helper to wait for loading to complete
const waitForLoadingComplete = async () => {
  await waitFor(() => {
    expect(screen.queryByText('Total Invariants')).toBeInTheDocument();
  }, { timeout: 3000 });
};

const mockInvariantsList = {
  items: [
    {
      id: 'INV-ACK-001',
      statement: 'Acknowledgment state is never gated on execution',
      severity: 'HIGH' as const,
      status: 'active' as const,
      enforcement: {
        type: 'guard' as const,
        description: 'Hard validation in AcknowledgmentEngine.ack()',
      },
      evidence: [
        {
          path: 'src/notification/acknowledgment.py',
          note: 'validate state transitions',
          line_ref: 'L42-L45',
        },
      ],
      owner: 'platform-team',
      last_reviewed: '2025-01-15',
    },
    {
      id: 'INV-DLV-001',
      statement: 'GUARANTEED delivery mode raises on failure',
      severity: 'HIGH' as const,
      status: 'active' as const,
      enforcement: {
        type: 'test' as const,
        description: 'Integration tests verify DeliveryError is raised',
      },
      evidence: [
        {
          path: 'tests/notification/test_service.py',
          note: 'Test GUARANTEED raises on failure',
        },
      ],
      owner: 'platform-team',
      last_reviewed: '2025-01-15',
    },
  ],
  pagination: {
    next_cursor: null,
    has_more: false,
    total_count: 2,
  },
};

const mockSummary = {
  total_count: 7,
  by_severity: { HIGH: 5, MEDIUM: 2, LOW: 0 },
  by_enforcement_type: { guard: 4, isolation: 1, test: 2, exception: 0 },
  by_status: { active: 7, inactive: 0 },
  exceptions_requiring_review: 0,
  last_updated: '2025-01-23T12:00:00Z',
};

describe('InvariantsPage', () => {
  beforeEach(() => {
    vi.mocked(api.fetchInvariants).mockResolvedValue(mockInvariantsList);
    vi.mocked(api.fetchInvariantsSummary).mockResolvedValue(mockSummary);
  });

  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  describe('Initial render', () => {
    it('renders page title', async () => {
      render(<InvariantsPage />);

      expect(screen.getByText('System Invariants')).toBeInTheDocument();
    });

    it('fetches and displays invariants list', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('INV-ACK-001')).toBeInTheDocument();
        expect(screen.getByText('INV-DLV-001')).toBeInTheDocument();
      });
    });

    it('fetches and displays summary statistics', async () => {
      render(<InvariantsPage />);

      await waitForLoadingComplete();

      // Check that total count and label are displayed
      // The value "7" might appear multiple times, so use getAllByText
      const sevenElements = screen.getAllByText('7');
      expect(sevenElements.length).toBeGreaterThan(0);
      expect(screen.getByText('Total Invariants')).toBeInTheDocument();
    });

    it('displays invariant details', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(
          screen.getByText('Acknowledgment state is never gated on execution')
        ).toBeInTheDocument();
        expect(screen.getByText(/Hard validation in AcknowledgmentEngine/)).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('allows filtering by severity', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('INV-ACK-001')).toBeInTheDocument();
      });

      const severitySelect = screen.getByLabelText('Filter by severity');
      fireEvent.change(severitySelect, { target: { value: 'HIGH' } });

      await waitFor(() => {
        expect(api.fetchInvariants).toHaveBeenCalledWith(
          expect.objectContaining({ severity: 'HIGH' })
        );
      });
    });

    it('allows filtering by enforcement type', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('INV-ACK-001')).toBeInTheDocument();
      });

      const enforcementSelect = screen.getByLabelText('Filter by enforcement type');
      fireEvent.change(enforcementSelect, { target: { value: 'guard' } });

      await waitFor(() => {
        expect(api.fetchInvariants).toHaveBeenCalledWith(
          expect.objectContaining({ enforcement_type: 'guard' })
        );
      });
    });

    it('allows filtering by status', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('INV-ACK-001')).toBeInTheDocument();
      });

      const statusSelect = screen.getByLabelText('Filter by status');
      fireEvent.change(statusSelect, { target: { value: 'active' } });

      await waitFor(() => {
        expect(api.fetchInvariants).toHaveBeenCalledWith(
          expect.objectContaining({ status: 'active' })
        );
      });
    });

    it('allows text search', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('INV-ACK-001')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText('Search invariant statements...');
      fireEvent.change(searchInput, { target: { value: 'acknowledgment' } });
      fireEvent.keyDown(searchInput, { key: 'Enter' });

      await waitFor(() => {
        expect(api.fetchInvariants).toHaveBeenCalledWith(
          expect.objectContaining({ search: 'acknowledgment' })
        );
      });
    });

    it('clears filters when Clear button is clicked', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('INV-ACK-001')).toBeInTheDocument();
      });

      // Set a filter first
      const severitySelect = screen.getByLabelText('Filter by severity');
      fireEvent.change(severitySelect, { target: { value: 'HIGH' } });

      await waitFor(() => {
        expect(screen.getByText('Clear')).toBeInTheDocument();
      });

      // Clear filters
      fireEvent.click(screen.getByText('Clear'));

      // After clearing, the API should be called with an object where severity is not 'HIGH'
      await waitFor(() => {
        const lastCall = vi.mocked(api.fetchInvariants).mock.calls.at(-1);
        expect(lastCall).toBeDefined();
        expect(lastCall![0].severity).toBeUndefined();
      });
    });
  });

  describe('Pagination', () => {
    it('shows pagination info', async () => {
      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText(/Showing 2 of 2 invariants/)).toBeInTheDocument();
      });
    });

    it('shows Load More button when has_more is true', async () => {
      vi.mocked(api.fetchInvariants).mockResolvedValue({
        ...mockInvariantsList,
        pagination: {
          next_cursor: 'cursor-123',
          has_more: true,
          total_count: 10,
        },
      });

      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('Load More')).toBeInTheDocument();
      });
    });

    it('loads more invariants when Load More is clicked', async () => {
      vi.mocked(api.fetchInvariants).mockResolvedValueOnce({
        ...mockInvariantsList,
        pagination: {
          next_cursor: 'cursor-123',
          has_more: true,
          total_count: 4,
        },
      });

      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('Load More')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Load More'));

      await waitFor(() => {
        expect(api.fetchInvariants).toHaveBeenCalledWith(
          expect.objectContaining({ cursor: 'cursor-123' })
        );
      });
    });
  });

  describe('Error handling', () => {
    it('displays error message when API fails', async () => {
      const mockError = new Error('Network error') as any;
      mockError.code = 'network_error';
      mockError.request_id = 'req-123';
      vi.mocked(api.fetchInvariants).mockRejectedValue(mockError);

      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('Error loading invariants')).toBeInTheDocument();
        expect(screen.getByText('Network error')).toBeInTheDocument();
        expect(screen.getByText(/Request ID: req-123/)).toBeInTheDocument();
      });
    });

    it('displays degraded state warning when appropriate', async () => {
      const mockError = new Error('Service degraded') as any;
      mockError.code = 'service_degraded';
      vi.mocked(api.fetchInvariants).mockRejectedValue(mockError);

      render(<InvariantsPage />);

      await waitFor(() => {
        expect(screen.getByText('Degraded State')).toBeInTheDocument();
      });
    });
  });

  describe('Empty state', () => {
    it('displays message when no invariants match filters', async () => {
      vi.mocked(api.fetchInvariants).mockResolvedValue({
        items: [],
        pagination: {
          next_cursor: null,
          has_more: false,
          total_count: 0,
        },
      });

      render(<InvariantsPage />);

      await waitFor(() => {
        expect(
          screen.getByText('No invariants found matching the current filters.')
        ).toBeInTheDocument();
      });
    });
  });
});

describe('InvariantsSummary', () => {
  beforeEach(() => {
    vi.mocked(api.fetchInvariants).mockResolvedValue(mockInvariantsList);
    vi.mocked(api.fetchInvariantsSummary).mockResolvedValue(mockSummary);
  });

  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  it('displays severity breakdown', async () => {
    render(<InvariantsPage />);

    await waitForLoadingComplete();

    expect(screen.getByText('By Severity')).toBeInTheDocument();
    // "High" appears in multiple places (badges + summary labels)
    const highElements = screen.getAllByText('High');
    expect(highElements.length).toBeGreaterThan(0);
    // Check that the summary stat "5" is present (HIGH count)
    const fiveElements = screen.getAllByText('5');
    expect(fiveElements.length).toBeGreaterThan(0);
  });

  it('displays enforcement type breakdown', async () => {
    render(<InvariantsPage />);

    await waitForLoadingComplete();

    expect(screen.getByText('By Enforcement Type')).toBeInTheDocument();
    // "Guard" appears in summary section
    const guardElements = screen.getAllByText('Guard');
    expect(guardElements.length).toBeGreaterThan(0);
    // Check that the summary stat "4" is present (guard count)
    const fourElements = screen.getAllByText('4');
    expect(fourElements.length).toBeGreaterThan(0);
  });

  it('displays status breakdown', async () => {
    render(<InvariantsPage />);

    await waitForLoadingComplete();

    expect(screen.getByText('By Status')).toBeInTheDocument();
    // "Active" appears in multiple places (status badges + summary), so use getAllByText
    const activeElements = screen.getAllByText('Active');
    expect(activeElements.length).toBeGreaterThan(0);
  });

  it('displays exceptions requiring review when > 0', async () => {
    // Override the summary mock for this test only
    vi.mocked(api.fetchInvariantsSummary).mockResolvedValueOnce({
      ...mockSummary,
      exceptions_requiring_review: 2,
    });

    render(<InvariantsPage />);

    await waitFor(() => {
      expect(screen.getByText(/2 exception\(s\) require review/)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('shows last updated timestamp', async () => {
    render(<InvariantsPage />);

    await waitForLoadingComplete();

    expect(screen.getByText(/Last updated:/)).toBeInTheDocument();
  });
});

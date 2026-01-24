/**
 * Tests for AuditEventList component.
 *
 * Validates the component follows the InvariantsList pattern.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuditEventList } from '../src/components/AuditEventList';
import { mockAuditEvent, mockAuditEventFailed, mockAuditEventAck } from '../src/test/mocks';
import type { PaginationInfo } from '../src/types/api';

describe('AuditEventList', () => {
  describe('Empty State', () => {
    it('shows empty state when no events and not loading', () => {
      render(
        <AuditEventList
          events={[]}
          pagination={null}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(screen.getByText(/No audit events found/)).toBeInTheDocument();
    });

    it('does not show empty state when loading', () => {
      render(
        <AuditEventList
          events={[]}
          pagination={null}
          loading={true}
          onLoadMore={() => {}}
        />
      );

      expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();
      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('shows loading spinner when loading with no events', () => {
      render(
        <AuditEventList
          events={[]}
          pagination={null}
          loading={true}
          onLoadMore={() => {}}
        />
      );

      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    });

    it('still shows events when loading more', () => {
      render(
        <AuditEventList
          events={[mockAuditEvent]}
          pagination={{ next_cursor: 'abc', has_more: true }}
          loading={true}
          onLoadMore={() => {}}
        />
      );

      // Should still show the events
      expect(screen.getByTestId('audit-event-list')).toBeInTheDocument();
      // Should show the event card
      expect(screen.getByTestId('audit-event-card')).toBeInTheDocument();
    });
  });

  describe('Event Display', () => {
    it('renders event cards for each event', () => {
      const events = [mockAuditEvent, mockAuditEventFailed, mockAuditEventAck];

      render(
        <AuditEventList
          events={events}
          pagination={{ next_cursor: null, has_more: false }}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      const cards = screen.getAllByTestId('audit-event-card');
      expect(cards).toHaveLength(3);
    });

    it('renders events in correct order', () => {
      const events = [mockAuditEvent, mockAuditEventFailed];

      render(
        <AuditEventList
          events={events}
          pagination={{ next_cursor: null, has_more: false }}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      const notificationIds = screen.getAllByTestId('notification-id');
      expect(notificationIds[0].textContent).toBe(mockAuditEvent.notification_id);
      expect(notificationIds[1].textContent).toBe(mockAuditEventFailed.notification_id);
    });
  });

  describe('Pagination', () => {
    it('shows load more button when has_more is true', () => {
      const pagination: PaginationInfo = {
        next_cursor: 'cursor-123',
        has_more: true,
      };

      render(
        <AuditEventList
          events={[mockAuditEvent]}
          pagination={pagination}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      expect(screen.getByTestId('load-more-btn')).toBeInTheDocument();
    });

    it('hides load more button when has_more is false', () => {
      const pagination: PaginationInfo = {
        next_cursor: null,
        has_more: false,
      };

      render(
        <AuditEventList
          events={[mockAuditEvent]}
          pagination={pagination}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      expect(screen.queryByTestId('load-more-btn')).not.toBeInTheDocument();
    });

    it('calls onLoadMore when load more button clicked', () => {
      const mockOnLoadMore = vi.fn();
      const pagination: PaginationInfo = {
        next_cursor: 'cursor-123',
        has_more: true,
      };

      render(
        <AuditEventList
          events={[mockAuditEvent]}
          pagination={pagination}
          loading={false}
          onLoadMore={mockOnLoadMore}
        />
      );

      fireEvent.click(screen.getByTestId('load-more-btn'));
      expect(mockOnLoadMore).toHaveBeenCalledTimes(1);
    });

    it('shows pagination info with event count', () => {
      const pagination: PaginationInfo = {
        next_cursor: null,
        has_more: false,
        total_count: 10,
      };

      render(
        <AuditEventList
          events={[mockAuditEvent, mockAuditEventFailed]}
          pagination={pagination}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      expect(screen.getByTestId('pagination')).toBeInTheDocument();
      expect(screen.getByText(/Showing 2 of 10/)).toBeInTheDocument();
    });

    it('shows singular event text for single event', () => {
      const pagination: PaginationInfo = {
        next_cursor: null,
        has_more: false,
      };

      render(
        <AuditEventList
          events={[mockAuditEvent]}
          pagination={pagination}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      expect(screen.getByText(/Showing 1.*event$/)).toBeInTheDocument();
    });
  });

  describe('Styling', () => {
    it('uses Tailwind CSS classes for container', () => {
      render(
        <AuditEventList
          events={[mockAuditEvent]}
          pagination={{ next_cursor: null, has_more: false }}
          loading={false}
          onLoadMore={() => {}}
        />
      );

      // Container should have space-y-4 for consistent spacing
      const container = screen.getByTestId('audit-event-list').parentElement;
      expect(container?.className).toContain('space-y-4');
    });
  });
});

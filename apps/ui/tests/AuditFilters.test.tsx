/**
 * Tests for AuditFilters component.
 *
 * Validates the component follows the InvariantsFilter pattern.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuditFilters } from '../src/components/AuditFilters';
import type { AuditEventFilter } from '../src/types/api';

describe('AuditFilters', () => {
  const defaultFilters: AuditEventFilter = { limit: 25 };

  describe('Rendering', () => {
    it('renders filter container with testid', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('audit-filters')).toBeInTheDocument();
    });

    it('renders event type dropdown', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('event-type-select')).toBeInTheDocument();
    });

    it('renders autonomy mode dropdown', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('autonomy-mode-select')).toBeInTheDocument();
    });

    it('renders notification ID input', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('notification-id-input')).toBeInTheDocument();
    });

    it('renders agent ID input', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('agent-id-input')).toBeInTheDocument();
    });

    it('renders correlation ID input', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('correlation-id-input')).toBeInTheDocument();
    });

    it('renders time range inputs', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('start-time-input')).toBeInTheDocument();
      expect(screen.getByTestId('end-time-input')).toBeInTheDocument();
    });

    it('renders apply button', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('apply-filters-btn')).toBeInTheDocument();
    });
  });

  describe('Filter Selection', () => {
    it('calls onFiltersChange when event type changes', () => {
      const mockOnChange = vi.fn();

      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={mockOnChange}
        />
      );

      fireEvent.change(screen.getByTestId('event-type-select'), {
        target: { value: 'delivery.succeeded' },
      });

      expect(mockOnChange).toHaveBeenCalledWith(
        expect.objectContaining({ event_type: 'delivery.succeeded' })
      );
    });

    it('calls onFiltersChange when autonomy mode changes', () => {
      const mockOnChange = vi.fn();

      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={mockOnChange}
        />
      );

      fireEvent.change(screen.getByTestId('autonomy-mode-select'), {
        target: { value: 'LIVE' },
      });

      expect(mockOnChange).toHaveBeenCalledWith(
        expect.objectContaining({ autonomy_mode: 'LIVE' })
      );
    });
  });

  describe('Apply Filters', () => {
    it('calls onFiltersChange with text inputs on apply', () => {
      const mockOnChange = vi.fn();

      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={mockOnChange}
        />
      );

      fireEvent.change(screen.getByTestId('notification-id-input'), {
        target: { value: '123e4567-e89b-12d3-a456-426614174000' },
      });

      fireEvent.click(screen.getByTestId('apply-filters-btn'));

      expect(mockOnChange).toHaveBeenCalledWith(
        expect.objectContaining({
          notification_id: '123e4567-e89b-12d3-a456-426614174000',
        })
      );
    });
  });

  describe('Clear Filters', () => {
    it('shows clear button when filters are active', () => {
      const activeFilters: AuditEventFilter = {
        limit: 25,
        event_type: 'delivery.succeeded',
      };

      render(
        <AuditFilters
          filters={activeFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.getByTestId('clear-filters-btn')).toBeInTheDocument();
    });

    it('hides clear button when no filters active', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      expect(screen.queryByTestId('clear-filters-btn')).not.toBeInTheDocument();
    });

    it('clears filters when clear button clicked', () => {
      const mockOnChange = vi.fn();
      const activeFilters: AuditEventFilter = {
        limit: 25,
        event_type: 'delivery.succeeded',
      };

      render(
        <AuditFilters
          filters={activeFilters}
          onFiltersChange={mockOnChange}
        />
      );

      fireEvent.click(screen.getByTestId('clear-filters-btn'));

      expect(mockOnChange).toHaveBeenCalledWith({ limit: 25 });
    });
  });

  describe('Event Type Options', () => {
    it('includes all event types in dropdown', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      const select = screen.getByTestId('event-type-select');

      expect(select).toContainHTML('notification.created');
      expect(select).toContainHTML('delivery.started');
      expect(select).toContainHTML('delivery.succeeded');
      expect(select).toContainHTML('delivery.failed');
      expect(select).toContainHTML('ack.received');
      expect(select).toContainHTML('escalation.triggered');
    });
  });

  describe('Autonomy Mode Options', () => {
    it('includes all autonomy modes in dropdown', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      const select = screen.getByTestId('autonomy-mode-select');

      expect(select).toContainHTML('PREVIEW');
      expect(select).toContainHTML('SHADOW');
      expect(select).toContainHTML('LIVE');
    });
  });

  describe('Styling', () => {
    it('uses Tailwind CSS classes', () => {
      render(
        <AuditFilters
          filters={defaultFilters}
          onFiltersChange={() => {}}
        />
      );

      const container = screen.getByTestId('audit-filters');
      expect(container.className).toContain('bg-white');
      expect(container.className).toContain('rounded-lg');
      expect(container.className).toContain('shadow');
    });
  });
});

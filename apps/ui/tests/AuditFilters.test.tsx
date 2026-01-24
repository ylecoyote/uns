/**
 * Tests for AuditFilters component.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuditFilters } from '../src/components/AuditFilters';
import type { AuditEventFilter } from '../src/types/api';

describe('AuditFilters', () => {
  const defaultFilter: AuditEventFilter = { limit: 25 };

  it('renders filter controls', () => {
    render(<AuditFilters filter={defaultFilter} onFilterChange={vi.fn()} />);

    expect(screen.getByTestId('audit-filters')).toBeInTheDocument();
    expect(screen.getByTestId('event-type-select')).toBeInTheDocument();
    expect(screen.getByTestId('autonomy-mode-select')).toBeInTheDocument();
    expect(screen.getByTestId('notification-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('agent-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('correlation-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('start-time-input')).toBeInTheDocument();
    expect(screen.getByTestId('end-time-input')).toBeInTheDocument();
  });

  it('renders apply and clear buttons', () => {
    render(<AuditFilters filter={defaultFilter} onFilterChange={vi.fn()} />);

    expect(screen.getByTestId('apply-filters-btn')).toBeInTheDocument();
    expect(screen.getByTestId('clear-filters-btn')).toBeInTheDocument();
  });

  it('calls onFilterChange when apply is clicked', () => {
    const onFilterChange = vi.fn();
    render(<AuditFilters filter={defaultFilter} onFilterChange={onFilterChange} />);

    // Select an event type
    const eventTypeSelect = screen.getByTestId('event-type-select');
    fireEvent.change(eventTypeSelect, { target: { value: 'delivery.succeeded' } });

    // Click apply
    const applyBtn = screen.getByTestId('apply-filters-btn');
    fireEvent.click(applyBtn);

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: 'delivery.succeeded',
      })
    );
  });

  it('clears filters when clear is clicked', () => {
    const onFilterChange = vi.fn();
    const filterWithValues: AuditEventFilter = {
      limit: 25,
      event_type: 'delivery.succeeded',
      autonomy_mode: 'LIVE',
    };

    render(<AuditFilters filter={filterWithValues} onFilterChange={onFilterChange} />);

    const clearBtn = screen.getByTestId('clear-filters-btn');
    fireEvent.click(clearBtn);

    expect(onFilterChange).toHaveBeenCalledWith({ limit: 25 });
  });

  it('shows all event type options', () => {
    render(<AuditFilters filter={defaultFilter} onFilterChange={vi.fn()} />);

    const select = screen.getByTestId('event-type-select');
    const options = select.querySelectorAll('option');

    // Should have "All Events" plus 12 event types
    expect(options.length).toBe(13);
    expect(options[0]).toHaveTextContent('All Events');
  });

  it('shows all autonomy mode options', () => {
    render(<AuditFilters filter={defaultFilter} onFilterChange={vi.fn()} />);

    const select = screen.getByTestId('autonomy-mode-select');
    const options = select.querySelectorAll('option');

    // Should have "All Modes" plus 3 modes
    expect(options.length).toBe(4);
    expect(options[0]).toHaveTextContent('All Modes');
    expect(options[1]).toHaveTextContent('Preview');
    expect(options[2]).toHaveTextContent('Shadow');
    expect(options[3]).toHaveTextContent('Live');
  });

  it('updates notification ID input', () => {
    const onFilterChange = vi.fn();
    render(<AuditFilters filter={defaultFilter} onFilterChange={onFilterChange} />);

    const input = screen.getByTestId('notification-id-input');
    fireEvent.change(input, { target: { value: '123e4567-e89b-12d3-a456-426614174000' } });

    const applyBtn = screen.getByTestId('apply-filters-btn');
    fireEvent.click(applyBtn);

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        notification_id: '123e4567-e89b-12d3-a456-426614174000',
      })
    );
  });

  it('updates agent ID input', () => {
    const onFilterChange = vi.fn();
    render(<AuditFilters filter={defaultFilter} onFilterChange={onFilterChange} />);

    const input = screen.getByTestId('agent-id-input');
    fireEvent.change(input, { target: { value: 'agent-uuid' } });

    const applyBtn = screen.getByTestId('apply-filters-btn');
    fireEvent.click(applyBtn);

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        agent_id: 'agent-uuid',
      })
    );
  });

  it('updates correlation ID input', () => {
    const onFilterChange = vi.fn();
    render(<AuditFilters filter={defaultFilter} onFilterChange={onFilterChange} />);

    const input = screen.getByTestId('correlation-id-input');
    fireEvent.change(input, { target: { value: 'corr-123' } });

    const applyBtn = screen.getByTestId('apply-filters-btn');
    fireEvent.click(applyBtn);

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({
        correlation_id: 'corr-123',
      })
    );
  });
});

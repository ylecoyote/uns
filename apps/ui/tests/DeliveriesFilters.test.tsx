/**
 * Tests for DeliveriesFilters component.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeliveriesFilters } from '../src/components/DeliveriesFilters';
import type { DeliveryFilter } from '../src/types/api';

describe('DeliveriesFilters', () => {
  const defaultFilter: DeliveryFilter = { limit: 25 };
  const mockOnFilterChange = vi.fn();

  beforeEach(() => {
    mockOnFilterChange.mockReset();
  });

  it('renders all filter controls', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    expect(screen.getByTestId('deliveries-filters')).toBeInTheDocument();
    expect(screen.getByTestId('status-select')).toBeInTheDocument();
    expect(screen.getByTestId('intent-select')).toBeInTheDocument();
    expect(screen.getByTestId('delivery-mode-select')).toBeInTheDocument();
    expect(screen.getByTestId('autonomy-mode-select')).toBeInTheDocument();
    expect(screen.getByTestId('channel-select')).toBeInTheDocument();
    expect(screen.getByTestId('notification-type-input')).toBeInTheDocument();
    expect(screen.getByTestId('agent-id-input')).toBeInTheDocument();
    expect(screen.getByTestId('limit-select')).toBeInTheDocument();
  });

  it('renders apply and clear buttons', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    expect(screen.getByTestId('apply-filters-btn')).toBeInTheDocument();
    expect(screen.getByTestId('clear-filters-btn')).toBeInTheDocument();
  });

  it('calls onFilterChange when apply is clicked', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    fireEvent.click(screen.getByTestId('apply-filters-btn'));

    expect(mockOnFilterChange).toHaveBeenCalledTimes(1);
  });

  it('calls onFilterChange with cleared filter when clear is clicked', () => {
    const filterWithValues: DeliveryFilter = {
      limit: 25,
      status: 'DELIVERED',
      intent: 'OPERATIONAL',
    };

    render(<DeliveriesFilters filter={filterWithValues} onFilterChange={mockOnFilterChange} />);

    fireEvent.click(screen.getByTestId('clear-filters-btn'));

    expect(mockOnFilterChange).toHaveBeenCalledWith({ limit: 25 });
  });

  it('has correct status options', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const statusSelect = screen.getByTestId('status-select');
    expect(statusSelect).toContainHTML('All');
    expect(statusSelect).toContainHTML('Pending');
    expect(statusSelect).toContainHTML('Delivered');
    expect(statusSelect).toContainHTML('Failed');
    expect(statusSelect).toContainHTML('Deduplicated');
    expect(statusSelect).toContainHTML('Rate Limited');
  });

  it('has correct intent options', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const intentSelect = screen.getByTestId('intent-select');
    expect(intentSelect).toContainHTML('All');
    expect(intentSelect).toContainHTML('Safety');
    expect(intentSelect).toContainHTML('Governance');
    expect(intentSelect).toContainHTML('Operational');
    expect(intentSelect).toContainHTML('Informational');
  });

  it('has correct delivery mode options', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const modeSelect = screen.getByTestId('delivery-mode-select');
    expect(modeSelect).toContainHTML('All');
    expect(modeSelect).toContainHTML('Guaranteed');
    expect(modeSelect).toContainHTML('Best Effort');
  });

  it('has correct autonomy mode options', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const autonomySelect = screen.getByTestId('autonomy-mode-select');
    expect(autonomySelect).toContainHTML('All');
    expect(autonomySelect).toContainHTML('Preview');
    expect(autonomySelect).toContainHTML('Shadow');
    expect(autonomySelect).toContainHTML('Live');
  });

  it('has correct channel options', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const channelSelect = screen.getByTestId('channel-select');
    expect(channelSelect).toContainHTML('All');
    expect(channelSelect).toContainHTML('Slack');
    expect(channelSelect).toContainHTML('Email');
    expect(channelSelect).toContainHTML('WebSocket');
    expect(channelSelect).toContainHTML('PagerDuty');
  });

  it('has correct limit options', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const limitSelect = screen.getByTestId('limit-select');
    expect(limitSelect).toContainHTML('10');
    expect(limitSelect).toContainHTML('25');
    expect(limitSelect).toContainHTML('50');
    expect(limitSelect).toContainHTML('100');
  });

  it('updates filter value when select changes', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const statusSelect = screen.getByTestId('status-select');
    fireEvent.change(statusSelect, { target: { value: 'DELIVERED' } });

    fireEvent.click(screen.getByTestId('apply-filters-btn'));

    expect(mockOnFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'DELIVERED' })
    );
  });

  it('updates filter value when text input changes', () => {
    render(<DeliveriesFilters filter={defaultFilter} onFilterChange={mockOnFilterChange} />);

    const notificationTypeInput = screen.getByTestId('notification-type-input');
    fireEvent.change(notificationTypeInput, { target: { value: 'order.placed' } });

    fireEvent.click(screen.getByTestId('apply-filters-btn'));

    expect(mockOnFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ notification_type: 'order.placed' })
    );
  });

  it('displays initial filter values', () => {
    const filterWithValues: DeliveryFilter = {
      limit: 50,
      status: 'FAILED',
      notification_type: 'trading.alert',
    };

    render(<DeliveriesFilters filter={filterWithValues} onFilterChange={mockOnFilterChange} />);

    expect(screen.getByTestId('status-select')).toHaveValue('FAILED');
    expect(screen.getByTestId('notification-type-input')).toHaveValue('trading.alert');
    expect(screen.getByTestId('limit-select')).toHaveValue('50');
  });
});

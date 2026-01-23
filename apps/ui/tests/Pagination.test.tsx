/**
 * Tests for Pagination component.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Pagination } from '../src/components/Pagination';
import type { PaginationInfo } from '../src/types/api';

describe('Pagination', () => {
  const paginationWithMore: PaginationInfo = {
    next_cursor: 'cursor-123',
    has_more: true,
    total_count: 100,
  };

  const paginationNoMore: PaginationInfo = {
    next_cursor: null,
    has_more: false,
    total_count: 25,
  };

  it('renders pagination info', () => {
    render(
      <Pagination
        pagination={paginationWithMore}
        isLoading={false}
        onLoadMore={vi.fn()}
        itemCount={25}
      />
    );

    expect(screen.getByTestId('pagination')).toBeInTheDocument();
    expect(screen.getByText(/Showing 25 events of 100/)).toBeInTheDocument();
  });

  it('renders load more button when has_more is true', () => {
    render(
      <Pagination
        pagination={paginationWithMore}
        isLoading={false}
        onLoadMore={vi.fn()}
        itemCount={25}
      />
    );

    expect(screen.getByTestId('load-more-btn')).toBeInTheDocument();
    expect(screen.getByText('Load More')).toBeInTheDocument();
  });

  it('does not render load more button when has_more is false', () => {
    render(
      <Pagination
        pagination={paginationNoMore}
        isLoading={false}
        onLoadMore={vi.fn()}
        itemCount={25}
      />
    );

    expect(screen.queryByTestId('load-more-btn')).not.toBeInTheDocument();
  });

  it('calls onLoadMore when button is clicked', () => {
    const onLoadMore = vi.fn();
    render(
      <Pagination
        pagination={paginationWithMore}
        isLoading={false}
        onLoadMore={onLoadMore}
        itemCount={25}
      />
    );

    const button = screen.getByTestId('load-more-btn');
    fireEvent.click(button);

    expect(onLoadMore).toHaveBeenCalled();
  });

  it('disables button when loading', () => {
    render(
      <Pagination
        pagination={paginationWithMore}
        isLoading={true}
        onLoadMore={vi.fn()}
        itemCount={25}
      />
    );

    const button = screen.getByTestId('load-more-btn');
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Loading...');
  });

  it('renders null when pagination is null', () => {
    const { container } = render(
      <Pagination
        pagination={null}
        isLoading={false}
        onLoadMore={vi.fn()}
        itemCount={0}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('handles singular event count', () => {
    render(
      <Pagination
        pagination={paginationNoMore}
        isLoading={false}
        onLoadMore={vi.fn()}
        itemCount={1}
      />
    );

    expect(screen.getByText(/Showing 1 event/)).toBeInTheDocument();
    expect(screen.queryByText(/events/)).not.toBeInTheDocument();
  });

  it('shows count without total when total_count is undefined', () => {
    const paginationNoTotal: PaginationInfo = {
      next_cursor: null,
      has_more: false,
    };

    render(
      <Pagination
        pagination={paginationNoTotal}
        isLoading={false}
        onLoadMore={vi.fn()}
        itemCount={10}
      />
    );

    expect(screen.getByText('Showing 10 events')).toBeInTheDocument();
    expect(screen.queryByText(/of/)).not.toBeInTheDocument();
  });
});

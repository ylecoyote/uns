/**
 * Tests for PlaceholderPage component.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlaceholderPage } from '../src/pages/PlaceholderPage';

describe('PlaceholderPage', () => {
  it('renders title', () => {
    render(<PlaceholderPage title="Test Page" description="Test description" />);
    expect(screen.getByRole('heading', { name: 'Test Page' })).toBeInTheDocument();
  });

  it('renders description', () => {
    render(<PlaceholderPage title="Test Page" description="Test description" />);
    expect(screen.getByText('Test description')).toBeInTheDocument();
  });

  it('shows not implemented message', () => {
    render(<PlaceholderPage title="Test Page" description="Test description" />);
    expect(screen.getByText('Page not yet implemented.')).toBeInTheDocument();
  });

  it('has placeholder-page class', () => {
    const { container } = render(
      <PlaceholderPage title="Test Page" description="Test description" />
    );
    expect(container.querySelector('.placeholder-page')).toBeInTheDocument();
  });

  it('has placeholder-note class on note', () => {
    const { container } = render(
      <PlaceholderPage title="Test Page" description="Test description" />
    );
    expect(container.querySelector('.placeholder-note')).toBeInTheDocument();
  });
});

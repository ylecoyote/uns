/**
 * Tests for DocsPage (/docs) - In-Portal Documentation & Runbooks Workspace.
 *
 * Verifies:
 * - Rendering the Overview & Visual Grammar section by default (including Modernist delivery vs. response badges, ACK PENDING, RESOLVED, and Profile Banner)
 * - Switching sections via the left navigation rail (workflows, state-machines, integration, runbooks, all)
 * - Deep-linking via /docs?section=runbooks, /docs?section=integration, and ?q= search query initialization
 * - Filtering content across all sections using the keyword search input (docs-search-input) and clearing search (docs-search-clear)
 * - Hardened TSG-01..TSG-06 commands, Runbook Environment Setup preamble, and Open in Console action links
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { DocsPage } from '../src/pages/DocsPage';

function renderDocsPage(initialEntry = '/docs') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/docs" element={<DocsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('DocsPage', () => {
  it('renders the Overview & Visual Grammar section by default with Modernist delivery vs. response badges and profile banner docs', () => {
    renderDocsPage('/docs');

    expect(screen.getByText('Documentation & Runbooks')).toBeInTheDocument();
    expect(screen.getByTestId('docs-section-overview')).toBeInTheDocument();
    expect(screen.queryByTestId('docs-section-workflows')).not.toBeInTheDocument();

    // Verify capability pills, Profile Banner, & BroadcastChannel handshake documentation
    expect(screen.getByText('OPERATOR')).toBeInTheDocument();
    expect(screen.getByText('RESPONDER')).toBeInTheDocument();
    expect(screen.getByText('PRODUCER')).toBeInTheDocument();
    expect(screen.getByText('READ-ONLY')).toBeInTheDocument();
    expect(
      screen.getByText('Profile & Mode Banner (LOCAL RECORDING MODE vs. Live External Delivery)')
    ).toBeInTheDocument();
    expect(screen.getAllByText('UNS_SESSION_REQUEST').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('UNS_SESSION_GRANT')).toBeInTheDocument();
    expect(screen.getByText('UNS_SESSION_SYNC')).toBeInTheDocument();
    expect(screen.getByText('UNS_SESSION_EXPIRE')).toBeInTheDocument();
    expect(screen.getByText('UNS_SESSION_CLEAR')).toBeInTheDocument();

    // Verify live Modernist badge visual grammar table (Filled Delivery vs. Outlined Response + RESOLVED)
    const badgeTable = screen.getByTestId('docs-badge-grammar-table');
    expect(badgeTable).toBeInTheDocument();
    expect(within(badgeTable).getAllByText('DELIVERED')[0]).toHaveClass('badge', 'tag-delivery-ok');
    expect(within(badgeTable).getAllByText('DEAD-LETTER')[0]).toHaveClass(
      'badge',
      'tag-delivery-fail'
    );
    expect(within(badgeTable).getAllByText('DEDUPLICATED')[0]).toHaveClass(
      'badge',
      'tag-delivery-info'
    );
    expect(within(badgeTable).getAllByText('ACKED')[0]).toHaveClass('badge', 'tag-response-ok');
    expect(within(badgeTable).getAllByText('DISMISSED')[0]).toHaveClass(
      'badge',
      'tag-response-warn'
    );
    expect(within(badgeTable).getAllByText('ACK TIMEOUT')[0]).toHaveClass(
      'badge',
      'tag-response-fail'
    );
    expect(within(badgeTable).getAllByText('ACK PENDING')[0]).toHaveClass(
      'badge',
      'tag-response-none'
    );
    expect(within(badgeTable).getAllByText('RESOLVED')[0]).toHaveClass('badge', 'tag-response-ok');
  });

  it('switches sections via the left navigation rail (workflows, state-machines, integration, runbooks)', () => {
    renderDocsPage('/docs');

    // Switch to 2. Console Surfaces & Workflows
    fireEvent.click(screen.getByTestId('docs-nav-workflows'));
    expect(screen.getByTestId('docs-section-workflows')).toBeInTheDocument();
    expect(screen.queryByTestId('docs-section-overview')).not.toBeInTheDocument();
    expect(
      screen.getByText('Deliveries & Obligation Triage (/deliveries & /deliveries/:id)')
    ).toBeInTheDocument();
    expect(screen.getByText(/withholds direct ACK\/Dismiss buttons/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Deliveries Explorer/i })).toHaveAttribute(
      'href',
      '/deliveries'
    );
    expect(screen.getByRole('link', { name: /Open Policy Workspace/i })).toHaveAttribute(
      'href',
      '/policy'
    );
    expect(screen.getByRole('link', { name: /Open Operations Workspace/i })).toHaveAttribute(
      'href',
      '/operations'
    );
    expect(screen.getByRole('link', { name: /Open Audit Timeline/i })).toHaveAttribute(
      'href',
      '/audit'
    );
    expect(screen.getByRole('link', { name: /Open System Invariants/i })).toHaveAttribute(
      'href',
      '/invariants'
    );

    // Switch to 3. Architecture & State Machines
    fireEvent.click(screen.getByTestId('docs-nav-state-machines'));
    expect(screen.getByTestId('docs-section-state-machines')).toBeInTheDocument();
    expect(
      screen.getByText('Delivery & Deduplication State Machine (uns_notifications.status)')
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Obligation Acknowledgment State Machine & Timeout Unit Contract (ack_timeout_minutes vs. ack_timeout_seconds)'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText('System Invariants (INV-UI-001) & Runtime Remediation Guarantees (F-01–F-08)')
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Filter: PENDING/i })).toHaveAttribute(
      'href',
      '/deliveries?status=PENDING'
    );

    // Switch to 4. Producer, MIP & Agent MCP
    fireEvent.click(screen.getByTestId('docs-nav-integration'));
    expect(screen.getByTestId('docs-section-integration')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Python uns.Runtime / uns.Client & Market Insights Platform (mip-uns) Integration'
      )
    ).toBeInTheDocument();

    // Switch to 5. Incident Runbooks (TSG-01–06)
    fireEvent.click(screen.getByTestId('docs-nav-runbooks'));
    expect(screen.getByTestId('docs-section-runbooks')).toBeInTheDocument();
    expect(
      screen.getByText('Runbook Environment Setup & Shell Bootstrap Preamble')
    ).toBeInTheDocument();
    expect(
      screen.getByText('TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay')
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'TSG-06: SQLite WAL Retention Maintenance (uns-maintain) & Verified Online Backups (uns-maintain-and-backup.sh)'
      )
    ).toBeInTheDocument();
    expect(screen.getByTestId('docs-action-runbook-tsg-01')).toHaveAttribute('href', '/operations');
    expect(screen.getByTestId('docs-action-runbook-tsg-04')).toHaveAttribute('href', '/policy');
  });

  it('supports deep-linking via /docs?section=runbooks, /docs?section=integration, and ?q= query parameter', () => {
    const { unmount } = renderDocsPage('/docs?section=runbooks');
    expect(screen.getByTestId('docs-section-runbooks')).toBeInTheDocument();
    expect(screen.queryByTestId('docs-section-overview')).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'TSG-02: Delivery Leases, Worker Crash Recovery & UNKNOWN SMTP Provider Effects'
      )
    ).toBeInTheDocument();
    unmount();

    const { unmount: unmount2 } = renderDocsPage('/docs?section=integration');
    expect(screen.getByTestId('docs-section-integration')).toBeInTheDocument();
    expect(screen.queryByTestId('docs-section-runbooks')).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'WebSocket Subprotocol Auth, MCP Server (uns-mcp) & Opt-In Channel Smoke Verifier'
      )
    ).toBeInTheDocument();
    unmount2();

    // Deep-link with ?q=TSG-04 pre-populates search input and filters to TSG-04 & effective_hash topics
    renderDocsPage('/docs?section=runbooks&q=TSG-04');
    expect(screen.getByTestId('docs-search-input')).toHaveValue('TSG-04');
    expect(
      screen.getByText(
        'TSG-04: Policy Lifecycle, Revision Governance, Content Hashing & Override Rejections'
      )
    ).toBeInTheDocument();
    expect(
      screen.queryByText('TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay')
    ).not.toBeInTheDocument();
  });

  it('filters content across all sections using the keyword search input and clears search', () => {
    renderDocsPage('/docs');

    const searchInput = screen.getByTestId('docs-search-input');

    // Type a query that matches TSG-02 in the runbooks section while starting on overview
    fireEvent.change(searchInput, { target: { value: 'LEASE_LOST' } });

    expect(screen.getByTestId('docs-section-runbooks')).toBeInTheDocument();
    expect(
      screen.getByText(
        'TSG-02: Delivery Leases, Worker Crash Recovery & UNKNOWN SMTP Provider Effects'
      )
    ).toBeInTheDocument();
    expect(screen.queryByTestId('docs-section-overview')).not.toBeInTheDocument();

    // Type a query that matches no topics
    fireEvent.change(searchInput, { target: { value: 'nonexistent-xyz-999' } });
    expect(screen.getByTestId('docs-empty-state')).toBeInTheDocument();

    // Clear search via Clear button
    const clearButton = screen.getByTestId('docs-search-clear');
    fireEvent.click(clearButton);

    expect(searchInput).toHaveValue('');
    expect(screen.queryByTestId('docs-empty-state')).not.toBeInTheDocument();
    // Because searching switched section to 'all', all 5 sections are now visible
    expect(screen.getByTestId('docs-section-overview')).toBeInTheDocument();
    expect(screen.getByTestId('docs-section-runbooks')).toBeInTheDocument();
  });
});

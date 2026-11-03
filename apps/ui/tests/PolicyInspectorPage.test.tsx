/**
 * Tests for PolicyInspectorPage component
 *
 * These tests verify:
 * - Page renders correctly with form and empty state
 * - Form validation works correctly
 * - API integration works (success and error cases)
 * - Resolution trace is displayed correctly
 * - Clear functionality works
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PolicyInspectorPage } from '../src/pages/PolicyInspectorPage';
import { clearConsoleSession, startConsoleSession } from '../src/auth/session';
import * as api from '../src/api/policies';

// Mock the API module
vi.mock('../src/api/policies');

const mockEffectivePolicyResponse = {
  notification_type: 'trading.order_placed',
  effective: {
    delivery_mode: 'GUARANTEED' as const,
    channels: ['SLACK' as const, 'EMAIL' as const],
    require_ack: true,
    ack_timeout_minutes: 60,
    dedup_window_seconds: 300,
  },
  resolution: {
    delivery_mode: [
      { source: 'explicit_override' as const, value: null, applied: false, reason: 'No override set' },
      { source: 'mode_override' as const, value: null, applied: false, reason: 'No mode override' },
      { source: 'policy_base' as const, value: 'GUARANTEED', applied: true, reason: null },
      { source: 'sdk_default' as const, value: 'BEST_EFFORT', applied: false, reason: null },
    ],
    channels: [
      { source: 'explicit_override' as const, value: null, applied: false, reason: null },
      { source: 'mode_override' as const, value: null, applied: false, reason: null },
      { source: 'policy_base' as const, value: ['SLACK', 'EMAIL'], applied: true, reason: null },
      { source: 'sdk_default' as const, value: ['WEBSOCKET'], applied: false, reason: null },
    ],
    require_ack: [
      { source: 'explicit_override' as const, value: null, applied: false, reason: null },
      { source: 'mode_override' as const, value: null, applied: false, reason: null },
      { source: 'policy_base' as const, value: true, applied: true, reason: null },
      { source: 'sdk_default' as const, value: false, applied: false, reason: null },
    ],
    ack_timeout_minutes: [
      { source: 'explicit_override' as const, value: null, applied: false, reason: null },
      { source: 'mode_override' as const, value: null, applied: false, reason: null },
      { source: 'policy_base' as const, value: 60, applied: true, reason: null },
      { source: 'sdk_default' as const, value: null, applied: false, reason: null },
    ],
    dedup_window_seconds: [
      { source: 'explicit_override' as const, value: null, applied: false, reason: null },
      { source: 'mode_override' as const, value: null, applied: false, reason: null },
      { source: 'policy_base' as const, value: 300, applied: true, reason: null },
      { source: 'sdk_default' as const, value: 60, applied: false, reason: null },
    ],
  },
  resolution_context: {
    intent: 'GOVERNANCE' as const,
    autonomy_mode: 'LIVE' as const,
    irreversible: false,
    policy_found: true,
    policy_notification_type: 'trading.order_placed',
  },
};

describe('PolicyInspectorPage', () => {
  beforeEach(() => {
    vi.mocked(api.fetchEffectivePolicy).mockResolvedValue(mockEffectivePolicyResponse);
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('Initial render', () => {
    it('renders page title and description', () => {
      render(<PolicyInspectorPage />);

      expect(screen.getByText('Policy Inspector')).toBeInTheDocument();
      expect(screen.getByText(/View effective policy values/)).toBeInTheDocument();
    });

    it('renders the form with all fields', () => {
      render(<PolicyInspectorPage />);

      expect(screen.getByLabelText('Notification Type')).toBeInTheDocument();
      expect(screen.getByLabelText('Intent')).toBeInTheDocument();
      expect(screen.getByLabelText('Autonomy Mode')).toBeInTheDocument();
      expect(screen.getByText('Irreversible Action')).toBeInTheDocument();
    });

    it('renders empty state initially', () => {
      render(<PolicyInspectorPage />);

      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(
        screen.getByText(/Enter a notification type and click "Inspect Policy"/)
      ).toBeInTheDocument();
    });
  });

  describe('Form validation', () => {
    it('shows error when notification type is empty', async () => {
      render(<PolicyInspectorPage />);

      fireEvent.click(screen.getByTestId('inspect-btn'));

      await waitFor(() => {
        expect(screen.getByText('Notification type is required')).toBeInTheDocument();
      });

      expect(api.fetchEffectivePolicy).not.toHaveBeenCalled();
    });

    it('shows error when notification type is only whitespace', async () => {
      render(<PolicyInspectorPage />);

      const input = screen.getByTestId('notification-type-input');
      fireEvent.change(input, { target: { value: '   ' } });
      fireEvent.click(screen.getByTestId('inspect-btn'));

      await waitFor(() => {
        expect(screen.getByText('Notification type is required')).toBeInTheDocument();
      });

      expect(api.fetchEffectivePolicy).not.toHaveBeenCalled();
    });
  });

  describe('API integration', () => {
    it('calls API with correct parameters', async () => {
      render(<PolicyInspectorPage />);

      // Fill in the form
      fireEvent.change(screen.getByTestId('notification-type-input'), {
        target: { value: 'trading.order_placed' },
      });
      fireEvent.change(screen.getByTestId('intent-select'), {
        target: { value: 'GOVERNANCE' },
      });
      fireEvent.change(screen.getByTestId('autonomy-mode-select'), {
        target: { value: 'LIVE' },
      });
      fireEvent.click(screen.getByTestId('irreversible-checkbox'));

      // Submit the form
      fireEvent.click(screen.getByTestId('inspect-btn'));

      await waitFor(() => {
        expect(api.fetchEffectivePolicy).toHaveBeenCalledWith(
          {
            notification_type: 'trading.order_placed',
            intent: 'GOVERNANCE',
            autonomy_mode: 'LIVE',
            irreversible: true,
          },
          { requestId: undefined }
        );
      });
    });

    it('displays resolution trace on success', async () => {
      render(<PolicyInspectorPage />);

      fireEvent.change(screen.getByTestId('notification-type-input'), {
        target: { value: 'trading.order_placed' },
      });
      fireEvent.click(screen.getByTestId('inspect-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('resolution-trace-display')).toBeInTheDocument();
      });

      // Check resolution context section contains expected values
      const contextSection = screen.getByTestId('resolution-context');
      expect(contextSection).toHaveTextContent('GOVERNANCE');
      expect(contextSection).toHaveTextContent('LIVE');

      // Check effective policy section contains expected values
      const effectiveSection = screen.getByTestId('effective-policy');
      expect(effectiveSection).toHaveTextContent('GUARANTEED');
      expect(effectiveSection).toHaveTextContent('SLACK, EMAIL');
    });

    it('displays error state on API failure', async () => {
      const mockError = {
        message: 'Network error',
        code: 'network_error',
        requestId: 'req-123',
      };
      vi.mocked(api.fetchEffectivePolicy).mockRejectedValue(mockError);

      render(<PolicyInspectorPage />);

      fireEvent.change(screen.getByTestId('notification-type-input'), {
        target: { value: 'test.type' },
      });
      fireEvent.click(screen.getByTestId('inspect-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toBeInTheDocument();
        expect(screen.getByText('Network error')).toBeInTheDocument();
        expect(screen.getByText(/Code: network_error/)).toBeInTheDocument();
        expect(screen.getByText(/Request ID: req-123/)).toBeInTheDocument();
      });
    });

    it('shows loading state while fetching', async () => {
      vi.mocked(api.fetchEffectivePolicy).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockEffectivePolicyResponse), 100))
      );

      render(<PolicyInspectorPage />);

      fireEvent.change(screen.getByTestId('notification-type-input'), {
        target: { value: 'test.type' },
      });
      fireEvent.click(screen.getByTestId('inspect-btn'));

      expect(screen.getByTestId('loading-state')).toBeInTheDocument();
      expect(screen.getByText('Resolving policy...')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.queryByTestId('loading-state')).not.toBeInTheDocument();
      });
    });
  });

  describe('Clear functionality', () => {
    it('clears form and results when Clear is clicked', async () => {
      render(<PolicyInspectorPage />);

      // Fill in and submit form
      fireEvent.change(screen.getByTestId('notification-type-input'), {
        target: { value: 'trading.order_placed' },
      });
      fireEvent.change(screen.getByTestId('intent-select'), {
        target: { value: 'GOVERNANCE' },
      });
      fireEvent.click(screen.getByTestId('inspect-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('resolution-trace-display')).toBeInTheDocument();
      });

      // Click clear
      fireEvent.click(screen.getByTestId('clear-btn'));

      // Check form is cleared
      expect(screen.getByTestId('notification-type-input')).toHaveValue('');
      expect(screen.getByTestId('intent-select')).toHaveValue('INFORMATIONAL');
      expect(screen.getByTestId('autonomy-mode-select')).toHaveValue('PREVIEW');
      expect(screen.getByTestId('irreversible-checkbox')).not.toBeChecked();

      // Check results are cleared
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });
});

describe('PolicyInspectorForm', () => {
  beforeEach(() => {
    vi.mocked(api.fetchEffectivePolicy).mockResolvedValue(mockEffectivePolicyResponse);
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('has correct default values', () => {
    render(<PolicyInspectorPage />);

    expect(screen.getByTestId('notification-type-input')).toHaveValue('');
    expect(screen.getByTestId('intent-select')).toHaveValue('INFORMATIONAL');
    expect(screen.getByTestId('autonomy-mode-select')).toHaveValue('PREVIEW');
    expect(screen.getByTestId('irreversible-checkbox')).not.toBeChecked();
  });

  it('disables buttons while loading', async () => {
    vi.mocked(api.fetchEffectivePolicy).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockEffectivePolicyResponse), 100))
    );

    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'test.type' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    expect(screen.getByTestId('inspect-btn')).toBeDisabled();
    expect(screen.getByTestId('clear-btn')).toBeDisabled();
    expect(screen.getByText('Inspecting...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('inspect-btn')).not.toBeDisabled();
    });
  });
});

describe('ResolutionTraceDisplay', () => {
  beforeEach(() => {
    vi.mocked(api.fetchEffectivePolicy).mockResolvedValue(mockEffectivePolicyResponse);
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('displays notification type in header', async () => {
    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('resolution-trace-display')).toBeInTheDocument();
    });

    // Check that the notification type appears in the header
    const header = screen.getByTestId('resolution-trace-display').querySelector('.resolution-header');
    expect(header).toHaveTextContent('trading.order_placed');
  });

  it('displays resolution context values', async () => {
    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('resolution-context')).toBeInTheDocument();
    });

    // Check context section exists with values
    const contextSection = screen.getByTestId('resolution-context');
    expect(contextSection).toHaveTextContent('Intent');
    expect(contextSection).toHaveTextContent('Autonomy Mode');
    expect(contextSection).toHaveTextContent('Irreversible');
    expect(contextSection).toHaveTextContent('Policy Found');
  });

  it('displays effective policy values', async () => {
    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('effective-policy')).toBeInTheDocument();
    });

    // Check effective policy section contains field labels
    const effectiveSection = screen.getByTestId('effective-policy');
    expect(effectiveSection).toHaveTextContent('Delivery Mode');
    expect(effectiveSection).toHaveTextContent('Channels');
    expect(effectiveSection).toHaveTextContent('Require Acknowledgment');
  });

  it('displays resolution trace for each field', async () => {
    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('resolution-trace')).toBeInTheDocument();
    });

    // Check field resolution sections exist
    expect(screen.getByTestId('field-resolution-delivery_mode')).toBeInTheDocument();
    expect(screen.getByTestId('field-resolution-channels')).toBeInTheDocument();
    expect(screen.getByTestId('field-resolution-require_ack')).toBeInTheDocument();
  });

  it('shows resolution steps with correct status', async () => {
    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('resolution-trace')).toBeInTheDocument();
    });

    // Check that resolution steps are rendered
    const steps = screen.getAllByTestId('resolution-step');
    expect(steps.length).toBeGreaterThan(0);

    // Check for APPLIED and SKIPPED status badges
    expect(screen.getAllByText('APPLIED').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SKIPPED').length).toBeGreaterThan(0);
  });

  it('displays source labels correctly', async () => {
    render(<PolicyInspectorPage />);

    fireEvent.change(screen.getByTestId('notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.click(screen.getByTestId('inspect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('resolution-trace')).toBeInTheDocument();
    });

    // Check source labels are displayed
    expect(screen.getAllByText('Explicit Override').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mode Override').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Policy Base').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SDK Default').length).toBeGreaterThan(0);
  });
});

describe('PolicyWorkspace Surface 4 (Catalog, Deep-Link, Simulator, Tagged Test Send, Reload)', () => {
  beforeEach(() => {
    clearConsoleSession();
    vi.mocked(api.fetchEffectivePolicy).mockResolvedValue(mockEffectivePolicyResponse);
    vi.mocked(api.fetchActivePolicies).mockResolvedValue({
      total_count: 1,
      items: [
        {
          notification_type: 'trading.order_placed',
          version: '1.0.0',
          status: 'ACTIVE',
          intent: 'GOVERNANCE',
          channels: ['SLACK', 'EMAIL'],
          delivery_mode: 'GUARANTEED',
          require_ack: true,
          ack_timeout_minutes: 60,
          ack_timeout_seconds: 3600,
          dedup_window_seconds: 300,
        },
      ],
    });
  });

  afterEach(() => {
    clearConsoleSession();
    vi.resetAllMocks();
  });

  it('auto-populates and inspects with catalog-resolved intent when ?notification_type= query param is present', async () => {
    render(
      <MemoryRouter initialEntries={['/policy?notification_type=trading.order_placed']}>
        <PolicyInspectorPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(api.fetchEffectivePolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          notification_type: 'trading.order_placed',
          intent: 'GOVERNANCE',
          autonomy_mode: 'LIVE',
        }),
        expect.anything()
      );
      expect(screen.getByTestId('notification-type-input')).toHaveValue('trading.order_placed');
      expect(screen.getByTestId('intent-select')).toHaveValue('GOVERNANCE');
    });
  });

  it('populates inspector and simulator when clicking a row in the Active Policies Catalog', async () => {
    startConsoleSession('producer-key', {
      subject: 'producer-user',
      scopes: ['observer', 'producer'],
      auth_mode: 'required',
    });

    render(
      <MemoryRouter initialEntries={['/policy']}>
        <PolicyInspectorPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('active-policy-row-trading.order_placed')
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('active-policy-row-trading.order_placed'));

    await waitFor(() => {
      expect(api.fetchEffectivePolicy).toHaveBeenCalledWith(
        {
          notification_type: 'trading.order_placed',
          intent: 'GOVERNANCE',
          autonomy_mode: 'LIVE',
          irreversible: false,
        },
        expect.anything()
      );
    });

    expect(screen.getByTestId('sim-notification-type-input')).toHaveValue(
      'trading.order_placed'
    );
  });

  it('allows producer to run dry-run Simulate and dispatch a tagged [TEST] live notification', async () => {
    startConsoleSession('producer-key', {
      subject: 'producer-user',
      scopes: ['observer', 'producer'],
      auth_mode: 'required',
    });

    vi.mocked(api.simulateNotification).mockResolvedValue({
      notification_id: '55555555-5555-4555-8555-555555555555',
      simulated: true,
      status: 'DELIVERED',
      channels_attempted: ['SLACK'],
      delivery_mode: 'GUARANTEED',
      require_ack: true,
      dedup_key: 'sim-dedup',
      dedup_window_seconds: 300,
      policy_source: 'policy',
      warnings: [],
      message: 'Simulated routing preview',
    });

    const dispatchedId = '77777777-7777-4777-8777-777777777777';
    vi.mocked(api.sendTestNotification).mockResolvedValue({
      notification_id: dispatchedId,
      status: 'PENDING',
      channels_attempted: ['SLACK'],
      channels_succeeded: [],
      channels_failed: [],
      require_ack: true,
      created_at: '2026-01-23T04:00:00Z',
      message: 'pending',
    });

    render(
      <MemoryRouter initialEntries={['/policy']}>
        <PolicyInspectorPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByTestId('sim-notification-type-input'), {
      target: { value: 'trading.order_placed' },
    });
    fireEvent.change(screen.getByTestId('sim-title-input'), {
      target: { value: 'Order placement check' },
    });

    // 1. Dry-run Simulate
    fireEvent.click(screen.getByTestId('simulate-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('simulation-result-card')).toBeInTheDocument();
    });
    expect(screen.getByTestId('sim-result-channels')).toHaveTextContent('SLACK');
    expect(screen.getByTestId('sim-result-delivery-mode')).toHaveTextContent('GUARANTEED');

    // 2. Tagged Live Test Send with inline confirmation
    fireEvent.click(screen.getByTestId('initiate-test-send-btn'));
    expect(screen.getByTestId('confirm-test-send-panel')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('confirm-test-send-btn'));

    await waitFor(() => {
      expect(api.sendTestNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          notification_type: 'trading.order_placed',
          title: '[TEST] Order placement check',
          source: 'uns-console-policy-test',
          metadata: {
            source: 'uns_console_policy_test',
            triggered_by: 'producer-user',
          },
        })
      );
    });

    expect(screen.getByTestId('test-send-delivery-link')).toHaveAttribute(
      'href',
      `/deliveries/${dispatchedId}`
    );
  });

  it('allows admin to atomically reload policies from server directory and refreshes catalog', async () => {
    startConsoleSession('admin-key', {
      subject: 'operator-admin',
      scopes: ['observer', 'admin'],
      auth_mode: 'required',
    });

    vi.mocked(api.reloadPolicies).mockResolvedValue({
      loaded_count: 3,
      persisted_count: 3,
      policy_count: 3,
      notification_types: ['ops.alert', 'safety.halt', 'trading.order_placed'],
    });

    render(
      <MemoryRouter initialEntries={['/policy']}>
        <PolicyInspectorPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('initiate-policy-reload-btn'));
    expect(screen.getByTestId('policy-reload-confirm-panel')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('confirm-policy-reload-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('policy-reload-result')).toBeInTheDocument();
    });

    expect(api.reloadPolicies).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('policy-reload-result')).toHaveTextContent(
      '3 loaded, 3 persisted, 3 active'
    );
  });

  it('renders Policy Revision History & Lineage with Modernist status badges, status filtering, and row selection into Inspector/Simulator', async () => {
    startConsoleSession('producer-key', {
      subject: 'producer-user',
      scopes: ['observer', 'producer'],
      auth_mode: 'required',
    });

    vi.mocked(api.fetchPolicyRevisions).mockResolvedValue({
      total_count: 4,
      items: [
        {
          notification_type: 'ops.canary_check',
          version: '0.2.0',
          status: 'DRAFT',
          config_hash: 'aaaa1111222233334444',
          intent: 'OPERATIONAL',
          channels: ['WEBSOCKET'],
          delivery_mode: 'BEST_EFFORT',
          require_ack: false,
          dedup_window_seconds: 90,
          created_at: '2026-01-23T01:00:00Z',
          updated_at: '2026-01-23T01:00:00Z',
        },
        {
          notification_type: 'trading.order_placed',
          version: '2.1.0',
          status: 'PREVIEW',
          config_hash: 'bbbb1111222233334444',
          intent: 'GOVERNANCE',
          channels: ['WEBSOCKET'],
          delivery_mode: 'BEST_EFFORT',
          require_ack: false,
          dedup_window_seconds: 60,
          created_at: '2026-01-23T03:00:00Z',
          updated_at: '2026-01-23T03:00:00Z',
        },
        {
          policy_id: 'pol-rev-200',
          notification_type: 'trading.order_placed',
          version: '2.0.0',
          status: 'ACTIVE',
          config_hash: 'cccc1111222233334444',
          previous_version_id: 'pol-rev-10000000',
          intent: 'GOVERNANCE',
          channels: ['SLACK', 'EMAIL'],
          delivery_mode: 'GUARANTEED',
          require_ack: true,
          dedup_window_seconds: 120,
          created_at: '2026-01-23T02:00:00Z',
          updated_at: '2026-01-23T02:00:00Z',
        },
        {
          policy_id: 'pol-rev-10000000',
          notification_type: 'trading.order_placed',
          version: '1.0.0',
          status: 'RETIRED',
          config_hash: 'dddd1111222233334444',
          previous_version_id: null,
          intent: 'GOVERNANCE',
          channels: ['SLACK'],
          delivery_mode: 'GUARANTEED',
          require_ack: true,
          dedup_window_seconds: 300,
          created_at: '2026-01-23T00:00:00Z',
          updated_at: '2026-01-23T02:00:00Z',
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={['/policy']}>
        <PolicyInspectorPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('policy-revisions-section')).toBeInTheDocument();
    });

    // Verify Modernist badge visual grammar per status
    expect(
      screen.getByTestId('policy-revision-status-trading.order_placed-2.0.0')
    ).toHaveClass('tag-delivery-ok');
    expect(
      screen.getByTestId('policy-revision-status-trading.order_placed-2.1.0')
    ).toHaveClass('tag-delivery-pending');
    expect(
      screen.getByTestId('policy-revision-status-ops.canary_check-0.2.0')
    ).toHaveClass('tag-delivery-pending');
    expect(
      screen.getByTestId('policy-revision-status-trading.order_placed-1.0.0')
    ).toHaveClass('badge-default');

    // Verify revision lineage column (previous_version_id vs ROOT)
    expect(
      screen.getByTestId('policy-revision-lineage-trading.order_placed-2.0.0')
    ).toHaveTextContent('Supersedes: pol-rev-...');
    expect(
      screen.getByTestId('policy-revision-lineage-trading.order_placed-1.0.0')
    ).toHaveTextContent('ROOT');

    // Filter by RETIRED using Modernist .seg segmented toggle
    fireEvent.click(screen.getByTestId('policy-status-filter-RETIRED'));
    expect(
      screen.getByTestId('policy-revision-row-trading.order_placed-1.0.0')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('policy-revision-row-trading.order_placed-2.0.0')
    ).not.toBeInTheDocument();

    // Reset filter to ALL and click PREVIEW revision to load into Inspector & Simulator
    // Policy lifecycle status PREVIEW must not be conflated with AutonomyMode PREVIEW
    fireEvent.click(screen.getByTestId('policy-status-filter-ALL'));
    fireEvent.click(
      screen.getByTestId('policy-revision-row-trading.order_placed-2.1.0')
    );

    await waitFor(() => {
      expect(api.fetchEffectivePolicy).toHaveBeenCalledWith(
        {
          notification_type: 'trading.order_placed',
          intent: 'GOVERNANCE',
          autonomy_mode: 'LIVE',
          irreversible: false,
        },
        expect.anything()
      );
    });

    expect(screen.getByTestId('sim-notification-type-input')).toHaveValue(
      'trading.order_placed'
    );
    expect(screen.getByTestId('sim-autonomy-mode-select')).toHaveValue('LIVE');
  });
});

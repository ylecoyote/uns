/**
 * Tests for routing configuration and router module.
 *
 * Verifies:
 * - Route constants are defined correctly
 * - Navigation configuration works
 * - Routes render correct components
 * - Redirects work as expected
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AppRoutes } from '../src/router';
import {
  ROUTES,
  ROUTE_CONFIGS,
  getRouteConfig,
  getNavRoutes,
  type RoutePath,
} from '../src/types/routes';

// Mock the fetch function for components that make API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock response for components that need data
const mockEmptyResponse = {
  items: [],
  pagination: { next_cursor: null, has_more: false },
};

describe('Route Constants', () => {
  it('defines HOME route', () => {
    expect(ROUTES.HOME).toBe('/');
  });

  it('defines AUDIT route', () => {
    expect(ROUTES.AUDIT).toBe('/audit');
  });

  it('defines DELIVERIES route', () => {
    expect(ROUTES.DELIVERIES).toBe('/deliveries');
  });

  it('defines POLICY route', () => {
    expect(ROUTES.POLICY).toBe('/policy');
  });

  it('defines OPERATIONS route', () => {
    expect(ROUTES.OPERATIONS).toBe('/operations');
  });

  it('defines INVARIANTS route', () => {
    expect(ROUTES.INVARIANTS).toBe('/invariants');
  });

  it('has unique route paths', () => {
    const paths = Object.values(ROUTES);
    const uniquePaths = new Set(paths);
    expect(uniquePaths.size).toBe(paths.length);
  });
});

describe('Route Configs', () => {
  it('has config for all routes except HOME', () => {
    // HOME redirects to another route, so it doesn't need a config
    const configPaths = ROUTE_CONFIGS.map((c) => c.path);
    expect(configPaths).toContain(ROUTES.AUDIT);
    expect(configPaths).toContain(ROUTES.DELIVERIES);
    expect(configPaths).toContain(ROUTES.POLICY);
    expect(configPaths).toContain(ROUTES.OPERATIONS);
    expect(configPaths).toContain(ROUTES.INVARIANTS);
  });

  it('marks AUDIT as implemented', () => {
    const config = getRouteConfig(ROUTES.AUDIT);
    expect(config?.implemented).toBe(true);
  });

  it('marks INVARIANTS as implemented', () => {
    const config = getRouteConfig(ROUTES.INVARIANTS);
    expect(config?.implemented).toBe(true);
  });

  it('marks DELIVERIES as implemented', () => {
    const config = getRouteConfig(ROUTES.DELIVERIES);
    expect(config?.implemented).toBe(true);
  });

  it('marks POLICY as implemented', () => {
    const config = getRouteConfig(ROUTES.POLICY);
    expect(config?.implemented).toBe(true);
  });

  it('marks OPERATIONS as implemented', () => {
    const config = getRouteConfig(ROUTES.OPERATIONS);
    expect(config?.implemented).toBe(true);
  });

  it('each config has required fields', () => {
    for (const config of ROUTE_CONFIGS) {
      expect(config.path).toBeDefined();
      expect(config.title).toBeDefined();
      expect(config.description).toBeDefined();
      expect(typeof config.implemented).toBe('boolean');
    }
  });
});

describe('getRouteConfig', () => {
  it('returns config for valid route', () => {
    const config = getRouteConfig(ROUTES.AUDIT);
    expect(config).toBeDefined();
    expect(config?.path).toBe(ROUTES.AUDIT);
    expect(config?.title).toBe('Audit');
  });

  it('returns undefined for invalid route', () => {
    const config = getRouteConfig('/invalid' as RoutePath);
    expect(config).toBeUndefined();
  });
});

describe('getNavRoutes', () => {
  it('returns routes sorted by navOrder', () => {
    const navRoutes = getNavRoutes();
    expect(navRoutes.length).toBe(ROUTE_CONFIGS.length);

    // Verify order based on navOrder
    for (let i = 1; i < navRoutes.length; i++) {
      const prevOrder = navRoutes[i - 1].navOrder ?? 99;
      const currOrder = navRoutes[i].navOrder ?? 99;
      expect(prevOrder).toBeLessThanOrEqual(currOrder);
    }
  });

  it('returns all navigation routes', () => {
    const navRoutes = getNavRoutes();
    expect(navRoutes.some((r) => r.path === ROUTES.AUDIT)).toBe(true);
    expect(navRoutes.some((r) => r.path === ROUTES.DELIVERIES)).toBe(true);
    expect(navRoutes.some((r) => r.path === ROUTES.POLICY)).toBe(true);
    expect(navRoutes.some((r) => r.path === ROUTES.INVARIANTS)).toBe(true);
  });

  it('does not mutate original ROUTE_CONFIGS', () => {
    const originalOrder = ROUTE_CONFIGS.map((c) => c.path);
    getNavRoutes();
    const newOrder = ROUTE_CONFIGS.map((c) => c.path);
    expect(newOrder).toEqual(originalOrder);
  });
});

describe('AppRoutes', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockEmptyResponse),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders AuditTimeline for /audit route', async () => {
    render(
      <MemoryRouter initialEntries={['/audit']}>
        <AppRoutes />
      </MemoryRouter>
    );

    // AuditTimeline renders "Audit Timeline" heading
    expect(screen.getByText('Audit Timeline')).toBeInTheDocument();
  });

  it('renders InvariantsPage for /invariants route', async () => {
    render(
      <MemoryRouter initialEntries={['/invariants']}>
        <AppRoutes />
      </MemoryRouter>
    );

    // InvariantsPage renders "System Invariants" heading
    expect(screen.getByText('System Invariants')).toBeInTheDocument();
  });

  it('renders DeliveriesListPage for /deliveries route', () => {
    render(
      <MemoryRouter initialEntries={['/deliveries']}>
        <AppRoutes />
      </MemoryRouter>
    );

    expect(screen.getByText('Deliveries')).toBeInTheDocument();
    // DeliveriesListPage shows the description instead of placeholder message
    expect(
      screen.getByText('View delivery timelines and filter by status, intent, channel, and more.')
    ).toBeInTheDocument();
    // DeliveriesListPage should show a loading state or content, not placeholder
    expect(screen.queryByText('Page not yet implemented.')).not.toBeInTheDocument();
  });

  it('renders PolicyInspectorPage for /policy route', () => {
    render(
      <MemoryRouter initialEntries={['/policy']}>
        <AppRoutes />
      </MemoryRouter>
    );

    expect(screen.getByText('Policy Inspector')).toBeInTheDocument();
    // PolicyInspectorPage should show form/content, not placeholder
    expect(screen.queryByText('Page not yet implemented.')).not.toBeInTheDocument();
  });

  it('redirects / to /audit', async () => {
    // We can't easily test Navigate redirect directly, but we can verify
    // that the AuditTimeline is rendered when we start at /
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>
    );

    // After redirect, AuditTimeline should be rendered
    expect(screen.getByText('Audit Timeline')).toBeInTheDocument();
  });

  it('redirects unknown routes to /', async () => {
    render(
      <MemoryRouter initialEntries={['/unknown-route']}>
        <AppRoutes />
      </MemoryRouter>
    );

    // After redirect chain, AuditTimeline should be rendered
    expect(screen.getByText('Audit Timeline')).toBeInTheDocument();
  });
});

describe('Implemented Pages', () => {
  it('renders DeliveriesListPage with correct title', () => {
    render(
      <MemoryRouter initialEntries={['/deliveries']}>
        <AppRoutes />
      </MemoryRouter>
    );

    expect(screen.getByText('Deliveries')).toBeInTheDocument();
  });

  it('renders PolicyInspectorPage with correct title', () => {
    render(
      <MemoryRouter initialEntries={['/policy']}>
        <AppRoutes />
      </MemoryRouter>
    );

    expect(screen.getByText('Policy Inspector')).toBeInTheDocument();
  });
});

describe('Route Type Safety', () => {
  it('ROUTES values are type-safe RoutePath', () => {
    // This is a compile-time check, but we can verify at runtime too
    const routePaths: RoutePath[] = Object.values(ROUTES);
    expect(routePaths.every((p) => typeof p === 'string')).toBe(true);
  });

  it('RouteConfig paths match ROUTES values', () => {
    const routeValues = Object.values(ROUTES);
    for (const config of ROUTE_CONFIGS) {
      expect(routeValues).toContain(config.path);
    }
  });
});

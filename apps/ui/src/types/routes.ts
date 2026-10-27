/**
 * Route type definitions and constants for type-safe routing.
 *
 * Centralizes route paths to prevent typos and enable IDE support.
 */

/**
 * Application route paths.
 * Use these constants instead of string literals for navigation.
 */
export const ROUTES = {
  /** Home/default route - redirects to audit */
  HOME: '/',

  /** Audit timeline - event stream viewer */
  AUDIT: '/audit',

  /** Deliveries explorer - delivery timeline */
  DELIVERIES: '/deliveries',

  /** Policy inspector - effective policy viewer */
  POLICY: '/policy',

  /** Operations & dead-letter recovery workspace */
  OPERATIONS: '/operations',

  /** Invariants viewer - system invariants */
  INVARIANTS: '/invariants',
} as const;

/**
 * Route path type derived from ROUTES constant.
 */
export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

/**
 * Route metadata for rendering navigation and route configuration.
 */
export interface RouteConfig {
  /** URL path */
  path: RoutePath;

  /** Display title in navigation */
  title: string;

  /** Description for placeholder pages */
  description: string;

  /** Whether the page is implemented */
  implemented: boolean;

  /** Navigation order (lower = first) */
  navOrder?: number;
}

/**
 * Route configurations for all app routes.
 * Used by router and navigation components.
 */
export const ROUTE_CONFIGS: RouteConfig[] = [
  {
    path: ROUTES.DELIVERIES,
    title: 'Deliveries',
    description: 'Delivery timeline explorer',
    implemented: true,
    navOrder: 1,
  },
  {
    path: ROUTES.POLICY,
    title: 'Policy',
    description: 'Effective policy inspector',
    implemented: true,
    navOrder: 2,
  },
  {
    path: ROUTES.OPERATIONS,
    title: 'Operations',
    description: 'Operational telemetry and dead-letter recovery',
    implemented: true,
    navOrder: 3,
  },
  {
    path: ROUTES.INVARIANTS,
    title: 'Invariants',
    description: 'System invariants viewer',
    implemented: true,
    navOrder: 4,
  },
  {
    path: ROUTES.AUDIT,
    title: 'Audit',
    description: 'Audit event stream viewer',
    implemented: true,
    navOrder: 5,
  },
];

/**
 * Get route config by path.
 */
export function getRouteConfig(path: RoutePath): RouteConfig | undefined {
  return ROUTE_CONFIGS.find((config) => config.path === path);
}

/**
 * Get routes for navigation (sorted by navOrder).
 */
export function getNavRoutes(): RouteConfig[] {
  return [...ROUTE_CONFIGS].sort((a, b) => (a.navOrder ?? 99) - (b.navOrder ?? 99));
}

/**
 * Centralized router configuration for UNS UI Dashboard.
 *
 * This module defines all application routes and provides:
 * - Route element mapping
 * - Navigation configuration
 * - Type-safe route utilities
 *
 * All pages are READ-ONLY per ui-scope.md.
 */

import { Routes, Route, Navigate } from 'react-router-dom';
import { AuditTimeline, InvariantsPage, PlaceholderPage } from './pages';
import { ROUTES, ROUTE_CONFIGS, type RouteConfig } from './types/routes';

/**
 * Get the React element for a route config.
 */
function getRouteElement(config: RouteConfig): React.ReactElement {
  if (!config.implemented) {
    return <PlaceholderPage title={config.title} description={config.description} />;
  }

  switch (config.path) {
    case ROUTES.AUDIT:
      return <AuditTimeline />;
    case ROUTES.INVARIANTS:
      return <InvariantsPage />;
    default:
      return <PlaceholderPage title={config.title} description={config.description} />;
  }
}

/**
 * AppRoutes component renders all application routes.
 *
 * Route structure:
 * - / redirects to /audit (default page)
 * - /audit - Audit event timeline
 * - /invariants - System invariants viewer
 * - /deliveries - Delivery explorer (placeholder)
 * - /policy - Policy inspector (placeholder)
 */
export function AppRoutes() {
  return (
    <Routes>
      {/* Default route redirects to audit */}
      <Route path={ROUTES.HOME} element={<Navigate to={ROUTES.AUDIT} replace />} />

      {/* Dynamic routes from config */}
      {ROUTE_CONFIGS.map((config) => (
        <Route key={config.path} path={config.path} element={getRouteElement(config)} />
      ))}

      {/* Catch-all for unknown routes - redirect to home */}
      <Route path="*" element={<Navigate to={ROUTES.HOME} replace />} />
    </Routes>
  );
}

export default AppRoutes;

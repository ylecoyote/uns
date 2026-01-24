/**
 * Main App component for UNS UI Dashboard.
 *
 * Provides routing and layout for all UI pages.
 * All pages are READ-ONLY per ui-scope.md.
 */

import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { AuditTimeline } from './pages/AuditTimeline';
import { DeliveriesListPage } from './pages/DeliveriesListPage';
import { DeliveriesDetailPage } from './pages/DeliveriesDetailPage';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="app-nav">
          <div className="nav-brand">UNS Dashboard</div>
          <ul className="nav-links">
            <li>
              <NavLink to="/deliveries" className={({ isActive }) => (isActive ? 'active' : '')}>
                Deliveries
              </NavLink>
            </li>
            <li>
              <NavLink to="/policy" className={({ isActive }) => (isActive ? 'active' : '')}>
                Policy
              </NavLink>
            </li>
            <li>
              <NavLink to="/invariants" className={({ isActive }) => (isActive ? 'active' : '')}>
                Invariants
              </NavLink>
            </li>
            <li>
              <NavLink to="/audit" className={({ isActive }) => (isActive ? 'active' : '')}>
                Audit
              </NavLink>
            </li>
          </ul>
          <div className="nav-badge">READ-ONLY</div>
        </nav>

        <main className="app-main">
          <Routes>
            <Route path="/" element={<AuditTimeline />} />
            <Route path="/audit" element={<AuditTimeline />} />
            <Route path="/deliveries" element={<DeliveriesListPage />} />
            <Route path="/deliveries/:notificationId" element={<DeliveriesDetailPage />} />
            <Route
              path="/policy"
              element={<PlaceholderPage title="Policy" description="Effective policy inspector" />}
            />
            <Route
              path="/invariants"
              element={<PlaceholderPage title="Invariants" description="System invariants viewer" />}
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="placeholder-page">
      <h1>{title}</h1>
      <p>{description}</p>
      <p className="placeholder-note">Page not yet implemented.</p>
    </div>
  );
}

export default App;

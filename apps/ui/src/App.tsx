/**
 * Main App component for UNS Console.
 *
 * Provides routing, capability-aware header pills, and layout for all UI pages.
 */

import { useSyncExternalStore } from 'react';
import { BrowserRouter, NavLink } from 'react-router-dom';
import { AppRoutes } from './router';
import { getNavRoutes } from './types/routes';
import {
  clearConsoleSession,
  getCapabilityPills,
  getConsoleSession,
  subscribeConsoleSession,
  type CapabilityPill,
} from './auth/session';
import { ConsoleSignIn } from './components/ConsoleSignIn';
import './App.css';

function pillClassName(pill: CapabilityPill): string {
  switch (pill) {
    case 'OPERATOR':
      return 'nav-badge nav-badge-operator';
    case 'RESPONDER':
      return 'nav-badge nav-badge-responder';
    case 'PRODUCER':
      return 'nav-badge nav-badge-producer';
    case 'READ-ONLY':
    default:
      return 'nav-badge';
  }
}

function App() {
  const session = useSyncExternalStore(subscribeConsoleSession, getConsoleSession);
  const navRoutes = getNavRoutes();

  if (!session.credential) return <ConsoleSignIn expired={session.expired} />;

  const capabilityPills = getCapabilityPills(session);

  return (
    <BrowserRouter>
      <div className="app">
        <nav className="app-nav">
          <div className="nav-brand">UNS Console</div>
          <ul className="nav-links">
            {navRoutes.map((route) => (
              <li key={route.path}>
                <NavLink to={route.path} className={({ isActive }) => (isActive ? 'active' : '')}>
                  {route.title}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="nav-session" data-testid="nav-session">
            <div className="nav-capabilities" data-testid="nav-capabilities">
              {capabilityPills.map((pill) => (
                <span
                  key={pill}
                  className={pillClassName(pill)}
                  data-testid={`capability-pill-${pill.toLowerCase()}`}
                >
                  {pill}
                </span>
              ))}
            </div>
            {session.subject && (
              <span className="nav-subject" data-testid="session-subject">
                ({session.subject})
              </span>
            )}
            <button type="button" className="btn btn-secondary" onClick={() => clearConsoleSession()}>
              Sign out
            </button>
          </div>
        </nav>

        <main className="app-main">
          <AppRoutes />
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;

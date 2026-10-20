/**
 * Main App component for UNS Console.
 *
 * Provides routing and layout for all UI pages.
 * All pages are READ-ONLY per ui-scope.md.
 */

import { BrowserRouter, NavLink } from 'react-router-dom';
import { AppRoutes } from './router';
import { getNavRoutes } from './types/routes';
import './App.css';

function App() {
  const navRoutes = getNavRoutes();

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
          <div className="nav-badge">READ-ONLY</div>
        </nav>

        <main className="app-main">
          <AppRoutes />
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;

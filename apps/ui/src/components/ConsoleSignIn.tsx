import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, apiGet } from '../api/client';
import { startConsoleSession } from '../auth/session';

function accessError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.statusCode === 401) return 'The API key was not accepted. Check the key and try again.';
    if (error.statusCode === 403) return 'This key does not have console access. Ask your service administrator for access.';
    if (error.statusCode === 503) return 'The service is unavailable. Try again or ask your service administrator to check its configuration.';
    return `Cannot open the console (HTTP ${error.statusCode}). Try again or contact your service administrator.`;
  }
  return 'Cannot reach the service. Check your connection and try again.';
}

export function ConsoleSignIn({ expired }: { expired: boolean }) {
  const [credential, setCredential] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(
    expired ? 'Your access is no longer valid. Enter a current API key to reconnect.' : null
  );
  const request = useRef<AbortController | null>(null);
  const keyInput = useRef<HTMLInputElement>(null);

  useEffect(() => () => { request.current?.abort(); }, []);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = credential.trim();
    if (!key || checking) return;

    const controller = new AbortController();
    request.current = controller;
    setChecking(true);
    setCredential('');
    setError(null);

    try {
      // Validate against a protected read before mounting any console pages.
      await apiGet('/audit', { limit: 1 }, { credential: key, signal: controller.signal });
      if (!controller.signal.aborted) startConsoleSession(key);
    } catch (cause) {
      if (!controller.signal.aborted) setError(accessError(cause));
    } finally {
      if (request.current === controller && !controller.signal.aborted) {
        request.current = null;
        setChecking(false);
        keyInput.current?.focus();
      }
    }
  }

  function cancel() {
    request.current?.abort();
    request.current = null;
    setChecking(false);
    keyInput.current?.focus();
  }

  return (
    <div className="app">
      <header className="app-nav"><div className="nav-brand">UNS Console</div></header>
      <main className="auth-main">
        <h1>Connect to UNS Console</h1>
        <p>Enter the API key supplied by your service administrator to view deliveries, policies, and audit events.</p>
        <form className="auth-form" onSubmit={connect} aria-busy={checking}>
          <div className="auth-field">
            <label htmlFor="console-api-key">API key</label>
            <input
              ref={keyInput}
              id="console-api-key"
              type="password"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              required
              value={credential}
              disabled={checking}
              onChange={event => { setCredential(event.target.value); setError(null); }}
              aria-describedby={error ? 'credential-help credential-error' : 'credential-help'}
              aria-invalid={Boolean(error)}
            />
            <p id="credential-help" className="auth-help">The key stays in memory for this tab. Reloading or signing out clears it.</p>
          </div>
          {error && <p id="credential-error" className="auth-error" role="alert">{error}</p>}
          <div className="auth-actions">
            <button className="btn btn-primary" type="submit" disabled={checking || !credential.trim()}>
              {checking ? 'Checking access…' : 'Connect'}
            </button>
            {checking && <button className="btn btn-secondary" type="button" onClick={cancel}>Cancel</button>}
          </div>
        </form>
      </main>
    </div>
  );
}

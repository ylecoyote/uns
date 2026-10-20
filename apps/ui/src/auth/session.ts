/** Tab-lifetime credentials. Never persist an API key in browser storage. */
interface ConsoleSession {
  readonly credential: string | null;
  readonly expired: boolean;
}

let session: ConsoleSession = { credential: null, expired: false };
const listeners = new Set<() => void>();

export function getConsoleSession(): ConsoleSession {
  return session;
}

export function subscribeConsoleSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function updateSession(next: ConsoleSession) {
  session = next;
  listeners.forEach(listener => listener());
}

export function startConsoleSession(credential: string) {
  updateSession({ credential, expired: false });
}

export function clearConsoleSession() {
  updateSession({ credential: null, expired: false });
}

export function expireConsoleSession(expected: ConsoleSession) {
  // A late response from an older session must not sign out a newer one.
  if (session === expected && session.credential !== null) {
    updateSession({ credential: null, expired: true });
  }
}

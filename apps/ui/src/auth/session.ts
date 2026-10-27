/**
 * Tab-lifetime credentials with optional in-memory BroadcastChannel multi-tab sync.
 * Never persist an API key in browser storage (localStorage / sessionStorage).
 */

import type { ConsoleScope } from '../types/api';

export type CapabilityPill = 'OPERATOR' | 'RESPONDER' | 'PRODUCER' | 'READ-ONLY';

export interface ConsoleSession {
  readonly credential: string | null;
  readonly subject: string | null;
  readonly scopes: readonly ConsoleScope[];
  readonly persistenceMode: string | null;
  readonly expired: boolean;
}

export interface ConsoleSessionMetadata {
  readonly subject?: string | null;
  readonly scopes?: readonly string[];
  readonly persistenceMode?: string | null;
}

type SessionChannelMessage =
  | { readonly type: 'UNS_SESSION_REQUEST' }
  | {
      readonly type: 'UNS_SESSION_GRANT';
      readonly credential: string;
      readonly subject: string | null;
      readonly scopes: readonly ConsoleScope[];
      readonly persistenceMode: string | null;
    }
  | {
      readonly type: 'UNS_SESSION_SYNC';
      readonly credential: string;
      readonly subject: string | null;
      readonly scopes: readonly ConsoleScope[];
      readonly persistenceMode: string | null;
    }
  | { readonly type: 'UNS_SESSION_CLEAR' }
  | {
      readonly type: 'UNS_SESSION_EXPIRE';
      readonly credential: string;
    };

const VALID_SCOPES: ReadonlySet<string> = new Set(['observer', 'responder', 'producer', 'admin']);
const CHANNEL_NAME = 'uns_console_session';

const EMPTY_SESSION: ConsoleSession = {
  credential: null,
  subject: null,
  scopes: [],
  persistenceMode: null,
  expired: false,
};

let session: ConsoleSession = EMPTY_SESSION;
const listeners = new Set<() => void>();
let broadcastChannel: BroadcastChannel | null = null;

function normalizeScopes(scopes?: readonly string[]): readonly ConsoleScope[] {
  if (!scopes || scopes.length === 0) return ['observer'];
  const valid = scopes.filter((scope): scope is ConsoleScope => VALID_SCOPES.has(scope));
  return valid.length > 0 ? Array.from(new Set(valid)) : ['observer'];
}

function handleChannelMessage(event: MessageEvent<unknown>) {
  const data = event.data as Partial<SessionChannelMessage> | null;
  if (!data || typeof data !== 'object' || typeof data.type !== 'string') return;

  if (data.type === 'UNS_SESSION_REQUEST') {
    if (session.credential !== null && broadcastChannel !== null) {
      const reply: SessionChannelMessage = {
        type: 'UNS_SESSION_GRANT',
        credential: session.credential,
        subject: session.subject,
        scopes: session.scopes,
        persistenceMode: session.persistenceMode,
      };
      broadcastChannel.postMessage(reply);
    }
    return;
  }

  if (data.type === 'UNS_SESSION_GRANT') {
    if (session.credential === null && typeof data.credential === 'string' && data.credential) {
      updateSession({
        credential: data.credential,
        subject: typeof data.subject === 'string' ? data.subject : null,
        scopes: normalizeScopes(Array.isArray(data.scopes) ? data.scopes : undefined),
        persistenceMode: typeof data.persistenceMode === 'string' ? data.persistenceMode : null,
        expired: false,
      });
    }
    return;
  }

  if (data.type === 'UNS_SESSION_SYNC') {
    if (typeof data.credential === 'string' && data.credential) {
      updateSession({
        credential: data.credential,
        subject: typeof data.subject === 'string' ? data.subject : null,
        scopes: normalizeScopes(Array.isArray(data.scopes) ? data.scopes : undefined),
        persistenceMode: typeof data.persistenceMode === 'string' ? data.persistenceMode : null,
        expired: false,
      });
    }
    return;
  }

  if (data.type === 'UNS_SESSION_EXPIRE') {
    if (
      typeof data.credential === 'string' &&
      data.credential &&
      session.credential === data.credential
    ) {
      updateSession({
        credential: null,
        subject: null,
        scopes: [],
        persistenceMode: null,
        expired: true,
      });
    }
    return;
  }

  if (data.type === 'UNS_SESSION_CLEAR') {
    if (session.credential !== null || session.expired) {
      updateSession(EMPTY_SESSION);
    }
  }
}

function ensureBroadcastChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  if (broadcastChannel === null) {
    try {
      broadcastChannel = new BroadcastChannel(CHANNEL_NAME);
      broadcastChannel.onmessage = handleChannelMessage;
    } catch {
      broadcastChannel = null;
    }
  }
  return broadcastChannel;
}

export function requestPeerConsoleSession(): void {
  const channel = ensureBroadcastChannel();
  if (channel !== null && session.credential === null) {
    try {
      const request: SessionChannelMessage = { type: 'UNS_SESSION_REQUEST' };
      channel.postMessage(request);
    } catch {
      // Ignore BroadcastChannel errors in restricted environments.
    }
  }
}

export function resetConsoleSessionChannelForTests(): void {
  if (broadcastChannel !== null) {
    try {
      broadcastChannel.close();
    } catch {
      // Ignore close errors in tests.
    }
    broadcastChannel = null;
  }
}

export function getConsoleSession(): ConsoleSession {
  return session;
}

export function subscribeConsoleSession(listener: () => void): () => void {
  ensureBroadcastChannel();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function updateSession(next: ConsoleSession) {
  session = next;
  listeners.forEach((listener) => listener());
}

export function startConsoleSession(credential: string, metadata?: ConsoleSessionMetadata) {
  const normalized = credential.trim() || credential;
  const next: ConsoleSession = {
    credential: normalized,
    subject: metadata?.subject ?? null,
    scopes: normalizeScopes(metadata?.scopes),
    persistenceMode: metadata?.persistenceMode ?? null,
    expired: false,
  };
  updateSession(next);
  const channel = ensureBroadcastChannel();
  if (channel !== null) {
    try {
      const message: SessionChannelMessage = {
        type: 'UNS_SESSION_SYNC',
        credential: normalized,
        subject: next.subject,
        scopes: next.scopes,
        persistenceMode: next.persistenceMode,
      };
      channel.postMessage(message);
    } catch {
      // Ignore BroadcastChannel errors.
    }
  }
}

export function clearConsoleSession(options?: { broadcast?: boolean }) {
  updateSession(EMPTY_SESSION);
  if (options?.broadcast !== false) {
    const channel = ensureBroadcastChannel();
    if (channel !== null) {
      try {
        const message: SessionChannelMessage = { type: 'UNS_SESSION_CLEAR' };
        channel.postMessage(message);
      } catch {
        // Ignore BroadcastChannel errors.
      }
    }
  }
}

export function expireConsoleSession(expected?: ConsoleSession | string) {
  const target =
    typeof expected === 'string'
      ? expected.trim()
      : expected && typeof expected === 'object'
        ? expected.credential
        : session.credential;
  const matches =
    typeof expected === 'string'
      ? Boolean(target && session.credential === target)
      : expected && typeof expected === 'object'
        ? session === expected && session.credential !== null
        : session.credential !== null;

  // A late response from an older session must not sign out a newer one.
  if (matches && target) {
    updateSession({
      credential: null,
      subject: null,
      scopes: [],
      persistenceMode: null,
      expired: true,
    });
    const channel = ensureBroadcastChannel();
    if (channel !== null) {
      try {
        const message: SessionChannelMessage = {
          type: 'UNS_SESSION_EXPIRE',
          credential: target,
        };
        channel.postMessage(message);
      } catch {
        // Ignore BroadcastChannel errors.
      }
    }
  }
}

export function hasScope(targetSession: ConsoleSession, requiredScope: ConsoleScope): boolean {
  if (!targetSession.credential) return false;
  if (targetSession.scopes.includes('admin')) return true;
  return targetSession.scopes.includes(requiredScope);
}

export function getCapabilityPills(targetSession: ConsoleSession): readonly CapabilityPill[] {
  if (!targetSession.credential) return [];
  if (targetSession.scopes.includes('admin')) return ['OPERATOR'];
  const pills: CapabilityPill[] = [];
  if (targetSession.scopes.includes('responder')) pills.push('RESPONDER');
  if (targetSession.scopes.includes('producer')) pills.push('PRODUCER');
  return pills.length > 0 ? pills : ['READ-ONLY'];
}

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiGet, apiRootRequest, apiRootRequestWithStatus, ApiError } from '../src/api/client';
import {
  clearConsoleSession,
  expireConsoleSession,
  getCapabilityPills,
  getConsoleSession,
  hasScope,
  requestPeerConsoleSession,
  resetConsoleSessionChannelForTests,
  startConsoleSession,
  subscribeConsoleSession,
} from '../src/auth/session';

const mockFetch = vi.fn();
const failure = (status: number, body: unknown) => ({ ok: false, status, json: async () => body });

beforeEach(() => {
  clearConsoleSession();
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  clearConsoleSession();
  vi.unstubAllGlobals();
});

describe('Authenticated API requests', () => {
  it('adds the active credential only to request headers', async () => {
    startConsoleSession('operator-test-key');
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    await apiGet('/audit');
    expect(mockFetch.mock.calls[0][0]).not.toContain('operator-test-key');
    expect(mockFetch.mock.calls[0][1]).toMatchObject({
      headers: { Authorization: 'Bearer operator-test-key' },
      cache: 'no-store',
      redirect: 'error',
    });
  });

  it('clears an invalid session even when a 401 body is not JSON', async () => {
    startConsoleSession('expired-test-key');
    mockFetch.mockResolvedValue({ ok: false, status: 401, json: async () => { throw new SyntaxError(); } });
    await expect(apiGet('/audit')).rejects.toMatchObject({ name: 'ApiError', statusCode: 401 });
    expect(getConsoleSession()).toMatchObject({ credential: null, expired: true });
  });

  it('keeps a valid session when an operation is forbidden', async () => {
    startConsoleSession('restricted-test-key');
    mockFetch.mockResolvedValue(failure(403, { detail: 'Not permitted' }));
    await expect(apiGet('/audit')).rejects.toMatchObject({ name: 'ApiError', statusCode: 403 });
    expect(getConsoleSession().credential).toBe('restricted-test-key');
  });

  it('does not let a delayed 401 invalidate a newer session, even with the same key', async () => {
    let finish!: (response: ReturnType<typeof failure>) => void;
    startConsoleSession('shared-test-key');
    mockFetch.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    const pending = apiGet('/audit');
    clearConsoleSession();
    startConsoleSession('shared-test-key');
    finish(failure(401, { detail: 'Invalid key' }));
    await expect(pending).rejects.toBeInstanceOf(ApiError);
    expect(getConsoleSession().credential).toBe('shared-test-key');
  });

  it('does not persist a credential used only for a sign-in probe', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    await apiGet('/audit', { limit: 1 }, { credential: 'probe-test-key' });
    expect(mockFetch.mock.calls[0][1].headers.Authorization).toBe('Bearer probe-test-key');
    expect(getConsoleSession().credential).toBeNull();
  });

  it('normalizes plain FastAPI errors without assuming a structured envelope', async () => {
    mockFetch.mockResolvedValue(failure(503, { detail: 'Unavailable' }));
    await expect(apiGet('/audit')).rejects.toMatchObject({ name: 'ApiError', statusCode: 503 });
  });

  it('normalizes non-JSON gateway errors without displaying the response body', async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 502, json: async () => { throw new SyntaxError(); } });
    await expect(apiGet('/audit')).rejects.toMatchObject({
      name: 'ApiError', statusCode: 502, message: 'The service returned an error (HTTP 502).',
    });
  });

  it('supports root-relative POST and DELETE mutations with structured 403/409 errors and allowStatus', async () => {
    startConsoleSession('responder-key', { subject: 'uns-responder', scopes: ['observer', 'responder'] });
    const controller = new AbortController();

    // 1. 403 Forbidden from auth.py keeps session alive and surfaces insufficient_scope
    mockFetch.mockResolvedValueOnce(
      failure(403, {
        detail: {
          error: 'insufficient_scope',
          message: "Credential principal 'uns-responder' lacks required 'admin' authority.",
        },
      })
    );
    await expect(
      apiRootRequest('POST', '/api/v1/policies/reload', {}, { signal: controller.signal })
    ).rejects.toMatchObject({
      name: 'ApiError',
      statusCode: 403,
      code: 'insufficient_scope',
    });
    expect(getConsoleSession().credential).toBe('responder-key');

    // 2. 409 Conflict from runtime route preserves detail message and keeps session alive
    mockFetch.mockResolvedValueOnce(
      failure(409, { detail: 'Obligation already satisfied by successor' })
    );
    await expect(
      apiRootRequest('POST', '/api/v1/runtime/notifications/abc/replay')
    ).rejects.toMatchObject({
      name: 'ApiError',
      statusCode: 409,
      message: 'Obligation already satisfied by successor',
    });
    expect(getConsoleSession().credential).toBe('responder-key');

    // 3. allowStatus: [503] parses degraded /readyz payload without throwing
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ status: 'not_ready', operational_progress: { pending_count: 4 } }),
    });
    const readiness = await apiRootRequestWithStatus<{
      status: string;
      operational_progress: { pending_count: number };
    }>('GET', '/readyz', undefined, { allowStatus: [503] });
    expect(readiness.status).toBe(503);
    expect(readiness.ok).toBe(false);
    expect(readiness.data.operational_progress.pending_count).toBe(4);
  });

  it('computes non-lossy capability pills and hasScope across the scope lattice', () => {
    startConsoleSession('obs-key', { subject: 'obs', scopes: ['observer'] });
    expect(getCapabilityPills(getConsoleSession())).toEqual(['READ-ONLY']);
    expect(hasScope(getConsoleSession(), 'observer')).toBe(true);
    expect(hasScope(getConsoleSession(), 'responder')).toBe(false);

    startConsoleSession('dual-key', { subject: 'dual', scopes: ['observer', 'producer', 'responder'] });
    expect(getCapabilityPills(getConsoleSession())).toEqual(['RESPONDER', 'PRODUCER']);
    expect(hasScope(getConsoleSession(), 'responder')).toBe(true);
    expect(hasScope(getConsoleSession(), 'producer')).toBe(true);
    expect(hasScope(getConsoleSession(), 'admin')).toBe(false);

    startConsoleSession('admin-key', { subject: 'admin-user', scopes: ['admin', 'observer'] });
    expect(getCapabilityPills(getConsoleSession())).toEqual(['OPERATOR']);
    expect(hasScope(getConsoleSession(), 'responder')).toBe(true);
    expect(hasScope(getConsoleSession(), 'producer')).toBe(true);
    expect(hasScope(getConsoleSession(), 'admin')).toBe(true);
  });

  it('hydrates and clears sessions across same-origin tabs via in-memory BroadcastChannel', () => {
    const channels = new Set<{ onmessage: ((event: MessageEvent) => void) | null }>();
    class MockBroadcastChannel {
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_name: string) {
        channels.add(this);
      }
      postMessage(data: unknown) {
        for (const peer of channels) {
          if (peer !== this && peer.onmessage) {
            peer.onmessage({ data } as MessageEvent);
          }
        }
      }
      close() {
        channels.delete(this);
      }
    }

    vi.stubGlobal('BroadcastChannel', MockBroadcastChannel);
    resetConsoleSessionChannelForTests();

    const unsubscribe = subscribeConsoleSession(() => {});
    const peerChannel = new MockBroadcastChannel('uns_console_session');
    const receivedMessages: unknown[] = [];
    peerChannel.onmessage = (event: MessageEvent) => {
      receivedMessages.push(event.data);
    };

    // Active tab grants session when peer tab requests it
    startConsoleSession('tab-shared-key', {
      subject: 'operator-1',
      scopes: ['admin', 'observer', 'producer', 'responder'],
      persistenceMode: 'persistent',
    });
    receivedMessages.length = 0;
    peerChannel.postMessage({ type: 'UNS_SESSION_REQUEST' });
    expect(receivedMessages).toEqual([
      {
        type: 'UNS_SESSION_GRANT',
        credential: 'tab-shared-key',
        subject: 'operator-1',
        scopes: ['admin', 'observer', 'producer', 'responder'],
        persistenceMode: 'persistent',
      },
    ]);

    // Peer tab sign-out clears this tab's in-memory session
    peerChannel.postMessage({ type: 'UNS_SESSION_CLEAR' });
    expect(getConsoleSession().credential).toBeNull();

    // Empty tab can hydrate from a peer grant and request a peer session
    requestPeerConsoleSession();
    peerChannel.postMessage({
      type: 'UNS_SESSION_GRANT',
      credential: 'hydrated-key',
      subject: 'responder-2',
      scopes: ['observer', 'responder'],
      persistenceMode: 'persistent',
    });
    expect(getConsoleSession()).toMatchObject({
      credential: 'hydrated-key',
      subject: 'responder-2',
      scopes: ['observer', 'responder'],
      persistenceMode: 'persistent',
      expired: false,
    });

    // UNS_SESSION_SYNC updates peer tab even when it already holds an older credential
    peerChannel.postMessage({
      type: 'UNS_SESSION_SYNC',
      credential: 'rotated-key',
      subject: 'operator-rotated',
      scopes: ['admin', 'observer'],
      persistenceMode: 'persistent',
    });
    expect(getConsoleSession()).toMatchObject({
      credential: 'rotated-key',
      subject: 'operator-rotated',
      scopes: ['admin', 'observer'],
      expired: false,
    });

    // UNS_SESSION_EXPIRE transitions peer tabs holding the same expired credential to expired: true
    peerChannel.postMessage({
      type: 'UNS_SESSION_EXPIRE',
      credential: 'rotated-key',
    });
    expect(getConsoleSession()).toMatchObject({
      credential: null,
      expired: true,
    });

    // Local expireConsoleSession broadcasts UNS_SESSION_EXPIRE to peer tabs
    startConsoleSession('expiring-key', {
      subject: 'obs',
      scopes: ['observer'],
    });
    receivedMessages.length = 0;
    expireConsoleSession(getConsoleSession());
    expect(getConsoleSession()).toMatchObject({
      credential: null,
      expired: true,
    });
    expect(receivedMessages).toEqual([
      {
        type: 'UNS_SESSION_EXPIRE',
        credential: 'expiring-key',
      },
    ]);

    unsubscribe();
    resetConsoleSessionChannelForTests();
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiGet, ApiError } from '../src/api/client';
import { clearConsoleSession, getConsoleSession, startConsoleSession } from '../src/auth/session';

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
});

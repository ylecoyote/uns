import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { mockAuditEventsResponse } from '../src/test/mocks';

const mockFetch = vi.fn();
const key = 'console-test-key';
const success = () => ({ ok: true, json: async () => mockAuditEventsResponse });
const denied = (status = 401) => ({
  ok: false,
  status,
  json: async () => ({ detail: 'Access denied' }),
});

function submitKey(value = key) {
  fireEvent.change(screen.getByLabelText('API key'), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
}

async function connect() {
  submitKey();
  await screen.findByRole('button', { name: 'Sign out' });
}

beforeEach(() => {
  window.history.replaceState({}, '', '/audit');
  mockFetch.mockReset().mockImplementation(async () => success());
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  const signOut = screen.queryByRole('button', { name: 'Sign out' });
  if (signOut) fireEvent.click(signOut);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Console access', () => {
  it('does not fetch or show console data before an operator connects', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Connect to UNS Console' })).toBeInTheDocument();
    expect(screen.getByLabelText('API key')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Connect' })).toBeDisabled();
    expect(screen.queryByTestId('audit-timeline-page')).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('validates access with a header, then authenticates console reads without browser storage', async () => {
    const writeStorage = vi.spyOn(Storage.prototype, 'setItem');
    render(<App />);
    await connect();
    await screen.findByTestId('audit-event-list');

    expect(mockFetch.mock.calls[0][0]).toContain('/ui/audit?limit=1');
    expect(mockFetch.mock.calls.length).toBeGreaterThanOrEqual(2);
    for (const [url, options] of mockFetch.mock.calls) {
      expect(url).not.toContain(key);
      expect(options.headers.Authorization).toBe(`Bearer ${key}`);
      expect(options.cache).toBe('no-store');
      expect(options.redirect).toBe('error');
    }
    expect(writeStorage).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain(key);
  });

  it('shows progress and lets an operator cancel a delayed check', async () => {
    let finish!: (response: ReturnType<typeof success>) => void;
    mockFetch.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    render(<App />);
    submitKey();
    expect(screen.getByRole('button', { name: 'Checking access…' })).toBeDisabled();
    expect(screen.getByLabelText('API key')).toHaveValue('');
    const signal = mockFetch.mock.calls[0][1].signal as AbortSignal;
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(signal.aborted).toBe(true);
    await act(async () => { finish(success()); });
    expect(screen.getByRole('heading', { name: 'Connect to UNS Console' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument();
  });

  it('rejects an invalid key without exposing the server error and allows retry', async () => {
    mockFetch.mockResolvedValueOnce({ ...denied(), json: async () => ({ detail: key }) });
    render(<App />);
    submitKey();
    expect(await screen.findByRole('alert')).toHaveTextContent('The API key was not accepted.');
    expect(screen.getByLabelText('API key')).toHaveValue('');
    expect(document.body.textContent).not.toContain(key);
    expect(screen.queryByTestId('audit-timeline-page')).not.toBeInTheDocument();
    await connect();
    expect(screen.getByTestId('audit-timeline-page')).toBeInTheDocument();
  });

  it('distinguishes forbidden access from an invalid credential', async () => {
    mockFetch.mockResolvedValueOnce(denied(403));
    render(<App />);
    submitKey();
    expect(await screen.findByRole('alert')).toHaveTextContent('This key does not have console access.');
  });

  it('shows an actionable unavailable-service error', async () => {
    mockFetch.mockResolvedValueOnce(denied(503));
    render(<App />);
    submitKey();
    expect(await screen.findByRole('alert')).toHaveTextContent('The service is unavailable.');
    expect(screen.getByRole('button', { name: 'Connect' })).toBeDisabled();
  });

  it('handles network failures and permits another attempt', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(<App />);
    submitKey();
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the service.');
    await connect();
  });

  it('removes console data on sign-out and uses the next key for a new session', async () => {
    render(<App />);
    await connect();
    await screen.findByTestId('audit-event-list');
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(screen.queryByTestId('audit-timeline-page')).not.toBeInTheDocument();
    expect(screen.getByLabelText('API key')).toHaveValue('');
    mockFetch.mockClear();
    submitKey('replacement-test-key');
    await screen.findByRole('button', { name: 'Sign out' });
    expect(mockFetch.mock.calls[0][1].headers.Authorization).toBe('Bearer replacement-test-key');
  });

  it('clears the session and its rendered data after a later 401', async () => {
    render(<App />);
    await connect();
    await screen.findByTestId('audit-event-list');
    mockFetch.mockResolvedValueOnce(denied());
    fireEvent.click(screen.getByRole('link', { name: 'Deliveries' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Your access is no longer valid.'));
    expect(screen.queryByTestId('audit-event-list')).not.toBeInTheDocument();
    expect(screen.getByLabelText('API key')).toHaveValue('');
  });
});

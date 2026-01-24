/**
 * Tests for API client functions.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getAuditEvents, ApiError, apiGet, fetchEffectivePolicy } from '../src/api';
import { mockAuditEventsResponse } from '../src/test/mocks';

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('apiGet', () => {
    it('makes GET request to correct URL', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiGet('/audit');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/ui/audit'),
        expect.objectContaining({
          method: 'GET',
        })
      );
    });

    it('includes query parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiGet('/audit', { limit: 10, event_type: 'delivery.succeeded' });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('limit=10');
      expect(callUrl).toContain('event_type=delivery.succeeded');
    });

    it('filters out undefined parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiGet('/audit', { limit: 10, event_type: undefined });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('limit=10');
      expect(callUrl).not.toContain('event_type');
    });

    it('includes request ID header when provided', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiGet('/audit', {}, { requestId: 'req-123' });

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders['X-Request-ID']).toBe('req-123');
    });

    it('throws ApiError on non-OK response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () =>
          Promise.resolve({
            error: { code: 'invalid_parameter', message: 'Invalid filter' },
            request_id: 'req-123',
          }),
      });

      await expect(apiGet('/audit')).rejects.toThrow(ApiError);
    });

    it('ApiError contains correct properties', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () =>
          Promise.resolve({
            error: { code: 'invalid_parameter', message: 'Invalid filter' },
            request_id: 'req-123',
          }),
      });

      try {
        await apiGet('/audit');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        if (err instanceof ApiError) {
          expect(err.code).toBe('invalid_parameter');
          expect(err.message).toBe('Invalid filter');
          expect(err.requestId).toBe('req-123');
          expect(err.statusCode).toBe(400);
        }
      }
    });
  });

  describe('getAuditEvents', () => {
    it('fetches audit events successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      const result = await getAuditEvents();

      expect(result.items).toHaveLength(3);
      expect(result.pagination.has_more).toBe(false);
    });

    it('passes filter parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({
        event_type: 'delivery.succeeded',
        autonomy_mode: 'LIVE',
        limit: 10,
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('event_type=delivery.succeeded');
      expect(callUrl).toContain('autonomy_mode=LIVE');
      expect(callUrl).toContain('limit=10');
    });

    it('passes notification_id filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({
        notification_id: '123e4567-e89b-12d3-a456-426614174000',
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('notification_id=123e4567-e89b-12d3-a456-426614174000');
    });

    it('passes agent_id filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({
        agent_id: 'agent-uuid-123',
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('agent_id=agent-uuid-123');
    });

    it('passes correlation_id filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({
        correlation_id: 'corr-123',
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('correlation_id=corr-123');
    });

    it('passes time range filters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({
        start_time: '2026-01-01T00:00:00Z',
        end_time: '2026-01-31T23:59:59Z',
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('start_time=2026-01-01T00%3A00%3A00Z');
      expect(callUrl).toContain('end_time=2026-01-31T23%3A59%3A59Z');
    });

    it('passes cursor for pagination', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({
        cursor: 'cursor-abc123',
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('cursor=cursor-abc123');
    });
  });

  describe('fetchEffectivePolicy', () => {
    const mockPolicyResponse = {
      notification_type: 'trading.order_placed',
      effective: {
        delivery_mode: 'GUARANTEED',
        channels: ['SLACK', 'EMAIL'],
        require_ack: true,
        ack_timeout_minutes: 60,
        dedup_window_seconds: 300,
      },
      resolution: {},
      resolution_context: {
        intent: 'GOVERNANCE',
        autonomy_mode: 'LIVE',
        irreversible: false,
        policy_found: true,
        policy_notification_type: 'trading.order_placed',
      },
    };

    it('fetches effective policy with correct parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPolicyResponse),
      });

      const result = await fetchEffectivePolicy({
        notification_type: 'trading.order_placed',
        intent: 'GOVERNANCE',
        autonomy_mode: 'LIVE',
        irreversible: false,
      });

      expect(result.notification_type).toBe('trading.order_placed');
      expect(result.effective.delivery_mode).toBe('GUARANTEED');

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/ui/policies/effective');
      expect(callUrl).toContain('notification_type=trading.order_placed');
      expect(callUrl).toContain('intent=GOVERNANCE');
      expect(callUrl).toContain('autonomy_mode=LIVE');
      expect(callUrl).toContain('irreversible=false');
    });

    it('passes request ID when provided', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPolicyResponse),
      });

      await fetchEffectivePolicy(
        {
          notification_type: 'test.type',
          intent: 'INFORMATIONAL',
          autonomy_mode: 'PREVIEW',
        },
        { requestId: 'test-req-123' }
      );

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders['X-Request-ID']).toBe('test-req-123');
    });

    it('handles API errors correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () =>
          Promise.resolve({
            error: { code: 'not_found', message: 'Policy not found' },
            request_id: 'req-456',
          }),
      });

      await expect(
        fetchEffectivePolicy({
          notification_type: 'unknown.type',
          intent: 'INFORMATIONAL',
          autonomy_mode: 'PREVIEW',
        })
      ).rejects.toThrow(ApiError);
    });
  });
});

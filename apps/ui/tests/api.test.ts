/**
 * Tests for the standardized typed API client.
 *
 * Tests cover:
 * - Core client functions (apiGet, apiRequest, buildQueryString, filterToParams)
 * - Audit API functions
 * - Invariants API functions
 * - Error handling with ApiError
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  apiGet,
  apiRequest,
  buildQueryString,
  filterToParams,
  getAuditEvents,
  fetchInvariants,
  fetchInvariantsSummary,
  ApiError,
} from '../src/api';
import { mockAuditEventsResponse } from '../src/test/mocks';
import type { InvariantListResponse, InvariantSummaryResponse } from '../src/types/invariants';

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('buildQueryString', () => {
    it('builds query string from params object', () => {
      const result = buildQueryString({ limit: 10, status: 'active' });
      expect(result).toBe('?limit=10&status=active');
    });

    it('filters out undefined values', () => {
      const result = buildQueryString({ limit: 10, status: undefined });
      expect(result).toBe('?limit=10');
    });

    it('returns empty string when no params', () => {
      const result = buildQueryString({});
      expect(result).toBe('');
    });

    it('handles boolean values', () => {
      const result = buildQueryString({ enabled: true, disabled: false });
      expect(result).toBe('?enabled=true&disabled=false');
    });

    it('encodes special characters', () => {
      const result = buildQueryString({ search: 'hello world' });
      expect(result).toBe('?search=hello+world');
    });
  });

  describe('filterToParams', () => {
    it('converts filter object to query params', () => {
      const result = filterToParams({ severity: 'HIGH', limit: 10 });
      expect(result).toEqual({ severity: 'HIGH', limit: 10 });
    });

    it('filters out undefined values', () => {
      const result = filterToParams({ severity: 'HIGH', limit: undefined });
      expect(result).toEqual({ severity: 'HIGH' });
    });

    it('filters out null values', () => {
      const result = filterToParams({ severity: 'HIGH', limit: null });
      expect(result).toEqual({ severity: 'HIGH' });
    });

    it('handles boolean values', () => {
      const result = filterToParams({ enabled: true, disabled: false });
      expect(result).toEqual({ enabled: true, disabled: false });
    });

    it('ignores non-primitive values', () => {
      const result = filterToParams({
        name: 'test',
        nested: { foo: 'bar' },
        array: [1, 2, 3],
      });
      expect(result).toEqual({ name: 'test' });
    });
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

    it('handles FastAPI wrapped errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            detail: {
              error: { code: 'validation_error', message: 'Validation failed' },
              request_id: 'req-456',
            },
          }),
      });

      try {
        await apiGet('/audit');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        if (err instanceof ApiError) {
          expect(err.code).toBe('validation_error');
          expect(err.message).toBe('Validation failed');
          expect(err.requestId).toBe('req-456');
          expect(err.statusCode).toBe(422);
        }
      }
    });

    it('includes Accept header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiGet('/audit');

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders.Accept).toBe('application/json');
    });

    it('passes abort signal', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      const controller = new AbortController();
      await apiGet('/audit', {}, { signal: controller.signal });

      const callOptions = mockFetch.mock.calls[0][1];
      expect(callOptions.signal).toBe(controller.signal);
    });
  });

  describe('apiRequest', () => {
    it('strips /ui prefix from full path', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiRequest('/ui/invariants/summary');

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/ui/invariants/summary');
      expect(callUrl).not.toContain('/ui/ui/');
    });

    it('handles path without /ui prefix', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiRequest('/invariants/summary');

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/ui/invariants/summary');
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

    it('passes request options', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAuditEventsResponse),
      });

      await getAuditEvents({}, { requestId: 'req-audit-123' });

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders['X-Request-ID']).toBe('req-audit-123');
    });
  });

  describe('fetchInvariants', () => {
    const mockInvariantsResponse: InvariantListResponse = {
      items: [
        {
          id: 'inv-001',
          statement: 'All notifications must have a valid recipient',
          severity: 'HIGH',
          status: 'active',
          enforcement: {
            type: 'guard',
            description: 'Enforced at API boundary',
          },
          evidence: [
            {
              path: 'src/validators/notification.ts',
              note: 'Validation guard',
              line_ref: '42',
            },
          ],
          owner: 'team-notifications',
          last_reviewed: '2026-01-15T10:00:00Z',
        },
      ],
      pagination: {
        next_cursor: null,
        has_more: false,
        total_count: 1,
      },
    };

    it('fetches invariants successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      const result = await fetchInvariants();

      expect(result.items).toHaveLength(1);
      expect(result.items[0].id).toBe('inv-001');
      expect(result.pagination.has_more).toBe(false);
    });

    it('passes filter parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      await fetchInvariants({
        severity: 'HIGH',
        enforcement_type: 'guard',
        limit: 20,
      });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('severity=HIGH');
      expect(callUrl).toContain('enforcement_type=guard');
      expect(callUrl).toContain('limit=20');
    });

    it('passes status filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      await fetchInvariants({ status: 'active' });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('status=active');
    });

    it('passes search filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      await fetchInvariants({ search: 'notification' });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('search=notification');
    });

    it('passes cursor for pagination', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      await fetchInvariants({ cursor: 'cursor-inv-123' });

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('cursor=cursor-inv-123');
    });

    it('passes request options', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      await fetchInvariants({}, { requestId: 'req-inv-123' });

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders['X-Request-ID']).toBe('req-inv-123');
    });

    it('makes request to correct endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInvariantsResponse),
      });

      await fetchInvariants();

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/ui/invariants');
      expect(callUrl).not.toContain('/summary');
    });
  });

  describe('fetchInvariantsSummary', () => {
    const mockSummaryResponse: InvariantSummaryResponse = {
      total_count: 25,
      by_severity: { HIGH: 10, MEDIUM: 10, LOW: 5 },
      by_enforcement_type: { guard: 15, isolation: 5, test: 3, exception: 2 },
      by_status: { active: 20, inactive: 5 },
      exceptions_requiring_review: 2,
      last_updated: '2026-01-23T12:00:00Z',
    };

    it('fetches summary successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSummaryResponse),
      });

      const result = await fetchInvariantsSummary();

      expect(result.total_count).toBe(25);
      expect(result.by_severity.HIGH).toBe(10);
      expect(result.exceptions_requiring_review).toBe(2);
    });

    it('makes request to correct endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSummaryResponse),
      });

      await fetchInvariantsSummary();

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/ui/invariants/summary');
    });

    it('passes request options', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSummaryResponse),
      });

      await fetchInvariantsSummary({ requestId: 'req-summary-123' });

      const callHeaders = mockFetch.mock.calls[0][1].headers;
      expect(callHeaders['X-Request-ID']).toBe('req-summary-123');
    });
  });

  describe('ApiError', () => {
    it('creates error with correct properties', () => {
      const errorResponse = {
        error: {
          code: 'not_found',
          message: 'Resource not found',
          details: { resource_id: '123' },
        },
        request_id: 'req-error-123',
      };

      const error = new ApiError(errorResponse, 404);

      expect(error.name).toBe('ApiError');
      expect(error.message).toBe('Resource not found');
      expect(error.code).toBe('not_found');
      expect(error.requestId).toBe('req-error-123');
      expect(error.statusCode).toBe(404);
      expect(error.details).toEqual({ resource_id: '123' });
    });

    it('extends Error class', () => {
      const error = new ApiError(
        {
          error: { code: 'test', message: 'Test error' },
          request_id: 'req-123',
        },
        500
      );

      expect(error).toBeInstanceOf(Error);
      expect(error).toBeInstanceOf(ApiError);
    });

    it('handles error without details', () => {
      const errorResponse = {
        error: {
          code: 'server_error',
          message: 'Internal server error',
        },
        request_id: 'req-500',
      };

      const error = new ApiError(errorResponse, 500);

      expect(error.details).toBeUndefined();
    });
  });
});

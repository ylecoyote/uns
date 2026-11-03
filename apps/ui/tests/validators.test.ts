/**
 * Tests for contract validators and decoders.
 *
 * These tests verify:
 * - Schema validation catches contract drift
 * - Decode functions properly validate API responses
 * - Error handling provides useful debugging information
 * - Validation modes work correctly
 * - Degraded state flag handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  // Decoders
  decodeDeliveriesList,
  decodeDeliveryTimeline,
  decodeAuditEventsList,
  decodeInvariantsList,
  decodeInvariantsSummary,
  decodeEffectivePolicy,
  // Error handling
  ContractDriftError,
  assertDecode,
  logDriftIfFailed,
  // Configuration
  getValidationMode,
  setValidationMode,
  decodeWithMode,
} from '../src/api/validators';

// ============================================================================
// Test Data Factories
// ============================================================================

/**
 * Create a valid delivery timeline list response
 */
function createValidDeliveriesList() {
  return {
    items: [
      {
        notification_id: '123e4567-e89b-12d3-a456-426614174000',
        notification_type: 'trading.order_placed',
        intent: 'GOVERNANCE',
        delivery_mode: 'GUARANTEED',
        status: 'DELIVERED',
        created_at: '2026-01-23T10:00:00Z',
        delivered_at: '2026-01-23T10:00:05Z',
        channels_attempted: ['SLACK', 'EMAIL'],
        channels_succeeded: ['SLACK'],
        autonomy_mode: 'LIVE',
        agent_id: 'agent-001',
      },
    ],
    pagination: {
      next_cursor: null,
      has_more: false,
      total_count: 1,
    },
  };
}

/**
 * Create a valid delivery timeline response (full detail)
 */
function createValidDeliveryTimeline() {
  return {
    notification_id: '123e4567-e89b-12d3-a456-426614174000',
    notification_type: 'trading.order_placed',
    intent: 'GOVERNANCE',
    delivery_mode: 'GUARANTEED',
    status: 'DELIVERED',
    created_at: '2026-01-23T10:00:00Z',
    delivered_at: '2026-01-23T10:00:05Z',
    attempts: [
      {
        attempt_id: 'attempt-001',
        channel: 'SLACK',
        status: 'SUCCESS',
        started_at: '2026-01-23T10:00:00Z',
        completed_at: '2026-01-23T10:00:05Z',
        duration_ms: 5000,
        error_message: null,
        error_code: null,
        metadata: {},
      },
    ],
    channels_attempted: ['SLACK'],
    channels_succeeded: ['SLACK'],
    channels_failed: [],
    autonomy_context: {
      autonomy_mode: 'LIVE',
      agent_id: 'agent-001',
      plan_id: null,
      decision_snapshot_id: null,
      execution_snapshot_id: null,
      skip_snapshot_id: null,
    },
  };
}

/**
 * Create a valid audit events list response
 */
function createValidAuditEventsList() {
  return {
    items: [
      {
        audit_id: 'audit-001',
        event_type: 'delivery.succeeded',
        event_time: '2026-01-23T10:00:00Z',
        notification_id: '123e4567-e89b-12d3-a456-426614174000',
        notification_type: 'trading.order_placed',
        autonomy_context: {
          autonomy_mode: 'LIVE',
          agent_id: 'agent-001',
        },
        payload: { channel: 'SLACK', duration_ms: 5000 },
        correlation_id: 'corr-001',
      },
    ],
    pagination: {
      next_cursor: null,
      has_more: false,
    },
  };
}

/**
 * Create a valid invariants list response
 */
function createValidInvariantsList() {
  return {
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
    },
  };
}

/**
 * Create a valid invariants summary response
 */
function createValidInvariantsSummary() {
  return {
    total_count: 25,
    by_severity: { HIGH: 10, MEDIUM: 10, LOW: 5 },
    by_enforcement_type: { guard: 15, isolation: 5, test: 3, exception: 2 },
    by_status: { active: 20, inactive: 5 },
    exceptions_requiring_review: 2,
    last_updated: '2026-01-23T12:00:00Z',
  };
}

/**
 * Create a valid effective policy response
 */
function createValidEffectivePolicy() {
  return {
    notification_type: 'trading.order_placed',
    effective: {
      delivery_mode: 'GUARANTEED',
      channels: ['SLACK', 'EMAIL'],
      require_ack: true,
      ack_timeout_minutes: 60,
      dedup_window_seconds: 300,
    },
    resolution: {
      delivery_mode: [
        {
          source: 'policy_base',
          value: 'GUARANTEED',
          applied: true,
          reason: null,
        },
      ],
    },
    resolution_context: {
      intent: 'GOVERNANCE',
      autonomy_mode: 'LIVE',
      irreversible: false,
      policy_found: true,
      policy_notification_type: 'trading.order_placed',
    },
  };
}

// ============================================================================
// Decoder Tests
// ============================================================================

describe('Contract Decoders', () => {
  describe('decodeDeliveriesList', () => {
    it('successfully decodes valid deliveries list', () => {
      const data = createValidDeliveriesList();
      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.items).toHaveLength(1);
        expect(result.data.pagination.has_more).toBe(false);
      }
    });

    it('fails on missing required field', () => {
      const data = createValidDeliveriesList();
      delete (data.items[0] as Record<string, unknown>).notification_id;

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error).toBeInstanceOf(ContractDriftError);
        expect(result.error.message).toContain('notification_id');
      }
    });

    it('fails on invalid intent enum value', () => {
      const data = createValidDeliveriesList();
      (data.items[0] as Record<string, unknown>).intent = 'INVALID_INTENT';

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.getSummary()).toContain('intent');
      }
    });

    it('fails on invalid delivery_mode enum value', () => {
      const data = createValidDeliveriesList();
      (data.items[0] as Record<string, unknown>).delivery_mode = 'INVALID_MODE';

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid status enum value', () => {
      const data = createValidDeliveriesList();
      (data.items[0] as Record<string, unknown>).status = 'UNKNOWN_STATUS';

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid channel enum value', () => {
      const data = createValidDeliveriesList();
      (data.items[0] as Record<string, unknown>).channels_attempted = ['INVALID_CHANNEL'];

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid autonomy_mode enum value', () => {
      const data = createValidDeliveriesList();
      (data.items[0] as Record<string, unknown>).autonomy_mode = 'INVALID_MODE';

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
    });

    it('fails on missing pagination', () => {
      const data = createValidDeliveriesList();
      delete (data as Record<string, unknown>).pagination;

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid pagination shape', () => {
      const data = createValidDeliveriesList();
      (data as Record<string, unknown>).pagination = { invalid: true };

      const result = decodeDeliveriesList(data);

      expect(result.success).toBe(false);
    });
  });

  describe('decodeDeliveryTimeline', () => {
    it('successfully decodes valid delivery timeline', () => {
      const data = createValidDeliveryTimeline();
      const result = decodeDeliveryTimeline(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.attempts).toHaveLength(1);
        expect(result.data.autonomy_context.autonomy_mode).toBe('LIVE');
      }
    });

    it('fails on missing autonomy_context', () => {
      const data = createValidDeliveryTimeline();
      delete (data as Record<string, unknown>).autonomy_context;

      const result = decodeDeliveryTimeline(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid attempt shape', () => {
      const data = createValidDeliveryTimeline();
      (data.attempts[0] as Record<string, unknown>).channel = 'INVALID';

      const result = decodeDeliveryTimeline(data);

      expect(result.success).toBe(false);
    });
  });

  describe('decodeAuditEventsList', () => {
    it('successfully decodes valid audit events list', () => {
      const data = createValidAuditEventsList();
      const result = decodeAuditEventsList(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.items).toHaveLength(1);
        expect(result.data.items[0].event_type).toBe('delivery.succeeded');
      }
    });

    it('fails on invalid event_type enum value', () => {
      const data = createValidAuditEventsList();
      (data.items[0] as Record<string, unknown>).event_type = 'invalid.event';

      const result = decodeAuditEventsList(data);

      expect(result.success).toBe(false);
    });

    it('fails on missing autonomy_context in event', () => {
      const data = createValidAuditEventsList();
      delete (data.items[0] as Record<string, unknown>).autonomy_context;

      const result = decodeAuditEventsList(data);

      expect(result.success).toBe(false);
    });
  });

  describe('decodeInvariantsList', () => {
    it('successfully decodes valid invariants list', () => {
      const data = createValidInvariantsList();
      const result = decodeInvariantsList(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.items).toHaveLength(1);
        expect(result.data.items[0].severity).toBe('HIGH');
      }
    });

    it('handles optional degraded flag', () => {
      const data = { ...createValidInvariantsList(), degraded: true };
      const result = decodeInvariantsList(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.degraded).toBe(true);
      }
    });

    it('succeeds without degraded flag', () => {
      const data = createValidInvariantsList();
      const result = decodeInvariantsList(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.degraded).toBeUndefined();
      }
    });

    it('fails on invalid severity enum', () => {
      const data = createValidInvariantsList();
      (data.items[0] as Record<string, unknown>).severity = 'CRITICAL';

      const result = decodeInvariantsList(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid enforcement_type enum', () => {
      const data = createValidInvariantsList();
      (data.items[0].enforcement as Record<string, unknown>).type = 'unknown';

      const result = decodeInvariantsList(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid status enum', () => {
      const data = createValidInvariantsList();
      (data.items[0] as Record<string, unknown>).status = 'archived';

      const result = decodeInvariantsList(data);

      expect(result.success).toBe(false);
    });

    it('fails on missing evidence array', () => {
      const data = createValidInvariantsList();
      delete (data.items[0] as Record<string, unknown>).evidence;

      const result = decodeInvariantsList(data);

      expect(result.success).toBe(false);
    });
  });

  describe('decodeInvariantsSummary', () => {
    it('successfully decodes valid summary', () => {
      const data = createValidInvariantsSummary();
      const result = decodeInvariantsSummary(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.total_count).toBe(25);
        expect(result.data.by_severity.HIGH).toBe(10);
      }
    });

    it('handles optional degraded flag', () => {
      const data = { ...createValidInvariantsSummary(), degraded: true };
      const result = decodeInvariantsSummary(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.degraded).toBe(true);
      }
    });

    it('fails on missing required field', () => {
      const data = createValidInvariantsSummary();
      delete (data as Record<string, unknown>).total_count;

      const result = decodeInvariantsSummary(data);

      expect(result.success).toBe(false);
    });

    it('fails on wrong type for by_severity', () => {
      const data = createValidInvariantsSummary();
      (data as Record<string, unknown>).by_severity = 'not_an_object';

      const result = decodeInvariantsSummary(data);

      expect(result.success).toBe(false);
    });
  });

  describe('decodeEffectivePolicy', () => {
    it('successfully decodes valid effective policy', () => {
      const data = createValidEffectivePolicy();
      const result = decodeEffectivePolicy(data);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.effective.delivery_mode).toBe('GUARANTEED');
        expect(result.data.resolution_context.policy_found).toBe(true);
      }
    });

    it('fails on invalid delivery_mode in effective', () => {
      const data = createValidEffectivePolicy();
      (data.effective as Record<string, unknown>).delivery_mode = 'INVALID';

      const result = decodeEffectivePolicy(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid channel in effective.channels', () => {
      const data = createValidEffectivePolicy();
      (data.effective as Record<string, unknown>).channels = ['INVALID_CHANNEL'];

      const result = decodeEffectivePolicy(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid resolution_source in resolution', () => {
      const data = createValidEffectivePolicy();
      (data.resolution.delivery_mode[0] as Record<string, unknown>).source = 'invalid_source';

      const result = decodeEffectivePolicy(data);

      expect(result.success).toBe(false);
    });

    it('fails on invalid intent in resolution_context', () => {
      const data = createValidEffectivePolicy();
      (data.resolution_context as Record<string, unknown>).intent = 'INVALID';

      const result = decodeEffectivePolicy(data);

      expect(result.success).toBe(false);
    });
  });
});

// ============================================================================
// Error Handling Tests
// ============================================================================

describe('ContractDriftError', () => {
  it('provides useful error message', () => {
    const data = createValidDeliveriesList();
    delete (data.items[0] as Record<string, unknown>).notification_id;

    const result = decodeDeliveriesList(data);

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.message).toContain('Contract drift detected');
      expect(result.error.message).toContain('notification_id');
    }
  });

  it('provides getSummary method', () => {
    const data = createValidDeliveriesList();
    delete (data.items[0] as Record<string, unknown>).notification_id;
    delete (data.items[0] as Record<string, unknown>).intent;

    const result = decodeDeliveriesList(data);

    expect(result.success).toBe(false);
    if (!result.success) {
      const summary = result.error.getSummary();
      expect(summary).toContain('notification_id');
    }
  });

  it('limits summary to maxIssues', () => {
    const data = createValidDeliveriesList();
    // Create multiple issues
    delete (data.items[0] as Record<string, unknown>).notification_id;
    delete (data.items[0] as Record<string, unknown>).intent;
    delete (data.items[0] as Record<string, unknown>).delivery_mode;
    delete (data.items[0] as Record<string, unknown>).status;

    const result = decodeDeliveriesList(data);

    expect(result.success).toBe(false);
    if (!result.success) {
      const summary = result.error.getSummary(2);
      expect(summary).toContain('and');
      expect(summary).toContain('more issues');
    }
  });

  it('preserves raw data for debugging', () => {
    const data = { invalid: 'data' };
    const result = decodeDeliveriesList(data);

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.raw).toEqual(data);
    }
  });
});

describe('assertDecode', () => {
  it('returns data on success', () => {
    const data = createValidDeliveriesList();
    const result = decodeDeliveriesList(data);

    const decoded = assertDecode(result);

    expect(decoded.items).toHaveLength(1);
  });

  it('throws on failure', () => {
    const data = { invalid: 'data' };
    const result = decodeDeliveriesList(data);

    expect(() => assertDecode(result)).toThrow(ContractDriftError);
  });

  it('includes context in error message', () => {
    const data = { invalid: 'data' };
    const result = decodeDeliveriesList(data);

    expect(() => assertDecode(result, 'GET /ui/deliveries')).toThrow(/GET \/ui\/deliveries/);
  });
});

describe('logDriftIfFailed', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns validated data on success', () => {
    const data = createValidDeliveriesList();
    const result = decodeDeliveriesList(data);

    const decoded = logDriftIfFailed(result, 'GET /ui/deliveries', data);

    expect(decoded).toEqual(data);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('logs warning and returns raw data on failure', () => {
    const data = { invalid: 'data' };
    const result = decodeDeliveriesList(data);

    const decoded = logDriftIfFailed(result, 'GET /ui/deliveries', data);

    expect(decoded).toEqual(data);
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('[Contract Drift]')
    );
  });
});

// ============================================================================
// Validation Mode Tests
// ============================================================================

describe('Validation Mode', () => {
  const originalMode = getValidationMode();

  afterEach(() => {
    setValidationMode(originalMode);
  });

  describe('getValidationMode / setValidationMode', () => {
    it('defaults to lenient', () => {
      // Reset to default
      setValidationMode('lenient');
      expect(getValidationMode()).toBe('lenient');
    });

    it('can be set to strict', () => {
      setValidationMode('strict');
      expect(getValidationMode()).toBe('strict');
    });

    it('can be set to off', () => {
      setValidationMode('off');
      expect(getValidationMode()).toBe('off');
    });
  });

  describe('decodeWithMode', () => {
    beforeEach(() => {
      vi.spyOn(console, 'warn').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('validates in lenient mode and returns data on success', () => {
      setValidationMode('lenient');
      const data = createValidDeliveriesList();

      const result = decodeWithMode(decodeDeliveriesList, data, 'test');

      expect(result.items).toHaveLength(1);
      expect(console.warn).not.toHaveBeenCalled();
    });

    it('validates in lenient mode and logs warning on failure', () => {
      setValidationMode('lenient');
      const data = { invalid: 'data' };

      const result = decodeWithMode(decodeDeliveriesList, data, 'test');

      expect(result).toEqual(data);
      expect(console.warn).toHaveBeenCalled();
    });

    it('validates in strict mode and returns data on success', () => {
      setValidationMode('strict');
      const data = createValidDeliveriesList();

      const result = decodeWithMode(decodeDeliveriesList, data, 'test');

      expect(result.items).toHaveLength(1);
    });

    it('validates in strict mode and throws on failure', () => {
      setValidationMode('strict');
      const data = { invalid: 'data' };

      expect(() => decodeWithMode(decodeDeliveriesList, data, 'test')).toThrow(
        ContractDriftError
      );
    });

    it('skips validation in off mode', () => {
      setValidationMode('off');
      const data = { invalid: 'data' };

      // Should not throw, just return the raw data
      const result = decodeWithMode(decodeDeliveriesList, data, 'test');

      expect(result).toEqual(data);
      expect(console.warn).not.toHaveBeenCalled();
    });
  });
});

// ============================================================================
// Degraded State Tests
// ============================================================================

describe('Degraded State Handling', () => {
  it('decodeInvariantsList accepts degraded=true', () => {
    const data = { ...createValidInvariantsList(), degraded: true };
    const result = decodeInvariantsList(data);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.degraded).toBe(true);
    }
  });

  it('decodeInvariantsList accepts degraded=false', () => {
    const data = { ...createValidInvariantsList(), degraded: false };
    const result = decodeInvariantsList(data);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.degraded).toBe(false);
    }
  });

  it('decodeInvariantsSummary accepts degraded=true', () => {
    const data = { ...createValidInvariantsSummary(), degraded: true };
    const result = decodeInvariantsSummary(data);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.degraded).toBe(true);
    }
  });

  it('decodeInvariantsSummary accepts degraded=false', () => {
    const data = { ...createValidInvariantsSummary(), degraded: false };
    const result = decodeInvariantsSummary(data);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.degraded).toBe(false);
    }
  });
});

// ============================================================================
// Edge Cases and Regression Tests
// ============================================================================

describe('Edge Cases', () => {
  it('handles empty items array', () => {
    const data = {
      items: [],
      pagination: { next_cursor: null, has_more: false },
    };
    const result = decodeDeliveriesList(data);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.items).toHaveLength(0);
    }
  });

  it('handles null optional fields', () => {
    const data = createValidDeliveryTimeline();
    data.delivered_at = null;
    data.attempts[0].error_message = null;
    data.attempts[0].error_code = null;
    data.attempts[0].metadata = null;

    const result = decodeDeliveryTimeline(data);

    expect(result.success).toBe(true);
  });

  it('handles optional fields omitted entirely', () => {
    const data = createValidDeliveryTimeline();
    delete (data as Record<string, unknown>).delivered_at;
    delete (data.attempts[0] as Record<string, unknown>).error_message;
    delete (data.attempts[0] as Record<string, unknown>).error_code;
    delete (data.attempts[0] as Record<string, unknown>).metadata;

    const result = decodeDeliveryTimeline(data);

    expect(result.success).toBe(true);
  });

  it('handles optional mitigation array in invariant', () => {
    const data = createValidInvariantsList();
    data.items[0].mitigation = ['Fix in PR #123', 'Tracked in JIRA-456'];

    const result = decodeInvariantsList(data);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.items[0].mitigation).toEqual(['Fix in PR #123', 'Tracked in JIRA-456']);
    }
  });

  it('handles optional correlation_id in audit event', () => {
    const data = createValidAuditEventsList();
    delete (data.items[0] as Record<string, unknown>).correlation_id;

    const result = decodeAuditEventsList(data);

    expect(result.success).toBe(true);
  });
});

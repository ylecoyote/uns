/**
 * Tests for AuditEventCard component.
 *
 * Validates the component displays audit events correctly with Tailwind styling.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuditEventCard } from '../src/components/AuditEventCard';
import { mockAuditEvent, mockAuditEventFailed, mockAuditEventAck } from '../src/test/mocks';

describe('AuditEventCard', () => {
  describe('Rendering', () => {
    it('renders with testid', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      expect(screen.getByTestId('audit-event-card')).toBeInTheDocument();
    });

    it('displays event type badge', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const badge = screen.getByTestId('event-type-badge');
      expect(badge).toBeInTheDocument();
      expect(badge.textContent).toBe('Delivered');
    });

    it('displays autonomy mode badge', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const badge = screen.getByTestId('autonomy-mode');
      expect(badge).toBeInTheDocument();
      expect(badge.textContent).toBe('LIVE');
    });

    it('displays event time', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      expect(screen.getByTestId('event-time')).toBeInTheDocument();
    });

    it('displays notification ID', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const notificationId = screen.getByTestId('notification-id');
      expect(notificationId.textContent).toBe(mockAuditEvent.notification_id);
    });

    it('displays notification type', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const notificationType = screen.getByTestId('notification-type');
      expect(notificationType.textContent).toBe(mockAuditEvent.notification_type);
    });

    it('displays agent ID', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const agentId = screen.getByTestId('agent-id');
      expect(agentId.textContent).toBe(mockAuditEvent.autonomy_context.agent_id);
    });

    it('displays correlation ID when present', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const correlationId = screen.getByTestId('correlation-id');
      expect(correlationId.textContent).toBe(mockAuditEvent.correlation_id);
    });

    it('hides correlation ID when not present', () => {
      render(<AuditEventCard event={mockAuditEventFailed} />);

      expect(screen.queryByTestId('correlation-id')).not.toBeInTheDocument();
    });

    it('displays payload in collapsible details', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      expect(screen.getByTestId('event-payload')).toBeInTheDocument();
    });
  });

  describe('Event Type Badges', () => {
    it('shows green badge for delivery.succeeded', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const badge = screen.getByTestId('event-type-badge');
      expect(badge.className).toContain('bg-green-100');
      expect(badge.className).toContain('text-green-800');
    });

    it('shows red badge for delivery.failed', () => {
      render(<AuditEventCard event={mockAuditEventFailed} />);

      const badge = screen.getByTestId('event-type-badge');
      expect(badge.className).toContain('bg-red-100');
      expect(badge.className).toContain('text-red-800');
    });

    it('shows green badge for ack.received', () => {
      render(<AuditEventCard event={mockAuditEventAck} />);

      const badge = screen.getByTestId('event-type-badge');
      expect(badge.className).toContain('bg-green-100');
      expect(badge.className).toContain('text-green-800');
    });
  });

  describe('Autonomy Mode Badges', () => {
    it('shows green badge for LIVE mode', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const badge = screen.getByTestId('autonomy-mode');
      expect(badge.className).toContain('bg-green-100');
      expect(badge.className).toContain('text-green-800');
    });

    it('shows purple badge for PREVIEW mode', () => {
      const previewEvent = {
        ...mockAuditEvent,
        autonomy_context: {
          ...mockAuditEvent.autonomy_context,
          autonomy_mode: 'PREVIEW' as const,
        },
      };

      render(<AuditEventCard event={previewEvent} />);

      const badge = screen.getByTestId('autonomy-mode');
      expect(badge.className).toContain('bg-purple-100');
      expect(badge.className).toContain('text-purple-800');
    });

    it('shows indigo badge for SHADOW mode', () => {
      const shadowEvent = {
        ...mockAuditEvent,
        autonomy_context: {
          ...mockAuditEvent.autonomy_context,
          autonomy_mode: 'SHADOW' as const,
        },
      };

      render(<AuditEventCard event={shadowEvent} />);

      const badge = screen.getByTestId('autonomy-mode');
      expect(badge.className).toContain('bg-indigo-100');
      expect(badge.className).toContain('text-indigo-800');
    });
  });

  describe('Payload Display', () => {
    it('formats payload as JSON', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const payload = screen.getByTestId('event-payload');
      expect(payload.textContent).toContain('DELIVERED');
    });

    it('hides payload when empty', () => {
      const eventWithoutPayload = {
        ...mockAuditEvent,
        payload: {},
      };

      render(<AuditEventCard event={eventWithoutPayload} />);

      expect(screen.queryByTestId('event-payload')).not.toBeInTheDocument();
    });
  });

  describe('Styling', () => {
    it('uses Tailwind CSS classes for card', () => {
      render(<AuditEventCard event={mockAuditEvent} />);

      const card = screen.getByTestId('audit-event-card');
      expect(card.className).toContain('bg-white');
      expect(card.className).toContain('rounded-lg');
      expect(card.className).toContain('shadow');
      expect(card.className).toContain('hover:shadow-md');
    });
  });
});

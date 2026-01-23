/**
 * Tests for AuditEventCard component.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuditEventCard } from '../src/components/AuditEventCard';
import { mockAuditEvent, mockAuditEventFailed, mockAuditEventAck } from '../src/test/mocks';

describe('AuditEventCard', () => {
  it('renders event type badge', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const badge = screen.getByTestId('event-type-badge');
    expect(badge).toHaveTextContent('Delivered');
  });

  it('renders event time formatted', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const time = screen.getByTestId('event-time');
    expect(time).toBeInTheDocument();
    // Should contain formatted date
    expect(time.textContent).toContain('2026');
  });

  it('renders notification ID', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const notificationId = screen.getByTestId('notification-id');
    expect(notificationId).toHaveTextContent(mockAuditEvent.notification_id);
  });

  it('renders notification type', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const notificationType = screen.getByTestId('notification-type');
    expect(notificationType).toHaveTextContent('trading.order_executed');
  });

  it('renders agent ID', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const agentId = screen.getByTestId('agent-id');
    expect(agentId).toHaveTextContent(mockAuditEvent.autonomy_context.agent_id);
  });

  it('renders autonomy mode', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const mode = screen.getByTestId('autonomy-mode');
    expect(mode).toHaveTextContent('LIVE');
  });

  it('renders correlation ID when present', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const correlationId = screen.getByTestId('correlation-id');
    expect(correlationId).toHaveTextContent('corr-123');
  });

  it('does not render correlation ID when not present', () => {
    render(<AuditEventCard event={mockAuditEventFailed} />);

    const correlationId = screen.queryByTestId('correlation-id');
    expect(correlationId).not.toBeInTheDocument();
  });

  it('renders payload in details element', () => {
    render(<AuditEventCard event={mockAuditEvent} />);

    const payload = screen.getByTestId('event-payload');
    expect(payload).toBeInTheDocument();
    expect(payload.textContent).toContain('DELIVERED');
    expect(payload.textContent).toContain('SLACK');
  });

  it('renders failed event with error badge', () => {
    render(<AuditEventCard event={mockAuditEventFailed} />);

    const badge = screen.getByTestId('event-type-badge');
    expect(badge).toHaveTextContent('Failed');
    expect(badge).toHaveClass('badge-error');
  });

  it('renders ack event with success badge', () => {
    render(<AuditEventCard event={mockAuditEventAck} />);

    const badge = screen.getByTestId('event-type-badge');
    expect(badge).toHaveTextContent('Acknowledged');
    expect(badge).toHaveClass('badge-success');
  });
});

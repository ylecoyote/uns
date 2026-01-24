/**
 * DeliveriesTable component displays delivery timeline summaries in a table.
 */

import { Link } from 'react-router-dom';
import type { DeliveryTimelineSummary, Channel, DeliveryStatus, NotificationIntent } from '../types/api';

interface DeliveriesTableProps {
  deliveries: DeliveryTimelineSummary[];
}

function truncateUUID(uuid: string): string {
  return uuid.slice(0, 8) + '...';
}

function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '-';
  try {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return isoString;
  }
}

function getStatusBadgeClass(status: DeliveryStatus): string {
  switch (status) {
    case 'DELIVERED':
      return 'badge-success';
    case 'FAILED':
      return 'badge-error';
    case 'PENDING':
      return 'badge-warning';
    case 'DEDUPLICATED':
    case 'RATE_LIMITED':
      return 'badge-info';
    default:
      return 'badge-default';
  }
}

function getIntentBadgeClass(intent: NotificationIntent): string {
  switch (intent) {
    case 'SAFETY':
      return 'badge-error';
    case 'GOVERNANCE':
      return 'badge-warning';
    case 'OPERATIONAL':
      return 'badge-info';
    case 'INFORMATIONAL':
      return 'badge-default';
    default:
      return 'badge-default';
  }
}

function getModeClass(mode: string): string {
  switch (mode) {
    case 'PREVIEW':
      return 'mode-preview';
    case 'SHADOW':
      return 'mode-shadow';
    case 'LIVE':
      return 'mode-live';
    default:
      return '';
  }
}

interface ChannelTagProps {
  channel: Channel;
  succeeded: boolean;
}

function ChannelTag({ channel, succeeded }: ChannelTagProps) {
  return (
    <span className={`channel-tag ${succeeded ? 'channel-success' : ''}`}>
      {channel}
    </span>
  );
}

export function DeliveriesTable({ deliveries }: DeliveriesTableProps) {
  if (deliveries.length === 0) {
    return null;
  }

  return (
    <div className="table-container" data-testid="deliveries-table">
      <table className="data-table">
        <thead>
          <tr>
            <th>Notification ID</th>
            <th>Type</th>
            <th>Intent</th>
            <th>Status</th>
            <th>Delivery Mode</th>
            <th>Autonomy</th>
            <th>Channels</th>
            <th>Created</th>
            <th>Delivered</th>
          </tr>
        </thead>
        <tbody>
          {deliveries.map((item) => (
            <tr key={item.notification_id} data-testid="delivery-row">
              <td>
                <Link
                  to={`/deliveries/${item.notification_id}`}
                  className="notification-link"
                  data-testid="notification-link"
                >
                  {truncateUUID(item.notification_id)}
                </Link>
              </td>
              <td className="notification-type">{item.notification_type}</td>
              <td>
                <span className={`badge ${getIntentBadgeClass(item.intent)}`}>
                  {item.intent}
                </span>
              </td>
              <td>
                <span className={`badge ${getStatusBadgeClass(item.status)}`}>
                  {item.status}
                </span>
              </td>
              <td>{item.delivery_mode}</td>
              <td>
                <span className={`mode-badge ${getModeClass(item.autonomy_mode)}`}>
                  {item.autonomy_mode}
                </span>
              </td>
              <td className="channels-cell">
                {item.channels_attempted.map((ch) => (
                  <ChannelTag
                    key={ch}
                    channel={ch}
                    succeeded={item.channels_succeeded.includes(ch)}
                  />
                ))}
              </td>
              <td className="timestamp">{formatDateTime(item.created_at)}</td>
              <td className="timestamp">{formatDateTime(item.delivered_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

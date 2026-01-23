"""Notification delivery channel adapters.

This package contains adapters for each delivery channel:
- Slack
- Email
- WebSocket
- PagerDuty

Each adapter implements the BaseAdapter interface.
"""

from notification.adapters.base import (
    AdapterConfigurationError,
    AdapterDeliveryError,
    AdapterError,
    AdapterStatus,
    AdapterTimeoutError,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)

__all__ = [
    "AdapterConfigurationError",
    "AdapterDeliveryError",
    "AdapterError",
    "AdapterStatus",
    "AdapterTimeoutError",
    "BaseAdapter",
    "DeliveryResult",
    "HealthCheckResult",
]

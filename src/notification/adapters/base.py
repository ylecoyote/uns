"""Base adapter interface for notification delivery channels.

This module defines the abstract base class that all channel adapters must implement.
Each adapter provides channel-specific delivery logic while maintaining a consistent
interface for the delivery service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from notification.models import Channel, Notification


class AdapterStatus(str, Enum):
    """Health status of an adapter."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


@dataclass
class DeliveryResult:
    """Result of a delivery attempt.

    Attributes:
        success: Whether the delivery succeeded
        channel: The channel that was used
        message_id: External ID from the channel (e.g., Slack message ts)
        error: Error message if delivery failed
        metadata: Additional channel-specific metadata
        delivered_at: Timestamp of delivery attempt
    """

    success: bool
    channel: Channel
    message_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    delivered_at: datetime | None = None


@dataclass
class HealthCheckResult:
    """Result of a health check.

    Attributes:
        status: Health status of the adapter
        message: Human-readable status message
        latency_ms: Response time in milliseconds
        metadata: Additional diagnostic information
    """

    status: AdapterStatus
    message: str
    latency_ms: float | None = None
    metadata: dict[str, Any] | None = None


class AdapterError(Exception):
    """Base exception for adapter errors."""

    def __init__(
        self,
        message: str,
        channel: Channel | None = None,
        retryable: bool = False,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize adapter error.

        Args:
            message: Error description
            channel: The channel where error occurred
            retryable: Whether the operation can be retried
            original_error: The underlying exception, if any
        """
        super().__init__(message)
        self.channel = channel
        self.retryable = retryable
        self.original_error = original_error


class AdapterConfigurationError(AdapterError):
    """Raised when adapter is misconfigured."""

    def __init__(self, message: str, channel: Channel | None = None) -> None:
        super().__init__(message, channel=channel, retryable=False)


class AdapterDeliveryError(AdapterError):
    """Raised when delivery fails."""

    pass


class AdapterTimeoutError(AdapterError):
    """Raised when operation times out."""

    def __init__(
        self,
        message: str,
        channel: Channel | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(message, channel=channel, retryable=True)
        self.timeout_seconds = timeout_seconds


class BaseAdapter(ABC):
    """Abstract base class for notification delivery adapters.

    All channel adapters must implement this interface to ensure
    consistent behavior across the delivery system.

    Adapters are responsible for:
    - Delivering notifications to their specific channel
    - Reporting health status
    - Handling channel-specific errors appropriately
    """

    @property
    @abstractmethod
    def channel(self) -> Channel:
        """Return the channel this adapter handles."""
        ...

    @abstractmethod
    async def deliver(self, notification: Notification) -> DeliveryResult:
        """Deliver a notification through this channel.

        Args:
            notification: The notification to deliver

        Returns:
            DeliveryResult with success/failure status and metadata

        Raises:
            AdapterDeliveryError: If delivery fails and cannot be handled
            AdapterTimeoutError: If the operation times out
            AdapterConfigurationError: If the adapter is misconfigured
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """Check the health of this adapter and its external dependencies.

        Returns:
            HealthCheckResult with status and diagnostic information
        """
        ...

    def format_message(self, notification: Notification) -> str:
        """Format a notification for this channel.

        Default implementation returns a simple text format.
        Subclasses can override for channel-specific formatting.

        Args:
            notification: The notification to format

        Returns:
            Formatted message string
        """
        return f"[{notification.intent.value}] {notification.title}\n\n{notification.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(channel={self.channel.value})"

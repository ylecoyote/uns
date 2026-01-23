"""Adapters for notification delivery channels.

This module provides channel-specific adapters for delivering notifications
through various channels (Slack, Email, WebSocket, PagerDuty).

Each adapter implements the BaseAdapter interface with:
- deliver(notification) - Deliver a notification
- health_check() - Check adapter health

Usage:
    from notification.adapters import get_adapter, AdapterRegistry
    from notification.models import Channel

    # Get a specific adapter
    slack_adapter = get_adapter(Channel.SLACK, config=slack_config)

    # Or use the registry for managing multiple adapters
    registry = AdapterRegistry()
    registry.register(Channel.SLACK, slack_adapter)
    adapter = registry.get(Channel.SLACK)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
from notification.adapters.email import EmailAdapter, EmailConfig
from notification.adapters.pagerduty import (
    PagerDutyAdapter,
    PagerDutyConfig,
    PagerDutySeverity,
)
from notification.adapters.slack import SlackAdapter, SlackConfig
from notification.adapters.websocket import (
    InMemoryConnectionManager,
    WebSocketAdapter,
    WebSocketConfig,
    WebSocketConnectionManager,
)
from notification.models import Channel

if TYPE_CHECKING:
    pass


# Type alias for adapter configuration
AdapterConfig = SlackConfig | EmailConfig | WebSocketConfig | PagerDutyConfig


def get_adapter(
    channel: Channel,
    config: AdapterConfig | None = None,
    connection_manager: WebSocketConnectionManager | None = None,
    **kwargs: Any,
) -> BaseAdapter:
    """Factory function to create an adapter for a specific channel.

    Args:
        channel: The channel to create an adapter for
        config: Channel-specific configuration object
        connection_manager: WebSocket connection manager (required for WebSocket)
        **kwargs: Additional arguments passed to config if config is None

    Returns:
        Configured adapter instance

    Raises:
        AdapterConfigurationError: If configuration is invalid
        ValueError: If channel is unknown

    Examples:
        # With config object
        slack_config = SlackConfig(
            bot_token="xoxb-...",
            default_channel="#alerts",
        )
        adapter = get_adapter(Channel.SLACK, config=slack_config)

        # With kwargs (creates config automatically)
        adapter = get_adapter(
            Channel.SLACK,
            bot_token="xoxb-...",
            default_channel="#alerts",
        )
    """
    if channel == Channel.SLACK:
        if config is None:
            config = SlackConfig(**kwargs)
        elif not isinstance(config, SlackConfig):
            raise AdapterConfigurationError(
                f"Expected SlackConfig for Slack adapter, got {type(config).__name__}",
                channel=Channel.SLACK,
            )
        return SlackAdapter(config=config)

    elif channel == Channel.EMAIL:
        if config is None:
            config = EmailConfig(**kwargs)
        elif not isinstance(config, EmailConfig):
            raise AdapterConfigurationError(
                f"Expected EmailConfig for Email adapter, got {type(config).__name__}",
                channel=Channel.EMAIL,
            )
        return EmailAdapter(config=config)

    elif channel == Channel.WEBSOCKET:
        if config is None:
            config = WebSocketConfig(**kwargs)
        elif not isinstance(config, WebSocketConfig):
            raise AdapterConfigurationError(
                f"Expected WebSocketConfig for WebSocket adapter, got {type(config).__name__}",
                channel=Channel.WEBSOCKET,
            )
        if connection_manager is None:
            connection_manager = InMemoryConnectionManager()
        return WebSocketAdapter(config=config, connection_manager=connection_manager)

    elif channel == Channel.PAGERDUTY:
        if config is None:
            config = PagerDutyConfig(**kwargs)
        elif not isinstance(config, PagerDutyConfig):
            raise AdapterConfigurationError(
                f"Expected PagerDutyConfig for PagerDuty adapter, got {type(config).__name__}",
                channel=Channel.PAGERDUTY,
            )
        return PagerDutyAdapter(config=config)

    else:
        raise ValueError(f"Unknown channel: {channel}")


@dataclass
class AdapterRegistry:
    """Registry for managing channel adapters.

    Provides centralized management of adapters including:
    - Registration and retrieval
    - Health checking
    - Graceful shutdown

    Example:
        registry = AdapterRegistry()
        registry.register(Channel.SLACK, slack_adapter)
        registry.register(Channel.EMAIL, email_adapter)

        # Get an adapter
        adapter = registry.get(Channel.SLACK)

        # Check health of all adapters
        health = await registry.health_check_all()

        # Shutdown all adapters
        await registry.shutdown()
    """

    _adapters: dict[Channel, BaseAdapter] = field(default_factory=dict)

    def register(self, channel: Channel, adapter: BaseAdapter) -> None:
        """Register an adapter for a channel.

        Args:
            channel: The channel for this adapter
            adapter: The adapter instance

        Raises:
            ValueError: If adapter channel doesn't match
        """
        if adapter.channel != channel:
            raise ValueError(
                f"Adapter channel mismatch: expected {channel}, got {adapter.channel}"
            )
        self._adapters[channel] = adapter

    def unregister(self, channel: Channel) -> BaseAdapter | None:
        """Unregister an adapter for a channel.

        Args:
            channel: The channel to unregister

        Returns:
            The removed adapter, or None if not registered
        """
        return self._adapters.pop(channel, None)

    def get(self, channel: Channel) -> BaseAdapter | None:
        """Get the adapter for a channel.

        Args:
            channel: The channel to get

        Returns:
            The adapter, or None if not registered
        """
        return self._adapters.get(channel)

    def get_required(self, channel: Channel) -> BaseAdapter:
        """Get the adapter for a channel, raising if not found.

        Args:
            channel: The channel to get

        Returns:
            The adapter

        Raises:
            KeyError: If adapter not registered
        """
        adapter = self._adapters.get(channel)
        if adapter is None:
            raise KeyError(f"No adapter registered for channel: {channel}")
        return adapter

    def has(self, channel: Channel) -> bool:
        """Check if an adapter is registered for a channel.

        Args:
            channel: The channel to check

        Returns:
            True if registered, False otherwise
        """
        return channel in self._adapters

    def list_channels(self) -> list[Channel]:
        """List all registered channels.

        Returns:
            List of registered channels
        """
        return list(self._adapters.keys())

    async def health_check_all(self) -> dict[Channel, HealthCheckResult]:
        """Check health of all registered adapters.

        Returns:
            Dict mapping channels to their health check results
        """
        import asyncio

        async def check_adapter(
            channel: Channel, adapter: BaseAdapter
        ) -> tuple[Channel, HealthCheckResult]:
            try:
                result = await adapter.health_check()
                return (channel, result)
            except Exception as e:
                return (
                    channel,
                    HealthCheckResult(
                        status=AdapterStatus.UNHEALTHY,
                        message=f"Health check failed: {e}",
                        metadata={"error": str(e)},
                    ),
                )

        tasks = [
            check_adapter(channel, adapter)
            for channel, adapter in self._adapters.items()
        ]

        results = await asyncio.gather(*tasks)
        return dict(results)

    async def shutdown(self) -> None:
        """Shutdown all registered adapters.

        Calls close() on adapters that support it.
        """
        for adapter in self._adapters.values():
            if hasattr(adapter, "close"):
                try:
                    await adapter.close()
                except Exception as e:
                    # Log but don't fail on shutdown errors
                    import logging

                    logging.getLogger(__name__).warning(
                        "Error closing adapter %s: %s", adapter.channel, e
                    )


__all__ = [
    # Base classes and types
    "AdapterConfig",
    "AdapterConfigurationError",
    "AdapterDeliveryError",
    "AdapterError",
    "AdapterRegistry",
    "AdapterStatus",
    "AdapterTimeoutError",
    "BaseAdapter",
    "DeliveryResult",
    "HealthCheckResult",
    # Adapters
    "EmailAdapter",
    "EmailConfig",
    "PagerDutyAdapter",
    "PagerDutyConfig",
    "PagerDutySeverity",
    "SlackAdapter",
    "SlackConfig",
    "WebSocketAdapter",
    "WebSocketConfig",
    "WebSocketConnectionManager",
    "InMemoryConnectionManager",
    # Factory
    "get_adapter",
]

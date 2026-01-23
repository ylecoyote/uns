"""Integration interfaces for the Unified Notification Service.

This module defines protocol-based interfaces that allow UNS to remain
ATP-agnostic (autonomous trading platform). External systems inject
implementations at runtime via dependency injection.

Key Design Goals:
- Core SDK can run without ATP imports
- Protocols properly isolate external dependencies
- Default implementations provide sensible fallbacks
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from notification.models import AckEvent, AckStatus, AutonomyContext, AutonomyMode


@runtime_checkable
class NotificationContextProvider(Protocol):
    """Protocol for providing autonomy context to notifications.

    Implementations of this interface allow external systems (like ATP)
    to inject their own context-building logic without coupling UNS
    to specific domain implementations.

    This enables:
    - ATP to provide rich context from its internal state
    - Testing with mock/stub implementations
    - Default behavior when no external context is available
    """

    @abstractmethod
    def get_current_context(self) -> AutonomyContext:
        """Retrieve the current autonomy context.

        Returns:
            AutonomyContext with current agent state including:
            - autonomy_mode: Current operating mode (PREVIEW/SHADOW/LIVE)
            - agent_id: UUID of the active agent
            - Optional snapshot IDs for traceability

        Raises:
            RuntimeError: If context cannot be determined (e.g., no active agent)
        """
        ...

    @abstractmethod
    def get_context_for_agent(self, agent_id: UUID) -> AutonomyContext:
        """Retrieve autonomy context for a specific agent.

        Args:
            agent_id: UUID of the target agent

        Returns:
            AutonomyContext for the specified agent

        Raises:
            KeyError: If agent_id is not found
            RuntimeError: If context cannot be determined
        """
        ...

    @abstractmethod
    def get_autonomy_mode(self) -> AutonomyMode:
        """Get the current autonomy mode.

        This is a convenience method for routing decisions that only
        need the mode without full context.

        Returns:
            Current AutonomyMode (PREVIEW, SHADOW, or LIVE)
        """
        ...


@runtime_checkable
class AcknowledgmentCallback(Protocol):
    """Protocol for handling acknowledgment events.

    Implementations receive callbacks when notifications are acknowledged,
    dismissed, or time out. This allows external systems to react to
    acknowledgment state changes without UNS knowing their implementation.

    Use cases:
    - ATP updating internal state based on operator acknowledgments
    - Triggering escalation workflows on timeout
    - Audit logging to external systems
    - Metrics and monitoring integration
    """

    @abstractmethod
    def on_ack(self, event: AckEvent) -> None:
        """Called when a notification is acknowledged.

        Args:
            event: AckEvent containing:
                - notification_id: UUID of the acknowledged notification
                - ack_status: The acknowledgment status (ACKED)
                - acked_by: Identifier of the acknowledging user/system
                - acked_at: Timestamp of acknowledgment
                - metadata: Additional context from the ack action
        """
        ...

    @abstractmethod
    def on_dismiss(self, event: AckEvent) -> None:
        """Called when a notification is dismissed.

        Dismissal indicates the operator saw but chose not to formally
        acknowledge the notification.

        Args:
            event: AckEvent with ack_status = DISMISSED
        """
        ...

    @abstractmethod
    def on_timeout(self, event: AckEvent) -> None:
        """Called when a notification acknowledgment times out.

        Timeout handling may trigger escalation for SAFETY notifications
        in LIVE mode.

        Args:
            event: AckEvent with ack_status = TIMED_OUT
        """
        ...

    @abstractmethod
    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Called on any acknowledgment status transition.

        This is a general-purpose hook for status changes that may not
        fit into the specific on_ack/on_dismiss/on_timeout categories.

        Args:
            notification_id: UUID of the notification
            old_status: Previous AckStatus
            new_status: New AckStatus
            metadata: Optional additional context
        """
        ...


class DefaultContextProvider:
    """Default implementation of NotificationContextProvider.

    Provides a minimal context provider that can be used when no
    external context provider is available. This allows the core
    SDK to function in standalone mode for testing or simple deployments.

    Note: For production ATP integration, replace with an ATP-aware
    implementation that reads from the actual agent state.
    """

    def __init__(
        self,
        default_mode: AutonomyMode | None = None,
        default_agent_id: UUID | None = None,
    ) -> None:
        """Initialize with optional default values.

        Args:
            default_mode: Default autonomy mode to use
            default_agent_id: Default agent ID to use
        """
        # Import here to avoid circular imports at module level
        from notification.models import AutonomyMode

        self._default_mode = default_mode or AutonomyMode.PREVIEW
        self._default_agent_id = default_agent_id
        self._contexts: dict[UUID, AutonomyContext] = {}

    def register_context(self, agent_id: UUID, context: AutonomyContext) -> None:
        """Register a context for a specific agent.

        This allows pre-configuration of contexts for testing or
        simple deployments without a full ATP integration.

        Args:
            agent_id: UUID of the agent
            context: AutonomyContext to register
        """
        self._contexts[agent_id] = context

    def unregister_context(self, agent_id: UUID) -> None:
        """Remove a registered context.

        Args:
            agent_id: UUID of the agent to unregister

        Raises:
            KeyError: If agent_id is not registered
        """
        del self._contexts[agent_id]

    def get_current_context(self) -> AutonomyContext:
        """Get a default context using configured defaults.

        Returns:
            AutonomyContext with default mode and agent_id

        Raises:
            RuntimeError: If no default agent_id is configured
        """
        from notification.models import AutonomyContext

        if self._default_agent_id is None:
            raise RuntimeError(
                "No default agent_id configured. "
                "Either configure a default or use get_context_for_agent()."
            )

        if self._default_agent_id in self._contexts:
            return self._contexts[self._default_agent_id]

        return AutonomyContext(
            autonomy_mode=self._default_mode,
            agent_id=self._default_agent_id,
        )

    def get_context_for_agent(self, agent_id: UUID) -> AutonomyContext:
        """Get context for a specific agent.

        Args:
            agent_id: UUID of the agent

        Returns:
            Registered AutonomyContext or a new one with default mode

        Raises:
            KeyError: If agent is not registered and strict mode is desired
        """
        from notification.models import AutonomyContext

        if agent_id in self._contexts:
            return self._contexts[agent_id]

        # Return a default context for unregistered agents
        return AutonomyContext(
            autonomy_mode=self._default_mode,
            agent_id=agent_id,
        )

    def get_autonomy_mode(self) -> AutonomyMode:
        """Get the default autonomy mode.

        Returns:
            The configured default AutonomyMode
        """
        return self._default_mode

    def update_mode(self, mode: AutonomyMode) -> None:
        """Update the default autonomy mode (for testing/configuration)."""
        self._default_mode = mode

class NoOpAcknowledgmentCallback:
    """No-operation implementation of AcknowledgmentCallback.

    Provides a silent implementation that can be used when no
    external callback handling is needed. Useful for testing
    or deployments that don't require ack event propagation.
    """

    def on_ack(self, event: AckEvent) -> None:
        """No-op: silently accepts ack events."""
        pass

    def on_dismiss(self, event: AckEvent) -> None:
        """No-op: silently accepts dismiss events."""
        pass

    def on_timeout(self, event: AckEvent) -> None:
        """No-op: silently accepts timeout events."""
        pass

    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """No-op: silently accepts status change events."""
        pass


class LoggingAcknowledgmentCallback:
    """Logging implementation of AcknowledgmentCallback.

    Logs all acknowledgment events for debugging and audit purposes.
    Can be used in development or as a base for more complex callbacks.
    """

    def __init__(self, logger: Any | None = None) -> None:
        """Initialize with optional logger.

        Args:
            logger: Logger instance. If None, uses standard logging.
        """
        if logger is None:
            import logging

            self._logger = logging.getLogger(__name__)
        else:
            self._logger = logger

    def on_ack(self, event: AckEvent) -> None:
        """Log acknowledgment event."""
        self._logger.info(
            "Notification acknowledged: notification_id=%s, acked_by=%s",
            event.notification_id,
            event.acked_by,
        )

    def on_dismiss(self, event: AckEvent) -> None:
        """Log dismissal event."""
        self._logger.info(
            "Notification dismissed: notification_id=%s, dismissed_by=%s",
            event.notification_id,
            event.acked_by,
        )

    def on_timeout(self, event: AckEvent) -> None:
        """Log timeout event."""
        self._logger.warning(
            "Notification timed out: notification_id=%s",
            event.notification_id,
        )

    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log status change event."""
        self._logger.info(
            "Notification status changed: notification_id=%s, %s -> %s, metadata=%s",
            notification_id,
            old_status,
            new_status,
            metadata,
        )


class CompositeAcknowledgmentCallback:
    """Composite callback that delegates to multiple callbacks.

    Allows combining multiple acknowledgment handlers (e.g., logging +
    metrics + ATP integration) into a single callback instance.
    """

    def __init__(self, callbacks: list[AcknowledgmentCallback] | None = None) -> None:
        """Initialize with optional list of callbacks.

        Args:
            callbacks: List of AcknowledgmentCallback implementations
        """
        self._callbacks: list[AcknowledgmentCallback] = callbacks or []

    def add_callback(self, callback: AcknowledgmentCallback) -> None:
        """Add a callback to the composite.

        Args:
            callback: AcknowledgmentCallback to add
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: AcknowledgmentCallback) -> None:
        """Remove a callback from the composite.

        Args:
            callback: AcknowledgmentCallback to remove

        Raises:
            ValueError: If callback is not in the list
        """
        self._callbacks.remove(callback)

    def on_ack(self, event: AckEvent) -> None:
        """Delegate to all registered callbacks."""
        for callback in self._callbacks:
            callback.on_ack(event)

    def on_dismiss(self, event: AckEvent) -> None:
        """Delegate to all registered callbacks."""
        for callback in self._callbacks:
            callback.on_dismiss(event)

    def on_timeout(self, event: AckEvent) -> None:
        """Delegate to all registered callbacks."""
        for callback in self._callbacks:
            callback.on_timeout(event)

    def on_status_change(
        self,
        notification_id: UUID,
        old_status: AckStatus,
        new_status: AckStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Delegate to all registered callbacks."""
        for callback in self._callbacks:
            callback.on_status_change(notification_id, old_status, new_status, metadata)

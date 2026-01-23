"""Interfaces for integration - dependency injection protocols.

This module provides protocols that allow the UNS core to remain
ATP-agnostic. Producers can inject their own context providers
and callbacks.
"""

from typing import Protocol, runtime_checkable
from uuid import UUID

from .models import AckStatus, AutonomyContext, AutonomyMode


@runtime_checkable
class NotificationContextProvider(Protocol):
    """Protocol for providing autonomy context to notifications.

    Implementations should fetch current agent context from
    external systems (e.g., ATP).
    """

    def get_current_context(self) -> AutonomyContext:
        """Retrieve the current autonomy context.

        Returns:
            AutonomyContext with current mode, agent_id, and optional snapshot IDs.

        Raises:
            RuntimeError: If context cannot be determined.
        """
        ...

    def get_agent_id(self) -> UUID:
        """Get the current agent identifier."""
        ...

    def get_autonomy_mode(self) -> AutonomyMode:
        """Get the current operating mode."""
        ...


@runtime_checkable
class AcknowledgmentCallback(Protocol):
    """Protocol for handling acknowledgment events.

    Implementations can trigger side effects when notifications
    are acknowledged (e.g., updating ATP state, logging).
    """

    def on_ack(
        self,
        notification_id: UUID,
        ack_status: AckStatus,
        acked_by: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Called when a notification is acknowledged.

        Args:
            notification_id: The notification that was acknowledged.
            ack_status: The acknowledgment status.
            acked_by: Optional identifier of who acknowledged.
            metadata: Optional additional metadata about the ack.
        """
        ...

    def on_timeout(
        self,
        notification_id: UUID,
        metadata: dict | None = None,
    ) -> None:
        """Called when a notification acknowledgment times out.

        Args:
            notification_id: The notification that timed out.
            metadata: Optional additional metadata.
        """
        ...


class DefaultContextProvider:
    """Default implementation of NotificationContextProvider.

    This is a simple implementation that can be configured with
    static values. For production use, implement a provider that
    fetches context from your actual agent/autonomy system.
    """

    def __init__(
        self,
        agent_id: UUID,
        autonomy_mode: AutonomyMode = AutonomyMode.PREVIEW,
        plan_id: UUID | None = None,
        decision_snapshot_id: UUID | None = None,
        execution_snapshot_id: UUID | None = None,
        skip_snapshot_id: UUID | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._autonomy_mode = autonomy_mode
        self._plan_id = plan_id
        self._decision_snapshot_id = decision_snapshot_id
        self._execution_snapshot_id = execution_snapshot_id
        self._skip_snapshot_id = skip_snapshot_id

    def get_current_context(self) -> AutonomyContext:
        return AutonomyContext(
            autonomy_mode=self._autonomy_mode,
            agent_id=self._agent_id,
            plan_id=self._plan_id,
            decision_snapshot_id=self._decision_snapshot_id,
            execution_snapshot_id=self._execution_snapshot_id,
            skip_snapshot_id=self._skip_snapshot_id,
        )

    def get_agent_id(self) -> UUID:
        return self._agent_id

    def get_autonomy_mode(self) -> AutonomyMode:
        return self._autonomy_mode

    def update_mode(self, mode: AutonomyMode) -> None:
        """Update the autonomy mode (for testing/configuration)."""
        self._autonomy_mode = mode

    def update_plan_id(self, plan_id: UUID | None) -> None:
        """Update the plan ID."""
        self._plan_id = plan_id


class NoOpAcknowledgmentCallback:
    """Default no-op implementation of AcknowledgmentCallback.

    Use this when you don't need to handle ack events externally.
    """

    def on_ack(
        self,
        notification_id: UUID,
        ack_status: AckStatus,
        acked_by: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """No-op acknowledgment handler."""
        pass

    def on_timeout(
        self,
        notification_id: UUID,
        metadata: dict | None = None,
    ) -> None:
        """No-op timeout handler."""
        pass

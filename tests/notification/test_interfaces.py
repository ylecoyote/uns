"""Tests for integration interfaces (ContextProvider, AckCallback).

These tests verify that:
- Protocols properly define the required interface
- Default implementations work correctly
- Core SDK can run without ATP imports (ATP-agnostic)
"""

import logging
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from notification.interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
)
from notification.models import AckEvent, AckStatus, AutonomyContext, AutonomyMode


class TestNotificationContextProviderProtocol:
    """Tests for NotificationContextProvider protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Verify the protocol can be used with isinstance()."""
        # DefaultContextProvider should satisfy the protocol
        provider = DefaultContextProvider(
            default_mode=AutonomyMode.PREVIEW,
            default_agent_id=uuid4(),
        )
        assert isinstance(provider, NotificationContextProvider)

    def test_custom_implementation_satisfies_protocol(self) -> None:
        """Verify custom implementations satisfy the protocol."""

        class CustomProvider:
            def get_current_context(self) -> AutonomyContext:
                return AutonomyContext(
                    autonomy_mode=AutonomyMode.LIVE,
                    agent_id=uuid4(),
                )

            def get_context_for_agent(self, agent_id) -> AutonomyContext:
                return AutonomyContext(
                    autonomy_mode=AutonomyMode.SHADOW,
                    agent_id=agent_id,
                )

            def get_autonomy_mode(self) -> AutonomyMode:
                return AutonomyMode.LIVE

        provider = CustomProvider()
        assert isinstance(provider, NotificationContextProvider)


class TestDefaultContextProvider:
    """Tests for DefaultContextProvider implementation."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        provider = DefaultContextProvider()
        assert provider._default_mode == AutonomyMode.PREVIEW

    def test_init_with_custom_mode(self) -> None:
        """Test initialization with custom mode."""
        provider = DefaultContextProvider(default_mode=AutonomyMode.LIVE)
        assert provider._default_mode == AutonomyMode.LIVE

    def test_init_with_custom_agent_id(self) -> None:
        """Test initialization with custom agent ID."""
        agent_id = uuid4()
        provider = DefaultContextProvider(default_agent_id=agent_id)
        assert provider._default_agent_id == agent_id

    def test_get_current_context_without_default_agent_raises(self) -> None:
        """Test that get_current_context raises without default agent."""
        provider = DefaultContextProvider()
        with pytest.raises(RuntimeError, match="No default agent_id configured"):
            provider.get_current_context()

    def test_get_current_context_with_default_agent(self) -> None:
        """Test get_current_context with configured default agent."""
        agent_id = uuid4()
        provider = DefaultContextProvider(
            default_mode=AutonomyMode.SHADOW,
            default_agent_id=agent_id,
        )
        context = provider.get_current_context()
        assert context.autonomy_mode == AutonomyMode.SHADOW
        assert context.agent_id == agent_id

    def test_get_current_context_prefers_registered_context(self) -> None:
        """Test that registered context is preferred over default."""
        agent_id = uuid4()
        plan_id = uuid4()
        provider = DefaultContextProvider(
            default_mode=AutonomyMode.PREVIEW,
            default_agent_id=agent_id,
        )
        registered_context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
            plan_id=plan_id,
        )
        provider.register_context(agent_id, registered_context)

        context = provider.get_current_context()
        assert context.autonomy_mode == AutonomyMode.LIVE
        assert context.plan_id == plan_id

    def test_register_and_get_context_for_agent(self) -> None:
        """Test registering and retrieving context for specific agent."""
        provider = DefaultContextProvider()
        agent_id = uuid4()
        plan_id = uuid4()

        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
            plan_id=plan_id,
        )
        provider.register_context(agent_id, context)

        retrieved = provider.get_context_for_agent(agent_id)
        assert retrieved == context

    def test_get_context_for_unregistered_agent_returns_default(self) -> None:
        """Test that unregistered agents get a default context."""
        provider = DefaultContextProvider(default_mode=AutonomyMode.SHADOW)
        agent_id = uuid4()

        context = provider.get_context_for_agent(agent_id)
        assert context.agent_id == agent_id
        assert context.autonomy_mode == AutonomyMode.SHADOW

    def test_unregister_context(self) -> None:
        """Test unregistering a context."""
        provider = DefaultContextProvider()
        agent_id = uuid4()
        context = AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )
        provider.register_context(agent_id, context)
        provider.unregister_context(agent_id)

        # Should now return default context
        retrieved = provider.get_context_for_agent(agent_id)
        assert retrieved.autonomy_mode == AutonomyMode.PREVIEW  # default

    def test_unregister_unknown_agent_raises(self) -> None:
        """Test that unregistering unknown agent raises KeyError."""
        provider = DefaultContextProvider()
        with pytest.raises(KeyError):
            provider.unregister_context(uuid4())

    def test_get_autonomy_mode(self) -> None:
        """Test getting the default autonomy mode."""
        provider = DefaultContextProvider(default_mode=AutonomyMode.LIVE)
        assert provider.get_autonomy_mode() == AutonomyMode.LIVE


class TestAcknowledgmentCallbackProtocol:
    """Tests for AcknowledgmentCallback protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Verify the protocol can be used with isinstance()."""
        callback = NoOpAcknowledgmentCallback()
        assert isinstance(callback, AcknowledgmentCallback)

    def test_custom_implementation_satisfies_protocol(self) -> None:
        """Verify custom implementations satisfy the protocol."""

        class CustomCallback:
            def on_ack(self, event: AckEvent) -> None:
                pass

            def on_dismiss(self, event: AckEvent) -> None:
                pass

            def on_timeout(self, event: AckEvent) -> None:
                pass

            def on_status_change(
                self, notification_id, old_status, new_status, metadata=None
            ) -> None:
                pass

        callback = CustomCallback()
        assert isinstance(callback, AcknowledgmentCallback)


class TestNoOpAcknowledgmentCallback:
    """Tests for NoOpAcknowledgmentCallback."""

    def test_on_ack_does_nothing(self) -> None:
        """Test that on_ack silently succeeds."""
        callback = NoOpAcknowledgmentCallback()
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.ACKED,
            acked_by="test_user",
        )
        # Should not raise
        callback.on_ack(event)

    def test_on_dismiss_does_nothing(self) -> None:
        """Test that on_dismiss silently succeeds."""
        callback = NoOpAcknowledgmentCallback()
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.DISMISSED,
        )
        callback.on_dismiss(event)

    def test_on_timeout_does_nothing(self) -> None:
        """Test that on_timeout silently succeeds."""
        callback = NoOpAcknowledgmentCallback()
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.TIMED_OUT,
        )
        callback.on_timeout(event)

    def test_on_status_change_does_nothing(self) -> None:
        """Test that on_status_change silently succeeds."""
        callback = NoOpAcknowledgmentCallback()
        callback.on_status_change(
            notification_id=uuid4(),
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )


class TestLoggingAcknowledgmentCallback:
    """Tests for LoggingAcknowledgmentCallback."""

    def test_on_ack_logs_info(self) -> None:
        """Test that on_ack logs at INFO level."""
        mock_logger = MagicMock()
        callback = LoggingAcknowledgmentCallback(logger=mock_logger)
        notification_id = uuid4()
        event = AckEvent(
            notification_id=notification_id,
            ack_status=AckStatus.ACKED,
            acked_by="test_user",
        )

        callback.on_ack(event)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "acknowledged" in call_args[0][0].lower()

    def test_on_dismiss_logs_info(self) -> None:
        """Test that on_dismiss logs at INFO level."""
        mock_logger = MagicMock()
        callback = LoggingAcknowledgmentCallback(logger=mock_logger)
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.DISMISSED,
            acked_by="test_user",
        )

        callback.on_dismiss(event)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "dismissed" in call_args[0][0].lower()

    def test_on_timeout_logs_warning(self) -> None:
        """Test that on_timeout logs at WARNING level."""
        mock_logger = MagicMock()
        callback = LoggingAcknowledgmentCallback(logger=mock_logger)
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.TIMED_OUT,
        )

        callback.on_timeout(event)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "timed out" in call_args[0][0].lower()

    def test_on_status_change_logs_info(self) -> None:
        """Test that on_status_change logs at INFO level."""
        mock_logger = MagicMock()
        callback = LoggingAcknowledgmentCallback(logger=mock_logger)

        callback.on_status_change(
            notification_id=uuid4(),
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "status changed" in call_args[0][0].lower()

    def test_uses_default_logger_when_none_provided(self) -> None:
        """Test that a default logger is created when none provided."""
        callback = LoggingAcknowledgmentCallback()
        assert callback._logger is not None
        assert isinstance(callback._logger, logging.Logger)


class TestCompositeAcknowledgmentCallback:
    """Tests for CompositeAcknowledgmentCallback."""

    def test_empty_composite_does_nothing(self) -> None:
        """Test that empty composite handles events without error."""
        callback = CompositeAcknowledgmentCallback()
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.ACKED,
        )
        # Should not raise
        callback.on_ack(event)

    def test_delegates_to_all_callbacks(self) -> None:
        """Test that events are delegated to all registered callbacks."""
        mock1 = MagicMock(spec=AcknowledgmentCallback)
        mock2 = MagicMock(spec=AcknowledgmentCallback)

        composite = CompositeAcknowledgmentCallback(callbacks=[mock1, mock2])
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.ACKED,
            acked_by="user",
        )

        composite.on_ack(event)

        mock1.on_ack.assert_called_once_with(event)
        mock2.on_ack.assert_called_once_with(event)

    def test_on_dismiss_delegates_to_all(self) -> None:
        """Test on_dismiss delegates to all callbacks."""
        mock1 = MagicMock(spec=AcknowledgmentCallback)
        mock2 = MagicMock(spec=AcknowledgmentCallback)

        composite = CompositeAcknowledgmentCallback(callbacks=[mock1, mock2])
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.DISMISSED,
        )

        composite.on_dismiss(event)

        mock1.on_dismiss.assert_called_once_with(event)
        mock2.on_dismiss.assert_called_once_with(event)

    def test_on_timeout_delegates_to_all(self) -> None:
        """Test on_timeout delegates to all callbacks."""
        mock1 = MagicMock(spec=AcknowledgmentCallback)
        mock2 = MagicMock(spec=AcknowledgmentCallback)

        composite = CompositeAcknowledgmentCallback(callbacks=[mock1, mock2])
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.TIMED_OUT,
        )

        composite.on_timeout(event)

        mock1.on_timeout.assert_called_once_with(event)
        mock2.on_timeout.assert_called_once_with(event)

    def test_on_status_change_delegates_to_all(self) -> None:
        """Test on_status_change delegates to all callbacks."""
        mock1 = MagicMock(spec=AcknowledgmentCallback)
        mock2 = MagicMock(spec=AcknowledgmentCallback)

        composite = CompositeAcknowledgmentCallback(callbacks=[mock1, mock2])
        notification_id = uuid4()

        composite.on_status_change(
            notification_id=notification_id,
            old_status=AckStatus.PENDING,
            new_status=AckStatus.ACKED,
            metadata={"key": "value"},
        )

        mock1.on_status_change.assert_called_once_with(
            notification_id, AckStatus.PENDING, AckStatus.ACKED, {"key": "value"}
        )
        mock2.on_status_change.assert_called_once_with(
            notification_id, AckStatus.PENDING, AckStatus.ACKED, {"key": "value"}
        )

    def test_add_callback(self) -> None:
        """Test adding a callback dynamically."""
        composite = CompositeAcknowledgmentCallback()
        mock = MagicMock(spec=AcknowledgmentCallback)

        composite.add_callback(mock)

        event = AckEvent(notification_id=uuid4(), ack_status=AckStatus.ACKED)
        composite.on_ack(event)

        mock.on_ack.assert_called_once_with(event)

    def test_remove_callback(self) -> None:
        """Test removing a callback dynamically."""
        mock = MagicMock(spec=AcknowledgmentCallback)
        composite = CompositeAcknowledgmentCallback(callbacks=[mock])

        composite.remove_callback(mock)

        event = AckEvent(notification_id=uuid4(), ack_status=AckStatus.ACKED)
        composite.on_ack(event)

        mock.on_ack.assert_not_called()

    def test_remove_unknown_callback_raises(self) -> None:
        """Test that removing unknown callback raises ValueError."""
        composite = CompositeAcknowledgmentCallback()
        mock = MagicMock(spec=AcknowledgmentCallback)

        with pytest.raises(ValueError):
            composite.remove_callback(mock)


class TestATPAgnostic:
    """Tests verifying core SDK can run without ATP imports.

    These tests ensure the fundamental design goal is met: UNS core
    should be fully functional without any ATP-specific dependencies.
    """

    def test_interfaces_import_without_atp(self) -> None:
        """Verify interfaces module imports without ATP."""
        # This test passes if the import at the top of the file succeeds
        # The fact that we can run these tests proves ATP-agnosticism
        from notification.interfaces import (
            AcknowledgmentCallback,
            DefaultContextProvider,
            NotificationContextProvider,
        )

        assert NotificationContextProvider is not None
        assert AcknowledgmentCallback is not None
        assert DefaultContextProvider is not None

    def test_default_provider_works_standalone(self) -> None:
        """Verify DefaultContextProvider works without ATP."""
        agent_id = uuid4()
        provider = DefaultContextProvider(
            default_mode=AutonomyMode.PREVIEW,
            default_agent_id=agent_id,
        )

        context = provider.get_current_context()
        assert context.agent_id == agent_id
        assert context.autonomy_mode == AutonomyMode.PREVIEW

    def test_noop_callback_works_standalone(self) -> None:
        """Verify NoOpAcknowledgmentCallback works without ATP."""
        callback = NoOpAcknowledgmentCallback()
        event = AckEvent(
            notification_id=uuid4(),
            ack_status=AckStatus.ACKED,
        )
        # All operations should succeed silently
        callback.on_ack(event)
        callback.on_dismiss(event)
        callback.on_timeout(event)
        callback.on_status_change(uuid4(), AckStatus.PENDING, AckStatus.ACKED)

    def test_protocol_based_injection(self) -> None:
        """Verify protocol-based dependency injection works.

        This simulates how ATP would inject its own implementations
        without UNS needing to know about ATP.
        """

        # Simulate ATP implementation
        class ATPContextProvider:
            def __init__(self) -> None:
                self.agent_id = uuid4()

            def get_current_context(self) -> AutonomyContext:
                return AutonomyContext(
                    autonomy_mode=AutonomyMode.LIVE,
                    agent_id=self.agent_id,
                    plan_id=uuid4(),  # ATP would provide real IDs
                )

            def get_context_for_agent(self, agent_id) -> AutonomyContext:
                return AutonomyContext(
                    autonomy_mode=AutonomyMode.SHADOW,
                    agent_id=agent_id,
                )

            def get_autonomy_mode(self) -> AutonomyMode:
                return AutonomyMode.LIVE

        # UNS accepts any protocol-compatible provider
        def use_provider(provider: NotificationContextProvider) -> AutonomyContext:
            return provider.get_current_context()

        atp_provider = ATPContextProvider()
        assert isinstance(atp_provider, NotificationContextProvider)

        context = use_provider(atp_provider)
        assert context.autonomy_mode == AutonomyMode.LIVE

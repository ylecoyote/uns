"""Tests for notification delivery adapters.

This module tests all channel adapters (Slack, Email, WebSocket, PagerDuty)
including their delivery, health check, and error handling functionality.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from notification.adapters import (
    AdapterConfigurationError,
    AdapterDeliveryError,
    AdapterRegistry,
    AdapterStatus,
    AdapterTimeoutError,
    DeliveryResult,
    EmailAdapter,
    EmailConfig,
    HealthCheckResult,
    InMemoryConnectionManager,
    PagerDutyAdapter,
    PagerDutyConfig,
    PagerDutySeverity,
    SlackAdapter,
    SlackConfig,
    WebSocketAdapter,
    WebSocketConfig,
    get_adapter,
)
from notification.models import (
    AutonomyContext,
    AutonomyMode,
    Channel,
    Notification,
    NotificationIntent,
    Priority,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def autonomy_context() -> AutonomyContext:
    """Create a test autonomy context."""
    return AutonomyContext(
        autonomy_mode=AutonomyMode.LIVE,
        agent_id=uuid4(),
    )


@pytest.fixture
def sample_notification(autonomy_context: AutonomyContext) -> Notification:
    """Create a sample notification for testing."""
    return Notification(
        notification_type="test.alert",
        intent=NotificationIntent.SAFETY,
        autonomy_context=autonomy_context,
        title="Test Alert",
        message="This is a test notification message.",
        source="test-suite",
        priority=Priority.HIGH,
        require_ack=True,
        ack_timeout_minutes=15,
        irreversible=True,
    )


@pytest.fixture
def info_notification(autonomy_context: AutonomyContext) -> Notification:
    """Create an informational notification for testing."""
    return Notification(
        notification_type="test.info",
        intent=NotificationIntent.INFORMATIONAL,
        autonomy_context=autonomy_context,
        title="Test Info",
        message="This is an informational message.",
        source="test-suite",
        priority=Priority.LOW,
    )


# ============================================================================
# Base Adapter Tests
# ============================================================================


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""

    def test_success_result(self) -> None:
        result = DeliveryResult(
            success=True,
            channel=Channel.SLACK,
            message_id="12345.67890",
            delivered_at=datetime.now(UTC),
        )
        assert result.success is True
        assert result.channel == Channel.SLACK
        assert result.message_id == "12345.67890"
        assert result.error is None

    def test_failure_result(self) -> None:
        result = DeliveryResult(
            success=False,
            channel=Channel.EMAIL,
            error="SMTP connection failed",
        )
        assert result.success is False
        assert result.error == "SMTP connection failed"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_healthy_result(self) -> None:
        result = HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="All systems operational",
            latency_ms=42.5,
        )
        assert result.status == AdapterStatus.HEALTHY
        assert result.latency_ms == 42.5

    def test_unhealthy_result(self) -> None:
        result = HealthCheckResult(
            status=AdapterStatus.UNHEALTHY,
            message="Connection failed",
            metadata={"error_code": 500},
        )
        assert result.status == AdapterStatus.UNHEALTHY
        assert result.metadata == {"error_code": 500}


class TestAdapterErrors:
    """Tests for adapter exception classes."""

    def test_adapter_error(self) -> None:
        error = AdapterDeliveryError(
            "Delivery failed",
            channel=Channel.SLACK,
            retryable=True,
        )
        assert str(error) == "Delivery failed"
        assert error.channel == Channel.SLACK
        assert error.retryable is True

    def test_configuration_error(self) -> None:
        error = AdapterConfigurationError(
            "Invalid token",
            channel=Channel.SLACK,
        )
        assert error.retryable is False

    def test_timeout_error(self) -> None:
        error = AdapterTimeoutError(
            "Request timed out",
            channel=Channel.PAGERDUTY,
            timeout_seconds=30.0,
        )
        assert error.retryable is True
        assert error.timeout_seconds == 30.0


# ============================================================================
# Slack Adapter Tests
# ============================================================================


class TestSlackConfig:
    """Tests for SlackConfig validation."""

    def test_valid_config(self) -> None:
        config = SlackConfig(
            bot_token="xoxb-1234567890-1234567890123-abcdefghijklmnop",
            default_channel="#alerts",
        )
        assert config.bot_token.startswith("xoxb-")
        assert config.default_channel == "#alerts"

    def test_missing_token(self) -> None:
        with pytest.raises(ValueError, match="bot_token is required"):
            SlackConfig(bot_token="", default_channel="#alerts")

    def test_invalid_token_prefix(self) -> None:
        with pytest.raises(ValueError, match="bot token"):
            SlackConfig(bot_token="invalid-token", default_channel="#alerts")

    def test_missing_channel(self) -> None:
        with pytest.raises(ValueError, match="default_channel is required"):
            SlackConfig(
                bot_token="xoxb-1234567890-1234567890123-abcdefghijklmnop",
                default_channel="",
            )


class TestSlackAdapter:
    """Tests for SlackAdapter."""

    @pytest.fixture
    def slack_config(self) -> SlackConfig:
        return SlackConfig(
            bot_token="xoxb-1234567890-1234567890123-abcdefghijklmnop",
            default_channel="#alerts",
            timeout_seconds=10.0,
            retry_attempts=2,
        )

    @pytest.fixture
    def slack_adapter(self, slack_config: SlackConfig) -> SlackAdapter:
        return SlackAdapter(config=slack_config)

    def test_channel_property(self, slack_adapter: SlackAdapter) -> None:
        assert slack_adapter.channel == Channel.SLACK

    def test_format_message(
        self, slack_adapter: SlackAdapter, sample_notification: Notification
    ) -> None:
        message = slack_adapter.format_message(sample_notification)
        assert ":rotating_light:" in message  # SAFETY emoji
        assert "Test Alert" in message
        assert sample_notification.message in message

    def test_build_blocks(
        self, slack_adapter: SlackAdapter, sample_notification: Notification
    ) -> None:
        blocks = slack_adapter._build_blocks(sample_notification)
        assert len(blocks) >= 4
        assert blocks[0]["type"] == "header"
        assert "SAFETY" in blocks[2]["elements"][0]["text"]

    def test_build_blocks_with_ack_buttons(
        self, slack_adapter: SlackAdapter, sample_notification: Notification
    ) -> None:
        blocks = slack_adapter._build_blocks(sample_notification)
        # Should have action buttons for ack-required notifications
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        assert len(actions[0]["elements"]) == 2  # Ack and Dismiss buttons

    @pytest.mark.asyncio
    async def test_deliver_success(
        self, slack_adapter: SlackAdapter, sample_notification: Notification
    ) -> None:
        with patch.object(
            slack_adapter._client,
            "post_message",
            new_callable=AsyncMock,
            return_value={"ok": True, "ts": "1234567890.123456", "channel": "C12345"},
        ):
            result = await slack_adapter.deliver(sample_notification)
            assert result.success is True
            assert result.channel == Channel.SLACK
            assert result.message_id == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_deliver_failure_retryable(
        self, slack_adapter: SlackAdapter, sample_notification: Notification
    ) -> None:
        with patch.object(
            slack_adapter._client,
            "post_message",
            new_callable=AsyncMock,
            side_effect=AdapterDeliveryError("rate_limited", retryable=True),
        ):
            result = await slack_adapter.deliver(sample_notification)
            assert result.success is False
            assert "rate_limited" in result.error

    @pytest.mark.asyncio
    async def test_deliver_timeout(
        self, slack_adapter: SlackAdapter, sample_notification: Notification
    ) -> None:
        with patch.object(
            slack_adapter._client,
            "post_message",
            new_callable=AsyncMock,
            side_effect=AdapterTimeoutError("timeout", channel=Channel.SLACK),
        ):
            result = await slack_adapter.deliver(sample_notification)
            assert result.success is False
            assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_health_check_success(self, slack_adapter: SlackAdapter) -> None:
        with patch.object(
            slack_adapter._client,
            "auth_test",
            new_callable=AsyncMock,
            return_value={"ok": True, "user_id": "U12345"},
        ):
            result = await slack_adapter.health_check()
            assert result.status == AdapterStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_failure(self, slack_adapter: SlackAdapter) -> None:
        with patch.object(
            slack_adapter._client,
            "auth_test",
            new_callable=AsyncMock,
            side_effect=AdapterConfigurationError("invalid_auth"),
        ):
            result = await slack_adapter.health_check()
            assert result.status == AdapterStatus.UNHEALTHY


# ============================================================================
# Email Adapter Tests
# ============================================================================


class TestEmailConfig:
    """Tests for EmailConfig validation."""

    def test_valid_config(self) -> None:
        config = EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user@example.com",
            password="password123",
            from_address="noreply@example.com",
            default_to_addresses=["alerts@example.com"],
        )
        assert config.smtp_host == "smtp.example.com"
        assert config.use_tls is True

    def test_missing_host(self) -> None:
        with pytest.raises(ValueError, match="smtp_host is required"):
            EmailConfig(
                smtp_host="",
                smtp_port=587,
                username="user",
                password="pass",
                from_address="from@example.com",
                default_to_addresses=["to@example.com"],
            )

    def test_tls_and_ssl_conflict(self) -> None:
        with pytest.raises(ValueError, match="Cannot use both TLS and SSL"):
            EmailConfig(
                smtp_host="smtp.example.com",
                smtp_port=587,
                username="user",
                password="pass",
                from_address="from@example.com",
                default_to_addresses=["to@example.com"],
                use_tls=True,
                use_ssl=True,
            )


class TestEmailAdapter:
    """Tests for EmailAdapter."""

    @pytest.fixture
    def email_config(self) -> EmailConfig:
        return EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user@example.com",
            password="password123",
            from_address="noreply@example.com",
            default_to_addresses=["alerts@example.com"],
            timeout_seconds=10.0,
            retry_attempts=2,
        )

    @pytest.fixture
    def email_adapter(self, email_config: EmailConfig) -> EmailAdapter:
        return EmailAdapter(config=email_config)

    def test_channel_property(self, email_adapter: EmailAdapter) -> None:
        assert email_adapter.channel == Channel.EMAIL

    def test_format_message(
        self, email_adapter: EmailAdapter, sample_notification: Notification
    ) -> None:
        message = email_adapter.format_message(sample_notification)
        assert "Intent: SAFETY" in message
        assert "Test Alert" in message
        assert sample_notification.message in message
        assert "requires acknowledgment" in message

    def test_build_message(
        self, email_adapter: EmailAdapter, sample_notification: Notification
    ) -> None:
        to_addresses = ["test@example.com"]
        message = email_adapter._build_message(sample_notification, to_addresses)

        assert "[SAFETY ALERT]" in message["Subject"]
        assert email_adapter.config.from_address == message["From"]
        assert message["X-Priority"] == "1"  # HIGH priority

    def test_get_recipients_default(
        self, email_adapter: EmailAdapter, sample_notification: Notification
    ) -> None:
        recipients = email_adapter._get_recipients(sample_notification)
        assert recipients == ["alerts@example.com"]

    def test_get_recipients_from_metadata(
        self, email_adapter: EmailAdapter, sample_notification: Notification
    ) -> None:
        sample_notification.metadata["email_to"] = ["custom@example.com"]
        recipients = email_adapter._get_recipients(sample_notification)
        assert recipients == ["custom@example.com"]

    @pytest.mark.asyncio
    async def test_deliver_success(
        self, email_adapter: EmailAdapter, sample_notification: Notification
    ) -> None:
        with patch.object(
            email_adapter,
            "_send_email_sync",
            return_value=None,
        ):
            result = await email_adapter.deliver(sample_notification)
            assert result.success is True
            assert result.channel == Channel.EMAIL

    @pytest.mark.asyncio
    async def test_health_check_success(self, email_adapter: EmailAdapter) -> None:
        with patch.object(
            email_adapter,
            "_check_connection_sync",
            return_value=None,
        ):
            result = await email_adapter.health_check()
            assert result.status == AdapterStatus.HEALTHY
            assert "smtp.example.com" in result.metadata.get("smtp_host", "")


# ============================================================================
# WebSocket Adapter Tests
# ============================================================================


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self, is_connected: bool = True) -> None:
        self._is_connected = is_connected
        self.sent_messages: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def send(self, message: str) -> None:
        if not self._is_connected:
            raise ConnectionError("Not connected")
        self.sent_messages.append(message)

    async def close(self) -> None:
        self._is_connected = False


class TestInMemoryConnectionManager:
    """Tests for InMemoryConnectionManager."""

    @pytest.fixture
    def manager(self) -> InMemoryConnectionManager:
        return InMemoryConnectionManager()

    @pytest.mark.asyncio
    async def test_register_and_broadcast(
        self, manager: InMemoryConnectionManager
    ) -> None:
        conn1 = MockWebSocketConnection()
        conn2 = MockWebSocketConnection()

        await manager.register("conn1", conn1)
        await manager.register("conn2", conn2)

        count = await manager.broadcast('{"test": "message"}')

        assert count == 2
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_send_to_user(self, manager: InMemoryConnectionManager) -> None:
        conn1 = MockWebSocketConnection()
        conn2 = MockWebSocketConnection()

        await manager.register("conn1", conn1, user_id="user1")
        await manager.register("conn2", conn2, user_id="user2")

        sent = await manager.send_to_user("user1", '{"test": "message"}')

        assert sent is True
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_send_to_agent(self, manager: InMemoryConnectionManager) -> None:
        conn1 = MockWebSocketConnection()
        agent_id = uuid4()

        await manager.register("conn1", conn1, agent_ids=[agent_id])

        sent = await manager.send_to_agent(agent_id, '{"test": "message"}')

        assert sent is True
        assert len(conn1.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_unregister(self, manager: InMemoryConnectionManager) -> None:
        conn1 = MockWebSocketConnection()
        await manager.register("conn1", conn1, user_id="user1")

        assert manager.get_connection_count() == 1

        await manager.unregister("conn1")

        assert manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_connection_count(self, manager: InMemoryConnectionManager) -> None:
        assert manager.get_connection_count() == 0

        conn1 = MockWebSocketConnection()
        await manager.register("conn1", conn1)

        assert manager.get_connection_count() == 1


class TestWebSocketAdapter:
    """Tests for WebSocketAdapter."""

    @pytest.fixture
    def ws_config(self) -> WebSocketConfig:
        return WebSocketConfig(
            broadcast_mode=True,
            include_metadata=True,
        )

    @pytest.fixture
    def connection_manager(self) -> InMemoryConnectionManager:
        return InMemoryConnectionManager()

    @pytest.fixture
    def ws_adapter(
        self, ws_config: WebSocketConfig, connection_manager: InMemoryConnectionManager
    ) -> WebSocketAdapter:
        return WebSocketAdapter(config=ws_config, connection_manager=connection_manager)

    def test_channel_property(self, ws_adapter: WebSocketAdapter) -> None:
        assert ws_adapter.channel == Channel.WEBSOCKET

    @pytest.mark.asyncio
    async def test_deliver_broadcast(
        self,
        ws_adapter: WebSocketAdapter,
        connection_manager: InMemoryConnectionManager,
        sample_notification: Notification,
    ) -> None:
        conn = MockWebSocketConnection()
        await connection_manager.register("conn1", conn)

        result = await ws_adapter.deliver(sample_notification)

        assert result.success is True
        assert result.channel == Channel.WEBSOCKET
        assert len(conn.sent_messages) == 1

        # Verify message structure
        payload = json.loads(conn.sent_messages[0])
        assert payload["type"] == "notification"
        assert payload["title"] == "Test Alert"
        assert payload["intent"] == "SAFETY"

    @pytest.mark.asyncio
    async def test_deliver_no_clients(
        self, ws_adapter: WebSocketAdapter, sample_notification: Notification
    ) -> None:
        result = await ws_adapter.deliver(sample_notification)

        # Fire-and-forget: no clients is not a failure
        assert result.success is True
        assert result.metadata.get("no_clients") is True

    @pytest.mark.asyncio
    async def test_health_check(
        self,
        ws_adapter: WebSocketAdapter,
        connection_manager: InMemoryConnectionManager,
    ) -> None:
        conn = MockWebSocketConnection()
        await connection_manager.register("conn1", conn)

        result = await ws_adapter.health_check()

        assert result.status == AdapterStatus.HEALTHY
        assert result.metadata.get("connection_count") == 1

    def test_build_payload(
        self, ws_adapter: WebSocketAdapter, sample_notification: Notification
    ) -> None:
        payload = ws_adapter._build_payload(sample_notification)

        assert payload["type"] == "notification"
        assert payload["notification_type"] == "test.alert"
        assert payload["require_ack"] is True
        assert "autonomy_context" in payload


# ============================================================================
# PagerDuty Adapter Tests
# ============================================================================


class TestPagerDutyConfig:
    """Tests for PagerDutyConfig validation."""

    def test_valid_config(self) -> None:
        config = PagerDutyConfig(
            routing_key="a" * 32,  # 32 char hex string
        )
        assert len(config.routing_key) == 32

    def test_missing_routing_key(self) -> None:
        with pytest.raises(ValueError, match="routing_key is required"):
            PagerDutyConfig(routing_key="")


class TestPagerDutyAdapter:
    """Tests for PagerDutyAdapter."""

    @pytest.fixture
    def pd_config(self) -> PagerDutyConfig:
        return PagerDutyConfig(
            routing_key="a" * 32,
            timeout_seconds=10.0,
            retry_attempts=2,
        )

    @pytest.fixture
    def pd_adapter(self, pd_config: PagerDutyConfig) -> PagerDutyAdapter:
        return PagerDutyAdapter(config=pd_config)

    def test_channel_property(self, pd_adapter: PagerDutyAdapter) -> None:
        assert pd_adapter.channel == Channel.PAGERDUTY

    def test_determine_severity_safety(
        self, pd_adapter: PagerDutyAdapter, sample_notification: Notification
    ) -> None:
        severity = pd_adapter._determine_severity(sample_notification)
        assert severity == PagerDutySeverity.CRITICAL

    def test_determine_severity_info(
        self, pd_adapter: PagerDutyAdapter, info_notification: Notification
    ) -> None:
        severity = pd_adapter._determine_severity(info_notification)
        assert severity == PagerDutySeverity.INFO

    def test_build_summary(
        self, pd_adapter: PagerDutyAdapter, sample_notification: Notification
    ) -> None:
        summary = pd_adapter._build_summary(sample_notification)
        assert "[IRREVERSIBLE]" in summary
        assert "[SAFETY]" in summary
        assert "Test Alert" in summary
        assert "LIVE" in summary

    def test_build_custom_details(
        self, pd_adapter: PagerDutyAdapter, sample_notification: Notification
    ) -> None:
        details = pd_adapter._build_custom_details(sample_notification)

        assert details["notification_type"] == "test.alert"
        assert details["intent"] == "SAFETY"
        assert details["irreversible"] is True
        assert details["require_ack"] is True

    @pytest.mark.asyncio
    async def test_deliver_success(
        self, pd_adapter: PagerDutyAdapter, sample_notification: Notification
    ) -> None:
        with patch.object(
            pd_adapter._client,
            "send_event",
            new_callable=AsyncMock,
            return_value={"status": "success", "dedup_key": "test-key"},
        ):
            result = await pd_adapter.deliver(sample_notification)
            assert result.success is True
            assert result.channel == Channel.PAGERDUTY

    @pytest.mark.asyncio
    async def test_deliver_failure(
        self, pd_adapter: PagerDutyAdapter, sample_notification: Notification
    ) -> None:
        with patch.object(
            pd_adapter._client,
            "send_event",
            new_callable=AsyncMock,
            side_effect=AdapterDeliveryError("bad request", retryable=False),
        ):
            result = await pd_adapter.deliver(sample_notification)
            assert result.success is False

    @pytest.mark.asyncio
    async def test_acknowledge_incident(self, pd_adapter: PagerDutyAdapter) -> None:
        with patch.object(
            pd_adapter._client,
            "send_event",
            new_callable=AsyncMock,
            return_value={"status": "success"},
        ):
            result = await pd_adapter.acknowledge_incident("test-dedup-key")
            assert result.success is True
            assert result.metadata.get("action") == "acknowledge"

    @pytest.mark.asyncio
    async def test_resolve_incident(self, pd_adapter: PagerDutyAdapter) -> None:
        with patch.object(
            pd_adapter._client,
            "send_event",
            new_callable=AsyncMock,
            return_value={"status": "success"},
        ):
            result = await pd_adapter.resolve_incident("test-dedup-key")
            assert result.success is True
            assert result.metadata.get("action") == "resolve"

    @pytest.mark.asyncio
    async def test_health_check(self, pd_adapter: PagerDutyAdapter) -> None:
        result = await pd_adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY


# ============================================================================
# Factory and Registry Tests
# ============================================================================


class TestGetAdapter:
    """Tests for get_adapter factory function."""

    def test_get_slack_adapter(self) -> None:
        config = SlackConfig(
            bot_token="xoxb-1234567890-1234567890123-abcdefghijklmnop",
            default_channel="#alerts",
        )
        adapter = get_adapter(Channel.SLACK, config=config)
        assert isinstance(adapter, SlackAdapter)
        assert adapter.channel == Channel.SLACK

    def test_get_email_adapter(self) -> None:
        config = EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user",
            password="pass",
            from_address="from@example.com",
            default_to_addresses=["to@example.com"],
        )
        adapter = get_adapter(Channel.EMAIL, config=config)
        assert isinstance(adapter, EmailAdapter)

    def test_get_websocket_adapter(self) -> None:
        config = WebSocketConfig()
        adapter = get_adapter(Channel.WEBSOCKET, config=config)
        assert isinstance(adapter, WebSocketAdapter)

    def test_get_pagerduty_adapter(self) -> None:
        config = PagerDutyConfig(routing_key="a" * 32)
        adapter = get_adapter(Channel.PAGERDUTY, config=config)
        assert isinstance(adapter, PagerDutyAdapter)

    def test_get_adapter_with_kwargs(self) -> None:
        adapter = get_adapter(
            Channel.SLACK,
            bot_token="xoxb-1234567890-1234567890123-abcdefghijklmnop",
            default_channel="#alerts",
        )
        assert isinstance(adapter, SlackAdapter)

    def test_get_adapter_wrong_config_type(self) -> None:
        config = EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user",
            password="pass",
            from_address="from@example.com",
            default_to_addresses=["to@example.com"],
        )
        with pytest.raises(AdapterConfigurationError, match="Expected SlackConfig"):
            get_adapter(Channel.SLACK, config=config)


class TestAdapterRegistry:
    """Tests for AdapterRegistry."""

    @pytest.fixture
    def registry(self) -> AdapterRegistry:
        return AdapterRegistry()

    @pytest.fixture
    def slack_adapter(self) -> SlackAdapter:
        config = SlackConfig(
            bot_token="xoxb-1234567890-1234567890123-abcdefghijklmnop",
            default_channel="#alerts",
        )
        return SlackAdapter(config=config)

    def test_register_and_get(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        registry.register(Channel.SLACK, slack_adapter)
        assert registry.get(Channel.SLACK) is slack_adapter

    def test_register_wrong_channel(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        with pytest.raises(ValueError, match="channel mismatch"):
            registry.register(Channel.EMAIL, slack_adapter)

    def test_has(self, registry: AdapterRegistry, slack_adapter: SlackAdapter) -> None:
        assert registry.has(Channel.SLACK) is False
        registry.register(Channel.SLACK, slack_adapter)
        assert registry.has(Channel.SLACK) is True

    def test_unregister(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        registry.register(Channel.SLACK, slack_adapter)
        removed = registry.unregister(Channel.SLACK)
        assert removed is slack_adapter
        assert registry.has(Channel.SLACK) is False

    def test_list_channels(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        registry.register(Channel.SLACK, slack_adapter)
        channels = registry.list_channels()
        assert Channel.SLACK in channels

    def test_get_required_success(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        registry.register(Channel.SLACK, slack_adapter)
        adapter = registry.get_required(Channel.SLACK)
        assert adapter is slack_adapter

    def test_get_required_missing(self, registry: AdapterRegistry) -> None:
        with pytest.raises(KeyError, match="No adapter registered"):
            registry.get_required(Channel.SLACK)

    @pytest.mark.asyncio
    async def test_health_check_all(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        registry.register(Channel.SLACK, slack_adapter)

        with patch.object(
            slack_adapter._client,
            "auth_test",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ):
            results = await registry.health_check_all()
            assert Channel.SLACK in results
            assert results[Channel.SLACK].status == AdapterStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_shutdown(
        self, registry: AdapterRegistry, slack_adapter: SlackAdapter
    ) -> None:
        registry.register(Channel.SLACK, slack_adapter)

        with patch.object(
            slack_adapter, "close", new_callable=AsyncMock
        ) as mock_close:
            await registry.shutdown()
            mock_close.assert_called_once()

"""Slack adapter for notification delivery.

This module implements the Slack channel adapter using the Slack Web API.
Supports both simple text messages and rich Block Kit formatted messages.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from notification.adapters.base import (
    AdapterConfigurationError,
    AdapterDeliveryError,
    AdapterStatus,
    AdapterTimeoutError,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)
from notification.models import Channel, NotificationIntent, Priority

if TYPE_CHECKING:
    from notification.models import Notification

logger = logging.getLogger(__name__)


@dataclass
class SlackConfig:
    """Configuration for the Slack adapter.

    Attributes:
        bot_token: Slack Bot OAuth token (xoxb-...)
        default_channel: Default channel ID to post to
        timeout_seconds: Request timeout in seconds
        retry_attempts: Number of retry attempts for transient failures
        use_blocks: Whether to use Block Kit formatting
    """

    bot_token: str
    default_channel: str
    timeout_seconds: float = 30.0
    retry_attempts: int = 3
    use_blocks: bool = True

    def __post_init__(self) -> None:
        if not self.bot_token:
            raise ValueError("bot_token is required")
        if not self.bot_token.startswith("xoxb-"):
            raise ValueError("bot_token must be a bot token (xoxb-...)")
        if not self.default_channel:
            raise ValueError("default_channel is required")


# Intent to emoji mapping for visual distinction
INTENT_EMOJI: dict[NotificationIntent, str] = {
    NotificationIntent.SAFETY: ":rotating_light:",
    NotificationIntent.GOVERNANCE: ":shield:",
    NotificationIntent.OPERATIONAL: ":gear:",
    NotificationIntent.INFORMATIONAL: ":information_source:",
}

# Priority to color mapping for attachments/blocks
PRIORITY_COLOR: dict[Priority, str] = {
    Priority.HIGH: "#FF0000",  # Red
    Priority.NORMAL: "#FFA500",  # Orange
    Priority.LOW: "#808080",  # Gray
}


class SlackClient:
    """HTTP client for Slack API calls.

    This is a minimal implementation that can be replaced with
    the official slack-sdk in production.
    """

    BASE_URL = "https://slack.com/api"

    def __init__(self, bot_token: str, timeout: float = 30.0) -> None:
        self.bot_token = bot_token
        self.timeout = timeout
        self._http_client: Any = None

    async def _get_client(self) -> Any:
        """Lazily initialize HTTP client."""
        if self._http_client is None:
            try:
                import httpx

                self._http_client = httpx.AsyncClient(
                    timeout=self.timeout,
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                )
            except ImportError as e:
                raise AdapterConfigurationError(
                    "httpx is required for Slack adapter. Install with: pip install httpx",
                    channel=Channel.SLACK,
                ) from e
        return self._http_client

    async def post_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """Post a message to Slack.

        Args:
            channel: Channel ID or name
            text: Fallback text for notifications
            blocks: Optional Block Kit blocks
            thread_ts: Optional thread timestamp for replies

        Returns:
            Slack API response

        Raises:
            AdapterDeliveryError: If the API call fails
            AdapterTimeoutError: If the request times out
        """
        client = await self._get_client()
        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            import httpx

            response = await client.post(
                f"{self.BASE_URL}/chat.postMessage",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                raise AdapterDeliveryError(
                    f"Slack API error: {error}",
                    channel=Channel.SLACK,
                    retryable=error in ("rate_limited", "service_unavailable"),
                )

            return data

        except httpx.TimeoutException as e:
            raise AdapterTimeoutError(
                f"Slack request timed out: {e}",
                channel=Channel.SLACK,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.HTTPStatusError as e:
            raise AdapterDeliveryError(
                f"Slack HTTP error: {e.response.status_code}",
                channel=Channel.SLACK,
                retryable=e.response.status_code >= 500,
                original_error=e,
            ) from e
        except Exception as e:
            if isinstance(e, AdapterDeliveryError | AdapterTimeoutError):
                raise
            raise AdapterDeliveryError(
                f"Slack delivery failed: {e}",
                channel=Channel.SLACK,
                original_error=e,
            ) from e

    async def auth_test(self) -> dict[str, Any]:
        """Test authentication and get bot info.

        Returns:
            Slack API response with bot info

        Raises:
            AdapterConfigurationError: If authentication fails
        """
        client = await self._get_client()
        try:
            import httpx

            response = await client.post(f"{self.BASE_URL}/auth.test")
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                raise AdapterConfigurationError(
                    f"Slack auth failed: {data.get('error', 'unknown')}",
                    channel=Channel.SLACK,
                )
            return data

        except httpx.HTTPStatusError as e:
            raise AdapterConfigurationError(
                f"Slack auth HTTP error: {e.response.status_code}",
                channel=Channel.SLACK,
            ) from e

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


@dataclass
class SlackAdapter(BaseAdapter):
    """Slack adapter for delivering notifications via Slack API.

    Supports:
    - Simple text messages
    - Rich Block Kit formatting
    - Intent-based emoji and color coding
    - Thread replies
    """

    config: SlackConfig
    _client: SlackClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = SlackClient(
            bot_token=self.config.bot_token,
            timeout=self.config.timeout_seconds,
        )

    @property
    def channel(self) -> Channel:
        return Channel.SLACK

    async def deliver(self, notification: Notification) -> DeliveryResult:
        """Deliver a notification to Slack.

        Args:
            notification: The notification to deliver

        Returns:
            DeliveryResult with delivery status and Slack message metadata
        """
        slack_channel = self._get_target_channel(notification)
        text = self.format_message(notification)

        blocks = None
        if self.config.use_blocks:
            blocks = self._build_blocks(notification)

        attempt = 0
        last_error: Exception | None = None

        while attempt < self.config.retry_attempts:
            attempt += 1
            try:
                response = await self._client.post_message(
                    channel=slack_channel,
                    text=text,
                    blocks=blocks,
                )

                logger.info(
                    "Slack notification delivered: notification_id=%s, channel=%s, ts=%s",
                    notification.notification_id,
                    slack_channel,
                    response.get("ts"),
                )

                return DeliveryResult(
                    success=True,
                    channel=Channel.SLACK,
                    message_id=response.get("ts"),
                    metadata={
                        "slack_channel": response.get("channel"),
                        "slack_ts": response.get("ts"),
                    },
                    delivered_at=datetime.now(UTC),
                )

            except AdapterTimeoutError:
                last_error = AdapterTimeoutError(
                    f"Slack delivery timed out after {attempt} attempts",
                    channel=Channel.SLACK,
                )
                logger.warning(
                    "Slack delivery timeout: notification_id=%s, attempt=%d",
                    notification.notification_id,
                    attempt,
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(1.0 * attempt)  # Exponential backoff

            except AdapterDeliveryError as e:
                last_error = e
                if not e.retryable:
                    break
                logger.warning(
                    "Slack delivery error (retryable): notification_id=%s, attempt=%d, error=%s",
                    notification.notification_id,
                    attempt,
                    str(e),
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(1.0 * attempt)

            except Exception as e:
                last_error = e
                logger.error(
                    "Slack delivery unexpected error: notification_id=%s, error=%s",
                    notification.notification_id,
                    str(e),
                )
                break

        error_msg = str(last_error) if last_error else "Unknown error"
        logger.error(
            "Slack delivery failed: notification_id=%s, error=%s",
            notification.notification_id,
            error_msg,
        )

        return DeliveryResult(
            success=False,
            channel=Channel.SLACK,
            error=error_msg,
            delivered_at=datetime.now(UTC),
        )

    async def health_check(self) -> HealthCheckResult:
        """Check Slack API connectivity and authentication."""
        start_time = datetime.now(UTC)

        try:
            await self._client.auth_test()
            latency = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                message="Slack API connection successful",
                latency_ms=latency,
            )

        except AdapterConfigurationError as e:
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message=f"Slack authentication failed: {e}",
                metadata={"error": str(e)},
            )

        except Exception as e:
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message=f"Slack health check failed: {e}",
                metadata={"error": str(e)},
            )

    def format_message(self, notification: Notification) -> str:
        """Format notification as plain text for Slack fallback."""
        emoji = INTENT_EMOJI.get(notification.intent, ":bell:")
        return f"{emoji} *{notification.title}*\n{notification.message}"

    def _get_target_channel(self, notification: Notification) -> str:
        """Determine the Slack channel to post to.

        Can be extended to support channel routing based on notification metadata.
        """
        # Check for channel override in metadata
        if "slack_channel" in notification.metadata:
            return notification.metadata["slack_channel"]
        return self.config.default_channel

    def _build_blocks(self, notification: Notification) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks for rich formatting."""
        emoji = INTENT_EMOJI.get(notification.intent, ":bell:")
        priority = notification.priority or Priority.NORMAL

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {notification.title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.message,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Intent:* {notification.intent.value} | *Priority:* {priority.value}",
                    },
                ],
            },
        ]

        # Add autonomy context info
        ctx = notification.autonomy_context
        context_text = f"*Mode:* {ctx.autonomy_mode.value} | *Agent:* `{ctx.agent_id}`"
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": context_text}],
            }
        )

        # Add notification ID for reference
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Notification ID: `{notification.notification_id}`",
                    }
                ],
            }
        )

        # Add action buttons for acknowledgment-requiring notifications
        if notification.require_ack:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Acknowledge"},
                            "style": "primary",
                            "action_id": f"ack_{notification.notification_id}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Dismiss"},
                            "action_id": f"dismiss_{notification.notification_id}",
                        },
                    ],
                }
            )

        return blocks

    async def close(self) -> None:
        """Clean up resources."""
        await self._client.close()

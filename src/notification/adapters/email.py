"""Email adapter for notification delivery.

This module implements the Email channel adapter using SMTP.
Supports both plain text and HTML formatted emails.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

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
class EmailConfig:
    """Configuration for the Email adapter.

    Attributes:
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port (587 for TLS, 465 for SSL)
        username: SMTP authentication username
        password: SMTP authentication password
        from_address: Sender email address
        default_to_addresses: Default recipient addresses
        use_tls: Use STARTTLS (port 587)
        use_ssl: Use SSL (port 465)
        timeout_seconds: Connection timeout in seconds
        retry_attempts: Number of retry attempts
    """

    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_address: str
    default_to_addresses: list[str]
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 30.0
    retry_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.smtp_host:
            raise ValueError("smtp_host is required")
        if not self.from_address:
            raise ValueError("from_address is required")
        if not self.default_to_addresses:
            raise ValueError("default_to_addresses is required")
        if self.use_tls and self.use_ssl:
            raise ValueError("Cannot use both TLS and SSL")


# Intent to subject prefix mapping
INTENT_PREFIX: dict[NotificationIntent, str] = {
    NotificationIntent.SAFETY: "[SAFETY ALERT]",
    NotificationIntent.GOVERNANCE: "[GOVERNANCE]",
    NotificationIntent.OPERATIONAL: "[OPERATIONAL]",
    NotificationIntent.INFORMATIONAL: "[INFO]",
}

# Priority to importance header mapping
PRIORITY_IMPORTANCE: dict[Priority, str] = {
    Priority.HIGH: "high",
    Priority.NORMAL: "normal",
    Priority.LOW: "low",
}


@dataclass
class EmailAdapter(BaseAdapter):
    """Email adapter for delivering notifications via SMTP.

    Supports:
    - Plain text and HTML emails
    - TLS and SSL encryption
    - Priority headers
    - Custom recipient routing
    """

    config: EmailConfig
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)

    @property
    def channel(self) -> Channel:
        return Channel.EMAIL

    async def deliver(self, notification: Notification) -> DeliveryResult:
        """Deliver a notification via email.

        Args:
            notification: The notification to deliver

        Returns:
            DeliveryResult with delivery status
        """
        to_addresses = self._get_recipients(notification)
        message = self._build_message(notification, to_addresses)

        attempt = 0
        last_error: Exception | None = None

        while attempt < self.config.retry_attempts:
            attempt += 1
            try:
                # Run SMTP in executor to avoid blocking
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        self._send_email_sync,
                        message,
                        to_addresses,
                    ),
                    timeout=self.config.timeout_seconds,
                )

                logger.info(
                    "Email notification delivered: notification_id=%s, recipients=%s",
                    notification.notification_id,
                    to_addresses,
                )

                return DeliveryResult(
                    success=True,
                    channel=Channel.EMAIL,
                    message_id=message["Message-ID"],
                    metadata={
                        "recipients": to_addresses,
                        "subject": message["Subject"],
                    },
                    delivered_at=datetime.now(UTC),
                )

            except TimeoutError:
                last_error = AdapterTimeoutError(
                    f"Email delivery timed out after {attempt} attempts",
                    channel=Channel.EMAIL,
                    timeout_seconds=self.config.timeout_seconds,
                )
                logger.warning(
                    "Email delivery timeout: notification_id=%s, attempt=%d",
                    notification.notification_id,
                    attempt,
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(1.0 * attempt)

            except smtplib.SMTPAuthenticationError as e:
                last_error = AdapterConfigurationError(
                    f"Email authentication failed: {e}",
                    channel=Channel.EMAIL,
                )
                logger.error(
                    "Email authentication failed: notification_id=%s",
                    notification.notification_id,
                )
                break  # Don't retry auth errors

            except smtplib.SMTPRecipientsRefused as e:
                last_error = AdapterDeliveryError(
                    f"Email recipients refused: {e}",
                    channel=Channel.EMAIL,
                    retryable=False,
                )
                logger.error(
                    "Email recipients refused: notification_id=%s, recipients=%s",
                    notification.notification_id,
                    to_addresses,
                )
                break

            except smtplib.SMTPException as e:
                last_error = AdapterDeliveryError(
                    f"Email SMTP error: {e}",
                    channel=Channel.EMAIL,
                    retryable=True,
                    original_error=e,
                )
                logger.warning(
                    "Email SMTP error: notification_id=%s, attempt=%d, error=%s",
                    notification.notification_id,
                    attempt,
                    str(e),
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(1.0 * attempt)

            except Exception as e:
                last_error = e
                logger.error(
                    "Email delivery unexpected error: notification_id=%s, error=%s",
                    notification.notification_id,
                    str(e),
                )
                break

        error_msg = str(last_error) if last_error else "Unknown error"
        logger.error(
            "Email delivery failed: notification_id=%s, error=%s",
            notification.notification_id,
            error_msg,
        )

        return DeliveryResult(
            success=False,
            channel=Channel.EMAIL,
            error=error_msg,
            delivered_at=datetime.now(UTC),
        )

    async def health_check(self) -> HealthCheckResult:
        """Check SMTP server connectivity."""
        start_time = datetime.now(UTC)

        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, self._check_connection_sync),
                timeout=self.config.timeout_seconds,
            )
            latency = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                message="SMTP connection successful",
                latency_ms=latency,
                metadata={
                    "smtp_host": self.config.smtp_host,
                    "smtp_port": self.config.smtp_port,
                },
            )

        except TimeoutError:
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message="SMTP connection timed out",
                metadata={
                    "smtp_host": self.config.smtp_host,
                    "timeout": self.config.timeout_seconds,
                },
            )

        except Exception as e:
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message=f"SMTP health check failed: {e}",
                metadata={"error": str(e)},
            )

    def format_message(self, notification: Notification) -> str:
        """Format notification as plain text email body."""
        lines = [
            f"Intent: {notification.intent.value}",
            f"Priority: {(notification.priority or Priority.NORMAL).value}",
            "",
            notification.title,
            "=" * len(notification.title),
            "",
            notification.message,
            "",
            "---",
            f"Notification ID: {notification.notification_id}",
            f"Source: {notification.source}",
            f"Agent ID: {notification.autonomy_context.agent_id}",
            f"Autonomy Mode: {notification.autonomy_context.autonomy_mode.value}",
        ]

        if notification.require_ack:
            lines.extend([
                "",
                "*** This notification requires acknowledgment ***",
                f"Timeout: {notification.ack_timeout_minutes} minutes",
            ])

        return "\n".join(lines)

    def _build_message(
        self,
        notification: Notification,
        to_addresses: list[str],
    ) -> MIMEMultipart:
        """Build email MIME message."""
        msg = MIMEMultipart("alternative")

        # Headers
        prefix = INTENT_PREFIX.get(notification.intent, "[UNS]")
        msg["Subject"] = f"{prefix} {notification.title}"
        msg["From"] = self.config.from_address
        msg["To"] = ", ".join(to_addresses)

        # Priority headers
        priority = notification.priority or Priority.NORMAL
        importance = PRIORITY_IMPORTANCE.get(priority, "normal")
        msg["X-Priority"] = str({Priority.HIGH: 1, Priority.NORMAL: 3, Priority.LOW: 5}.get(priority, 3))
        msg["Importance"] = importance

        # Custom headers
        msg["X-UNS-Notification-ID"] = str(notification.notification_id)
        msg["X-UNS-Intent"] = notification.intent.value
        msg["X-UNS-Autonomy-Mode"] = notification.autonomy_context.autonomy_mode.value

        # Plain text body
        text_body = self.format_message(notification)
        msg.attach(MIMEText(text_body, "plain"))

        # HTML body
        html_body = self._build_html_body(notification)
        msg.attach(MIMEText(html_body, "html"))

        return msg

    def _build_html_body(self, notification: Notification) -> str:
        """Build HTML email body."""
        priority = notification.priority or Priority.NORMAL
        color = {"HIGH": "#dc3545", "NORMAL": "#fd7e14", "LOW": "#6c757d"}.get(
            priority.value, "#fd7e14"
        )

        ack_section = ""
        if notification.require_ack:
            ack_section = f"""
            <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; margin-top: 20px; border-radius: 4px;">
                <strong>⚠️ This notification requires acknowledgment</strong><br>
                Timeout: {notification.ack_timeout_minutes} minutes
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ border-left: 4px solid {color}; padding-left: 15px; margin-bottom: 20px; }}
                .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
                .intent-badge {{ background-color: {color}; color: white; }}
                .content {{ padding: 20px; background-color: #f8f9fa; border-radius: 4px; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <span class="badge intent-badge">{notification.intent.value}</span>
                    <h2 style="margin: 10px 0;">{notification.title}</h2>
                </div>
                <div class="content">
                    {notification.message.replace(chr(10), '<br>')}
                </div>
                {ack_section}
                <div class="footer">
                    <strong>Notification Details:</strong><br>
                    ID: {notification.notification_id}<br>
                    Source: {notification.source}<br>
                    Agent: {notification.autonomy_context.agent_id}<br>
                    Mode: {notification.autonomy_context.autonomy_mode.value}
                </div>
            </div>
        </body>
        </html>
        """

    def _get_recipients(self, notification: Notification) -> list[str]:
        """Determine email recipients."""
        if "email_to" in notification.metadata:
            to_list = notification.metadata["email_to"]
            if isinstance(to_list, str):
                return [to_list]
            return list(to_list)
        return self.config.default_to_addresses.copy()

    def _send_email_sync(
        self,
        message: MIMEMultipart,
        to_addresses: list[str],
    ) -> None:
        """Synchronous email sending (runs in executor)."""
        server: smtplib.SMTP
        if self.config.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port,
                context=context,
                timeout=self.config.timeout_seconds,
            )
        else:
            server = smtplib.SMTP(
                self.config.smtp_host,
                self.config.smtp_port,
                timeout=self.config.timeout_seconds,
            )
            if self.config.use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)

        try:
            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)
            server.sendmail(
                self.config.from_address,
                to_addresses,
                message.as_string(),
            )
        finally:
            server.quit()

    def _check_connection_sync(self) -> None:
        """Synchronous connection check (runs in executor)."""
        server: smtplib.SMTP
        if self.config.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port,
                context=context,
                timeout=self.config.timeout_seconds,
            )
        else:
            server = smtplib.SMTP(
                self.config.smtp_host,
                self.config.smtp_port,
                timeout=self.config.timeout_seconds,
            )
            if self.config.use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)

        try:
            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)
            server.noop()  # Simple check command
        finally:
            server.quit()

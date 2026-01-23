"""PagerDuty adapter for notification delivery.

This module implements the PagerDuty channel adapter for critical
incident management and escalation. Used for SAFETY notifications
with irreversible actions as specified in the PRD.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
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


class PagerDutySeverity(str, Enum):
    """PagerDuty event severity levels."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class PagerDutyEventAction(str, Enum):
    """PagerDuty event actions."""

    TRIGGER = "trigger"
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"


@dataclass
class PagerDutyConfig:
    """Configuration for the PagerDuty adapter.

    Attributes:
        routing_key: PagerDuty Events API v2 routing key (integration key)
        timeout_seconds: Request timeout in seconds
        retry_attempts: Number of retry attempts for transient failures
        default_severity: Default severity for events
        source: Source field for events (default: UNS)
    """

    routing_key: str
    timeout_seconds: float = 30.0
    retry_attempts: int = 3
    default_severity: PagerDutySeverity = PagerDutySeverity.ERROR
    source: str = "UNS"

    def __post_init__(self) -> None:
        if not self.routing_key:
            raise ValueError("routing_key is required")
        # PagerDuty routing keys are 32 character hex strings
        if len(self.routing_key) != 32:
            logger.warning(
                "PagerDuty routing_key length is %d, expected 32 characters",
                len(self.routing_key),
            )


# Map notification intent to PagerDuty severity
INTENT_SEVERITY: dict[NotificationIntent, PagerDutySeverity] = {
    NotificationIntent.SAFETY: PagerDutySeverity.CRITICAL,
    NotificationIntent.GOVERNANCE: PagerDutySeverity.ERROR,
    NotificationIntent.OPERATIONAL: PagerDutySeverity.WARNING,
    NotificationIntent.INFORMATIONAL: PagerDutySeverity.INFO,
}

# Map notification priority to PagerDuty severity
PRIORITY_SEVERITY: dict[Priority, PagerDutySeverity] = {
    Priority.HIGH: PagerDutySeverity.CRITICAL,
    Priority.NORMAL: PagerDutySeverity.ERROR,
    Priority.LOW: PagerDutySeverity.WARNING,
}


class PagerDutyClient:
    """HTTP client for PagerDuty Events API v2."""

    EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str, timeout: float = 30.0) -> None:
        self.routing_key = routing_key
        self.timeout = timeout
        self._http_client: Any = None

    async def _get_client(self) -> Any:
        """Lazily initialize HTTP client."""
        if self._http_client is None:
            try:
                import httpx

                self._http_client = httpx.AsyncClient(
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )
            except ImportError as e:
                raise AdapterConfigurationError(
                    "httpx is required for PagerDuty adapter. Install with: pip install httpx",
                    channel=Channel.PAGERDUTY,
                ) from e
        return self._http_client

    async def send_event(
        self,
        action: PagerDutyEventAction,
        dedup_key: str,
        summary: str,
        severity: PagerDutySeverity,
        source: str,
        component: str | None = None,
        group: str | None = None,
        custom_details: dict[str, Any] | None = None,
        links: list[dict[str, str]] | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Send an event to PagerDuty Events API v2.

        Args:
            action: Event action (trigger, acknowledge, resolve)
            dedup_key: Deduplication key for the incident
            summary: Event summary (max 1024 chars)
            severity: Event severity
            source: Source of the event
            component: Affected component
            group: Logical grouping
            custom_details: Additional details
            links: Related links
            images: Related images

        Returns:
            PagerDuty API response

        Raises:
            AdapterDeliveryError: If the API call fails
            AdapterTimeoutError: If the request times out
        """
        client = await self._get_client()

        payload: dict[str, Any] = {
            "routing_key": self.routing_key,
            "event_action": action.value,
            "dedup_key": dedup_key,
            "payload": {
                "summary": summary[:1024],  # PagerDuty limit
                "severity": severity.value,
                "source": source,
            },
        }

        if component:
            payload["payload"]["component"] = component
        if group:
            payload["payload"]["group"] = group
        if custom_details:
            payload["payload"]["custom_details"] = custom_details
        if links:
            payload["links"] = links
        if images:
            payload["images"] = images

        try:
            import httpx

            response = await client.post(self.EVENTS_API_URL, json=payload)

            # PagerDuty returns 202 Accepted for successful events
            if response.status_code == 202:
                return response.json()

            # Handle errors
            if response.status_code == 400:
                data = response.json()
                raise AdapterDeliveryError(
                    f"PagerDuty bad request: {data.get('message', 'unknown')}",
                    channel=Channel.PAGERDUTY,
                    retryable=False,
                )
            elif response.status_code == 429:
                raise AdapterDeliveryError(
                    "PagerDuty rate limited",
                    channel=Channel.PAGERDUTY,
                    retryable=True,
                )
            else:
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException as e:
            raise AdapterTimeoutError(
                f"PagerDuty request timed out: {e}",
                channel=Channel.PAGERDUTY,
                timeout_seconds=self.timeout,
            ) from e
        except httpx.HTTPStatusError as e:
            raise AdapterDeliveryError(
                f"PagerDuty HTTP error: {e.response.status_code}",
                channel=Channel.PAGERDUTY,
                retryable=e.response.status_code >= 500,
                original_error=e,
            ) from e
        except Exception as e:
            if isinstance(e, (AdapterDeliveryError, AdapterTimeoutError)):
                raise
            raise AdapterDeliveryError(
                f"PagerDuty delivery failed: {e}",
                channel=Channel.PAGERDUTY,
                original_error=e,
            ) from e

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


@dataclass
class PagerDutyAdapter(BaseAdapter):
    """PagerDuty adapter for incident management and escalation.

    Used for critical notifications that require immediate attention,
    particularly SAFETY notifications with irreversible actions.

    Supports:
    - Event triggering
    - Incident acknowledgment
    - Incident resolution
    - Custom severity mapping
    - Rich custom details
    """

    config: PagerDutyConfig
    _client: PagerDutyClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = PagerDutyClient(
            routing_key=self.config.routing_key,
            timeout=self.config.timeout_seconds,
        )

    @property
    def channel(self) -> Channel:
        return Channel.PAGERDUTY

    async def deliver(self, notification: Notification) -> DeliveryResult:
        """Deliver a notification to PagerDuty as an incident.

        Args:
            notification: The notification to deliver

        Returns:
            DeliveryResult with delivery status and PagerDuty incident key
        """
        severity = self._determine_severity(notification)
        dedup_key = self._get_dedup_key(notification)
        summary = self._build_summary(notification)
        custom_details = self._build_custom_details(notification)

        attempt = 0
        last_error: Exception | None = None

        while attempt < self.config.retry_attempts:
            attempt += 1
            try:
                response = await self._client.send_event(
                    action=PagerDutyEventAction.TRIGGER,
                    dedup_key=dedup_key,
                    summary=summary,
                    severity=severity,
                    source=self.config.source,
                    component=notification.source,
                    group=notification.autonomy_context.autonomy_mode.value,
                    custom_details=custom_details,
                )

                logger.info(
                    "PagerDuty incident triggered: notification_id=%s, dedup_key=%s, status=%s",
                    notification.notification_id,
                    dedup_key,
                    response.get("status"),
                )

                return DeliveryResult(
                    success=True,
                    channel=Channel.PAGERDUTY,
                    message_id=dedup_key,
                    metadata={
                        "pagerduty_dedup_key": dedup_key,
                        "pagerduty_status": response.get("status"),
                        "severity": severity.value,
                    },
                    delivered_at=datetime.now(UTC),
                )

            except AdapterTimeoutError:
                last_error = AdapterTimeoutError(
                    f"PagerDuty delivery timed out after {attempt} attempts",
                    channel=Channel.PAGERDUTY,
                )
                logger.warning(
                    "PagerDuty delivery timeout: notification_id=%s, attempt=%d",
                    notification.notification_id,
                    attempt,
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(1.0 * attempt)

            except AdapterDeliveryError as e:
                last_error = e
                if not e.retryable:
                    break
                logger.warning(
                    "PagerDuty delivery error (retryable): notification_id=%s, attempt=%d, error=%s",
                    notification.notification_id,
                    attempt,
                    str(e),
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(1.0 * attempt)

            except Exception as e:
                last_error = e
                logger.error(
                    "PagerDuty delivery unexpected error: notification_id=%s, error=%s",
                    notification.notification_id,
                    str(e),
                )
                break

        error_msg = str(last_error) if last_error else "Unknown error"
        logger.error(
            "PagerDuty delivery failed: notification_id=%s, error=%s",
            notification.notification_id,
            error_msg,
        )

        return DeliveryResult(
            success=False,
            channel=Channel.PAGERDUTY,
            error=error_msg,
            delivered_at=datetime.now(UTC),
        )

    async def acknowledge_incident(self, dedup_key: str) -> DeliveryResult:
        """Acknowledge an existing PagerDuty incident.

        Args:
            dedup_key: Deduplication key of the incident to acknowledge

        Returns:
            DeliveryResult with acknowledgment status
        """
        try:
            response = await self._client.send_event(
                action=PagerDutyEventAction.ACKNOWLEDGE,
                dedup_key=dedup_key,
                summary="Incident acknowledged",
                severity=self.config.default_severity,
                source=self.config.source,
            )

            logger.info(
                "PagerDuty incident acknowledged: dedup_key=%s",
                dedup_key,
            )

            return DeliveryResult(
                success=True,
                channel=Channel.PAGERDUTY,
                message_id=dedup_key,
                metadata={
                    "action": "acknowledge",
                    "pagerduty_status": response.get("status"),
                },
                delivered_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error(
                "PagerDuty acknowledge failed: dedup_key=%s, error=%s",
                dedup_key,
                str(e),
            )

            return DeliveryResult(
                success=False,
                channel=Channel.PAGERDUTY,
                error=str(e),
                delivered_at=datetime.now(UTC),
            )

    async def resolve_incident(self, dedup_key: str) -> DeliveryResult:
        """Resolve an existing PagerDuty incident.

        Args:
            dedup_key: Deduplication key of the incident to resolve

        Returns:
            DeliveryResult with resolution status
        """
        try:
            response = await self._client.send_event(
                action=PagerDutyEventAction.RESOLVE,
                dedup_key=dedup_key,
                summary="Incident resolved",
                severity=self.config.default_severity,
                source=self.config.source,
            )

            logger.info(
                "PagerDuty incident resolved: dedup_key=%s",
                dedup_key,
            )

            return DeliveryResult(
                success=True,
                channel=Channel.PAGERDUTY,
                message_id=dedup_key,
                metadata={
                    "action": "resolve",
                    "pagerduty_status": response.get("status"),
                },
                delivered_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error(
                "PagerDuty resolve failed: dedup_key=%s, error=%s",
                dedup_key,
                str(e),
            )

            return DeliveryResult(
                success=False,
                channel=Channel.PAGERDUTY,
                error=str(e),
                delivered_at=datetime.now(UTC),
            )

    async def health_check(self) -> HealthCheckResult:
        """Check PagerDuty API connectivity.

        Note: PagerDuty Events API doesn't have a health check endpoint,
        so we validate the configuration instead.
        """
        # Validate configuration
        if not self.config.routing_key:
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message="PagerDuty routing key not configured",
            )

        if len(self.config.routing_key) != 32:
            return HealthCheckResult(
                status=AdapterStatus.DEGRADED,
                message="PagerDuty routing key appears invalid (expected 32 chars)",
                metadata={"routing_key_length": len(self.config.routing_key)},
            )

        # Can't actually test connectivity without triggering an incident
        return HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="PagerDuty adapter configured",
            metadata={
                "source": self.config.source,
                "default_severity": self.config.default_severity.value,
            },
        )

    def format_message(self, notification: Notification) -> str:
        """Format notification as PagerDuty summary."""
        return self._build_summary(notification)

    def _determine_severity(self, notification: Notification) -> PagerDutySeverity:
        """Determine PagerDuty severity from notification."""
        # Check metadata override first
        if "pagerduty_severity" in notification.metadata:
            severity_str = notification.metadata["pagerduty_severity"]
            try:
                return PagerDutySeverity(severity_str.lower())
            except ValueError:
                logger.warning("Invalid pagerduty_severity in metadata: %s", severity_str)

        # Use intent-based severity
        severity = INTENT_SEVERITY.get(notification.intent)
        if severity:
            return severity

        # Fall back to priority-based
        if notification.priority:
            priority_severity = PRIORITY_SEVERITY.get(notification.priority)
            if priority_severity:
                return priority_severity

        return self.config.default_severity

    def _get_dedup_key(self, notification: Notification) -> str:
        """Get deduplication key for PagerDuty incident."""
        # Use notification's dedup_key if available
        if notification.dedup_key:
            return f"uns-{notification.dedup_key}"

        # Fall back to notification ID
        return f"uns-{notification.notification_id}"

    def _build_summary(self, notification: Notification) -> str:
        """Build PagerDuty event summary."""
        prefix = f"[{notification.intent.value}]"
        if notification.irreversible:
            prefix = f"[IRREVERSIBLE] {prefix}"

        summary = f"{prefix} {notification.title}"

        # Add autonomy context
        ctx = notification.autonomy_context
        summary += f" (Mode: {ctx.autonomy_mode.value})"

        return summary[:1024]  # PagerDuty limit

    def _build_custom_details(self, notification: Notification) -> dict[str, Any]:
        """Build custom details for PagerDuty incident."""
        ctx = notification.autonomy_context

        details: dict[str, Any] = {
            "notification_id": str(notification.notification_id),
            "notification_type": notification.notification_type,
            "intent": notification.intent.value,
            "message": notification.message,
            "source": notification.source,
            "irreversible": notification.irreversible,
            "autonomy_mode": ctx.autonomy_mode.value,
            "agent_id": str(ctx.agent_id),
            "created_at": notification.created_at.isoformat(),
        }

        if notification.priority:
            details["priority"] = notification.priority.value

        if notification.require_ack:
            details["require_ack"] = True
            details["ack_timeout_minutes"] = notification.ack_timeout_minutes

        if ctx.plan_id:
            details["plan_id"] = str(ctx.plan_id)

        if notification.correlation_id:
            details["correlation_id"] = notification.correlation_id

        # Include safe metadata (filter internal keys)
        if notification.metadata:
            safe_metadata = {
                k: v
                for k, v in notification.metadata.items()
                if not k.startswith("_") and k != "pagerduty_severity"
            }
            if safe_metadata:
                details["metadata"] = safe_metadata

        return details

    async def close(self) -> None:
        """Clean up resources."""
        await self._client.close()

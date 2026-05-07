"""Delivery service for notification orchestration.

This module implements the core delivery flow with GUARANTEED vs BEST_EFFORT
semantics as specified in the PRD.

Delivery Steps (Strict Order):
1. Deduplication check
2. Rate limit check
3. WebSocket delivery (fire-and-forget)
4. Persistent channel delivery
   - GUARANTEED: sequential fallback (Slack -> Email -> PagerDuty)
   - BEST_EFFORT: attempt all channels
5. Ack timeout scheduling (if required)
6. Audit log write
7. GUARANTEED failure raises exception

Failure Semantics:
- GUARANTEED: MUST raise if all persistent channels fail, escalate via PagerDuty/DLQ
- BEST_EFFORT: MAY fail silently, MUST log failure
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from notification.adapters.base import (
    AdapterError,
    BaseAdapter,
    DeliveryResult,
)
from notification.deduplication import should_deduplicate
from notification.dlq import DLQService
from notification.models import (
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationResult,
)
from notification.policies import get_policy_registry
from notification.rate_limiting import acquire_rate_limit

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """Raised when GUARANTEED delivery fails all channels."""

    def __init__(
        self,
        message: str,
        notification: Notification,
        channel_errors: dict[Channel, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.notification = notification
        self.channel_errors = channel_errors or {}


class AdapterRegistry(Protocol):
    """Protocol for adapter registry."""

    def get_adapter(self, channel: Channel) -> BaseAdapter | None:
        """Get adapter for a channel."""
        ...


class AuditLogger(Protocol):
    """Protocol for audit logging."""

    def log_delivery(
        self,
        notification: Notification,
        result: NotificationResult,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a delivery attempt."""
        ...


class AckScheduler(Protocol):
    """Protocol for acknowledgment timeout scheduling."""

    def schedule_timeout(
        self,
        notification: Notification,
        timeout_minutes: int,
    ) -> None:
        """Schedule an ack timeout check."""
        ...


class NoOpAuditLogger:
    """No-operation audit logger for testing."""

    def log_delivery(
        self,
        notification: Notification,
        result: NotificationResult,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        logger.debug(
            "Audit: notification_id=%s status=%s channels_succeeded=%s metadata=%s",
            notification.notification_id,
            result.status.value,
            [c.value for c in result.channels_succeeded],
            metadata,
        )


class NoOpAckScheduler:
    """No-operation ack scheduler for testing."""

    def schedule_timeout(
        self,
        notification: Notification,
        timeout_minutes: int,
    ) -> None:
        logger.debug(
            "Ack timeout scheduled: notification_id=%s timeout=%d minutes",
            notification.notification_id,
            timeout_minutes,
        )


@dataclass
class SimpleAdapterRegistry:
    """Simple in-memory adapter registry.

    Maps channels to adapter instances for delivery.
    """

    _adapters: dict[Channel, BaseAdapter] = field(default_factory=dict)

    def register(self, adapter: BaseAdapter) -> None:
        """Register an adapter."""
        self._adapters[adapter.channel] = adapter

    def unregister(self, channel: Channel) -> None:
        """Unregister an adapter."""
        self._adapters.pop(channel, None)

    def get_adapter(self, channel: Channel) -> BaseAdapter | None:
        """Get adapter for a channel."""
        return self._adapters.get(channel)


# Persistent channels in fallback order for GUARANTEED delivery
PERSISTENT_CHANNELS_FALLBACK_ORDER = [
    Channel.SLACK,
    Channel.EMAIL,
    Channel.PAGERDUTY,
]


def _is_persistent_channel(channel: Channel) -> bool:
    """Check if a channel is persistent (not fire-and-forget)."""
    return channel != Channel.WEBSOCKET


@dataclass
class DeliveryService:
    """Service for orchestrating notification delivery.

    Implements the delivery flow with GUARANTEED vs BEST_EFFORT semantics.
    """

    adapter_registry: AdapterRegistry
    audit_logger: AuditLogger = field(default_factory=NoOpAuditLogger)
    ack_scheduler: AckScheduler = field(default_factory=NoOpAckScheduler)
    escalation_callback: Callable[[Notification, dict[Channel, str]], None] | None = None
    dlq_service: DLQService | None = None

    async def deliver(self, notification: Notification) -> NotificationResult:
        """Deliver a notification through the configured channels.

        This method implements the strict delivery flow:
        1. Deduplication check
        2. Rate limit check
        3. WebSocket delivery (fire-and-forget)
        4. Persistent channel delivery (GUARANTEED vs BEST_EFFORT)
        5. Ack timeout scheduling
        6. Audit logging

        Args:
            notification: The notification to deliver

        Returns:
            NotificationResult with delivery status

        Raises:
            DeliveryError: For GUARANTEED mode when all persistent channels fail
        """
        start_time = datetime.now(UTC)

        policy_registry = get_policy_registry()

        # Step 1: Deduplication check
        dedup_window = policy_registry.get_dedup_window(notification.notification_type)
        if should_deduplicate(notification, window_seconds=dedup_window):
            result = NotificationResult(
                notification_id=notification.notification_id,
                status=DeliveryStatus.DEDUPLICATED,
                delivered_at=start_time,
            )
            self.audit_logger.log_delivery(notification, result, {"reason": "deduplicated"})
            return result

        # Step 2: Resolve delivery mode and channels
        delivery_mode = (
            notification.delivery_mode
            if notification.delivery_mode
            else policy_registry.get_delivery_mode(
                notification.notification_type, notification.intent
            )
        )
        channels = (
            notification.channels
            if notification.channels
            else policy_registry.get_channels_for_mode(
                notification.notification_type,
                notification.intent,
                notification.autonomy_context.autonomy_mode,
                notification.irreversible,
            )
        )

        logger.info(
            "Delivering notification: notification_id=%s mode=%s channels=%s",
            notification.notification_id,
            delivery_mode.value,
            [c.value for c in channels],
        )

        channels_attempted: list[Channel] = []
        channels_succeeded: list[Channel] = []
        channels_failed: list[Channel] = []
        channel_errors: dict[Channel, str] = {}

        # Step 3: WebSocket delivery (fire-and-forget, no rate limit check)
        if Channel.WEBSOCKET in channels:
            ws_result = await self._deliver_websocket(notification)
            channels_attempted.append(Channel.WEBSOCKET)
            if ws_result.success:
                channels_succeeded.append(Channel.WEBSOCKET)
            else:
                channels_failed.append(Channel.WEBSOCKET)
                if ws_result.error:
                    channel_errors[Channel.WEBSOCKET] = ws_result.error
            # WebSocket is fire-and-forget, continue regardless of result

        # Step 4: Persistent channel delivery
        persistent_channels = [c for c in channels if _is_persistent_channel(c)]

        if delivery_mode == DeliveryMode.GUARANTEED:
            # Sequential fallback for GUARANTEED
            persistent_result = await self._deliver_guaranteed(
                notification, persistent_channels
            )
        else:
            # Attempt all channels for BEST_EFFORT
            persistent_result = await self._deliver_best_effort(
                notification, persistent_channels
            )

        channels_attempted.extend(persistent_result["attempted"])
        channels_succeeded.extend(persistent_result["succeeded"])
        channels_failed.extend(persistent_result["failed"])
        channel_errors.update(persistent_result["errors"])

        # Determine overall status
        if channels_succeeded:
            status = DeliveryStatus.SUCCESS
        elif delivery_mode == DeliveryMode.GUARANTEED and not channels_succeeded:
            # GUARANTEED failure: all persistent channels failed
            status = DeliveryStatus.FAILED
        else:
            # BEST_EFFORT: log failure but don't raise
            status = DeliveryStatus.FAILED

        result = NotificationResult(
            notification_id=notification.notification_id,
            status=status,
            channels_attempted=channels_attempted,
            channels_succeeded=channels_succeeded,
            channels_failed=channels_failed,
            error_message="; ".join(f"{c.value}: {e}" for c, e in channel_errors.items())
            if channel_errors
            else None,
            delivered_at=datetime.now(UTC),
        )

        # Step 5: Ack timeout scheduling (if required)
        require_ack = (
            notification.require_ack
            if notification.require_ack is not None
            else policy_registry.get_require_ack_for_mode(
                notification.notification_type,
                notification.intent,
                notification.autonomy_context.autonomy_mode,
            )
        )

        if require_ack and status == DeliveryStatus.SUCCESS:
            ack_timeout = (
                notification.ack_timeout_minutes
                if notification.ack_timeout_minutes is not None
                else policy_registry.get_ack_timeout(
                    notification.notification_type, notification.intent
                )
            )
            self.ack_scheduler.schedule_timeout(notification, ack_timeout)

        # Step 6: Audit log write
        self.audit_logger.log_delivery(notification, result)

        # Step 7: GUARANTEED failure handling
        if delivery_mode == DeliveryMode.GUARANTEED and status == DeliveryStatus.FAILED:
            # Record visible degradation before surfacing the delivery error.
            if self.dlq_service is not None:
                self.dlq_service.enqueue(
                    notification,
                    reason="guaranteed_delivery_failed",
                    metadata={
                        "channel_errors": {
                            channel.value: error for channel, error in channel_errors.items()
                        },
                        "channels_attempted": [channel.value for channel in channels_attempted],
                        "channels_failed": [channel.value for channel in channels_failed],
                    },
                )

            if self.escalation_callback:
                try:
                    self.escalation_callback(notification, channel_errors)
                except Exception as e:
                    logger.error(
                        "Escalation callback failed: notification_id=%s error=%s",
                        notification.notification_id,
                        str(e),
                    )

            raise DeliveryError(
                f"GUARANTEED delivery failed for notification {notification.notification_id}: "
                f"all persistent channels failed",
                notification=notification,
                channel_errors=channel_errors,
            )

        return result

    async def _deliver_websocket(self, notification: Notification) -> DeliveryResult:
        """Deliver via WebSocket (fire-and-forget).

        WebSocket delivery is non-blocking and doesn't affect overall
        delivery status for GUARANTEED mode.
        """
        adapter = self.adapter_registry.get_adapter(Channel.WEBSOCKET)
        if adapter is None:
            logger.warning("No WebSocket adapter registered")
            return DeliveryResult(
                success=False,
                channel=Channel.WEBSOCKET,
                error="No adapter registered",
            )

        try:
            result = await adapter.deliver(notification)
            return result
        except AdapterError as e:
            logger.warning(
                "WebSocket delivery failed (fire-and-forget): notification_id=%s error=%s",
                notification.notification_id,
                str(e),
            )
            return DeliveryResult(
                success=False,
                channel=Channel.WEBSOCKET,
                error=str(e),
            )

    async def _deliver_guaranteed(
        self,
        notification: Notification,
        channels: list[Channel],
    ) -> dict[str, Any]:
        """Deliver with GUARANTEED semantics.

        Sequential fallback: try channels in order until one succeeds.
        Order: Slack -> Email -> PagerDuty

        Returns dict with attempted, succeeded, failed, errors.
        """
        attempted: list[Channel] = []
        succeeded: list[Channel] = []
        failed: list[Channel] = []
        errors: dict[Channel, str] = {}

        # Sort channels by fallback order
        ordered_channels = sorted(
            channels,
            key=lambda c: (
                PERSISTENT_CHANNELS_FALLBACK_ORDER.index(c)
                if c in PERSISTENT_CHANNELS_FALLBACK_ORDER
                else len(PERSISTENT_CHANNELS_FALLBACK_ORDER)
            ),
        )

        for channel in ordered_channels:
            # Rate limit check per channel
            if not acquire_rate_limit(channel):
                logger.warning(
                    "Rate limit exceeded for channel %s, trying next",
                    channel.value,
                )
                attempted.append(channel)
                failed.append(channel)
                errors[channel] = "Rate limit exceeded"
                continue

            adapter = self.adapter_registry.get_adapter(channel)
            if adapter is None:
                logger.warning("No adapter registered for channel %s", channel.value)
                attempted.append(channel)
                failed.append(channel)
                errors[channel] = "No adapter registered"
                continue

            try:
                result = await adapter.deliver(notification)
                attempted.append(channel)

                if result.success:
                    succeeded.append(channel)
                    logger.info(
                        "GUARANTEED delivery succeeded: notification_id=%s channel=%s",
                        notification.notification_id,
                        channel.value,
                    )
                    # Success - stop trying other channels
                    break
                else:
                    failed.append(channel)
                    errors[channel] = result.error or "Delivery failed"
                    logger.warning(
                        "GUARANTEED delivery failed, trying fallback: "
                        "notification_id=%s channel=%s error=%s",
                        notification.notification_id,
                        channel.value,
                        result.error,
                    )

            except AdapterError as e:
                attempted.append(channel)
                failed.append(channel)
                errors[channel] = str(e)
                logger.warning(
                    "GUARANTEED delivery error, trying fallback: "
                    "notification_id=%s channel=%s error=%s",
                    notification.notification_id,
                    channel.value,
                    str(e),
                )

        return {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors,
        }

    async def _deliver_best_effort(
        self,
        notification: Notification,
        channels: list[Channel],
    ) -> dict[str, Any]:
        """Deliver with BEST_EFFORT semantics.

        Attempt all channels concurrently. Log failures but don't raise.

        Returns dict with attempted, succeeded, failed, errors.
        """
        attempted: list[Channel] = []
        succeeded: list[Channel] = []
        failed: list[Channel] = []
        errors: dict[Channel, str] = {}

        async def deliver_to_channel(channel: Channel) -> tuple[Channel, DeliveryResult | str]:
            """Deliver to a single channel, returning result or error."""
            # Rate limit check
            if not acquire_rate_limit(channel):
                return channel, "Rate limit exceeded"

            adapter = self.adapter_registry.get_adapter(channel)
            if adapter is None:
                return channel, "No adapter registered"

            try:
                result = await adapter.deliver(notification)
                return channel, result
            except AdapterError as e:
                return channel, str(e)

        # Deliver to all channels concurrently
        tasks = [deliver_to_channel(c) for c in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                # Unexpected exception
                logger.error("Unexpected error in BEST_EFFORT delivery: %s", str(result))
                continue

            channel, delivery_result = result
            attempted.append(channel)

            if isinstance(delivery_result, str):
                # Error message
                failed.append(channel)
                errors[channel] = delivery_result
                logger.warning(
                    "BEST_EFFORT delivery failed: notification_id=%s channel=%s error=%s",
                    notification.notification_id,
                    channel.value,
                    delivery_result,
                )
            elif isinstance(delivery_result, DeliveryResult):
                if delivery_result.success:
                    succeeded.append(channel)
                else:
                    failed.append(channel)
                    errors[channel] = delivery_result.error or "Delivery failed"
                    logger.warning(
                        "BEST_EFFORT delivery failed: notification_id=%s channel=%s error=%s",
                        notification.notification_id,
                        channel.value,
                        delivery_result.error,
                    )

        return {
            "attempted": attempted,
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors,
        }


# Global delivery service instance
_delivery_service: DeliveryService | None = None


def get_delivery_service() -> DeliveryService:
    """Get the global delivery service instance.

    Raises:
        RuntimeError: If service hasn't been configured
    """
    global _delivery_service
    if _delivery_service is None:
        raise RuntimeError(
            "Delivery service not configured. Call configure_delivery_service() first."
        )
    return _delivery_service


def configure_delivery_service(
    adapter_registry: AdapterRegistry,
    audit_logger: AuditLogger | None = None,
    ack_scheduler: AckScheduler | None = None,
    escalation_callback: Callable[[Notification, dict[Channel, str]], None] | None = None,
    dlq_service: DLQService | None = None,
) -> DeliveryService:
    """Configure the global delivery service.

    Args:
        adapter_registry: Registry of channel adapters
        audit_logger: Optional custom audit logger
        ack_scheduler: Optional custom ack scheduler
        escalation_callback: Optional callback for GUARANTEED failures
        dlq_service: Optional DLQ writer for visible delivery failures

    Returns:
        The configured DeliveryService instance
    """
    global _delivery_service
    _delivery_service = DeliveryService(
        adapter_registry=adapter_registry,
        audit_logger=audit_logger or NoOpAuditLogger(),
        ack_scheduler=ack_scheduler or NoOpAckScheduler(),
        escalation_callback=escalation_callback,
        dlq_service=dlq_service,
    )
    return _delivery_service


async def deliver(notification: Notification) -> NotificationResult:
    """Deliver a notification using the global service.

    This is the primary interface for notification delivery.

    Args:
        notification: The notification to deliver

    Returns:
        NotificationResult with delivery status

    Raises:
        DeliveryError: For GUARANTEED mode when all channels fail
    """
    return await get_delivery_service().deliver(notification)

def configure_delivery_service_with_audit(
    adapter_registry: AdapterRegistry,
    audit_store: Any = None,
    fail_silently: bool = False,
    ack_scheduler: AckScheduler | None = None,
    escalation_callback: Callable[[Notification, dict[Channel, str]], None] | None = None,
    dlq_service: DLQService | None = None,
) -> DeliveryService:
    """Configure the delivery service with persistent audit logging.

    This is a convenience function that sets up the delivery service
    with a PersistentAuditLogger instead of the NoOpAuditLogger.

    Args:
        adapter_registry: Registry of channel adapters
        audit_store: AuditStore implementation for persistence
                    (defaults to InMemoryAuditStore if None)
        fail_silently: Whether audit failures should be suppressed
        ack_scheduler: Optional custom ack scheduler
        escalation_callback: Optional callback for GUARANTEED failures
        dlq_service: Optional DLQ writer for visible delivery failures

    Returns:
        The configured DeliveryService instance

    Example:
        from notification.audit import InMemoryAuditStore
        from notification.service import (
            configure_delivery_service_with_audit,
            SimpleAdapterRegistry
        )

        registry = SimpleAdapterRegistry()
        # ... register adapters ...

        # With in-memory audit (development)
        service = configure_delivery_service_with_audit(registry)

        # With database audit (production)
        from db.audit_store import create_sqlalchemy_audit_store
        db_store = create_sqlalchemy_audit_store("postgresql://...")
        service = configure_delivery_service_with_audit(
            registry,
            audit_store=db_store
        )
    """
    from notification.audit import InMemoryAuditStore, PersistentAuditLogger

    if audit_store is None:
        audit_store = InMemoryAuditStore()

    audit_logger = PersistentAuditLogger(
        store=audit_store,
        fail_silently=fail_silently,
    )

    return configure_delivery_service(
        adapter_registry=adapter_registry,
        audit_logger=audit_logger,
        ack_scheduler=ack_scheduler,
        escalation_callback=escalation_callback,
        dlq_service=dlq_service,
    )

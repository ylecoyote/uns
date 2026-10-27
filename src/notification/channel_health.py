"""Standalone channel-health tracking for UNS runtime observability."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from notification.models import Channel


class ChannelHealthStatus(str, Enum):
    """Runtime health status for a delivery channel."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ChannelHealth(BaseModel):
    """Current health state for one delivery channel."""

    channel: Channel
    status: ChannelHealthStatus = ChannelHealthStatus.HEALTHY
    consecutive_failures: int = 0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_failure_reason: str | None = None


class ChannelHealthSummary(BaseModel):
    """Aggregate channel-health summary for runtime observability."""

    status: ChannelHealthStatus
    total_channels: int
    healthy_channels: list[Channel] = Field(default_factory=list)
    degraded_channels: list[Channel] = Field(default_factory=list)
    unavailable_channels: list[Channel] = Field(default_factory=list)
    channels: list[ChannelHealth] = Field(default_factory=list)


class ChannelHealthTracker:
    """In-memory channel-health tracker.

    This intentionally reports health separately from process readiness. Optional
    channel outages should be visible without making `/ready` fail.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        unavailable_threshold: int = 5,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._unavailable_threshold = max(unavailable_threshold, failure_threshold)
        self._health: dict[Channel, ChannelHealth] = {}

    def get_channel_health(self, channel: Channel) -> ChannelHealth:
        """Return current health for a channel."""
        return self._health.get(channel) or ChannelHealth(channel=channel)

    def record_success(self, channel: Channel) -> ChannelHealth:
        """Record a successful channel operation and recover health."""
        health = ChannelHealth(
            channel=channel,
            status=ChannelHealthStatus.HEALTHY,
            consecutive_failures=0,
            last_success_at=datetime.now(UTC),
        )
        self._health[channel] = health
        return health

    def record_failure(self, channel: Channel, reason: str | None = None) -> ChannelHealth:
        """Record a failed channel operation and update degradation state."""
        current = self.get_channel_health(channel)
        failures = current.consecutive_failures + 1
        if failures >= self._unavailable_threshold:
            status = ChannelHealthStatus.UNAVAILABLE
        elif failures >= self._failure_threshold:
            status = ChannelHealthStatus.DEGRADED
        else:
            status = ChannelHealthStatus.HEALTHY

        health = ChannelHealth(
            channel=channel,
            status=status,
            consecutive_failures=failures,
            last_success_at=current.last_success_at,
            last_failure_at=datetime.now(UTC),
            last_failure_reason=reason,
        )
        self._health[channel] = health
        return health

    def get_summary(self) -> ChannelHealthSummary:
        """Return aggregate channel-health state."""
        channels = [self.get_channel_health(channel) for channel in Channel]
        healthy = [
            health.channel
            for health in channels
            if health.status == ChannelHealthStatus.HEALTHY
        ]
        degraded = [
            health.channel
            for health in channels
            if health.status == ChannelHealthStatus.DEGRADED
        ]
        unavailable = [
            health.channel
            for health in channels
            if health.status == ChannelHealthStatus.UNAVAILABLE
        ]

        if unavailable:
            status = ChannelHealthStatus.UNAVAILABLE
        elif degraded:
            status = ChannelHealthStatus.DEGRADED
        else:
            status = ChannelHealthStatus.HEALTHY

        return ChannelHealthSummary(
            status=status,
            total_channels=len(Channel),
            healthy_channels=healthy,
            degraded_channels=degraded,
            unavailable_channels=unavailable,
            channels=channels,
        )

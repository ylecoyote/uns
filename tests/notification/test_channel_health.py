"""Tests for standalone channel-health tracking."""

from __future__ import annotations

from notification.channel_health import ChannelHealthStatus, ChannelHealthTracker
from notification.models import Channel


def test_channel_starts_healthy() -> None:
    tracker = ChannelHealthTracker()

    health = tracker.get_channel_health(Channel.SLACK)

    assert health.channel == Channel.SLACK
    assert health.status == ChannelHealthStatus.HEALTHY
    assert health.consecutive_failures == 0


def test_channel_degrades_after_failure_threshold() -> None:
    tracker = ChannelHealthTracker(failure_threshold=2)

    tracker.record_failure(Channel.SLACK, reason="timeout")
    tracker.record_failure(Channel.SLACK, reason="timeout")

    health = tracker.get_channel_health(Channel.SLACK)
    assert health.status == ChannelHealthStatus.DEGRADED
    assert health.consecutive_failures == 2
    assert health.last_failure_reason == "timeout"


def test_success_recovers_degraded_channel() -> None:
    tracker = ChannelHealthTracker(failure_threshold=1)
    tracker.record_failure(Channel.PAGERDUTY, reason="rate limited")

    tracker.record_success(Channel.PAGERDUTY)

    health = tracker.get_channel_health(Channel.PAGERDUTY)
    assert health.status == ChannelHealthStatus.HEALTHY
    assert health.consecutive_failures == 0
    assert health.last_failure_reason is None


def test_summary_reports_degraded_channels() -> None:
    tracker = ChannelHealthTracker(failure_threshold=1)
    tracker.record_failure(Channel.EMAIL, reason="smtp unavailable")

    summary = tracker.get_summary()

    assert summary.status == ChannelHealthStatus.DEGRADED
    assert summary.total_channels == len(Channel)
    assert summary.degraded_channels == [Channel.EMAIL]

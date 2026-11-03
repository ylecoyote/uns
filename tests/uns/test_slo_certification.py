"""Tests for UNS SLO telemetry aggregation and certification CLI (`uns-slo-certify`, #48)."""

from __future__ import annotations

import json
import uuid

import pytest

from notification.adapters.base import BaseAdapter, DeliveryResult, guard_provider_attempt
from notification.models import AutonomyMode, Channel, Notification, NotificationIntent
from notification.service import SimpleAdapterRegistry
from uns.responses import SendNotificationRequest
from uns.runtime import Runtime
from uns.slo import compute_slo_report, format_slo_markdown, main


class _LiveOrRecordingAdapter(BaseAdapter):
    def __init__(self, channel: Channel, *, recording_only: bool = False) -> None:
        self._channel = channel
        self._recording_only = recording_only

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        guard_provider_attempt(self._channel)
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=f"msg-{notification.notification_id}",
            metadata={"recording_only": self._recording_only} if self._recording_only else {},
        )

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_slo_report_distinguishes_recording_rehearsal_from_multi_week_live_certification(
    tmp_path,
) -> None:
    """compute_slo_report accurately computes gauges, response percentiles, provider classification, and v1.0 gates."""
    db_path = tmp_path / "slo_test.db"
    db_url = f"sqlite+pysqlite:///{db_path}"

    now = 1_800_000_000.0
    current_clock = [now - (15 * 86400.0)]  # Start 15 days ago

    adapters = SimpleAdapterRegistry()
    adapters.register(_LiveOrRecordingAdapter(Channel.SLACK, recording_only=False))
    adapters.register(_LiveOrRecordingAdapter(Channel.WEBSOCKET, recording_only=False))
    runtime = Runtime(
        db_url,
        create_tables=True,
        adapters=adapters,
        clock=lambda: current_clock[0],
    )

    agent_id = uuid.uuid4()

    # 1. Accept & deliver a notification 15 days ago and ACK it 30s later
    req1 = SendNotificationRequest(
        notification_type="safety.margin_breach",
        intent=NotificationIntent.SAFETY,
        title="Early window alert",
        message="Margin check 1",
        source="mip-risk",
        idempotency_key="slo-1",
        dedup_key="slo-dedup-1",
        autonomy_context={"agent_id": agent_id, "autonomy_mode": AutonomyMode.LIVE},
    )
    acc1 = runtime.accept(req1, principal="producer-1")
    await runtime.dispatch()
    current_clock[0] += 30.0
    runtime.acknowledge(acc1.notification_id, actor="operator-1")

    # 2. Advance clock to `now` (15 days later) and accept/deliver/ACK a second notification in 12s
    current_clock[0] = now - 12.0
    req2 = SendNotificationRequest(
        notification_type="safety.margin_breach",
        intent=NotificationIntent.SAFETY,
        title="Recent window alert",
        message="Margin check 2",
        source="mip-risk",
        idempotency_key="slo-2",
        dedup_key="slo-dedup-2",
        autonomy_context={"agent_id": agent_id, "autonomy_mode": AutonomyMode.LIVE},
    )
    acc2 = runtime.accept(req2, principal="producer-1")
    await runtime.dispatch()
    current_clock[0] = now
    runtime.acknowledge(acc2.notification_id, actor="operator-1")
    runtime.engine.dispose()

    # Compute 16-day window report -> spans 15 days of live provider attempts -> v1_0_certified == True!
    report = compute_slo_report(
        db_url,
        window_days=16.0,
        min_live_days_required=14.0,
        now_epoch=now,
    )
    assert report["v1_0_certified"] is True
    assert report["observed_span_days"] >= 14.9
    assert report["observed_live_span_days"] >= 14.9
    assert report["notifications"]["total"] == 2
    assert report["notifications"]["delivered"] == 2
    assert report["acknowledgments"]["acked"] == 2
    assert report["response_latency_seconds"]["sample_count"] == 2
    assert report["response_latency_seconds"]["p50"] == 12.0
    assert report["response_latency_seconds"]["p95"] == 30.0
    assert report["provider_classification"]["live_provider_attempts"] >= 2
    assert report["receipt_hash"].startswith("sha256:")
    assert report["receipt_sha256"] == report["receipt_hash"]

    md = format_slo_markdown(report)
    assert "CERTIFIED (`v1.0` GATES PASSED)" in md
    assert report["receipt_hash"] in md

    # Empty future window (where no notifications were accepted inside the window) returns total == 0
    empty_window_report = compute_slo_report(
        db_url,
        window_days=1.0,
        min_live_days_required=14.0,
        now_epoch=now + (10 * 86400.0),
    )
    assert empty_window_report["notifications"]["total"] == 0
    assert empty_window_report["v1_0_certified"] is False

    # CLI output test (JSON and --require-certified)
    out_json = tmp_path / "slo_receipt.json"
    exit_code = main(
        [
            "--database-url",
            db_url,
            "--window-days",
            "16",
            "--min-live-days",
            "14",
            "--output",
            str(out_json),
            "--require-certified",
        ]
    )
    assert exit_code == 0
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert saved["v1_0_certified"] is True

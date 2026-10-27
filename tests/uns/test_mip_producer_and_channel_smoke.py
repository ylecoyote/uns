"""Tests for MIP producer integration demo and opt-in real-channel smoke verifier."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from examples.mip_producer_demo import (
    DEFAULT_MIP_POLICY_DIR,
    build_recording_registry,
    load_mip_policies,
    run_http_demo,
    run_local_demo,
)
from examples.mip_producer_demo import (
    main as mip_demo_main,
)
from scripts.opt_in_channel_smoke import (
    SMOKE_TAG,
    SlackWebhookSmokeAdapter,
    build_channel_adapter,
    inspect_channel_readiness,
    run_channel_smoke,
)
from scripts.opt_in_channel_smoke import (
    main as smoke_main,
)

from agsignal.app import create_app
from notification.adapters.base import DeliveryResult
from notification.models import Channel, Notification
from uns.runtime import Runtime


@pytest.mark.asyncio
async def test_mip_producer_local_demo_exercises_simulation_ack_and_dedup(
    tmp_path: Path,
) -> None:
    db_url = f"sqlite:///{tmp_path / 'mip_local.db'}"
    receipt = await run_local_demo(
        database_url=db_url,
        policy_dir=DEFAULT_MIP_POLICY_DIR,
        principal="mip-desk-producer",
        responder_principal="mip-risk-officer",
    )

    assert receipt["mode"] == "local_recording"
    assert receipt["verified"] is True
    assert receipt["policy_types_loaded"] == [
        "execution.slippage",
        "governance.approval_required",
        "safety.kill_switch",
    ]

    sim = receipt["simulation"]
    assert sim["notification_type"] == "governance.approval_required"
    assert sim["simulated"] is True
    assert sim["delivery_mode"] == "GUARANTEED"
    assert sim["require_ack"] is True
    assert "SLACK" in sim["channels"]
    assert sim["policy_source"] == "policy"

    safety = receipt["safety_kill_switch"]
    assert safety["status"] == "DELIVERED"
    assert safety["require_ack"] is True
    assert safety["initial_ack_status"] == "PENDING"
    assert safety["final_ack_status"] == "ACKED"
    assert safety["acked_by"] == "mip-risk-officer"
    assert "ACKED" in safety["event_kinds"]

    dedup = receipt["deduplication"]
    assert dedup["notification_type"] == "execution.slippage"
    assert dedup["primary_status"] == "DELIVERED"
    assert dedup["duplicate_status"] == "DEDUPLICATED"
    assert dedup["obligation_owner_id"] == dedup["primary_notification_id"]
    assert dedup["obligation_resolution_status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_mip_producer_http_demo_against_live_asgi_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from notification.rate_limiting import configure_rate_limiter

    configure_rate_limiter({})
    producer_key = "test-producer-secret-key"
    responder_key = "test-responder-secret-key"
    admin_key = "test-admin-secret-key"

    monkeypatch.setenv("UNS_PRODUCER_API_KEY", producer_key)
    monkeypatch.setenv("UNS_PRODUCER_API_PRINCIPAL", "mip-http-producer")
    monkeypatch.setenv("UNS_RESPONDER_API_KEY", responder_key)
    monkeypatch.setenv("UNS_RESPONDER_API_PRINCIPAL", "mip-http-responder")
    monkeypatch.setenv("UNS_API_KEY", admin_key)
    monkeypatch.setenv("UNS_API_PRINCIPAL", "mip-http-admin")

    db_url = f"sqlite:///{tmp_path / 'mip_http.db'}"
    registry, _ = build_recording_registry()
    runtime = Runtime(db_url, adapters=registry, create_tables=True)
    try:
        load_mip_policies(runtime, policy_dir=DEFAULT_MIP_POLICY_DIR)
        app = create_app(runtime=runtime)
        transport = httpx.ASGITransport(app=app)

        receipt = await run_http_demo(
            "http://127.0.0.1:18080",
            policy_dir=DEFAULT_MIP_POLICY_DIR,
            reload_policies=True,
            transport=transport,
        )

        assert receipt["mode"] == "http"
        assert receipt["verified"] is True
        assert receipt["simulation"]["simulated"] is True
        assert receipt["simulation"]["policy_source"] == "policy"
        assert receipt["safety_kill_switch"]["status"] == "DELIVERED"
        assert receipt["safety_kill_switch"]["final_ack_status"] == "ACKED"
        assert receipt["safety_kill_switch"]["acked_by"] == "mip-http-responder"
        assert receipt["deduplication"]["primary_status"] == "DELIVERED"
        assert receipt["deduplication"]["duplicate_status"] == "DEDUPLICATED"
        assert (
            receipt["deduplication"]["obligation_owner_id"]
            == receipt["deduplication"]["primary_notification_id"]
        )
    finally:
        runtime.engine.dispose()


@pytest.mark.asyncio
async def test_mip_producer_http_demo_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in (
        "UNS_PRODUCER_API_KEY",
        "UNS_API_KEY",
        "AGSIGNAL_PRODUCER_API_KEY",
        "AGSIGNAL_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValueError, match="UNS_PRODUCER_API_KEY"):
        await run_http_demo("http://127.0.0.1:18080")


def test_mip_producer_cli_json_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mip_demo_main(["--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "local_recording"
    assert payload["verified"] is True


def test_opt_in_channel_smoke_readiness_inspection_and_pii_masking() -> None:
    empty_readiness = inspect_channel_readiness(env={})
    assert empty_readiness["slack"]["configured"] is False
    assert empty_readiness["slack"]["missing_env"] == ["UNS_SLACK_WEBHOOK_URL"]
    assert empty_readiness["email"]["configured"] is False
    assert empty_readiness["email"]["missing_env"] == [
        "UNS_SMTP_HOST",
        "UNS_SMTP_FROM",
        "UNS_SMOKE_EMAIL_TO",
    ]
    assert empty_readiness["pagerduty"]["configured"] is False
    assert empty_readiness["pagerduty"]["missing_env"] == ["UNS_PAGERDUTY_ROUTING_KEY"]

    configured_env = {
        "UNS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T000/B000/XXXX",
        "UNS_SMTP_HOST": "smtp.example.com",
        "UNS_SMTP_FROM": "alerts@example.com",
        "UNS_SMOKE_EMAIL_TO": "oncall@example.com",
        "UNS_PAGERDUTY_ROUTING_KEY": "a" * 32,
    }
    ready = inspect_channel_readiness(env=configured_env)
    assert ready["slack"]["configured"] is True
    assert ready["slack"]["mode"] == "webhook"
    assert ready["email"]["configured"] is True
    assert ready["email"]["from_address_masked"] == "a***@example.com"
    assert ready["email"]["recipients_masked"] == ["o***@example.com"]
    assert ready["pagerduty"]["configured"] is True
    assert ready["pagerduty"]["routing_key_length"] == 32


def test_opt_in_channel_smoke_dry_run_and_unconfigured_exit_zero_without_traffic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 1. Default dry-run even with credentials present sends no external traffic.
    configured_env = {
        "UNS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T000/B000/XXXX",
        "UNS_SMTP_HOST": "smtp.example.com",
        "UNS_SMTP_FROM": "alerts@example.com",
        "UNS_SMOKE_EMAIL_TO": "oncall@example.com",
        "UNS_PAGERDUTY_ROUTING_KEY": "b" * 32,
    }
    exit_code = smoke_main(["--dry-run", "--json"], env=configured_env)
    assert exit_code == 0
    dry_report = json.loads(capsys.readouterr().out)
    assert dry_report["mode"] == "dry_run"
    assert dry_report["external_traffic_sent"] is False
    assert dry_report["attempts"] == []
    assert set(dry_report["configured_channels"]) == {"slack", "email", "pagerduty"}

    # 2. --execute when env vars are absent sends no external traffic and exits 0.
    unconfigured_exit = smoke_main(["--execute", "--json"], env={})
    assert unconfigured_exit == 0
    unconfigured_report = json.loads(capsys.readouterr().out)
    assert unconfigured_report["mode"] == "unconfigured_skip"
    assert unconfigured_report["external_traffic_sent"] is False
    assert unconfigured_report["attempts"] == []


@pytest.mark.asyncio
async def test_opt_in_channel_smoke_execute_dispatches_tagged_messages_through_adapters() -> None:
    configured_env = {
        "UNS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T000/B000/XXXX",
        "UNS_SMTP_HOST": "smtp.example.com",
        "UNS_SMTP_FROM": "alerts@example.com",
        "UNS_SMOKE_EMAIL_TO": "oncall@example.com",
        "UNS_PAGERDUTY_ROUTING_KEY": "c" * 32,
    }

    observed_notifications: dict[str, Notification] = {}

    async def fake_slack_deliver(
        self: SlackWebhookSmokeAdapter, notification: Notification
    ) -> DeliveryResult:
        observed_notifications["slack"] = notification
        return DeliveryResult(
            success=True,
            channel=Channel.SLACK,
            message_id="slack-smoke-msg-1",
            metadata={"transport": "webhook", "http_status": 200},
            delivered_at=datetime.now(UTC),
        )

    async def fake_email_deliver(self: Any, notification: Notification) -> DeliveryResult:
        observed_notifications["email"] = notification
        return DeliveryResult(
            success=True,
            channel=Channel.EMAIL,
            message_id="<smoke-email-1@example.com>",
            metadata={
                "recipients": ["oncall@example.com"],
                "provider_outcome": "SUCCEEDED",
            },
            delivered_at=datetime.now(UTC),
        )

    async def fake_pd_deliver(self: Any, notification: Notification) -> DeliveryResult:
        observed_notifications["pagerduty"] = notification
        return DeliveryResult(
            success=True,
            channel=Channel.PAGERDUTY,
            message_id="pd-smoke-dedup-1",
            metadata={"pagerduty_status": "success", "severity": "warning"},
            delivered_at=datetime.now(UTC),
        )

    with (
        patch.object(SlackWebhookSmokeAdapter, "deliver", new=fake_slack_deliver),
        patch("notification.adapters.email.EmailAdapter.deliver", new=fake_email_deliver),
        patch("notification.adapters.pagerduty.PagerDutyAdapter.deliver", new=fake_pd_deliver),
    ):
        report = await run_channel_smoke(execute=True, env=configured_env)

    assert report["mode"] == "executed"
    assert report["external_traffic_sent"] is True
    assert len(report["attempts"]) == 3

    by_channel = {item["channel"]: item for item in report["attempts"]}
    assert set(by_channel) == {"SLACK", "EMAIL", "PAGERDUTY"}

    for channel_key, notification in observed_notifications.items():
        assert SMOKE_TAG in notification.title
        assert SMOKE_TAG in notification.message
        attempt = by_channel[channel_key.upper()]
        assert attempt["attempt_status"] == "DELIVERED"
        assert attempt["success"] is True
        assert isinstance(attempt["latency_ms"], float)
        assert attempt["latency_ms"] >= 0.0
        assert attempt["provider_receipt"]["message_id"] is not None
        assert "CHANNEL_ATTEMPT_RESULT" in attempt["event_kinds"]
        assert "DELIVERY_RESULT" in attempt["event_kinds"]

    # Verify PII masking on email receipt metadata
    assert by_channel["EMAIL"]["provider_receipt"]["metadata"]["recipients"] == [
        "o***@example.com"
    ]


def test_opt_in_channel_smoke_cli_returns_nonzero_when_provider_attempt_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configured_env = {
        "UNS_PAGERDUTY_ROUTING_KEY": "d" * 32,
    }
    failed_result = DeliveryResult(
        success=False,
        channel=Channel.PAGERDUTY,
        error="PagerDuty HTTP 500",
        delivered_at=datetime.now(UTC),
    )
    with patch(
        "notification.adapters.pagerduty.PagerDutyAdapter.deliver",
        new=AsyncMock(return_value=failed_result),
    ):
        exit_code = smoke_main(
            ["--execute", "--channel", "pagerduty", "--json"],
            env=configured_env,
        )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "executed"
    assert payload["attempts"][0]["attempt_status"] == "FAILED"
    assert payload["attempts"][0]["success"] is False


def test_build_channel_adapter_supports_webhook_and_bot_token_for_slack() -> None:
    webhook_adapter = build_channel_adapter(
        "slack",
        env={"UNS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T000/B000/XXXX"},
    )
    assert isinstance(webhook_adapter, SlackWebhookSmokeAdapter)

    bot_adapter = build_channel_adapter(
        "slack",
        env={
            "UNS_SLACK_BOT_TOKEN": "xoxb-123456-abcdef",
            "UNS_SLACK_CHANNEL": "#ops-alerts",
        },
    )
    assert bot_adapter.channel == Channel.SLACK

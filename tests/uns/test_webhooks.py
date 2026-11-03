"""Tests for signed Slack and PagerDuty inbound webhooks and bi-directional sync."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from db.policy_store import SQLAlchemyPolicyStore
from notification.adapters.base import (
    AdapterStatus,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    Notification,
    NotificationIntent,
)
from notification.policies import NotificationPolicy
from notification.service import SimpleAdapterRegistry
from uns.app import create_app
from uns.responses import AutonomyContextRequest, SendNotificationRequest
from uns.runtime import Runtime


class _RecordingChannelAdapter(BaseAdapter):
    """Test adapter that records deliveries and PagerDuty outbound sync calls."""

    guards_provider_attempts = True

    def __init__(self, channel: Channel) -> None:
        self._channel = channel
        self.delivered: list[Notification] = []
        self.acknowledged_keys: list[str] = []
        self.resolved_keys: list[str] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        self.delivered.append(notification)
        dedup_key = (
            f"uns-{notification.dedup_key}"
            if notification.dedup_key
            else f"uns-{notification.notification_id}"
        )
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=dedup_key,
            metadata={"pagerduty_dedup_key": dedup_key},
            delivered_at=datetime.now(UTC),
        )

    async def acknowledge_incident(self, dedup_key: str) -> DeliveryResult:
        self.acknowledged_keys.append(dedup_key)
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=dedup_key,
            metadata={"action": "acknowledge"},
            delivered_at=datetime.now(UTC),
        )

    async def resolve_incident(self, dedup_key: str) -> DeliveryResult:
        self.resolved_keys.append(dedup_key)
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=dedup_key,
            metadata={"action": "resolve"},
            delivered_at=datetime.now(UTC),
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status=AdapterStatus.HEALTHY, message="ok")

    def format_message(self, notification: Notification) -> str:
        return notification.message


def _sign_slack(secret: str, timestamp: int, raw_body: bytes) -> dict[str, str]:
    basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}".encode()
    digest = hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": str(timestamp),
        "X-Slack-Signature": f"v0={digest}",
    }


def _sign_pagerduty(secret: str, raw_body: bytes) -> dict[str, str]:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return {
        "X-PagerDuty-Signature": f"v1={digest}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def webhook_env(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Runtime, _RecordingChannelAdapter, str]:
    operator_key = f"op-key-{uuid4().hex}"
    monkeypatch.setenv("UNS_API_KEY", operator_key)
    monkeypatch.setenv("UNS_API_PRINCIPAL", "test-operator")
    monkeypatch.setenv("UNS_SLACK_SIGNING_SECRET", f"slack-secret-{uuid4().hex}")
    monkeypatch.setenv("UNS_PAGERDUTY_WEBHOOK_SECRET", f"pd-secret-{uuid4().hex}")

    now = [1_730_000_000.0]
    registry = SimpleAdapterRegistry()
    slack_adapter = _RecordingChannelAdapter(Channel.SLACK)
    pd_adapter = _RecordingChannelAdapter(Channel.PAGERDUTY)
    registry.register(slack_adapter)
    registry.register(pd_adapter)

    runtime = Runtime(
        "sqlite://",
        adapters=registry,
        create_tables=True,
        clock=lambda: now[0],
    )
    SQLAlchemyPolicyStore(runtime.sessions).save_snapshot(
        [
            NotificationPolicy(
                notification_type="ops.provider.degraded",
                intent=NotificationIntent.OPERATIONAL,
                channels=[Channel.SLACK, Channel.PAGERDUTY],
                delivery_mode=DeliveryMode.GUARANTEED,
                require_ack=True,
                ack_timeout_minutes=15,
                dedup_window_seconds=300,
            ),
            NotificationPolicy(
                notification_type="safety.kill_switch",
                intent=NotificationIntent.SAFETY,
                channels=[Channel.PAGERDUTY],
                delivery_mode=DeliveryMode.GUARANTEED,
                require_ack=True,
                ack_timeout_minutes=15,
                dedup_window_seconds=300,
            ),
        ]
    )
    app = create_app(runtime=runtime)
    client = TestClient(app)
    return client, runtime, pd_adapter, operator_key


def _make_request(
    *,
    notification_type: str = "ops.provider.degraded",
    intent: NotificationIntent = NotificationIntent.OPERATIONAL,
    dedup_key: str = "wyredeck-provider-primary",
) -> SendNotificationRequest:
    return SendNotificationRequest(
        notification_type=notification_type,
        intent=intent,
        title="Provider Health Degraded",
        message="Upstream provider exhausted retry budget",
        source="wyredeck",
        dedup_key=dedup_key,
        autonomy_context=AutonomyContextRequest(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
    )


async def test_slack_and_pagerduty_webhooks_fail_closed_when_secrets_unset(
    monkeypatch: pytest.MonkeyPatch,
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, _runtime, _pd, _op_key = webhook_env
    monkeypatch.delenv("UNS_SLACK_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("UNS_PAGERDUTY_WEBHOOK_SECRET", raising=False)

    res_slack = client.post("/api/v1/webhooks/slack", content=b"{}")
    assert res_slack.status_code == 503
    assert "not configured" in res_slack.json()["detail"]

    res_pd = client.post("/api/v1/webhooks/pagerduty", content=b"{}")
    assert res_pd.status_code == 503
    assert "not configured" in res_pd.json()["detail"]


async def test_slack_webhook_rejects_invalid_signature_and_stale_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, runtime, _pd, _op_key = webhook_env
    secret = uuid4().hex
    monkeypatch.setenv("UNS_SLACK_SIGNING_SECRET", secret)
    now_ts = int(runtime.clock())

    body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()

    # Bad signature
    res_bad = client.post(
        "/api/v1/webhooks/slack",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": str(now_ts),
            "X-Slack-Signature": "v0=deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert res_bad.status_code == 401

    # Expired timestamp (> 300s old)
    stale_headers = _sign_slack(secret, now_ts - 600, body)
    stale_headers["Content-Type"] = "application/json"
    res_stale = client.post("/api/v1/webhooks/slack", content=body, headers=stale_headers)
    assert res_stale.status_code == 401
    assert "replay window" in res_stale.json()["detail"]


async def test_slack_webhook_url_verification_challenge(
    monkeypatch: pytest.MonkeyPatch,
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, runtime, _pd, _op_key = webhook_env
    secret = uuid4().hex
    monkeypatch.setenv("UNS_SLACK_SIGNING_SECRET", secret)
    now_ts = int(runtime.clock())

    body = json.dumps({"type": "url_verification", "challenge": "slack-challenge-token"}).encode()
    headers = _sign_slack(secret, now_ts, body)
    headers["Content-Type"] = "application/json"

    res = client.post("/api/v1/webhooks/slack", content=body, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"challenge": "slack-challenge-token"}


async def test_slack_webhook_block_actions_acknowledges_follower_via_canonical_owner(
    monkeypatch: pytest.MonkeyPatch,
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, runtime, _pd, _op_key = webhook_env
    secret = uuid4().hex
    monkeypatch.setenv("UNS_SLACK_SIGNING_SECRET", secret)
    now_ts = int(runtime.clock())

    # Send owner and deduplicated follower
    owner = await runtime.send(_make_request(dedup_key="dedup-group-1"), principal="producer-1")
    follower = await runtime.send(_make_request(dedup_key="dedup-group-1"), principal="producer-1")
    assert owner.status.value == "DELIVERED"
    assert follower.status.value == "DEDUPLICATED"
    assert follower.obligation_owner_id == owner.notification_id

    # Click Acknowledge button on the follower notification ID using URL-encoded form payload
    slack_payload: dict[str, Any] = {
        "type": "block_actions",
        "team": {"id": "T99999"},
        "user": {"id": "U12345", "username": "oncall.alice"},
        "actions": [
            {
                "action_id": f"ack_{follower.notification_id}",
                "value": str(follower.notification_id),
            }
        ],
    }
    raw_body = urlencode({"payload": json.dumps(slack_payload)}).encode("utf-8")
    headers = _sign_slack(secret, now_ts, raw_body)
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    res = client.post("/api/v1/webhooks/slack", content=raw_body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["replace_original"] is True
    assert data["ack_status"] == "ACKED"
    assert data["acked_by"] == "slack:T99999:U12345"
    assert data["notification_id"] == str(follower.notification_id)
    assert data["obligation_owner_id"] == str(owner.notification_id)

    # Verify both owner and follower reflect ACKED in runtime
    owner_row = runtime.get(owner.notification_id)
    follower_row = runtime.get(follower.notification_id)
    assert owner_row["ack_status"] == "ACKED"
    assert owner_row["actor"] == "slack:T99999:U12345"
    assert follower_row["effective_ack_status"] == "ACKED"


async def test_slack_webhook_dismiss_action(
    monkeypatch: pytest.MonkeyPatch,
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, runtime, _pd, _op_key = webhook_env
    secret = uuid4().hex
    monkeypatch.setenv("UNS_SLACK_SIGNING_SECRET", secret)
    now_ts = int(runtime.clock())

    sent = await runtime.send(_make_request(dedup_key="dedup-dismiss"), principal="producer-1")
    slack_payload = {
        "type": "block_actions",
        "user": {"id": "U77777", "name": "bob"},
        "actions": [{"action_id": f"dismiss_{sent.notification_id}"}],
    }
    raw_body = json.dumps(slack_payload).encode("utf-8")
    headers = _sign_slack(secret, now_ts, raw_body)
    headers["Content-Type"] = "application/json"

    res = client.post("/api/v1/webhooks/slack", content=raw_body, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["ack_status"] == "DISMISSED"
    assert body["acked_by"] == "slack:U77777"
    assert runtime.get(sent.notification_id)["ack_status"] == "DISMISSED"


async def test_pagerduty_webhook_acknowledges_and_resolves_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, runtime, _pd, _op_key = webhook_env
    pd_secret = uuid4().hex
    monkeypatch.setenv("UNS_PAGERDUTY_WEBHOOK_SECRET", pd_secret)

    sent = await runtime.send(
        _make_request(
            notification_type="safety.kill_switch",
            intent=NotificationIntent.SAFETY,
            dedup_key="kill-switch-alpha",
        ),
        principal="producer-1",
    )
    assert sent.status.value == "DELIVERED"

    # 1. PagerDuty sends incident.acknowledged with comma-separated rotation signatures
    ack_event = {
        "event": {
            "id": "01PDACK001",
            "event_type": "incident.acknowledged",
            "agent": {"id": "PUSER01", "summary": "Dana OnCall"},
            "data": {
                "id": "PINC001",
                "dedup_key": "uns-kill-switch-alpha",
            },
        }
    }
    raw_ack = json.dumps(ack_event).encode("utf-8")
    valid_sig = _sign_pagerduty(pd_secret, raw_ack)["X-PagerDuty-Signature"]
    res_ack = client.post(
        "/api/v1/webhooks/pagerduty",
        content=raw_ack,
        headers={
            "X-PagerDuty-Signature": f"v1=0000000000000000,{valid_sig}",
            "Content-Type": "application/json",
        },
    )
    assert res_ack.status_code == 200
    ack_data = res_ack.json()
    assert ack_data["status"] == "settled"
    assert ack_data["already_settled"] is False
    assert ack_data["ack_status"] == "ACKED"
    assert ack_data["acked_by"] == "pagerduty:PUSER01"
    assert ack_data["obligation_owner_id"] == str(sent.notification_id)

    # 2. PagerDuty later sends incident.resolved for the same incident -> returns 200 already_settled
    resolve_event = {
        "event": {
            "id": "01PDRES002",
            "event_type": "incident.resolved",
            "agent": {"id": "PUSER02", "summary": "Dana OnCall"},
            "data": {
                "id": "PINC001",
                "dedup_key": "uns-kill-switch-alpha",
            },
        }
    }
    raw_res = json.dumps(resolve_event).encode("utf-8")
    res_resolve = client.post(
        "/api/v1/webhooks/pagerduty",
        content=raw_res,
        headers=_sign_pagerduty(pd_secret, raw_res),
    )
    assert res_resolve.status_code == 200
    res_data = res_resolve.json()
    assert res_data["status"] == "settled"
    assert res_data["already_settled"] is True
    assert res_data["ack_status"] == "ACKED"

    # 3. Non-settlement PagerDuty event (incident.triggered) is ignored with 200
    trig_event = {"event": {"id": "01PDTRIG", "event_type": "incident.triggered", "data": {}}}
    raw_trig = json.dumps(trig_event).encode("utf-8")
    res_trig = client.post(
        "/api/v1/webhooks/pagerduty",
        content=raw_trig,
        headers=_sign_pagerduty(pd_secret, raw_trig),
    )
    assert res_trig.status_code == 200
    assert res_trig.json()["status"] == "ignored"


async def test_outbound_pagerduty_sync_on_http_ack_and_dismiss(
    webhook_env: tuple[TestClient, Runtime, _RecordingChannelAdapter, str],
) -> None:
    client, runtime, pd_adapter, operator_key = webhook_env

    sent_ack = await runtime.send(
        _make_request(
            notification_type="safety.kill_switch",
            intent=NotificationIntent.SAFETY,
            dedup_key="pd-outbound-ack",
        ),
        principal="producer-1",
    )
    res_ack = client.post(
        f"/api/v1/notifications/{sent_ack.notification_id}/ack",
        headers={"X-UNS-API-Key": operator_key},
        json={"metadata": {"note": "Acked in console"}},
    )
    assert res_ack.status_code == 200
    assert "uns-pd-outbound-ack" in pd_adapter.acknowledged_keys

    sent_dismiss = await runtime.send(
        _make_request(
            notification_type="safety.kill_switch",
            intent=NotificationIntent.SAFETY,
            dedup_key="pd-outbound-dismiss",
        ),
        principal="producer-1",
    )
    res_dismiss = client.post(
        f"/api/v1/notifications/{sent_dismiss.notification_id}/dismiss",
        headers={"X-UNS-API-Key": operator_key},
        json={"metadata": {"note": "Dismissed in console"}},
    )
    assert res_dismiss.status_code == 200
    assert "uns-pd-outbound-dismiss" in pd_adapter.resolved_keys

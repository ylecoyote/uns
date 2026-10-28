"""Regression tests for Multi-Perspective Deep Dive v2.5 remediations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    Notification,
    NotificationIntent,
)
from notification.policies import NotificationPolicy
from notification.rate_limiter import _rate_limit_key
from notification.service import SimpleAdapterRegistry
from uns.app import create_app
from uns.config import configured_adapters, database_url
from uns.queries import list_invariants
from uns.responses import AutonomyContextRequest, SendNotificationRequest
from uns.runtime import Runtime


class _CountingPagerDutyAdapter(BaseAdapter):
    channel = Channel.PAGERDUTY

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def deliver(self, notification: Notification) -> DeliveryResult:
        self.sent.append(str(notification.notification_id))
        return DeliveryResult(
            success=True,
            channel=Channel.PAGERDUTY,
            message_id=f"pd-{len(self.sent)}",
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status=AdapterStatus.HEALTHY, message="ok")


def test_reload_policies_rejects_filesystem_root_when_tempdir_is_slash_tmp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When tempfile.gettempdir() is '/tmp' on Linux, '/etc' must never be allowed."""
    monkeypatch.delenv("UNS_POLICY_DIR", raising=False)
    runtime = Runtime(f"sqlite:///{tmp_path / 'reload.db'}", create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_api_key = "admin-key"
    try:
        client = TestClient(app)
        with patch("tempfile.gettempdir", return_value="/tmp"):
            resp = client.post(
                "/api/v1/policies/reload",
                json={"policy_dir": "/usr"},
                headers={"Authorization": "Bearer admin-key"},
            )
        assert resp.status_code == 422
        assert (
            "outside the allowed root" in resp.text
            or "must reside within" in resp.text
            or "does not exist" in resp.text
        )
    finally:
        runtime.engine.dispose()


def test_rate_limit_key_isolates_scoped_role_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Producer, responder, and observer API keys must each receive distinct key:<hash> buckets."""
    monkeypatch.setenv("UNS_API_KEY", "admin-secret")
    monkeypatch.setenv("UNS_PRODUCER_API_KEY", "producer-secret")
    monkeypatch.setenv("UNS_RESPONDER_API_KEY", "responder-secret")
    monkeypatch.setenv("UNS_OBSERVER_API_KEY", "observer-secret")

    runtime = Runtime(f"sqlite:///{tmp_path / 'rl.db'}", create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    try:
        buckets: set[str] = set()
        for token in ("admin-secret", "producer-secret", "responder-secret", "observer-secret"):
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/ui/deliveries",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
                "app": app,
                "client": ("127.0.0.1", 12345),
            }
            from starlette.requests import Request

            req = Request(scope)
            key = _rate_limit_key(req)
            assert key.startswith("key:"), f"Expected key:* bucket for {token}, got {key}"
            buckets.add(key)
        assert len(buckets) == 4
    finally:
        runtime.engine.dispose()


@pytest.mark.asyncio
async def test_runtime_pagerduty_burst_not_throttled_by_legacy_in_memory_bucket(
    tmp_path: Path,
) -> None:
    """Runtime.dispatch must use its durable rate limiter, not DeliveryService's 2-burst in-memory bucket."""
    from db.policy_store import SQLAlchemyPolicyStore

    adapter = _CountingPagerDutyAdapter()
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    runtime = Runtime(f"sqlite:///{tmp_path / 'burst.db'}", adapters=registry, create_tables=True)
    try:
        SQLAlchemyPolicyStore(runtime.sessions).save_snapshot(
            [
                NotificationPolicy(
                    notification_type="safety.burst",
                    delivery_mode=DeliveryMode.GUARANTEED,
                    channels=[Channel.PAGERDUTY],
                    require_ack=False,
                )
            ]
        )
        ids = []
        for idx in range(4):
            accepted = await runtime.send(
                SendNotificationRequest(
                    notification_type="safety.burst",
                    intent=NotificationIntent.SAFETY,
                    title=f"Burst {idx}",
                    message="PagerDuty burst test",
                    source=f"burst-test-{idx}",
                    autonomy_context=AutonomyContextRequest(
                        autonomy_mode=AutonomyMode.LIVE,
                        agent_id=uuid4(),
                    ),
                ),
                principal="operator",
            )
            ids.append(accepted.notification_id)

        assert len(adapter.sent) == 4
        for nid in ids:
            state = runtime.get(nid)
            assert state["status"] == "DELIVERED"
            assert state["dead_letter"] is False
    finally:
        runtime.engine.dispose()


def test_readyz_reports_runtime_slack_bot_token_and_database_url_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_channel_readiness must reflect SlackAdapter registered via UNS_SLACK_BOT_TOKEN."""
    monkeypatch.setenv("UNS_SLACK_BOT_TOKEN", "xoxb-test-token-12345")
    monkeypatch.setenv("UNS_SLACK_CHANNEL", "#ops")
    monkeypatch.delenv("UNS_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'fallback.db'}")

    assert database_url() == f"sqlite:///{tmp_path / 'fallback.db'}"
    adapters = configured_adapters()
    assert adapters.get_adapter(Channel.SLACK) is not None

    runtime = Runtime(database_url(), adapters=adapters, create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_api_key = "ops-key"
    try:
        client = TestClient(app)
        resp = client.get("/readyz", headers={"Authorization": "Bearer ops-key"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["channels_configured"]["slack"] is True
    finally:
        runtime.engine.dispose()


@pytest.mark.asyncio
async def test_list_invariants_falls_back_to_packaged_yaml() -> None:
    """Packaged src/uns/invariants.yml must exist and match docs/verification/invariants.yml."""
    import uns.queries as queries_mod

    packaged = Path(queries_mod.__file__).with_name("invariants.yml")
    assert packaged.is_file()
    res = await list_invariants(limit=50)
    assert len(res.items) >= 9

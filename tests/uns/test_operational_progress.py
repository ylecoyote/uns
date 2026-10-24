"""Readiness distinguishes obligation age, retry lateness, and retained uncertainty."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.uns.test_delivery_remediation import request

from agsignal.app import create_app
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.rate_limiting import configure_rate_limiter
from notification.service import SimpleAdapterRegistry
from uns.runtime import Runtime


class RecordingAdapter(BaseAdapter):
    channel = Channel.SLACK

    def __init__(self):
        self.success = True
        self.provider_outcome = None

    async def deliver(self, notification):
        return DeliveryResult(
            success=self.success,
            channel=self.channel,
            metadata={"provider_outcome": self.provider_outcome},
        )

    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY, "recording adapter")


@pytest.fixture
def state(tmp_path, monkeypatch):
    for name in ("UNS_POLICY_DIR", "AGSIGNAL_POLICY_DIR"):
        monkeypatch.delenv(name, raising=False)
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    now = [1000.0]
    adapter = RecordingAdapter()
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    runtime = Runtime(
        f"sqlite:///{tmp_path}/progress.db",
        create_tables=True,
        adapters=registry,
        clock=lambda: now[0],
        retry_seconds=3700,
    )
    yield runtime, adapter, now
    runtime.engine.dispose()


def test_empty_progress_has_zero_counts_and_unknown_ages(state):
    runtime, _, _ = state
    assert runtime.operational_progress() == {
        "pending_count": 0,
        "oldest_pending_age_seconds": None,
        "oldest_due_attempt_lateness_seconds": None,
        "overdue_ack_count": 0,
        "pending_callback_count": 0,
        "oldest_callback_retry_age_seconds": None,
        "unresolved_failure_count": 0,
        "unknown_attempt_count": 0,
    }


@pytest.mark.asyncio
async def test_pending_age_survives_backoff_and_counts_only_dispatch_owners(state):
    runtime, adapter, now = state
    owner = runtime.accept(request("owner"), principal="producer")
    runtime.accept(request("follower"), principal="producer")
    adapter.success = False
    assert await runtime.dispatch(owner.notification_id)
    assert runtime.get(owner.notification_id)["next_attempt"] == 4700.0

    now[0] = 4600.0
    progress = runtime.operational_progress()
    assert progress["pending_count"] == 1
    assert progress["oldest_pending_age_seconds"] == 3600.0
    assert progress["oldest_due_attempt_lateness_seconds"] is None

    now[0] = 4800.0
    progress = runtime.operational_progress()
    assert progress["oldest_pending_age_seconds"] == 3800.0
    assert progress["oldest_due_attempt_lateness_seconds"] == 100.0

    adapter.success = True
    assert await runtime.dispatch(owner.notification_id)
    progress = runtime.operational_progress()
    assert progress["pending_count"] == 0
    assert progress["oldest_pending_age_seconds"] is None
    assert progress["oldest_due_attempt_lateness_seconds"] is None


@pytest.mark.asyncio
async def test_dispatch_lateness_starts_after_active_lease_expires(state, monkeypatch):
    runtime, adapter, now = state
    owner = runtime.accept(request(), principal="producer")
    observations = []

    async def delayed_provider_result(notification):
        now[0] += 50
        observations.append(runtime.operational_progress())
        now[0] += 15
        observations.append(runtime.operational_progress())
        return DeliveryResult(success=False, channel=Channel.SLACK)

    monkeypatch.setattr(adapter, "deliver", delayed_provider_result)
    assert not await runtime.dispatch(owner.notification_id)
    assert observations[0]["oldest_pending_age_seconds"] == 50.0
    assert observations[0]["oldest_due_attempt_lateness_seconds"] is None
    assert observations[1]["oldest_pending_age_seconds"] == 65.0
    assert observations[1]["oldest_due_attempt_lateness_seconds"] == 5.0


@pytest.mark.asyncio
async def test_overdue_ack_and_callback_retry_progress_follow_durable_transitions(state):
    runtime, _, now = state

    async def failing_callback(event):
        raise RuntimeError("callback consumer unavailable")

    runtime.callback = failing_callback
    delivered = await runtime.send(request(require_ack=True), principal="producer")
    now[0] = runtime.get(delivered.notification_id)["deadline"] + 1
    assert runtime.operational_progress()["overdue_ack_count"] == 1
    runtime.expire()
    now[0] += 10
    progress = runtime.operational_progress()
    assert progress["overdue_ack_count"] == 0
    assert progress["pending_callback_count"] == 1
    assert progress["oldest_callback_retry_age_seconds"] == 10.0

    await runtime.deliver_callbacks()
    progress = runtime.operational_progress()
    assert progress["pending_callback_count"] == 1
    assert progress["oldest_callback_retry_age_seconds"] is None
    now[0] += 9
    assert runtime.operational_progress()["oldest_callback_retry_age_seconds"] == 7.0
    await runtime.deliver_callbacks()
    now[0] += 4
    await runtime.deliver_callbacks()
    progress = runtime.operational_progress()
    assert progress["pending_callback_count"] == 0
    assert progress["oldest_callback_retry_age_seconds"] is None


@pytest.mark.asyncio
async def test_unknown_attempt_evidence_survives_successful_replay(state):
    runtime, adapter, _ = state
    runtime.max_attempts = 1
    adapter.success = False
    adapter.provider_outcome = "UNKNOWN"
    failed = await runtime.send(request(), principal="producer")
    progress = runtime.operational_progress()
    assert progress["unknown_attempt_count"] == 1
    assert progress["unresolved_failure_count"] == 1

    runtime.replay(failed.notification_id, actor="operator")
    adapter.success = True
    adapter.provider_outcome = None
    assert await runtime.dispatch(failed.notification_id)
    progress = runtime.operational_progress()
    assert progress["unknown_attempt_count"] == 1
    assert progress["unresolved_failure_count"] == 0


@pytest.mark.asyncio
async def test_readyz_uses_counts_without_loading_dead_letter_histories(state, monkeypatch):
    runtime, adapter, _ = state
    runtime.max_attempts = 1
    adapter.success = False
    adapter.provider_outcome = "NOT_STARTED"
    await runtime.send(request(), principal="producer")

    def reject_history_loading():
        pytest.fail("Readiness must not materialize dead-letter histories")

    monkeypatch.setattr(runtime, "dead_letters", reject_history_loading)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.agsignal_api_key = "progress-test-key"
    with TestClient(app, headers={"Authorization": "Bearer progress-test-key"}) as client:
        response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["dlq_depth"] == 1
    assert body["operational_progress"]["unresolved_failure_count"] == 1
    assert body["operational_progress"]["unknown_attempt_count"] == 0

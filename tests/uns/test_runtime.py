from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from agsignal.responses import SendNotificationRequest
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import AckStatus, Channel, DeliveryStatus
from notification.service import SimpleAdapterRegistry
from uns.runtime import Conflict, Runtime


class RecordingAdapter(BaseAdapter):
    def __init__(self, channel=Channel.SLACK, success=True):
        self._channel = channel
        self.success = success
        self.calls = []

    @property
    def channel(self):
        return self._channel

    async def deliver(self, notification):
        self.calls.append(notification.notification_id)
        return DeliveryResult(success=self.success, channel=self.channel)

    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY)


def request(**changes):
    data = {
        "notification_type": "test.safety",
        "intent": "SAFETY",
        "title": "Test",
        "message": "Test",
        "source": "test",
        "autonomy_context": {"agent_id": str(uuid4()), "autonomy_mode": "LIVE"},
        "idempotency_key": "key",
    }
    data.update(changes)
    return SendNotificationRequest(**data)


@pytest.fixture
def setup(tmp_path):
    from notification.policies import PolicyRegistry, configure_policy_registry
    from notification.rate_limiting import configure_rate_limiter

    configure_rate_limiter({})
    configure_policy_registry(registry=PolicyRegistry())
    adapter = RecordingAdapter()
    registry = SimpleAdapterRegistry()
    registry.register(adapter)
    url = f"sqlite:///{tmp_path}/runtime.db"
    runtime = Runtime(url, adapters=registry, create_tables=True)
    return runtime, adapter, url, registry


@pytest.mark.asyncio
async def test_acceptance_survives_restart_then_dispatches(setup):
    runtime, adapter, url, registry = setup
    accepted = runtime.accept(request(), principal="operator")
    assert accepted.status == DeliveryStatus.PENDING
    assert not adapter.calls
    assert runtime.get(accepted.notification_id)["deadline"] is None
    restarted = Runtime(url, adapters=registry)
    await restarted.run_once()
    assert adapter.calls == [accepted.notification_id]
    state = restarted.get(accepted.notification_id)
    assert state["status"] == "DELIVERED"
    assert state["ack_status"] == "PENDING"
    assert state["deadline"] > state["delivered_at"]
    result = restarted.acknowledge(accepted.notification_id, actor="operator")
    assert result.ack_status == AckStatus.ACKED
    assert restarted.acknowledge(accepted.notification_id, actor="operator") == result
    with pytest.raises(Conflict):
        restarted.acknowledge(accepted.notification_id, actor="operator", dismiss=True)


def test_concurrent_idempotency_is_scoped_and_payload_bound(setup):
    runtime, _, url, registry = setup
    payload = request()
    other = Runtime(url, adapters=registry)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda i: (runtime if i % 2 else other).accept(payload, principal="p"), range(8)
            )
        )
    assert len({r.notification_id for r in responses}) == 1
    with pytest.raises(Conflict):
        runtime.accept(payload.model_copy(update={"message": "changed"}), principal="p")
    assert runtime.accept(payload, principal="q").notification_id != responses[0].notification_id


@pytest.mark.asyncio
async def test_websocket_cannot_satisfy_guaranteed_and_failure_is_durable(setup):
    runtime, adapter, url, registry = setup
    adapter.success = False
    registry.register(RecordingAdapter(Channel.WEBSOCKET))
    runtime.max_attempts = 1
    result = await runtime.send(request(), principal="p")
    assert result.status == DeliveryStatus.FAILED
    state = Runtime(url).get(result.notification_id)
    assert state["dead_letter"] is True
    assert state["deadline"] is None
    assert state["ack_status"] is None


@pytest.mark.asyncio
async def test_deadline_and_terminal_race_are_persisted(setup):
    runtime, _, url, registry = setup
    result = await runtime.send(request(), principal="p")
    state = runtime.get(result.notification_id)
    runtime.expire(now=state["deadline"] + 1)
    assert Runtime(url).get(result.notification_id)["ack_status"] == "TIMED_OUT"
    with pytest.raises(Conflict):
        runtime.acknowledge(result.notification_id, actor="p")
    runtime.expire(now=state["deadline"] + 2)
    assert len([e for e in runtime.events(result.notification_id) if e["kind"] == "TIMED_OUT"]) == 1


def test_guaranteed_websocket_only_is_rejected(setup):
    runtime, _, _, _ = setup
    with pytest.raises(ValueError, match="persistent"):
        runtime.accept(
            request(autonomy_context={"agent_id": str(uuid4()), "autonomy_mode": "PREVIEW"}),
            principal="p",
        )


@pytest.mark.asyncio
async def test_http_sdk_mcp_share_identity_and_actual_delivery(setup):
    from fastapi.testclient import TestClient

    from agsignal.app import create_app
    from agsignal_mcp.runtime import MCPRuntimeConfig, RuntimeState
    from agsignal_mcp.tools import SendSignalInput, send_signal
    from uns.client import Client

    runtime, adapter, _, _ = setup
    payload = request()
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.agsignal_api_key = "local-test"
    app.state.agsignal_api_principal = "p"
    client = TestClient(app, headers={"Authorization": "Bearer local-test"})
    received = client.post("/api/v1/notifications", json=payload.model_dump(mode="json"))
    assert received.status_code == 202, received.text
    assert received.json()["status"] == "DELIVERED"
    sdk_result = await Client(runtime, principal="p").send(payload)
    assert sdk_result.idempotent_replay
    state = RuntimeState(runtime=runtime, audit_store=runtime.audit_store)
    mcp_payload = SendSignalInput(
        **payload.model_dump(mode="json"), deliver=True, operator_intent="deliver"
    )
    mcp_result = await send_signal(
        mcp_payload,
        runtime_state=state,
        config=MCPRuntimeConfig(
            read_only=False, require_delivery_confirmation=False, operator_principal="p"
        ),
    )
    assert mcp_result["notification_id"] == received.json()["notification_id"]
    assert mcp_result["idempotent_replay"]
    assert len(adapter.calls) == 1
    denied = client.post(
        f"/api/v1/notifications/{sdk_result.notification_id}/ack", json={"acked_by": "imposter"}
    )
    assert denied.status_code == 403
    ack = client.post(f"/api/v1/notifications/{sdk_result.notification_id}/ack", json={})
    assert ack.json()["acked_by"] == "p"


def test_accept_audit_failure_rolls_back_work_and_idempotency(setup, monkeypatch):
    from sqlalchemy import select

    from uns.runtime import work

    runtime, _, _, _ = setup

    def fail(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(runtime, "_audit", fail)
    with pytest.raises(RuntimeError, match="audit storage"):
        runtime.accept(request(), principal="p")
    with runtime.sessions() as session:
        assert session.execute(select(work)).first() is None


@pytest.mark.asyncio
async def test_expired_lease_recovers_with_ambiguity_evidence(setup):
    from sqlalchemy import update

    from uns.runtime import work

    runtime, adapter, _, _ = setup
    accepted = runtime.accept(request(), principal="p")
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(accepted.notification_id))
            .values(attempts=1, lease_token="crashed", lease_until=runtime.clock() - 1)
        )
    await runtime.run_once()
    event = next(
        e for e in runtime.events(accepted.notification_id) if e["kind"] == "ATTEMPT_STARTED"
    )
    assert event["payload"]["recovery_may_repeat_provider_effect"]
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_two_workers_and_terminal_response_race(setup):
    import asyncio

    runtime, adapter, url, registry = setup
    second = Runtime(url, adapters=registry)
    accepted = runtime.accept(request(), principal="p")
    await asyncio.gather(
        runtime.dispatch(accepted.notification_id), second.dispatch(accepted.notification_id)
    )
    assert len(adapter.calls) == 1

    def respond(dismiss):
        try:
            return runtime.acknowledge(accepted.notification_id, actor="p", dismiss=dismiss)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(respond, [True, False]))
    assert sum(r is not None for r in results) == 1


@pytest.mark.asyncio
async def test_simulation_has_no_side_effects_and_defaults_are_attributed(setup):
    from sqlalchemy import select

    from uns.client import Client
    from uns.runtime import work

    runtime, adapter, _, _ = setup
    payload = request()
    await Client(runtime, principal="p").simulate(payload)
    with runtime.sessions() as session:
        assert session.execute(select(work)).first() is None
    response = await runtime.send(payload, principal="p")
    n = runtime.get(response.notification_id)["notification"]
    assert n["policy_config_id"] and n["policy_config_hash"] and n["policy_evaluation_id"]
    assert n["metadata"]["uns_resolution"]["effective_hash"]


def test_policy_reload_failure_keeps_registry_and_database(setup, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from agsignal.app import create_app
    from db.models import PersistedNotificationPolicy

    runtime, _, _, _ = setup
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.agsignal_api_key = "key"
    app.state.agsignal_api_principal = "p"
    client = TestClient(app, headers={"Authorization": "Bearer key"})
    path = tmp_path / "policies"
    path.mkdir()
    (path / "a.yaml").write_text(
        "notification_type: test.one\nstatus: ACTIVE\ndelivery_mode: BEST_EFFORT\n"
    )
    (path / "b.yaml").write_text(
        "notification_type: test.two\nstatus: ACTIVE\ndelivery_mode: BEST_EFFORT\n"
    )
    before = runtime.policy_runtime.registry().get_all()
    original = app.state.policy_store._save_policy
    count = 0

    def fail_second(session, policy):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("persistence failure")
        return original(session, policy)

    monkeypatch.setattr(app.state.policy_store, "_save_policy", fail_second)
    with pytest.raises(RuntimeError, match="persistence failure"):
        client.post("/api/v1/policies/reload", json={"policy_dir": str(path)})
    assert runtime.policy_runtime.registry().get_all() == before
    with runtime.sessions() as session:
        assert session.execute(select(PersistedNotificationPolicy)).first() is None
    monkeypatch.setattr(app.state.policy_store, "_save_policy", original)
    response = client.post("/api/v1/policies/reload", json={"policy_dir": str(path)})
    assert response.status_code == 200, response.text
    assert runtime.policy_runtime.registry().get_sync("test.one")


@pytest.mark.asyncio
async def test_callback_failure_does_not_rewrite_terminal_state(setup):
    runtime, _, url, registry = setup
    calls = []

    async def callback(event):
        calls.append(event["id"])
        if len(calls) == 1:
            raise RuntimeError("callback unavailable")

    runtime.callback = callback
    response = await runtime.send(request(), principal="p")
    runtime.acknowledge(response.notification_id, actor="p")
    await runtime.deliver_callbacks()
    assert runtime.get(response.notification_id)["ack_status"] == "ACKED"
    event = runtime.events(response.notification_id)[-1]
    assert event["callback_error"]
    restarted = Runtime(
        url, adapters=registry, callback=callback, clock=lambda: runtime.clock() + 10
    )
    await restarted.deliver_callbacks()
    assert len(calls) == 2 and calls[0] == calls[1]
    assert restarted.events(response.notification_id)[-1]["callback_pending"] is False


@pytest.mark.asyncio
async def test_crash_after_provider_success_retains_ambiguity_and_recovers(setup, monkeypatch):
    runtime, adapter, url, registry = setup
    accepted = runtime.accept(request(), principal="p")
    original = runtime._audit
    monkeypatch.setattr(
        runtime,
        "_audit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("commit interrupted")),
    )
    with pytest.raises(RuntimeError, match="commit interrupted"):
        await runtime.dispatch(accepted.notification_id)
    assert len(adapter.calls) == 1
    assert runtime.get(accepted.notification_id)["status"] == "PENDING"
    monkeypatch.setattr(runtime, "_audit", original)
    recovered = Runtime(url, adapters=registry, clock=lambda: runtime.clock() + 70)
    await recovered.run_once()
    assert len(adapter.calls) == 2
    assert recovered.get(accepted.notification_id)["status"] == "DELIVERED"


@pytest.mark.asyncio
async def test_ack_audit_failure_rolls_back_terminal_transition(setup, monkeypatch):
    runtime, _, _, _ = setup
    response = await runtime.send(request(), principal="p")

    def fail(*args, **kwargs):
        raise RuntimeError("event commit failed")

    monkeypatch.setattr(runtime, "_event", fail)
    with pytest.raises(RuntimeError, match="event commit failed"):
        runtime.acknowledge(response.notification_id, actor="p")
    assert runtime.get(response.notification_id)["ack_status"] == "PENDING"
    assert not runtime.audit_store.get_ack_audits_for_notification(response.notification_id)


@pytest.mark.asyncio
async def test_preview_best_effort_and_override_provenance(setup):
    runtime, _, _, registry = setup
    registry.register(RecordingAdapter(Channel.WEBSOCKET))
    payload = request(
        delivery_mode="BEST_EFFORT",
        require_ack=False,
        autonomy_context={"agent_id": str(uuid4()), "autonomy_mode": "PREVIEW"},
    )
    response = await runtime.send(payload, principal="p")
    assert response.status == DeliveryStatus.DELIVERED
    state = runtime.get(response.notification_id)
    resolution = state["notification"]["metadata"]["uns_resolution"]
    assert resolution["overrides"]["delivery_mode"] == "BEST_EFFORT"
    assert resolution["effective"]["channels"] == ["WEBSOCKET"]
    assert state["ack_status"] is None


@pytest.mark.asyncio
async def test_console_projects_policy_delivery_and_response(setup):
    from fastapi.testclient import TestClient

    from agsignal.app import create_app

    runtime, _, _, _ = setup
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.agsignal_api_key = "test-console-key"
    app.state.agsignal_api_principal = "p"
    client = TestClient(app, headers={"Authorization": "Bearer test-console-key"})
    response = await runtime.send(request(), principal="p")
    runtime.acknowledge(response.notification_id, actor="p")
    result = client.get(f"/ui/deliveries/{response.notification_id}")
    assert result.status_code == 200, result.text
    state = result.json()["runtime_state"]
    assert state["delivery_status"] == "DELIVERED"
    assert state["ack_status"] == "ACKED"
    assert state["policy_config_hash"] and state["policy_evaluation_id"]
    assert state["deadline"] and not state["dead_letter"]

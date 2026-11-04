"""Audit reproductions. Passing assertions demonstrate current defects, not fixes.

Run: .venv/bin/python -m pytest verification/mpdd-2026-11-03/test_audit_probes.py -q
All databases and provider effects are synthetic and local to pytest tmp_path.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from notification.adapters.base import BaseAdapter, DeliveryResult
from notification.adapters.pagerduty import PagerDutyAdapter, PagerDutyConfig
from notification.models import Channel, DeliveryMode, Notification, NotificationIntent
from notification.policies import NotificationPolicy, PolicyStatus
from notification.policy_learning import DeltaState
from notification.service import SimpleAdapterRegistry
from uns.app import create_app
from uns.governance import (
    ApprovalStatus,
    Condition,
    Decision,
    GovernanceApprovalBridge,
    Operator,
    Policy,
    Rule,
    ThenClause,
    decide,
)
from uns.responses import SendNotificationRequest
from uns.runtime import Runtime
from uns.shadow_evaluator import config_dict_to_policy, policy_to_config_dict
from uns_mcp.factory import create_mcp_server
from uns_mcp.runtime import MCPRuntimeConfig


class SyntheticAdapter(BaseAdapter):
    channel = Channel.SLACK

    async def deliver(self, notification):
        return DeliveryResult(
            success=True, channel=self.channel, message_id=str(notification.notification_id)
        )

    async def health_check(self):
        return True


def request(kind="tenant-b.alert", source="team-b", **kwargs):
    return SendNotificationRequest(
        notification_type=kind,
        source=source,
        intent=NotificationIntent.OPERATIONAL,
        title="Synthetic private event",
        message="synthetic-team-b-marker",
        autonomy_context={"agent_id": uuid4(), "autonomy_mode": "LIVE"},
        **kwargs,
    )


@pytest.fixture(
    params=["sqlite", "postgres"] if os.getenv("UNS_AUDIT_DATABASE_URL") else ["sqlite"]
)
def runtime(tmp_path, request):
    schema = None
    owner = None
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    if request.param == "postgres":
        owner = create_engine(os.environ["UNS_AUDIT_DATABASE_URL"])
        schema = f"audit_{uuid4().hex}"
        with owner.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = (
            make_url(os.environ["UNS_AUDIT_DATABASE_URL"])
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
    adapters = SimpleAdapterRegistry()
    adapters.register(SyntheticAdapter())
    rt = None
    try:
        rt = Runtime(url, create_tables=True, adapters=adapters, shadow_min_samples=1)
        yield rt
    finally:
        if rt is not None:
            rt.engine.dispose()
        if owner is not None:
            with owner.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            owner.dispose()


def scoped_client(runtime):
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_scoped_api_keys = json.dumps(
        [
            {
                "key": "synthetic-a-observer",
                "principal": "tenant-a-observer",
                "role": "observer",
                "allowed_sources": ["team-a"],
                "allowed_namespaces": ["tenant-a.*"],
            }
        ]
    )
    return TestClient(app), {"Authorization": "Bearer synthetic-a-observer"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/runtime/notifications/{id}",
        "/api/v1/notifications/{id}/delivery",
        "/ui/audit",
    ],
)
def test_scoped_http_reads_disclose_other_namespace(runtime, path):
    sent = asyncio.run(runtime.send(request(), principal="synthetic-producer"))
    client, headers = scoped_client(runtime)
    # Control: the canonical status path correctly rejects this same key.
    assert (
        client.get(f"/api/v1/notifications/{sent.notification_id}", headers=headers).status_code
        == 403
    )
    result = client.get(path.format(id=sent.notification_id), headers=headers)
    assert result.status_code == 200
    assert str(sent.notification_id) in result.text


@pytest.mark.parametrize("path", ["/ui/deliveries", "/ui/deliveries/{id}"])
def test_ui_reads_ignore_source_bounds(runtime, path):
    sent = asyncio.run(runtime.send(request(kind="tenant-a.alert"), principal="synthetic-producer"))
    client, headers = scoped_client(runtime)
    assert (
        client.get(f"/api/v1/notifications/{sent.notification_id}", headers=headers).status_code
        == 403
    )
    result = client.get(path.format(id=sent.notification_id), headers=headers)
    assert result.status_code == 200
    assert str(sent.notification_id) in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    [
        "get_notification_status",
        "get_ack_status",
        "get_delivery_status",
        "list_audit_events",
    ],
)
async def test_registered_mcp_reads_ignore_configured_bounds(runtime, tool_name):
    sent = await runtime.send(request(), principal="synthetic-producer")
    server = create_mcp_server(
        MCPRuntimeConfig(
            allowed_sources=frozenset({"team-a"}),
            allowed_namespaces=frozenset({"tenant-a.*"}),
        ),
        runtime=runtime,
    )
    args = {} if tool_name.startswith("list_") else {"notification_id": str(sent.notification_id)}
    result = await server._tool_manager.call_tool(tool_name, args)
    assert str(sent.notification_id) in str(result)


def approval_decision(**kwargs):
    policy = Policy(
        id="synthetic-gate",
        version="1",
        context_schema="synthetic",
        rules=[
            Rule(
                id="review",
                when=[Condition(field="needs_review", operator=Operator.EQ, value=True)],
                then=ThenClause(
                    decision=Decision.REQUIRE_APPROVAL, target_reviewer_role="risk-officer"
                ),
            )
        ],
    )
    return decide(policy, {"needs_review": True}, subject_id="shared-agent", **kwargs)


def test_approval_identity_reused_across_tenant_and_resource(runtime):
    first = approval_decision(tenant_id="tenant-a", resource_id="action-1")
    second = approval_decision(tenant_id="tenant-b", resource_id="action-2")
    assert first.decision_id == second.decision_id
    bridge = GovernanceApprovalBridge(runtime=runtime)
    original = bridge.request_approval(first)
    asyncio.run(runtime.dispatch(original.notification_id))
    bridge.resolve_approval(first.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer-a")
    reused = bridge.request_approval(second)
    assert reused.status == ApprovalStatus.APPROVED
    assert reused.decision_record.tenant_id == "tenant-a"
    assert reused.decision_record.resource_id == "action-1"
    assert reused.notification_id == original.notification_id


def test_terminal_callback_failure_is_not_retried(runtime):
    called = []

    def unavailable_callback(record):
        called.append(record.approval_id)
        raise OSError("synthetic callback unavailable")

    bridge = GovernanceApprovalBridge(runtime=runtime, on_settled=unavailable_callback)
    record = approval_decision()
    original = bridge.request_approval(record)
    asyncio.run(runtime.dispatch(original.notification_id))
    with pytest.raises(OSError):
        bridge.resolve_approval(
            record.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer"
        )
    result = bridge.resolve_approval(
        record.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer"
    )
    assert result.status == ApprovalStatus.APPROVED
    assert len(called) == 1


def test_shadow_candidate_cache_misses_other_process_writes(runtime):
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="tenant-a.alert",
            version="1",
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            ack_timeout_minutes=10,
        )
    )
    peer = Runtime(runtime.database_url, shadow_min_samples=1)
    try:
        # Cache "no candidates" on the first worker before the peer creates one.
        assert runtime.shadow_evaluator.evaluate_intake(request(kind="tenant-a.alert")) == []
        delta = peer.shadow_evaluator.propose_delta(
            policy_type="tenant-a.alert",
            field_path="ack_timeout_minutes",
            proposed_value=20,
            reasoning="Synthetic peer proposal",
            actor="operator",
            promote_to_shadow=True,
        )
        runtime.policy_runtime.refresh_snapshot()
        # A local store can see the peer's candidate, but the negative cache cannot.
        assert runtime.learning_store.get_delta(delta.delta_id) is not None
        assert runtime.shadow_evaluator.evaluate_intake(request(kind="tenant-a.alert")) == []
        assert peer.shadow_evaluator.evaluate_intake(request(kind="tenant-a.alert"))
    finally:
        peer.engine.dispose()


def test_zero_dedup_window_is_silently_replaced():
    original = NotificationPolicy(
        notification_type="tenant-a.alert", channels=[Channel.SLACK], dedup_window_seconds=0
    )
    hydrated = config_dict_to_policy(
        policy_to_config_dict(original, original.notification_type),
        version="2",
        status=PolicyStatus.PREVIEW,
    )
    assert original.dedup_window_seconds == 0
    assert hydrated.dedup_window_seconds == 300


def test_pagerduty_provider_key_collides_across_isolated_intake(runtime):
    first = runtime.accept(request(dedup_key="same-producer-key"), principal="tenant-a")
    second = runtime.accept(request(dedup_key="same-producer-key"), principal="tenant-b")
    a, b = runtime.get(first.notification_id), runtime.get(second.notification_id)
    assert a["dedup_key"] != b["dedup_key"]
    adapter = PagerDutyAdapter(PagerDutyConfig(routing_key="synthetic-no-network"))
    assert adapter._get_dedup_key(
        Notification.model_validate(a["notification"])
    ) == adapter._get_dedup_key(Notification.model_validate(b["notification"]))


@pytest.mark.asyncio
async def test_signed_pagerduty_callback_settles_wrong_tenant_on_key_collision(
    runtime, monkeypatch
):
    secret = "synthetic-webhook-secret"
    monkeypatch.setenv("UNS_PAGERDUTY_WEBHOOK_SECRET", secret)
    adapter = PagerDutyAdapter(PagerDutyConfig(routing_key="synthetic-no-network"))

    async def local_provider(**kwargs):
        return {"status": "success", "dedup_key": kwargs["dedup_key"]}

    monkeypatch.setattr(adapter._client, "send_event", local_provider)
    runtime.adapters.register(adapter)
    for kind in ("tenant-a.alert", "tenant-b.alert"):
        runtime.policy_runtime.store.save_policy(
            NotificationPolicy(
                notification_type=kind,
                channels=[Channel.PAGERDUTY],
                delivery_mode=DeliveryMode.GUARANTEED,
                require_ack=True,
                ack_timeout_minutes=15,
            )
        )
    first = await runtime.send(
        request(kind="tenant-a.alert", source="team-a", dedup_key="shared"), principal="tenant-a"
    )
    second = await runtime.send(
        request(kind="tenant-b.alert", source="team-b", dedup_key="shared"), principal="tenant-b"
    )
    body = json.dumps(
        {
            "event": {
                "event_type": "incident.acknowledged",
                "agent": {"id": "tenant-a-reviewer"},
                "data": {"incident_key": "uns-shared"},
            }
        }
    ).encode()
    signature = "v1=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    client = TestClient(create_app(runtime=runtime, skip_persistence_config=True))
    result = client.post(
        "/api/v1/webhooks/pagerduty",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PagerDuty-Signature": signature,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["notification_id"] == str(second.notification_id)
    assert runtime.get(second.notification_id)["ack_status"] == "ACKED"
    assert runtime.get(first.notification_id)["ack_status"] == "PENDING"


def baseline(runtime):
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="tenant-a.alert",
            version="1",
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            ack_timeout_minutes=10,
            dedup_window_seconds=60,
        )
    )


def test_producer_can_bypass_admin_shadow_promotion_endpoint(runtime):
    baseline(runtime)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_producer_api_key = "synthetic-producer-key"
    client = TestClient(app)
    headers = {"Authorization": "Bearer synthetic-producer-key"}
    response = client.post(
        "/api/v1/policies/proposals",
        headers=headers,
        json={
            "policy_type": "tenant-a.alert",
            "field_path": "ack_timeout_minutes",
            "proposed_value": 20,
            "reasoning": "Synthetic proposal",
            "promote_to_shadow": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "SHADOW"
    delta_id = response.json()["delta_id"]
    assert (
        client.post(
            f"/api/v1/policies/proposals/{delta_id}/shadow", headers=headers, json={}
        ).status_code
        == 403
    )
    assert runtime.policy_runtime.store.list_revisions(status=PolicyStatus.PREVIEW)


def test_activate_older_delta_activates_different_approved_candidate(runtime):
    baseline(runtime)
    evaluator = runtime.shadow_evaluator
    delta_a = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=20,
        reasoning="Candidate A",
        actor="operator",
        promote_to_shadow=True,
    )
    delta_b = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="dedup_window_seconds",
        proposed_value=120,
        reasoning="Candidate B",
        actor="operator",
        promote_to_shadow=True,
    )
    assert len(evaluator.evaluate_intake(request(kind="tenant-a.alert"))) == 2
    evaluator.approve_to_draft(delta_a.delta_id, actor="operator")
    evaluator.approve_to_draft(delta_b.delta_id, actor="operator")
    _, activated, applied = evaluator.activate_draft(delta_id=delta_a.delta_id, actor="operator")
    # Asked to apply A's timeout change; B's dedup change is activated instead.
    assert activated.ack_timeout_minutes == 10
    assert activated.dedup_window_seconds == 120
    assert applied.delta_id == delta_a.delta_id
    assert applied.state == DeltaState.APPLIED


def test_failed_preview_persistence_leaves_shadow_state_committed(runtime, monkeypatch):
    baseline(runtime)
    evaluator = runtime.shadow_evaluator
    delta = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=20,
        reasoning="Synthetic storage failure",
        actor="operator",
    )

    def unavailable_store(*args, **kwargs):
        raise OSError("synthetic policy-store write failure")

    monkeypatch.setattr(evaluator.policy_store, "save_policy", unavailable_store)
    with pytest.raises(OSError):
        evaluator.promote_to_shadow(delta.delta_id, actor="operator")
    assert evaluator.learning_store.get_delta(delta.delta_id).state == DeltaState.SHADOW
    assert evaluator.policy_store.list_revisions(status=PolicyStatus.PREVIEW) == []
    with pytest.raises(ValueError):
        evaluator.promote_to_shadow(delta.delta_id, actor="operator")


@pytest.mark.asyncio
async def test_slo_certifies_with_two_samples_and_two_week_stalled_backlog(tmp_path):
    from uns.slo import compute_slo_report

    now = 1_800_000_000.0
    current = [now - 14 * 86400]
    url = f"sqlite:///{tmp_path / 'slo.db'}"
    adapters = SimpleAdapterRegistry()
    adapters.register(SyntheticAdapter())
    rt = Runtime(url, create_tables=True, adapters=adapters, clock=lambda: current[0])
    try:
        rt.accept(request(dedup_key="stalled"), principal="synthetic-producer")
        await rt.send(request(dedup_key="first"), principal="synthetic-producer")
        current[0] = now
        await rt.send(request(dedup_key="last"), principal="synthetic-producer")
        report = compute_slo_report(url, now_epoch=now)
        assert report["operational_gauges"]["pending_count"] == 1
        assert report["operational_gauges"]["oldest_pending_age_seconds"] == 14 * 86400
        assert report["provider_classification"]["live_provider_attempts"] == 2
        assert report["v1_0_certified"] is True
    finally:
        rt.engine.dispose()


def test_anonymous_unknown_paths_allocate_permanent_metric_series(runtime):
    from notification.metrics import http_request_duration_seconds, http_requests_total

    client = TestClient(create_app(runtime=runtime, skip_persistence_config=True))
    prefix = f"/synthetic-unmatched-{uuid4().hex}"
    for i in range(20):
        assert client.get(f"{prefix}/{i}").status_code == 404
    counters = [key for key in http_requests_total._metrics if key[1].startswith(prefix)]
    histograms = [
        key for key in http_request_duration_seconds._metrics if key[1].startswith(prefix)
    ]
    assert len(counters) == 20
    assert len(histograms) == 20


def test_readiness_failure_uses_http_200(runtime, monkeypatch):
    client, headers = scoped_client(runtime)

    def unavailable_progress():
        raise OSError("synthetic database unavailable")

    monkeypatch.setattr(runtime, "operational_progress", unavailable_progress)
    result = client.get("/readyz", headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "not_ready"


@pytest.mark.asyncio
async def test_channel_health_stays_healthy_after_repeated_delivery_failures(runtime):
    class FailingAdapter(SyntheticAdapter):
        async def deliver(self, notification):
            return DeliveryResult(success=False, channel=self.channel, error="synthetic outage")

    runtime.adapters.register(FailingAdapter())
    runtime.max_attempts = 1
    baseline(runtime)
    client, headers = scoped_client(runtime)
    for i in range(5):
        sent = await runtime.send(
            request(kind="tenant-a.alert", dedup_key=f"failure-{i}"), principal="synthetic-producer"
        )
        assert runtime.get(sent.notification_id)["dead_letter"] is True
    result = client.get("/api/v1/channels/health", headers=headers)
    assert result.status_code == 200
    slack = next(item for item in result.json()["channels"] if item["channel"] == "SLACK")
    assert slack["status"] == "HEALTHY"
    assert slack["consecutive_failures"] == 0

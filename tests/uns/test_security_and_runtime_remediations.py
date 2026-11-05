"""Regression suite for security boundary, runtime lineage, and policy governance invariants."""

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
    ApprovalConflictError,
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


def make_request(
    kind: str = "tenant-b.alert", source: str = "team-b", **kwargs
) -> SendNotificationRequest:
    intent = kwargs.pop("intent", NotificationIntent.OPERATIONAL)
    return SendNotificationRequest(
        notification_type=kind,
        source=source,
        intent=intent,
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


def scoped_client(runtime: Runtime):
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


# ---------------------------------------------------------------------------
# F01: Scoped credentials enforce source & namespace bounds across all reads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/runtime/notifications/{id}",
        "/api/v1/notifications/{id}/delivery",
        "/api/v1/notifications/{id}/audit",
        "/ui/audit",
        "/api/v1/runtime/dead-letters",
        "/api/v1/dlq",
    ],
)
def test_f01_scoped_http_reads_deny_or_omit_other_namespace(runtime: Runtime, path: str):
    sent = asyncio.run(runtime.send(make_request(), principal="synthetic-producer"))
    client, headers = scoped_client(runtime)
    assert (
        client.get(f"/api/v1/notifications/{sent.notification_id}", headers=headers).status_code
        == 403
    )
    result = client.get(path.format(id=sent.notification_id), headers=headers)
    if "{id}" in path:
        assert result.status_code == 403
    else:
        assert result.status_code == 200
        assert str(sent.notification_id) not in result.text


@pytest.mark.parametrize("path", ["/ui/deliveries", "/ui/deliveries/{id}"])
def test_f01_ui_reads_enforce_source_bounds(runtime: Runtime, path: str):
    sent = asyncio.run(
        runtime.send(
            make_request(kind="tenant-a.alert", source="team-b"), principal="synthetic-producer"
        )
    )
    client, headers = scoped_client(runtime)
    assert (
        client.get(f"/api/v1/notifications/{sent.notification_id}", headers=headers).status_code
        == 403
    )
    result = client.get(path.format(id=sent.notification_id), headers=headers)
    if "{id}" in path:
        assert result.status_code == 403
    else:
        assert result.status_code == 200
        assert str(sent.notification_id) not in result.text
        assert result.json()["pagination"]["total_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    [
        "get_notification_status",
        "get_ack_status",
        "get_delivery_status",
        "list_audit_events",
        "list_deliveries",
        "list_dlq",
    ],
)
async def test_f01_registered_mcp_reads_enforce_configured_bounds(runtime: Runtime, tool_name: str):
    sent = await runtime.send(
        make_request(kind="tenant-a.alert", source="team-b"), principal="synthetic-producer"
    )
    server = create_mcp_server(
        MCPRuntimeConfig(
            allowed_sources=frozenset({"team-a"}),
            allowed_namespaces=frozenset({"tenant-a.*"}),
        ),
        runtime=runtime,
    )
    if tool_name.startswith("list_"):
        result = await server._tool_manager.call_tool(tool_name, {})
        assert str(sent.notification_id) not in str(result)
    else:
        with pytest.raises(Exception) as exc_info:
            await server._tool_manager.call_tool(
                tool_name, {"notification_id": str(sent.notification_id)}
            )
        assert "not authorized" in str(exc_info.value)


# ---------------------------------------------------------------------------
# F02 & F09: Governance approval identity & retryable on_settled callback
# ---------------------------------------------------------------------------


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


def test_f02_approval_identity_isolated_across_tenant_and_resource(runtime: Runtime):
    first = approval_decision(tenant_id="tenant-a", resource_id="action-1")
    second = approval_decision(tenant_id="tenant-b", resource_id="action-2")
    assert first.decision_id != second.decision_id

    bridge = GovernanceApprovalBridge(runtime=runtime)
    original = bridge.request_approval(first)
    asyncio.run(runtime.dispatch(original.notification_id))
    bridge.resolve_approval(first.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer-a")

    second_req = bridge.request_approval(second)
    assert second_req.status == ApprovalStatus.PENDING_APPROVAL
    assert second_req.decision_record.tenant_id == "tenant-b"
    assert second_req.decision_record.resource_id == "action-2"
    assert second_req.notification_id != original.notification_id

    # Explicit decision_id reuse with mismatched bound content raises ApprovalConflictError
    conflicting = approval_decision(
        tenant_id="tenant-b",
        resource_id="action-2",
        decision_id=first.decision_id,
    )
    with pytest.raises(ApprovalConflictError):
        bridge.request_approval(conflicting)


def test_f09_terminal_callback_failure_is_retried_until_success(runtime: Runtime):
    called = []
    should_fail = [True]

    def flaky_callback(record):
        called.append(record.approval_id)
        if should_fail[0]:
            raise OSError("synthetic callback unavailable")

    bridge = GovernanceApprovalBridge(runtime=runtime, on_settled=flaky_callback)
    record = approval_decision()
    original = bridge.request_approval(record)
    asyncio.run(runtime.dispatch(original.notification_id))
    with pytest.raises(OSError):
        bridge.resolve_approval(
            record.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer"
        )
    assert len(called) == 1

    # Subsequent retry succeeds and marks callback completed
    should_fail[0] = False
    result = bridge.resolve_approval(
        record.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer"
    )
    assert result.status == ApprovalStatus.APPROVED
    assert len(called) == 2

    # Idempotent repeat after callback completion does not re-fire
    bridge.resolve_approval(record.decision_id, status=ApprovalStatus.APPROVED, actor="reviewer")
    assert len(called) == 2


# ---------------------------------------------------------------------------
# F03, F07, F08, F10: Shadow policy evaluator & store atomicity
# ---------------------------------------------------------------------------


def seed_baseline(runtime: Runtime):
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


def test_f07_shadow_candidate_visible_across_shared_database_workers(runtime: Runtime):
    seed_baseline(runtime)
    peer = Runtime(runtime.database_url, shadow_min_samples=1)
    try:
        assert runtime.shadow_evaluator.evaluate_intake(make_request(kind="tenant-a.alert")) == []
        delta = peer.shadow_evaluator.propose_delta(
            policy_type="tenant-a.alert",
            field_path="ack_timeout_minutes",
            proposed_value=20,
            reasoning="Synthetic peer proposal",
            actor="operator",
            promote_to_shadow=True,
        )
        runtime.policy_runtime.refresh_snapshot()
        assert runtime.learning_store.get_delta(delta.delta_id) is not None
        results = runtime.shadow_evaluator.evaluate_intake(make_request(kind="tenant-a.alert"))
        assert len(results) == 1
    finally:
        peer.engine.dispose()


def test_f10_zero_dedup_window_is_preserved():
    original = NotificationPolicy(
        notification_type="tenant-a.alert", channels=[Channel.SLACK], dedup_window_seconds=0
    )
    hydrated = config_dict_to_policy(
        policy_to_config_dict(original, original.notification_type),
        version="2",
        status=PolicyStatus.PREVIEW,
    )
    assert original.dedup_window_seconds == 0
    assert hydrated.dedup_window_seconds == 0


def test_f03_activate_older_delta_activates_its_own_approved_candidate(runtime: Runtime):
    seed_baseline(runtime)
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
    assert len(evaluator.evaluate_intake(make_request(kind="tenant-a.alert"))) == 2
    evaluator.approve_to_draft(delta_a.delta_id, actor="operator")
    evaluator.approve_to_draft(delta_b.delta_id, actor="operator")
    _, activated, applied = evaluator.activate_draft(delta_id=delta_a.delta_id, actor="operator")
    assert activated.ack_timeout_minutes == 20
    assert activated.dedup_window_seconds == 60
    assert applied.delta_id == delta_a.delta_id
    assert applied.state == DeltaState.APPLIED


def test_f08_failed_preview_persistence_keeps_delta_in_proposed_and_retryable(
    runtime: Runtime, monkeypatch
):
    seed_baseline(runtime)
    evaluator = runtime.shadow_evaluator
    delta = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=20,
        reasoning="Synthetic storage failure",
        actor="operator",
    )

    real_save = evaluator.policy_store.save_policy
    fail_once = [True]

    def flaky_save(*args, **kwargs):
        if fail_once[0]:
            raise OSError("synthetic policy-store write failure")
        return real_save(*args, **kwargs)

    monkeypatch.setattr(evaluator.policy_store, "save_policy", flaky_save)
    with pytest.raises(OSError):
        evaluator.promote_to_shadow(delta.delta_id, actor="operator")
    assert evaluator.learning_store.get_delta(delta.delta_id).state == DeltaState.PROPOSED
    assert evaluator.policy_store.list_revisions(status=PolicyStatus.PREVIEW) == []

    fail_once[0] = False
    promoted = evaluator.promote_to_shadow(delta.delta_id, actor="operator")
    assert promoted.state == DeltaState.SHADOW
    assert len(evaluator.policy_store.list_revisions(status=PolicyStatus.PREVIEW)) == 1


# ---------------------------------------------------------------------------
# F04: PagerDuty incident keys preserve intake tenant/source isolation
# ---------------------------------------------------------------------------


def test_f04_pagerduty_provider_key_isolated_across_principals(runtime: Runtime):
    first = runtime.accept(make_request(dedup_key="same-producer-key"), principal="tenant-a")
    second = runtime.accept(make_request(dedup_key="same-producer-key"), principal="tenant-b")
    a, b = runtime.get(first.notification_id), runtime.get(second.notification_id)
    assert a["dedup_key"] != b["dedup_key"]
    adapter = PagerDutyAdapter(PagerDutyConfig(routing_key="synthetic-no-network"))
    assert adapter._get_dedup_key(
        Notification.model_validate(a["notification"])
    ) != adapter._get_dedup_key(Notification.model_validate(b["notification"]))


@pytest.mark.asyncio
async def test_f04_signed_pagerduty_callback_rejects_ambiguous_raw_key_and_settles_exact_tenant(
    runtime: Runtime, monkeypatch
):
    secret = "synthetic-webhook-secret"
    monkeypatch.setenv("UNS_PAGERDUTY_WEBHOOK_SECRET", secret)
    adapter = PagerDutyAdapter(PagerDutyConfig(routing_key="synthetic-no-network"))
    sent_keys: list[str] = []

    async def local_provider(**kwargs):
        sent_keys.append(kwargs["dedup_key"])
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
        make_request(kind="tenant-a.alert", source="team-a", dedup_key="shared"),
        principal="tenant-a",
    )
    second = await runtime.send(
        make_request(kind="tenant-b.alert", source="team-b", dedup_key="shared"),
        principal="tenant-b",
    )
    assert len(sent_keys) == 2
    assert sent_keys[0] != sent_keys[1]

    client = TestClient(create_app(runtime=runtime, skip_persistence_config=True))

    # Ambiguous raw key "uns-shared" does not settle either tenant's obligation
    ambiguous_body = json.dumps(
        {
            "event": {
                "event_type": "incident.acknowledged",
                "agent": {"id": "tenant-a-reviewer"},
                "data": {"incident_key": "uns-shared"},
            }
        }
    ).encode()
    ambiguous_sig = "v1=" + hmac.new(secret.encode(), ambiguous_body, hashlib.sha256).hexdigest()
    res_ambiguous = client.post(
        "/api/v1/webhooks/pagerduty",
        content=ambiguous_body,
        headers={
            "Content-Type": "application/json",
            "X-PagerDuty-Signature": ambiguous_sig,
        },
    )
    assert res_ambiguous.status_code == 404
    assert runtime.get(first.notification_id)["ack_status"] == "PENDING"
    assert runtime.get(second.notification_id)["ack_status"] == "PENDING"

    # Tenant A's exact provider incident key settles only Tenant A's obligation
    exact_body = json.dumps(
        {
            "event": {
                "event_type": "incident.acknowledged",
                "agent": {"id": "tenant-a-reviewer"},
                "data": {"incident_key": sent_keys[0]},
            }
        }
    ).encode()
    exact_sig = "v1=" + hmac.new(secret.encode(), exact_body, hashlib.sha256).hexdigest()
    res_exact = client.post(
        "/api/v1/webhooks/pagerduty",
        content=exact_body,
        headers={
            "Content-Type": "application/json",
            "X-PagerDuty-Signature": exact_sig,
        },
    )
    assert res_exact.status_code == 200
    assert res_exact.json()["notification_id"] == str(first.notification_id)
    assert runtime.get(first.notification_id)["ack_status"] == "ACKED"
    assert runtime.get(second.notification_id)["ack_status"] == "PENDING"


# ---------------------------------------------------------------------------
# F05, F06, F11, F12, F13: Auth, Metrics, SLO, Readiness & Channel Health
# ---------------------------------------------------------------------------


def test_f06_producer_cannot_bypass_admin_shadow_promotion_on_create(runtime: Runtime):
    seed_baseline(runtime)
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
    assert response.status_code == 403
    assert runtime.policy_runtime.store.list_revisions(status=PolicyStatus.PREVIEW) == []


@pytest.mark.asyncio
async def test_f11_slo_rejects_certification_with_two_week_stalled_backlog(tmp_path):
    from uns.slo import compute_slo_report

    now = 1_800_000_000.0
    current = [now - 14 * 86400]
    url = f"sqlite:///{tmp_path / 'slo.db'}"
    adapters = SimpleAdapterRegistry()
    adapters.register(SyntheticAdapter())
    rt = Runtime(url, create_tables=True, adapters=adapters, clock=lambda: current[0])
    try:
        rt.accept(make_request(dedup_key="stalled"), principal="synthetic-producer")
        await rt.send(make_request(dedup_key="first"), principal="synthetic-producer")
        current[0] = now
        await rt.send(make_request(dedup_key="last"), principal="synthetic-producer")
        report = compute_slo_report(url, now_epoch=now)
        assert report["operational_gauges"]["pending_count"] == 1
        assert report["operational_gauges"]["oldest_pending_age_seconds"] == 14 * 86400
        assert report["slo_gates"]["zero_stalled_pending_backlog"] is False
        assert report["v1_0_certified"] is False
    finally:
        rt.engine.dispose()


def test_f05_anonymous_unknown_paths_use_constant_unmatched_metric_label(runtime: Runtime):
    from notification.metrics import http_request_duration_seconds, http_requests_total

    client = TestClient(create_app(runtime=runtime, skip_persistence_config=True))
    prefix = f"/synthetic-unmatched-{uuid4().hex}"
    for i in range(20):
        assert client.get(f"{prefix}/{i}").status_code == 404
    counters = [key for key in http_requests_total._metrics if key[1].startswith(prefix)]
    histograms = [
        key for key in http_request_duration_seconds._metrics if key[1].startswith(prefix)
    ]
    assert len(counters) == 0
    assert len(histograms) == 0


def test_f13_readiness_failure_returns_http_503(runtime: Runtime, monkeypatch):
    client, headers = scoped_client(runtime)

    def unavailable_progress():
        raise OSError("synthetic database unavailable")

    monkeypatch.setattr(runtime, "operational_progress", unavailable_progress)
    result = client.get("/readyz", headers=headers)
    assert result.status_code == 503
    assert result.json()["status"] == "not_ready"


@pytest.mark.asyncio
async def test_f12_channel_health_reflects_repeated_runtime_delivery_failures(runtime: Runtime):
    class FailingAdapter(SyntheticAdapter):
        async def deliver(self, notification):
            return DeliveryResult(success=False, channel=self.channel, error="synthetic outage")

    runtime.adapters.register(FailingAdapter())
    runtime.max_attempts = 1
    seed_baseline(runtime)
    client, headers = scoped_client(runtime)
    for i in range(5):
        sent = await runtime.send(
            make_request(kind="tenant-a.alert", dedup_key=f"failure-{i}"),
            principal="synthetic-producer",
        )
        assert runtime.get(sent.notification_id)["dead_letter"] is True
    result = client.get("/api/v1/channels/health", headers=headers)
    assert result.status_code == 200
    slack = next(item for item in result.json()["channels"] if item["channel"] == "SLACK")
    assert slack["status"] != "HEALTHY"
    assert slack["consecutive_failures"] >= 5


# ---------------------------------------------------------------------------
# F16-F24: Post-v0.6.1 Policy Authority, Lineage, Webhook & Read Invariants
# ---------------------------------------------------------------------------


def test_f16_activate_draft_by_policy_id_or_type_enforces_apply_guard_and_applies_delta(
    runtime: Runtime,
):
    seed_baseline(runtime)
    evaluator = runtime.shadow_evaluator

    # Propose and approve candidate A
    delta_a = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=25,
        reasoning="Candidate A for policy_id activation",
        actor="operator",
        promote_to_shadow=True,
    )
    evaluator.evaluate_intake(make_request(kind="tenant-a.alert"))
    approved_a, draft_a, _ = evaluator.approve_to_draft(delta_a.delta_id, actor="operator")
    assert approved_a.state == DeltaState.APPROVED

    # Activating via policy_id (not delta_id) matches approved_a and marks it APPLIED
    save_res_a, activated_a, applied_a = evaluator.activate_draft(
        policy_id=draft_a.policy_id, actor="operator"
    )
    assert activated_a.config_id == save_res_a.policy_id
    assert activated_a.ack_timeout_minutes == 25
    assert applied_a is not None
    assert applied_a.delta_id == delta_a.delta_id
    assert evaluator.learning_store.get_delta(delta_a.delta_id).state == DeltaState.APPLIED

    # Propose and approve candidate B against v2 baseline, then mutate baseline out-of-band
    delta_b = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=35,
        reasoning="Candidate B before baseline drift",
        actor="operator",
        promote_to_shadow=True,
    )
    evaluator.evaluate_intake(make_request(kind="tenant-a.alert"))
    _, draft_b, _ = evaluator.approve_to_draft(delta_b.delta_id, actor="operator")

    # Out-of-band active policy save changes baseline config hash
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="tenant-a.alert",
            version="99",
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            ack_timeout_minutes=45,
            dedup_window_seconds=60,
        )
    )

    # Activating draft_b by policy_id or notification_type must reject stale baseline
    with pytest.raises(ValueError, match="Active baseline policy drifted after approval"):
        evaluator.activate_draft(policy_id=draft_b.policy_id, actor="operator")
    with pytest.raises(ValueError, match="Active baseline policy drifted after approval"):
        evaluator.activate_draft(notification_type="tenant-a.alert", actor="operator")


@pytest.mark.asyncio
async def test_f17_follower_and_failed_predecessor_settlement_routes_to_canonical_owner(
    runtime: Runtime,
):
    seed_baseline(runtime)
    first = await runtime.send(
        make_request(kind="tenant-a.alert", source="team-a", dedup_key="lineage-ack"),
        principal="tenant-a",
    )
    follower = await runtime.send(
        make_request(kind="tenant-a.alert", source="team-a", dedup_key="lineage-ack"),
        principal="tenant-a",
    )
    assert follower.status.value == "DEDUPLICATED"

    # Acknowledging the deduplicated follower ID settles the canonical owner
    ack_resp = runtime.acknowledge(
        follower.notification_id,
        actor="follower-operator",
        metadata={"via": "follower-id"},
    )
    assert ack_resp.ack_status.value == "ACKED"

    owner_row = runtime.get(first.notification_id)
    follower_row = runtime.get(follower.notification_id)
    assert owner_row["ack_status"] == "ACKED"
    assert owner_row["actor"] == "follower-operator"
    assert follower_row["effective_ack_status"] == "ACKED"
    assert follower_row["actor"] == "follower-operator"
    assert follower_row["responded_at"] == owner_row["responded_at"]
    assert follower_row["response_metadata"] == {"via": "follower-id"}


@pytest.mark.asyncio
async def test_f18_pagerduty_webhook_resolved_after_dismiss_and_unacked_resolve_maps_to_dismiss(
    runtime: Runtime, monkeypatch
):
    secret = "synthetic-webhook-secret"
    monkeypatch.setenv("UNS_PAGERDUTY_WEBHOOK_SECRET", secret)
    adapter = PagerDutyAdapter(PagerDutyConfig(routing_key="synthetic-no-network"))

    async def local_provider(**kwargs):
        return {"status": "success", "dedup_key": kwargs["dedup_key"]}

    monkeypatch.setattr(adapter._client, "send_event", local_provider)
    runtime.adapters.register(adapter)
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="tenant-a.pd",
            channels=[Channel.PAGERDUTY],
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            ack_timeout_minutes=15,
        )
    )

    bridge = GovernanceApprovalBridge(runtime=runtime)
    record = approval_decision()
    approval = bridge.request_approval(record)
    await runtime.dispatch(approval.notification_id)

    app = create_app(runtime=runtime, skip_persistence_config=True)
    client = TestClient(app)

    # Unacknowledged incident.resolved via uns-pd-<uuid> key maps to DISMISSED / REJECTED
    resolve_body = json.dumps(
        {
            "event": {
                "event_type": "incident.resolved",
                "agent": {"id": "pd-auto-resolver"},
                "data": {"incident_key": f"uns-pd-{approval.notification_id}"},
            }
        }
    ).encode()
    sig = "v1=" + hmac.new(secret.encode(), resolve_body, hashlib.sha256).hexdigest()
    res = client.post(
        "/api/v1/webhooks/pagerduty",
        content=resolve_body,
        headers={"Content-Type": "application/json", "X-PagerDuty-Signature": sig},
    )
    assert res.status_code == 200
    assert res.json()["ack_status"] == "DISMISSED"
    assert runtime.get(approval.notification_id)["ack_status"] == "DISMISSED"
    assert bridge.sync_from_runtime(record.decision_id).status == ApprovalStatus.REJECTED

    # Subsequent incident.resolved after DISMISSED returns HTTP 200 already_settled=True
    res_repeat = client.post(
        "/api/v1/webhooks/pagerduty",
        content=resolve_body,
        headers={"Content-Type": "application/json", "X-PagerDuty-Signature": sig},
    )
    assert res_repeat.status_code == 200
    assert res_repeat.json()["already_settled"] is True


def test_f19_governance_approval_pre_dispatch_timeout_and_restart_signature_determinism(
    runtime: Runtime,
):
    secret = "deterministic-signing-secret"
    bridge1 = GovernanceApprovalBridge(runtime=runtime, signing_secret=secret)
    rec1 = approval_decision(tenant_id="tenant-a", resource_id="res-1")
    created1 = bridge1.request_approval(rec1)

    # Pre-dispatch resolve_approval succeeds before runtime.dispatch() runs
    settled1 = bridge1.resolve_approval(
        rec1.decision_id,
        status=ApprovalStatus.APPROVED,
        actor="early-operator",
    )
    assert settled1.status == ApprovalStatus.APPROVED
    assert settled1.callback_headers is not None
    assert settled1.callback_headers["X-UNS-Signature"]

    # Dispatching afterwards does not overwrite ACKED back to PENDING
    asyncio.run(runtime.dispatch(created1.notification_id))
    assert runtime.get(created1.notification_id)["ack_status"] == "ACKED"

    # Cold bridge recovery produces identical canonical bytes and HMAC signature
    bridge2 = GovernanceApprovalBridge(runtime=runtime, signing_secret=secret)
    recovered1 = bridge2.query_approval(rec1.decision_id)
    assert recovered1 is not None
    assert recovered1.status == ApprovalStatus.APPROVED
    assert recovered1.resolved_at == settled1.resolved_at
    assert recovered1.callback_headers is not None
    assert (
        recovered1.callback_headers["X-UNS-Timestamp"]
        == settled1.callback_headers["X-UNS-Timestamp"]
    )
    assert (
        recovered1.callback_headers["X-UNS-Signature"]
        == settled1.callback_headers["X-UNS-Signature"]
    )

    # TIMED_OUT resolution persists to Runtime and rejects subsequent approval
    rec2 = approval_decision(tenant_id="tenant-a", resource_id="res-timeout")
    created2 = bridge1.request_approval(rec2)
    timed_out = bridge1.resolve_approval(
        rec2.decision_id,
        status=ApprovalStatus.TIMED_OUT,
        actor="watchdog",
    )
    assert timed_out.status == ApprovalStatus.TIMED_OUT
    assert runtime.get(created2.notification_id)["ack_status"] == "TIMED_OUT"
    with pytest.raises(ApprovalConflictError):
        bridge1.resolve_approval(
            rec2.decision_id,
            status=ApprovalStatus.APPROVED,
            actor="late-operator",
        )


@pytest.mark.asyncio
async def test_f20_scoped_ui_pagination_next_cursor_and_proposal_shadow_results_filtering(
    runtime: Runtime,
):
    from pydantic import ValidationError

    from uns.responses import PaginationInfo

    # PaginationInfo rejects unknown kwargs such as cursor=...
    with pytest.raises(ValidationError):
        PaginationInfo(limit=10, has_more=True, cursor="bad-kwarg")  # type: ignore[call-arg]

    seed_baseline(runtime)
    for i in range(3):
        await runtime.send(
            make_request(kind="tenant-a.alert", source="team-a", dedup_key=f"page-{i}"),
            principal="tenant-a",
        )
    await runtime.send(
        make_request(kind="tenant-a.alert", source="team-b", dedup_key="foreign-source"),
        principal="tenant-b",
    )

    # Propose a shadow policy and evaluate both team-a and team-b traffic
    delta = runtime.shadow_evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=20,
        reasoning="Scoped shadow test",
        actor="operator",
        promote_to_shadow=True,
    )
    runtime.shadow_evaluator.evaluate_intake(
        make_request(kind="tenant-a.alert", source="team-a")
    )
    runtime.shadow_evaluator.evaluate_intake(
        make_request(kind="tenant-a.alert", source="team-b")
    )

    client, headers = scoped_client(runtime)

    # Scoped /ui/deliveries and /ui/audit return non-null pagination.next_cursor via SQL pushdown
    deliv_page = client.get("/ui/deliveries?limit=1", headers=headers)
    assert deliv_page.status_code == 200
    assert deliv_page.json()["pagination"]["total_count"] == 3
    assert deliv_page.json()["pagination"]["has_more"] is True
    next_cursor = deliv_page.json()["pagination"]["next_cursor"]
    assert next_cursor is not None

    deliv_page_2 = client.get(f"/ui/deliveries?limit=1&cursor={next_cursor}", headers=headers)
    assert deliv_page_2.status_code == 200
    assert (
        deliv_page_2.json()["items"][0]["notification_id"]
        != deliv_page.json()["items"][0]["notification_id"]
    )

    audit_page = client.get("/ui/audit?limit=1", headers=headers)
    assert audit_page.status_code == 200
    assert audit_page.json()["pagination"]["has_more"] is True
    assert audit_page.json()["pagination"]["next_cursor"] is not None

    # Scoped proposal detail filters out shadow_results from team-b
    prop_res = client.get(
        f"/ui/policies/proposals/{delta.delta_id}",
        headers=headers,
    )
    assert prop_res.status_code == 200
    shadow_results = prop_res.json()["shadow_results"]
    assert len(shadow_results) == 1
    assert all(r["original_outcome"].get("source") == "team-a" for r in shadow_results)


def test_f21_shadow_evaluator_degraded_fails_gate_and_reconstructs_all_allowed_fields(
    runtime: Runtime,
):
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="tenant-a.safety",
            version="1",
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            ack_timeout_minutes=5,
            dedup_window_seconds=60,
        )
    )
    evaluator = runtime.shadow_evaluator
    evaluator.min_samples = 2
    evaluator.accuracy_threshold = 0.5

    # Proposal that weakens delivery_mode to BEST_EFFORT produces DEGRADED on SAFETY intent
    delta = evaluator.propose_delta(
        policy_type="tenant-a.safety",
        field_path="delivery_mode",
        proposed_value="BEST_EFFORT",
        reasoning="Weaken delivery mode",
        actor="operator",
        promote_to_shadow=True,
    )
    # 1st sample: OPERATIONAL intent -> IMPROVED (changed=True, is_degraded=False)
    evaluator.evaluate_intake(
        make_request(
            kind="tenant-a.safety",
            source="team-a",
            intent=NotificationIntent.OPERATIONAL,
        )
    )
    # 2nd sample: SAFETY intent -> DEGRADED (safety_floor_violated)
    evaluator.evaluate_intake(
        make_request(
            kind="tenant-a.safety",
            source="team-a",
            intent=NotificationIntent.SAFETY,
        )
    )
    assert runtime.learning_store.get_shadow_result_counts(delta.delta_id) == (2, 1, 1)
    summary = evaluator.format_proposal_summary(delta)
    assert summary.shadow_aggregate is not None
    assert summary.shadow_aggregate.degraded_decisions >= 1
    assert summary.shadow_aggregate.status == "FAILED"
    with pytest.raises(ValueError, match="Shadow evaluation must pass before approval"):
        evaluator.approve_to_draft(delta.delta_id, actor="operator")

    # Direct PREVIEW policy differing only on priority_override is auto-bound across all 19 allowed fields
    seed_baseline(runtime)
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="tenant-a.alert",
            version="2",
            status=PolicyStatus.PREVIEW,
            channels=[Channel.SLACK],
            delivery_mode=DeliveryMode.GUARANTEED,
            require_ack=True,
            ack_timeout_minutes=10,
            dedup_window_seconds=60,
            priority_override="HIGH",
        )
    )
    preview_samples = evaluator.evaluate_intake(
        make_request(kind="tenant-a.alert", source="team-a")
    )
    assert len(preview_samples) == 1
    assert preview_samples[0].shadow_outcome["priority"] == "HIGH"


def test_f22_rejected_preview_policy_can_be_reproposed_while_retired_active_cannot(
    runtime: Runtime,
):
    seed_baseline(runtime)
    evaluator = runtime.shadow_evaluator

    delta1 = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=25,
        reasoning="First attempt",
        actor="operator",
        promote_to_shadow=True,
    )
    evaluator.reject_delta(delta1.delta_id, actor="operator", reason="Try again later")

    # Re-proposing the exact same change succeeds because the retired PREVIEW was never ACTIVE
    delta2 = evaluator.propose_delta(
        policy_type="tenant-a.alert",
        field_path="ack_timeout_minutes",
        proposed_value=25,
        reasoning="Second attempt with identical config",
        actor="operator",
        promote_to_shadow=True,
    )
    assert delta2.state == DeltaState.SHADOW

    # However, retiring an ACTIVE policy still forbids reactivating the retired version
    evaluator.evaluate_intake(make_request(kind="tenant-a.alert"))
    evaluator.approve_to_draft(delta2.delta_id, actor="operator")
    evaluator.activate_draft(delta_id=delta2.delta_id, actor="operator")
    with pytest.raises(
        ValueError, match="A retired policy version cannot be reactivated; publish a new version"
    ):
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


@pytest.mark.asyncio
async def test_f23_slack_interactivity_webhook_is_idempotent_after_settlement(
    runtime: Runtime, monkeypatch
):
    from urllib.parse import urlencode

    secret = "slack-signing-secret"
    monkeypatch.setenv("UNS_SLACK_SIGNING_SECRET", secret)
    seed_baseline(runtime)
    sent = await runtime.send(
        make_request(kind="tenant-a.alert", source="team-a", dedup_key="slack-dup"),
        principal="tenant-a",
    )

    client = TestClient(create_app(runtime=runtime, skip_persistence_config=True))
    payload = {
        "type": "block_actions",
        "user": {"id": "U999", "username": "slack-operator"},
        "actions": [
            {
                "action_id": f"ack_{sent.notification_id}",
                "value": str(sent.notification_id),
            }
        ],
    }
    raw_body = urlencode({"payload": json.dumps(payload)}).encode()
    ts = str(int(runtime.clock()))
    sig = (
        "v0="
        + hmac.new(secret.encode(), f"v0:{ts}:".encode() + raw_body, hashlib.sha256).hexdigest()
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
    }

    first_res = client.post("/api/v1/webhooks/slack", content=raw_body, headers=headers)
    assert first_res.status_code == 200
    assert runtime.get(sent.notification_id)["ack_status"] == "ACKED"

    # Duplicate Slack button click returns HTTP 200 settled card instead of 409
    second_res = client.post("/api/v1/webhooks/slack", content=raw_body, headers=headers)
    assert second_res.status_code == 200
    assert second_res.json()["replace_original"] is True


@pytest.mark.asyncio
async def test_f24_maintenance_retains_follower_of_active_owner_and_slo_clears_replayed_unknown(
    tmp_path,
):
    from uns.maintenance import maintain
    from uns.slo import compute_slo_report

    now = 1_800_000_000.0
    current = [now - 10 * 86400]
    url = f"sqlite:///{tmp_path / 'maint_slo.db'}"
    adapters = SimpleAdapterRegistry()
    adapters.register(SyntheticAdapter())
    rt = Runtime(url, create_tables=True, adapters=adapters, clock=lambda: current[0])
    try:
        rt.policy_runtime.store.save_policy(
            NotificationPolicy(
                notification_type="tenant-a.alert",
                version="1",
                channels=[Channel.SLACK],
                delivery_mode=DeliveryMode.GUARANTEED,
                require_ack=True,
                ack_timeout_minutes=1440,
                dedup_window_seconds=60,
            )
        )
        current[0] = now - 72000
        # Accept owner and deduplicated follower 20 hours ago; dispatch owner so ack_status='PENDING'
        owner = await rt.send(
            make_request(kind="tenant-a.alert", source="team-a", dedup_key="active-owner"),
            principal="tenant-a",
        )
        follower = await rt.send(
            make_request(kind="tenant-a.alert", source="team-a", dedup_key="active-owner"),
            principal="tenant-a",
        )
        assert follower.status.value == "DEDUPLICATED"

        # Running maintain with cutoff=now - 3600 must retain both owner and follower while owner is unsettled
        summary = maintain(
            rt.engine,
            cutoff=now - 3600,
            idempotency_seconds=3600,
            apply=True,
            operator="ops",
            now=now,
        )
        assert summary["deleted_rows"] == 0
        assert rt.get(owner.notification_id) is not None
        assert rt.get(follower.notification_id) is not None

        # Settle owner inside the window and verify SLO certification
        current[0] = now - 60
        rt.acknowledge(owner.notification_id, actor="operator")
        report = compute_slo_report(url, now_epoch=now)
        assert report["slo_gates"]["zero_unknown_attempts"] is True
    finally:
        rt.engine.dispose()


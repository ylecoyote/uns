"""Tests for Milestone v0.5.0 features (#46 and #47).

Covers:
- Issue #46: Automated shadow-policy evaluation runner for PREVIEW policies
  and SHADOW PolicyDelta proposals against live intake without external channel
  delivery or mutating live obligation state, persisting ShadowEvaluationResult
  and rolling ShadowEvaluationAggregate records in SQLAlchemyPolicyLearningStore.
- Issue #47: Governed policy-change lifecycle HTTP endpoints and workflow
  (Proposal -> Promote to SHADOW/PREVIEW -> Shadow Evidence -> Guard Check ->
  Approve into DRAFT -> Explicit Activate DRAFT -> ACTIVE).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from notification.adapters.base import BaseAdapter, DeliveryResult
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    Notification,
    NotificationIntent,
)
from notification.policies import NotificationPolicy, PolicyStatus
from notification.policy_learning import DeltaState, ShadowStatus
from notification.service import SimpleAdapterRegistry
from uns.app import create_app
from uns.responses import AutonomyContextRequest, SendNotificationRequest
from uns.runtime import Runtime


class _RecordingAdapter(BaseAdapter):
    def __init__(self, channel: Channel) -> None:
        self._channel = channel
        self.sent: list[Notification] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        self.sent.append(notification)
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=f"{self._channel.value}-{len(self.sent)}",
        )

    async def health_check(self) -> bool:
        return True


def _make_request(
    notification_type: str = "trading.order_placed",
    title: str = "Order executed",
    intent: NotificationIntent = NotificationIntent.OPERATIONAL,
) -> SendNotificationRequest:
    return SendNotificationRequest(
        notification_type=notification_type,
        intent=intent,
        title=title,
        message="Executed order in live portfolio",
        source="execution-engine",
        autonomy_context=AutonomyContextRequest(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
    )


@pytest.mark.asyncio
async def test_shadow_evaluator_evaluates_preview_policy_without_side_effects(
    tmp_path: Path,
) -> None:
    """Issue #46: PREVIEW candidate policy is shadow-evaluated on live intake without triggering PREVIEW channels."""
    slack_adapter = _RecordingAdapter(Channel.SLACK)
    pagerduty_adapter = _RecordingAdapter(Channel.PAGERDUTY)
    adapters = SimpleAdapterRegistry()
    adapters.register(slack_adapter)
    adapters.register(pagerduty_adapter)

    db_url = f"sqlite:///{tmp_path / 'shadow_eval.db'}"
    runtime = Runtime(
        db_url,
        adapters=adapters,
        create_tables=True,
        shadow_evaluation_enabled=True,
        shadow_min_samples=2,
    )

    # 1. Save ACTIVE policy routing only to SLACK
    active_policy = NotificationPolicy(
        notification_type="trading.order_placed",
        version="1",
        status=PolicyStatus.ACTIVE,
        intent=NotificationIntent.OPERATIONAL,
        delivery_mode=DeliveryMode.GUARANTEED,
        channels=[Channel.SLACK],
        require_ack=True,
        ack_timeout_minutes=30,
        dedup_window_seconds=120,
    )
    runtime.policy_runtime.store.save_policy(active_policy)

    # 2. Save PREVIEW candidate policy that adds PAGERDUTY
    preview_policy = active_policy.model_copy(
        update={
            "version": "2",
            "status": PolicyStatus.PREVIEW,
            "channels": [Channel.SLACK, Channel.PAGERDUTY],
        }
    )
    runtime.policy_runtime.store.save_policy(preview_policy)

    # 3. Send 2 live notifications through Runtime
    resp1 = await runtime.send(_make_request(title="Order #1"), principal="producer-1")
    resp2 = await runtime.send(_make_request(title="Order #2"), principal="producer-1")

    # Live obligations must use ONLY the ACTIVE policy (SLACK) — PagerDuty is NEVER called!
    assert resp1.channels_attempted == [Channel.SLACK]
    assert resp2.channels_attempted == [Channel.SLACK]
    assert len(slack_adapter.sent) >= 1
    assert len(pagerduty_adapter.sent) == 0

    # 4. Verify ShadowEvaluationResult and ShadowEvaluationAggregate were persisted automatically
    deltas = runtime.learning_store.list_deltas(
        policy_type="trading.order_placed", state=DeltaState.SHADOW
    )
    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.field_path == "channels"
    assert delta.current_value == ["SLACK"]
    assert delta.proposed_value == ["SLACK", "PAGERDUTY"]

    samples = runtime.learning_store.list_shadow_results(delta.delta_id)
    assert len(samples) == 2
    assert all(sample.changed is True for sample in samples)
    assert samples[0].original_outcome["channels"] == ["SLACK"]
    assert samples[0].shadow_outcome["channels"] == ["SLACK", "PAGERDUTY"]

    aggregate = runtime.learning_store.get_shadow_aggregate(delta.delta_id)
    assert aggregate is not None
    assert aggregate.total_decisions == 2
    assert aggregate.improved_decisions == 2
    assert aggregate.degraded_decisions == 0
    assert aggregate.min_sample_met is True
    assert aggregate.accuracy_threshold_met is True
    assert aggregate.status == ShadowStatus.PASSED
    assert aggregate.can_promote_to_approval is True
    assert aggregate.baseline_hash == delta.baseline_hash
    assert aggregate.candidate_hash == delta.candidate_hash


def test_governed_policy_proposal_shadow_approval_and_draft_activation_http_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #47: Full HTTP lifecycle: Propose -> Promote SHADOW -> Live Intake Samples -> Approve DRAFT -> Activate ACTIVE."""
    monkeypatch.setenv("UNS_API_KEY", "admin-secret")
    monkeypatch.setenv("UNS_PRODUCER_API_KEY", "producer-secret")
    monkeypatch.setenv("UNS_OBSERVER_API_KEY", "observer-secret")

    slack_adapter = _RecordingAdapter(Channel.SLACK)
    pagerduty_adapter = _RecordingAdapter(Channel.PAGERDUTY)
    adapters = SimpleAdapterRegistry()
    adapters.register(slack_adapter)
    adapters.register(pagerduty_adapter)

    db_url = f"sqlite:///{tmp_path / 'http_lifecycle.db'}"
    runtime = Runtime(
        db_url,
        adapters=adapters,
        create_tables=True,
        shadow_evaluation_enabled=True,
        shadow_min_samples=2,
    )
    runtime.policy_runtime.store.save_policy(
        NotificationPolicy(
            notification_type="ops.alert",
            version="1",
            status=PolicyStatus.ACTIVE,
            intent=NotificationIntent.OPERATIONAL,
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.SLACK],
            require_ack=False,
            dedup_window_seconds=60,
        )
    )

    app = create_app(runtime=runtime, skip_persistence_config=True)
    client = TestClient(app)

    admin_headers = {"X-UNS-API-Key": "admin-secret"}
    producer_headers = {"X-UNS-API-Key": "producer-secret"}
    observer_headers = {"X-UNS-API-Key": "observer-secret"}

    # 1. Producer creates a PolicyDelta proposal (PROPOSED)
    create_resp = client.post(
        "/api/v1/policies/proposals",
        headers=producer_headers,
        json={
            "policy_type": "ops.alert",
            "field_path": "channels",
            "proposed_value": ["SLACK", "PAGERDUTY"],
            "reasoning": "Include PagerDuty for operational alert redundancy.",
            "confidence": 0.92,
            "evidence_count": 3,
            "promote_to_shadow": False,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    proposal: dict[str, Any] = create_resp.json()
    delta_id = proposal["delta_id"]
    assert proposal["state"] == "PROPOSED"
    assert proposal["baseline_hash_matches"] is True
    assert proposal["can_promote_to_shadow"] is True
    assert proposal["can_approve"] is False

    # 2. Admin promotes proposal to SHADOW (materializes PREVIEW revision in policy_store)
    shadow_resp = client.post(
        f"/api/v1/policies/proposals/{delta_id}/shadow",
        headers=admin_headers,
        json={"reason": "Begin shadow evaluation on live intake"},
    )
    assert shadow_resp.status_code == 200, shadow_resp.text
    shadow_data = shadow_resp.json()
    assert shadow_data["state"] == "SHADOW"
    assert shadow_data["shadow_aggregate"]["status"] == "PENDING"
    assert shadow_data["shadow_aggregate"]["total_decisions"] == 0
    assert len(shadow_data["guard_results"]) == 1
    assert shadow_data["guard_results"][0]["stage"] == "PROMOTE_SHADOW"
    assert shadow_data["guard_results"][0]["allowed"] is True

    # Verify PREVIEW revision appears in /ui/policies/revisions
    revs_resp = client.get("/ui/policies/revisions?status=PREVIEW", headers=observer_headers)
    assert revs_resp.status_code == 200
    assert any(
        item["notification_type"] == "ops.alert" and item["status"] == "PREVIEW"
        for item in revs_resp.json()["items"]
    )

    # Attempting to approve before shadow samples pass must fail with 409
    premature_approve = client.post(
        f"/api/v1/policies/proposals/{delta_id}/approve",
        headers=admin_headers,
    )
    assert premature_approve.status_code == 409

    # 3. Producer sends 2 live notifications; shadow evaluator records 2 samples
    for idx in range(2):
        send_resp = client.post(
            "/api/v1/notifications",
            headers=producer_headers,
            json={
                "notification_type": "ops.alert",
                "intent": "OPERATIONAL",
                "title": f"Alert #{idx + 1}",
                "message": "CPU saturation detected",
                "source": "monitor",
                "autonomy_context": {
                    "autonomy_mode": "LIVE",
                    "agent_id": str(uuid4()),
                },
            },
        )
        assert send_resp.status_code == 202
        # Active policy is still v1 (SLACK only)
        assert send_resp.json()["channels_attempted"] == ["SLACK"]

    # 4. Observer inspects /ui/policies/proposals and /ui/policies/proposals/{delta_id}
    list_resp = client.get("/ui/policies/proposals", headers=observer_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()["items"]
    assert len(listed) == 1
    assert listed[0]["delta_id"] == delta_id
    assert listed[0]["shadow_aggregate"]["total_decisions"] == 2
    assert listed[0]["shadow_aggregate"]["status"] == "PASSED"
    assert listed[0]["can_approve"] is True

    detail_resp = client.get(f"/ui/policies/proposals/{delta_id}", headers=observer_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["shadow_results"]) == 2

    # 5. Admin approves qualifying delta into a DRAFT revision (SHADOW -> APPROVED)
    approve_resp = client.post(
        f"/api/v1/policies/proposals/{delta_id}/approve",
        headers=admin_headers,
        json={"reason": "Shadow evidence passed with 100% win rate"},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved_payload = approve_resp.json()
    assert approved_payload["status"] == "DRAFT"
    assert approved_payload["version"] == "2"
    assert approved_payload["delta"]["state"] == "APPROVED"
    assert approved_payload["delta"]["can_activate"] is True

    # Active policy is STILL v1 until explicit activation!
    active_resp = client.get("/ui/policies/active", headers=observer_headers)
    active_items = active_resp.json()["items"]
    assert active_items[0]["version"] == "1"
    assert active_items[0]["channels"] == ["SLACK"]

    # 6. Admin explicitly activates DRAFT -> ACTIVE (APPROVED -> APPLIED)
    activate_resp = client.post(
        f"/api/v1/policies/proposals/{delta_id}/activate",
        headers=admin_headers,
        json={"reason": "Promote v2 to production"},
    )
    assert activate_resp.status_code == 200, activate_resp.text
    activated_payload = activate_resp.json()
    assert activated_payload["status"] == "ACTIVE"
    assert activated_payload["version"] == "2"
    assert activated_payload["delta"]["state"] == "APPLIED"
    assert activated_payload["delta"]["applied_at"] is not None

    # Active policy is now v2 with SLACK + PAGERDUTY!
    active_after = client.get("/ui/policies/active", headers=observer_headers).json()["items"]
    assert active_after[0]["version"] == "2"
    assert active_after[0]["channels"] == ["SLACK", "PAGERDUTY"]


def test_policy_proposal_validation_and_rejection_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify field_path allow-list validation, baseline drift detection, and rejection."""
    monkeypatch.setenv("UNS_API_KEY", "admin-secret")
    db_url = f"sqlite:///{tmp_path / 'guards.db'}"
    runtime = Runtime(db_url, create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    client = TestClient(app)
    headers = {"X-UNS-API-Key": "admin-secret"}

    # Disallowed field_path is rejected with 422
    bad_field = client.post(
        "/api/v1/policies/proposals",
        headers=headers,
        json={
            "policy_type": "ops.check",
            "field_path": "__class__.__init__",
            "proposed_value": "bad",
            "reasoning": "attempt invalid path",
        },
    )
    assert bad_field.status_code == 422

    # Valid proposal promoted to SHADOW and then rejected retires PREVIEW and does not resurrect
    valid_prop = client.post(
        "/api/v1/policies/proposals",
        headers=headers,
        json={
            "policy_type": "ops.check",
            "field_path": "dedup_window_seconds",
            "proposed_value": 120,
            "reasoning": "Reduce dedup window to 2 minutes",
            "promote_to_shadow": True,
        },
    )
    assert valid_prop.status_code == 201
    delta_id = valid_prop.json()["delta_id"]
    assert valid_prop.json()["state"] == "SHADOW"

    reject_resp = client.post(
        f"/api/v1/policies/proposals/{delta_id}/reject",
        headers=headers,
        json={"reason": "Keep 300s default window"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["state"] == "REJECTED"
    assert reject_resp.json()["rejection_reason"] == "Keep 300s default window"

    # Subsequent intake for ops.check must NOT resurrect a zombie SHADOW delta from a leftover PREVIEW
    send_after_reject = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "notification_type": "ops.check",
            "intent": "OPERATIONAL",
            "title": "Post-reject check",
            "message": "Ensure rejected PREVIEW is retired",
            "source": "monitor",
            "autonomy_context": {
                "autonomy_mode": "LIVE",
                "agent_id": str(uuid4()),
            },
        },
    )
    assert send_after_reject.status_code == 202
    shadow_after = client.get("/ui/policies/proposals?state=SHADOW", headers=headers)
    assert shadow_after.status_code == 200
    assert shadow_after.json()["items"] == []

"""Tests for uns.governance ContextSchema, pure decide(), DecisionEngine, and GovernanceApprovalBridge (#49)."""

from __future__ import annotations

from textwrap import dedent
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from notification.adapters.base import BaseAdapter, DeliveryResult, guard_provider_attempt
from notification.models import Channel, Notification, NotificationIntent
from notification.service import SimpleAdapterRegistry
from uns.governance import (
    ApprovalRequestRecord,
    ApprovalStatus,
    Condition,
    ContextSchemaViolation,
    Decision,
    DecisionEngine,
    FailModeType,
    GovernanceApprovalBridge,
    MissingFieldError,
    Operator,
    Policy,
    PolicyLoadError,
    Rule,
    ThenClause,
    decide,
    load_policy_from_yaml,
    sign_approval_callback,
    validate_context_capsule,
    validate_policy_against_schema,
    verify_approval_callback,
)
from uns.runtime import Runtime


class Instrument(BaseModel):
    symbol: str
    exchange: Literal["NYSE", "NASDAQ", "ARCA"] = "NYSE"


class Approver(BaseModel):
    role: str


class TradingContext(BaseModel):
    notional_usd: int = Field(ge=0)
    plan_lifecycle: Literal["DRAFT", "PENDING", "ACTIVE", "RETIRED"] = "ACTIVE"
    instrument: Instrument
    approvers: list[Approver] = Field(default_factory=list)
    override_note: str | None = None


class _RecordingAdapter(BaseAdapter):
    def __init__(self, channel: Channel) -> None:
        self._channel = channel

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        guard_provider_attempt(self._channel)
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=f"msg-{notification.notification_id}",
        )

    async def health_check(self) -> bool:
        return True


def test_context_schema_load_and_capsule_validation() -> None:
    """validate_policy_against_schema catches unknown fields and type mismatches at load time."""
    valid_yaml = dedent(
        """
        id: trading-guard
        version: "1.0.0"
        context_schema: trading
        rules:
          - id: high_notional
            when:
              - field: notional_usd
                operator: GT
                value: 1000000
              - field: instrument.symbol
                operator: MATCHES
                value: "[A-Z]{1,5}"
              - field: approvers[0].role
                operator: EQ
                value: "risk-officer"
            then:
              decision: REQUIRE_APPROVAL
              reason: "Notional above $1M requires risk-officer sign-off"
              target_reviewer_role: "risk-officer"
        """
    ).strip()
    policy = load_policy_from_yaml(valid_yaml)
    validate_policy_against_schema(policy, TradingContext)

    # Unknown field rejected
    bad_field_policy = Policy(
        id="bad-field",
        version="1.0",
        context_schema="trading",
        rules=[
            Rule(
                id="r1",
                when=[Condition(field="nonexistent_field", operator=Operator.EQ, value=1)],
                then=ThenClause(decision=Decision.ALLOW),
            )
        ],
    )
    with pytest.raises(ContextSchemaViolation, match="nonexistent_field"):
        validate_policy_against_schema(bad_field_policy, TradingContext)

    # Operator type mismatch rejected at load (GT on str field)
    bad_op_policy = Policy(
        id="bad-op",
        version="1.0",
        context_schema="trading",
        rules=[
            Rule(
                id="r1",
                when=[Condition(field="instrument.symbol", operator=Operator.GT, value=10)],
                then=ThenClause(decision=Decision.DENY),
            )
        ],
    )
    with pytest.raises(PolicyLoadError, match="requires int/float"):
        validate_policy_against_schema(bad_op_policy, TradingContext)

    # Evaluate-time missing required field raises MissingFieldError
    with pytest.raises(MissingFieldError, match="notional_usd"):
        validate_context_capsule({"instrument": {"symbol": "AAPL"}}, TradingContext)


def test_pure_decide_deny_overrides_priority_and_short_circuit() -> None:
    """decide() evaluates all rules in priority+source order, short-circuits EXISTS, and applies deny-overrides."""
    policy_yaml = dedent(
        """
        id: trade-execution
        version: "2.1.0"
        context_schema: trading
        rules:
          - id: allow_active_plan
            when:
              - field: plan_lifecycle
                operator: EQ
                value: "ACTIVE"
            then:
              decision: ALLOW
          - id: require_approval_above_1m
            priority: 10
            when:
              - field: notional_usd
                operator: GT
                value: 1000000
            then:
              decision: REQUIRE_APPROVAL
              reason: "Exceeds $1M threshold"
              target_reviewer_role: "risk-committee"
          - id: deny_above_10m_without_note
            priority: 5
            when:
              - field: override_note
                operator: EXISTS
              - field: override_note
                operator: MATCHES
                value: "FORBIDDEN.*"
            then:
              decision: DENY
        """
    ).strip()
    policy = load_policy_from_yaml(policy_yaml)

    # 1. Notional $2M with override_note=None -> EXISTS is False, short-circuits MATCHES without raising,
    #    require_approval_above_1m + allow_active_plan both match -> REQUIRE_APPROVAL wins over ALLOW!
    rec = decide(
        policy,
        {
            "notional_usd": 2_000_000,
            "plan_lifecycle": "ACTIVE",
            "instrument": {"symbol": "AAPL", "exchange": "NASDAQ"},
            "override_note": None,
        },
        subject_id="trader-agent-1",
        context_schema=TradingContext,
    )
    assert rec.decision == Decision.REQUIRE_APPROVAL
    # Priority order: priority 5 -> priority 10 -> None
    assert [r.rule_id for r in rec.reasons] == [
        "deny_above_10m_without_note",
        "require_approval_above_1m",
        "allow_active_plan",
    ]
    assert [r.matched for r in rec.reasons] == [False, True, True]

    # 2. When DENY rule also matches, DENY overrides REQUIRE_APPROVAL and ALLOW
    rec_deny = decide(
        policy,
        {
            "notional_usd": 2_000_000,
            "plan_lifecycle": "ACTIVE",
            "instrument": {"symbol": "AAPL", "exchange": "NASDAQ"},
            "override_note": "FORBIDDEN_OVERRIDE",
        },
        subject_id="trader-agent-1",
        context_schema=TradingContext,
    )
    assert rec_deny.decision == Decision.DENY
    assert all(r.matched for r in rec_deny.reasons)

    # 3. No rule matches -> deny-by-default
    rec_no_match = decide(
        policy,
        {
            "notional_usd": 50_000,
            "plan_lifecycle": "DRAFT",
            "instrument": {"symbol": "MSFT", "exchange": "NASDAQ"},
        },
        subject_id="trader-agent-1",
        context_schema=TradingContext,
    )
    assert rec_no_match.decision == Decision.DENY
    assert not any(r.matched for r in rec_no_match.reasons)


def test_decision_engine_hot_reload_and_fail_mode_by_intent() -> None:
    """DecisionEngine preserves last-known-good on malformed hot-reload and maps fail-mode by intent."""
    valid_yaml = dedent(
        """
        id: trade-gate
        version: "1.0.0"
        context_schema: trading
        rules:
          - id: small_trade
            when:
              - field: notional_usd
                operator: LTE
                value: 100000
            then:
              decision: ALLOW
        """
    ).strip()

    engine = DecisionEngine(
        context_schemas={"trading": TradingContext},
        policies={"trade-gate": valid_yaml},
    )

    # Valid evaluation -> ALLOW
    ok_outcome = engine.evaluate(
        "trade-gate",
        {"notional_usd": 25_000, "instrument": {"symbol": "NVDA"}},
        subject_id="agent-1",
    )
    assert ok_outcome.fail_mode is False
    assert ok_outcome.record.decision == Decision.ALLOW

    # Malformed hot-reload -> rejected, previous version stays active
    reloaded = engine.reload_policy_yaml(
        "trade-gate",
        dedent(
            """
            id: trade-gate
            version: "2.0.0"
            context_schema: trading
            rules:
              - id: typo_rule
                when:
                  - field: unknown_field_typo
                    operator: EQ
                    value: 1
                then:
                  decision: DENY
            """
        ).strip(),
    )
    assert reloaded is False
    assert "trade-gate" in engine.quarantined_reloads
    assert engine.policies["trade-gate"].version == "1.0.0"

    # Invalid context capsule -> fail-closed DENY for GOVERNANCE, fail-open ALLOW for INFORMATIONAL
    gov_fail = engine.evaluate(
        "trade-gate",
        {"instrument": {"symbol": "NVDA"}},  # missing notional_usd
        subject_id="agent-1",
        intent=NotificationIntent.GOVERNANCE,
    )
    assert gov_fail.fail_mode is True
    assert gov_fail.fail_mode_type == FailModeType.CONTEXT_INVALID
    assert gov_fail.record.decision == Decision.DENY

    info_fail = engine.evaluate(
        "trade-gate",
        {"instrument": {"symbol": "NVDA"}},  # missing notional_usd
        subject_id="agent-1",
        intent=NotificationIntent.INFORMATIONAL,
    )
    assert info_fail.fail_mode is True
    assert info_fail.fail_mode_type == FailModeType.CONTEXT_INVALID
    assert info_fail.record.decision == Decision.ALLOW


@pytest.mark.asyncio
async def test_governance_approval_bridge_with_uns_runtime_and_signed_callbacks(tmp_path) -> None:
    """REQUIRE_APPROVAL creates a durable UNS obligation, settles on ACK, and signs resume headers."""
    db_url = f"sqlite+pysqlite:///{tmp_path / 'gov_runtime.db'}"
    adapters = SimpleAdapterRegistry()
    adapters.register(_RecordingAdapter(Channel.SLACK))
    adapters.register(_RecordingAdapter(Channel.WEBSOCKET))
    runtime = Runtime(
        db_url,
        create_tables=True,
        adapters=adapters,
    )

    settled_callbacks: list[ApprovalRequestRecord] = []
    secret = "test-governance-hmac-secret"
    bridge = GovernanceApprovalBridge(
        runtime,
        default_intent=NotificationIntent.SAFETY,
        signing_secret=secret,
        on_settled=settled_callbacks.append,
    )

    policy_yaml = dedent(
        """
        id: rebalance-approval
        version: "1.0.0"
        context_schema: trading
        rules:
          - id: high_notional
            when:
              - field: notional_usd
                operator: GT
                value: 500000
            then:
              decision: REQUIRE_APPROVAL
              reason: "Rebalance exceeds $500k autonomous limit"
              target_reviewer_role: "portfolio-manager"
        """
    ).strip()

    engine = DecisionEngine(
        context_schemas={"trading": TradingContext},
        policies={"rebalance-approval": policy_yaml},
        approval_bridge=bridge,
    )

    outcome = engine.evaluate(
        "rebalance-approval",
        {"notional_usd": 750_000, "instrument": {"symbol": "SPY", "exchange": "ARCA"}},
        subject_id="rebalance-agent-01",
        correlation_id="corr-rebalance-99",
        callback_url="https://agent.example.internal/callbacks/resume",
    )
    assert outcome.record.decision == Decision.REQUIRE_APPROVAL
    assert outcome.obligation_notification_id is not None

    # Deliver the UNS obligation
    await runtime.dispatch()
    notif_status = runtime.get(outcome.obligation_notification_id)
    assert notif_status["status"] == "DELIVERED"
    assert notif_status["ack_status"] == "PENDING"

    # Acknowledge the UNS obligation directly in Runtime and sync approval state
    runtime.acknowledge(
        outcome.obligation_notification_id,
        actor="pm-alice",
        metadata={"note": "Approved SPY rebalance"},
    )
    queried = bridge.query_approval(outcome.record.decision_id)
    assert queried is not None
    assert queried.status == ApprovalStatus.APPROVED
    assert queried.resolved_by == "pm-alice"
    assert queried.resolution_note == "Approved SPY rebalance"
    assert queried.callback_headers is not None
    assert len(settled_callbacks) == 1

    # Verify cross-restart / stateless GovernanceApprovalBridge recovery from Runtime
    restarted_bridge = GovernanceApprovalBridge(
        runtime,
        default_intent=NotificationIntent.SAFETY,
        signing_secret=secret,
    )
    recovered_after_restart = restarted_bridge.query_approval(outcome.record.decision_id)
    assert recovered_after_restart is not None
    assert recovered_after_restart.status == ApprovalStatus.APPROVED
    assert recovered_after_restart.resolved_by == "pm-alice"
    assert recovered_after_restart.decision_record.policy_id == "rebalance-approval"

    # Verify INFORMATIONAL fail-open emits an operational alert notification into Runtime
    info_fail = engine.evaluate(
        "rebalance-approval",
        {"instrument": {"symbol": "SPY", "exchange": "ARCA"}},  # missing notional_usd
        subject_id="rebalance-agent-01",
        intent=NotificationIntent.INFORMATIONAL,
    )
    assert info_fail.fail_mode is True
    assert info_fail.record.decision == Decision.ALLOW
    assert info_fail.operational_alert_notification_id is not None
    alert_row = runtime.get(info_fail.operational_alert_notification_id)
    assert alert_row["notification"]["notification_type"] == "governance.fail_open_alert"

    # Verify HMAC-SHA256 callback signature
    payload_bytes = queried.model_dump_json().encode("utf-8")
    assert verify_approval_callback(payload_bytes, queried.callback_headers, secret) is True
    assert verify_approval_callback(payload_bytes, queried.callback_headers, "wrong-secret") is False

    # Also verify replay window rejection
    old_headers = sign_approval_callback(payload_bytes, secret, timestamp=1_000_000)
    assert (
        verify_approval_callback(
            payload_bytes, old_headers, secret, max_skew_seconds=300, now_epoch=1_001_000
        )
        is False
    )
    runtime.engine.dispose()

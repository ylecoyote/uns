from __future__ import annotations

from uuid import UUID

import pytest

from agsignal_mcp.factory import AGSIGNAL_MCP_TOOL_NAMES
from agsignal_mcp.runtime import MCPRuntimeConfig, RuntimeState
from agsignal_mcp.tools import (
    AckNotificationInput,
    SendSignalInput,
    ack_notification,
    dismiss_notification,
    get_ack_status,
    get_channel_health,
    list_deliveries,
    list_dlq,
    ready,
    send_signal,
)

WRITABLE_CONFIG = MCPRuntimeConfig(
    read_only=False,
    operator_principal="operator",
    delivery_confirmation_token="approved",
)


def _signal_input(**overrides: object) -> SendSignalInput:
    payload: dict[str, object] = {
        "notification_type": "agent.risk_limit_breach",
        "intent": "SAFETY",
        "title": "Risk limit breached",
        "message": "Agent entered a position outside configured limits.",
        "source": "agent-runtime",
        "autonomy_context": {
            "autonomy_mode": "LIVE",
            "agent_id": "00000000-0000-0000-0000-000000000001",
        },
    }
    payload.update(overrides)
    return SendSignalInput.model_validate(payload)


def test_v1_status_tool_names_are_declared() -> None:
    assert "ack_notification" in AGSIGNAL_MCP_TOOL_NAMES
    assert "dismiss_notification" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_ack_status" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_delivery_status" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_effective_policy" in AGSIGNAL_MCP_TOOL_NAMES
    assert "list_invariants" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_invariants_summary" in AGSIGNAL_MCP_TOOL_NAMES
    assert "list_dlq" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_channel_health" in AGSIGNAL_MCP_TOOL_NAMES
    assert "ready" in AGSIGNAL_MCP_TOOL_NAMES
    assert "reload_policies" not in AGSIGNAL_MCP_TOOL_NAMES
    assert "remove_dlq_entry" not in AGSIGNAL_MCP_TOOL_NAMES


def test_ready_reports_runtime_mode() -> None:
    response = ready(MCPRuntimeConfig(mode="read-only", read_only=True))

    assert response["status"] == "ready"
    assert response["service"] == "agsignal-mcp"
    assert response["mode"] == "read-only"
    assert response["read_only"] is True


@pytest.mark.asyncio
async def test_ack_notification_is_disabled_in_read_only_mode() -> None:
    with pytest.raises(ValueError, match="disabled in read-only mode"):
        await ack_notification(
            AckNotificationInput(notification_id="00000000-0000-0000-0000-000000000001"),
            config=MCPRuntimeConfig(mode="read-only", read_only=True),
        )


@pytest.mark.asyncio
async def test_ack_notification_updates_tracked_signal() -> None:
    state = RuntimeState(legacy_fixture_mode=True)
    sent = await send_signal(
        _signal_input(
            deliver=True,
            operator_intent="deliver",
            operator_confirmation_token="approved",
        ),
        runtime_state=state,
        config=WRITABLE_CONFIG,
    )

    acked = await ack_notification(
        AckNotificationInput(notification_id=sent["notification_id"]),
        runtime_state=state,
        config=WRITABLE_CONFIG,
    )
    status = await get_ack_status(sent["notification_id"])

    assert acked["ack_status"] == "ACKED"
    assert acked["acked_by"] == "operator"
    assert status["ack_status"] == "ACKED"
    assert len(state.audit_store.get_ack_audits_for_notification(UUID(sent["notification_id"]))) == 1


@pytest.mark.asyncio
async def test_dismiss_notification_is_disabled_in_read_only_mode() -> None:
    with pytest.raises(ValueError, match="dismiss_notification is disabled in read-only mode"):
        await dismiss_notification(
            AckNotificationInput(notification_id="00000000-0000-0000-0000-000000000001"),
            config=MCPRuntimeConfig(mode="read-only", read_only=True),
        )


@pytest.mark.asyncio
async def test_dismiss_notification_marks_signal_dismissed() -> None:
    state = RuntimeState(legacy_fixture_mode=True)
    sent = await send_signal(
        _signal_input(
            deliver=True,
            operator_intent="deliver",
            operator_confirmation_token="approved",
        ),
        runtime_state=state,
        config=WRITABLE_CONFIG,
    )

    dismissed = await dismiss_notification(
        AckNotificationInput(notification_id=sent["notification_id"]),
        runtime_state=state,
        config=WRITABLE_CONFIG,
    )
    status = await get_ack_status(sent["notification_id"])

    assert dismissed["notification_id"] == sent["notification_id"]
    assert dismissed["ack_status"] == "DISMISSED"
    assert dismissed["acked_by"] == "operator"
    assert "acked_at" in dismissed
    assert dismissed["metadata"] == {}
    assert status["ack_status"] == "DISMISSED"
    assert (
        len(state.audit_store.get_ack_audits_for_notification(UUID(sent["notification_id"]))) == 1
    )


@pytest.mark.asyncio
async def test_dismiss_notification_requires_acked_by_match_when_provided() -> None:
    state = RuntimeState(legacy_fixture_mode=True)
    sent = await send_signal(
        _signal_input(
            deliver=True,
            operator_intent="deliver",
            operator_confirmation_token="approved",
        ),
        runtime_state=state,
        config=WRITABLE_CONFIG,
    )

    with pytest.raises(ValueError, match="acked_by must match the operator principal"):
        await dismiss_notification(
            AckNotificationInput(
                notification_id=sent["notification_id"],
                acked_by="someone-else",
            ),
            runtime_state=state,
            config=WRITABLE_CONFIG,
        )


def test_runtime_inspection_tools_are_json_safe() -> None:
    state = RuntimeState(legacy_fixture_mode=True)

    assert list_dlq(state)["depth"] == 0
    channel_health = get_channel_health(state)

    assert "status" in channel_health


@pytest.mark.asyncio
async def test_read_model_tool_can_run_inside_existing_event_loop() -> None:
    response = await list_deliveries(limit=1)

    assert "items" in response
    assert "pagination" in response

"""Root integration checks across actual MCP process and shared persisted policy."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from db.policy_store import SQLAlchemyPolicyStore
from notification.models import Channel, DeliveryMode, NotificationIntent
from notification.policies import NotificationPolicy
from uns.runtime import Runtime


def _tool_data(result):
    assert not result.isError, result.content
    data = getattr(result, "structuredContent", None)
    if data is not None:
        return data
    return json.loads(next(block.text for block in result.content if block.type == "text"))


@pytest.mark.asyncio
async def test_running_mcp_process_observes_new_active_snapshot(tmp_path):
    url = f"sqlite:///{tmp_path}/shared.db"
    runtime = Runtime(url, create_tables=True)
    store = SQLAlchemyPolicyStore(runtime.sessions)
    initial = NotificationPolicy(
        notification_type="integration.snapshot",
        version="1",
        intent=NotificationIntent.SAFETY,
        channels=[Channel.SLACK],
        delivery_mode=DeliveryMode.GUARANTEED,
        require_ack=True,
        ack_timeout_minutes=15,
    )
    store.save_snapshot([initial])
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("UNS_", "AGSIGNAL_")) and key != "DATABASE_URL"
    }
    environment.update(
        UNS_DATABASE_URL=url,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "agsignal_mcp.transports.stdio"], env=environment
    )
    async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        args = {
            "notification_type": "integration.snapshot",
            "intent": "SAFETY",
            "autonomy_mode": "LIVE",
        }
        before = _tool_data(await client.call_tool("get_effective_policy", args))
        assert before["effective"]["channels"] == ["SLACK"]
        assert before["effective"]["require_ack"] is True
        updated = initial.model_copy(
            update={"version": "2", "channels": [Channel.EMAIL], "ack_timeout_minutes": 7}
        )
        store.save_snapshot([updated])
        after = _tool_data(await client.call_tool("get_effective_policy", args))
        assert after["effective"]["channels"] == ["EMAIL"]
        assert after["effective"]["ack_timeout_minutes"] == 7
    runtime.engine.dispose()

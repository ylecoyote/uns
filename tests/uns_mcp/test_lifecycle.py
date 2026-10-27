"""Exercise the running MCP protocol server, including idle recovery and exit."""
from __future__ import annotations

import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from tests.uns.test_transport_security import configured as configured
from tests.uns.test_transport_security import signal

from uns_mcp.factory import create_mcp_server
from uns_mcp.runtime import MCPRuntimeConfig


async def wait_until(predicate):
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_writable_mcp_recovers_idle_retries_expires_responses_and_stops(configured):
    _, runtime, adapter = configured
    adapter.success = False
    runtime.retry_seconds = 0
    accepted = await runtime.send(signal(), principal="operator")
    assert runtime.get(accepted.notification_id)["status"] == "PENDING"
    adapter.success = True
    server = create_mcp_server(MCPRuntimeConfig(
        read_only=False, require_delivery_confirmation=False, operator_principal="operator",
    ), runtime=runtime)
    async with create_connected_server_and_client_session(server) as session:
        assert (await session.call_tool("health")).isError is False
        await wait_until(lambda: runtime.get(accepted.notification_id)["status"] == "DELIVERED")
        row = runtime.get(accepted.notification_id)
        runtime.clock = lambda: row["deadline"] + 1
        # No tool invocation is needed to drive timeout processing.
        await wait_until(lambda: runtime.get(accepted.notification_id)["ack_status"] == "TIMED_OUT")
        worker = next(task for task in asyncio.all_tasks() if task.get_name() == "uns-mcp-worker")
    assert worker.done()
    assert worker.cancelled()
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_read_only_mcp_never_starts_delivery_worker(configured):
    _, runtime, adapter = configured
    accepted = runtime.accept(signal(), principal="operator")
    server = create_mcp_server(runtime=runtime)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("ack_notification", {"payload": {"notification_id": str(accepted.notification_id)}})
        assert result.isError
        assert not any(task.get_name() == "uns-mcp-worker" for task in asyncio.all_tasks())
        assert runtime.get(accepted.notification_id)["status"] == "PENDING"
        assert adapter.calls == 0


def test_writable_mcp_requires_explicit_principal_at_startup():
    with pytest.raises(ValueError, match="principal"):
        create_mcp_server(MCPRuntimeConfig(read_only=False))


def test_cold_mcp_process_uses_persisted_policy(tmp_path):
    """A new interpreter has no policy registry or runtime singleton to inherit."""
    import json
    import os
    import subprocess
    import sys
    import textwrap

    from db.policy_store import SQLAlchemyPolicyStore
    from notification.policies import NotificationPolicy
    from uns.runtime import Runtime

    url = f"sqlite:///{tmp_path}/cold-mcp.db"
    runtime = Runtime(url, create_tables=True)
    policy = NotificationPolicy.from_dict({
        "notification_type": "security.test", "version": "1", "status": "ACTIVE",
        "delivery_mode": "GUARANTEED", "channels": {"LIVE": ["EMAIL"]},
        "require_ack": {"LIVE": True}, "ack_timeout_minutes": 7,
    })
    SQLAlchemyPolicyStore(runtime.sessions).save_snapshot([policy])
    runtime.engine.dispose()
    script = textwrap.dedent('''
        import asyncio, json
        from uns_mcp.factory import create_mcp_server
        from mcp.shared.memory import create_connected_server_and_client_session
        async def run():
            server = create_mcp_server()
            async with create_connected_server_and_client_session(server) as session:
                result = await session.call_tool("simulate_signal", {"payload": {
                    "notification_type": "security.test", "intent": "OPERATIONAL",
                    "title": "cold", "message": "cold", "source": "cold",
                    "autonomy_context": {"autonomy_mode": "LIVE", "agent_id": "00000000-0000-0000-0000-000000000001"}
                }})
                assert not result.isError, result
                print(result.content[0].text)
        asyncio.run(run())
    ''')
    env = {key: value for key, value in os.environ.items() if not key.startswith("UNS_")}
    env.update({"UNS_DATABASE_URL": url, "PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1"})
    process = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr
    preview = json.loads(process.stdout)
    assert preview["require_ack"] is True
    assert preview["delivery_mode"] == "GUARANTEED"
    assert preview["channels_attempted"] == ["EMAIL"]
    assert preview["policy_source"] == "policy"


@pytest.mark.asyncio
async def test_tool_mutations_require_durable_runtime_unless_explicit_fixture_mode():
    from uns_mcp.tools import (
        AckNotificationInput,
        SendSignalInput,
        ack_notification,
        send_signal,
    )

    config = MCPRuntimeConfig(read_only=False, require_delivery_confirmation=False, operator_principal="operator")
    payload = signal()
    with pytest.raises(ValueError, match="durable runtime"):
        await send_signal(SendSignalInput(**payload.model_dump(mode="json"), deliver=True, operator_intent="deliver"), config=config)
    with pytest.raises(ValueError, match="durable runtime"):
        await ack_notification(AckNotificationInput(notification_id=payload.autonomy_context.agent_id), config=config)

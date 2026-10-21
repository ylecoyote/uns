"""Direct MCP helpers and protocol tools must read their owning durable runtime."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from tests.uns.test_transport_security import RecordingAdapter, signal

from agsignal.api.read_models import InMemoryReadModelAdapter, SQLAlchemyReadModelAdapter
from agsignal.responses import NotificationStatusResponse
from agsignal_mcp.factory import create_mcp_server
from agsignal_mcp.runtime import MCPRuntimeConfig, RuntimeState
from agsignal_mcp.tools import (
    AckNotificationInput,
    SendSignalInput,
    ack_notification,
    get_ack_status,
    get_delivery_status,
    get_notification_status,
    list_audit_events,
    list_deliveries,
    list_dlq,
    send_signal,
)
from notification.audit import InMemoryAuditStore
from notification.service import SimpleAdapterRegistry
from uns.runtime import Runtime

WRITABLE_CONFIG = MCPRuntimeConfig(
    read_only=False,
    require_delivery_confirmation=False,
    operator_principal="operator",
)


@pytest.fixture
def runtime_pair(tmp_path):
    runtimes = []
    adapters = []
    for name in ("first", "second"):
        adapter = RecordingAdapter()
        registry = SimpleAdapterRegistry()
        registry.register(adapter)
        runtimes.append(Runtime(
            f"sqlite:///{tmp_path}/{name}.db", adapters=registry, create_tables=True,
            max_attempts=1,
        ))
        adapters.append(adapter)
    yield runtimes, adapters
    for runtime in runtimes:
        runtime.engine.dispose()


def test_runtime_state_binds_omitted_durable_read_dependencies(runtime_pair):
    runtimes, _ = runtime_pair
    for runtime in runtimes:
        state = RuntimeState(runtime=runtime)
        assert state.audit_store is runtime.audit_store
        assert isinstance(state.read_model_adapter, SQLAlchemyReadModelAdapter)
        assert state.read_model_adapter.runtime is runtime


@pytest.mark.asyncio
async def test_runtime_state_preserves_explicit_read_dependencies(runtime_pair):
    runtimes, _ = runtime_pair
    sent = await runtimes[0].send(signal(), principal="operator")
    audit_store = InMemoryAuditStore()
    adapter = InMemoryReadModelAdapter(audit_store)
    state = RuntimeState(
        runtime=runtimes[0], audit_store=audit_store, read_model_adapter=adapter,
    )

    assert state.audit_store is audit_store
    assert state.read_model_adapter is adapter
    assert get_delivery_status(sent.notification_id, runtime_state=state)["found"] is False
    assert (await list_deliveries(runtime_state=state))["items"] == []
    assert (await list_audit_events(runtime_state=state))["items"] == []


@pytest.mark.asyncio
async def test_direct_helpers_read_durable_send_and_ack_with_runtime_isolation(runtime_pair):
    runtimes, _ = runtime_pair
    state, other_state = (RuntimeState(runtime=runtime) for runtime in runtimes)
    payload = SendSignalInput(
        **signal().model_dump(mode="json"), deliver=True, operator_intent="deliver",
    )
    sent = await send_signal(payload, runtime_state=state, config=WRITABLE_CONFIG)
    notification_id = sent["notification_id"]
    await ack_notification(
        AckNotificationInput(notification_id=notification_id),
        runtime_state=state,
        config=WRITABLE_CONFIG,
    )

    assert await get_ack_status(UUID(notification_id), runtime_state=state) == {
        "notification_id": notification_id, "ack_status": "ACKED",
    }
    assert await get_notification_status(notification_id, runtime_state=state) == {
        "notification_id": notification_id, "found": True,
        "ack_status": "ACKED", "status": "DELIVERED",
    }
    assert get_delivery_status(notification_id, runtime_state=state)["found"] is True
    assert {item["notification_id"] for item in
            (await list_deliveries(runtime_state=state))["items"]} == {notification_id}
    assert {item["notification_id"] for item in
            (await list_audit_events(runtime_state=state))["items"]} == {notification_id}

    assert await get_ack_status(notification_id, runtime_state=other_state) == {
        "notification_id": notification_id, "ack_status": None,
    }
    assert await get_notification_status(notification_id, runtime_state=other_state) == {
        "notification_id": notification_id, "found": False,
    }
    assert get_delivery_status(notification_id, runtime_state=other_state)["found"] is False
    assert (await list_deliveries(runtime_state=other_state))["items"] == []
    assert (await list_audit_events(runtime_state=other_state))["items"] == []


@pytest.mark.asyncio
async def test_direct_dlq_reads_only_its_durable_runtime(runtime_pair):
    runtimes, adapters = runtime_pair
    adapters[0].success = False
    sent = await runtimes[0].send(signal(), principal="operator")

    actual = list_dlq(RuntimeState(runtime=runtimes[0]))
    assert actual["depth"] == 1
    assert actual["items"][0]["notification_id"] == str(sent.notification_id)
    assert list_dlq(RuntimeState(runtime=runtimes[1])) == {"depth": 0, "items": []}


@pytest.mark.asyncio
async def test_factory_and_direct_helpers_have_matching_runtime_reads_and_schemas(runtime_pair):
    runtimes, adapters = runtime_pair
    sent = await runtimes[0].send(signal(), principal="operator")
    runtimes[0].acknowledge(sent.notification_id, actor="operator")
    adapters[0].success = False
    await runtimes[0].send(signal(), principal="operator")
    notification_id = str(sent.notification_id)

    for runtime in runtimes:
        state = RuntimeState(runtime=runtime)
        expected = {
            "get_ack_status": await get_ack_status(notification_id, runtime_state=state),
            "get_notification_status": await get_notification_status(
                notification_id, runtime_state=state,
            ),
            "get_delivery_status": get_delivery_status(notification_id, runtime_state=state),
            "list_deliveries": await list_deliveries(runtime_state=state),
            "list_audit_events": await list_audit_events(runtime_state=state),
            "list_dlq": list_dlq(state),
        }
        server = create_mcp_server(runtime=runtime)
        async with create_connected_server_and_client_session(server) as session:
            schemas = {tool.name: tool.inputSchema for tool in (await session.list_tools()).tools}
            for name, response in expected.items():
                args = {"notification_id": notification_id} if name.startswith("get_") else {}
                result = await session.call_tool(name, args)
                assert not result.isError, result
                assert json.loads(result.content[0].text) == response
                expected_inputs = {"notification_id"} if args else ({"limit"} if name != "list_dlq" else set())
                assert set(schemas[name]["properties"]) == expected_inputs


@pytest.mark.asyncio
@pytest.mark.parametrize("notification_id", [
    "00000000-0000-0000-0000-000000000001",
    "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
    "not-a-uuid",
])
async def test_durable_status_queries_preserve_missing_identifier_contract(
    runtime_pair, notification_id,
):
    runtimes, _ = runtime_pair
    state = RuntimeState(runtime=runtimes[0])
    expected = {
        "get_ack_status": {"notification_id": notification_id, "ack_status": None},
        "get_notification_status": {"notification_id": notification_id, "found": False},
    }
    assert await get_ack_status(notification_id, runtime_state=state) == expected["get_ack_status"]
    assert await get_notification_status(notification_id, runtime_state=state) == expected["get_notification_status"]
    async with create_connected_server_and_client_session(
        create_mcp_server(runtime=runtimes[0]),
    ) as session:
        for name, response in expected.items():
            result = await session.call_tool(name, {"notification_id": notification_id})
            assert not result.isError, result
            assert json.loads(result.content[0].text) == response


@pytest.mark.asyncio
@pytest.mark.parametrize("with_state", [False, True])
async def test_no_runtime_status_helpers_retain_legacy_schema(with_state):
    notification_id = uuid4()
    state = RuntimeState(legacy_fixture_mode=True) if with_state else None
    assert await get_ack_status(notification_id, runtime_state=state) == {
        "notification_id": str(notification_id), "ack_status": None,
    }
    assert await get_notification_status(notification_id, runtime_state=state) == (
        NotificationStatusResponse(notification_id=notification_id, found=False)
        .model_dump(mode="json")
    )
    for helper in (get_ack_status, get_notification_status):
        with pytest.raises(ValueError):
            await helper("not-a-uuid", runtime_state=state)

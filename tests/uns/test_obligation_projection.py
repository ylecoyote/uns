"""Canonical response evidence survives handoffs and is consistent across transports."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import update
from tests.uns import test_delivery_remediation as delivery_fixtures
from tests.uns.test_delivery_remediation import request

from notification.models import Channel
from notification.rate_limiting import RateLimitConfig, configure_rate_limiter
from uns.app import create_app
from uns.runtime import work
from uns_mcp.factory import create_mcp_server
from uns_mcp.runtime import RuntimeState
from uns_mcp.tools import get_ack_status, get_notification_status

PROJECTION_FIELDS = (
    "obligation_owner_id",
    "effective_ack_status",
    "ack_inherited",
    "obligation_resolution_status",
    "obligation_resolution_error",
)


@pytest.fixture
def state(tmp_path, monkeypatch):
    for name in ("UNS_POLICY_DIR", "UNS_POLICY_DIR"):
        monkeypatch.delenv(name, raising=False)
    fixture = delivery_fixtures.state.__wrapped__(tmp_path)
    configure_rate_limiter({Channel.SLACK: RateLimitConfig(tokens_per_second=100, bucket_size=100)})
    yield fixture
    fixture[0].engine.dispose()


def projection(body):
    return {field: body[field] for field in PROJECTION_FIELDS}


async def assert_transport_projection(runtime, identifier, expected):
    """Exercise HTTP and registered MCP tools, not only their internal helpers."""
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_api_key = "projection-test-key"
    app.state.uns_api_principal = "projection-observer"
    client = TestClient(app, headers={"Authorization": "Bearer projection-test-key"})
    for suffix in ("", "/ack-status"):
        response = client.get(f"/api/v1/notifications/{identifier}{suffix}")
        assert response.status_code == 200
        assert projection(response.json()) == expected

    runtime_state = RuntimeState(runtime=runtime)
    for helper in (get_notification_status, get_ack_status):
        assert projection(await helper(identifier, runtime_state=runtime_state)) == expected

    server = create_mcp_server(runtime=runtime)
    async with create_connected_server_and_client_session(server) as session:
        for tool in ("get_notification_status", "get_ack_status"):
            result = await session.call_tool(tool, {"notification_id": str(identifier)})
            assert not result.isError, result
            assert projection(json.loads(result.content[0].text)) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("replay_root", [False, True])
async def test_projection_follows_twelve_real_owners_and_root_replay(state, replay_root):
    runtime, adapter, _, _, _ = state
    accepted = [
        runtime.accept(request(f"handoff-{index}", require_ack=True), principal="producer")
        for index in range(12)
    ]
    original_ids = [str(response.notification_id) for response in accepted]
    current_id = original_ids[0]
    adapter.success = False

    # These links are formed by real exhaustion and promotion, not injected rows.
    failure_count = 12 if replay_root else 11
    failed_ids = []
    for index in range(failure_count):
        assert await runtime.dispatch(current_id)
        failed_ids.append(current_id)
        row = runtime.get(current_id)
        assert row["status"] == "FAILED"
        if index < 11:
            current_id = row["dedup_successor_id"]
            assert current_id is not None
        else:
            assert row["dedup_successor_id"] is None
    assert len(set(failed_ids)) == failure_count

    if replay_root:
        runtime.replay(original_ids[0], actor="operator")
        current_id = original_ids[0]

    adapter.success = True
    assert await runtime.dispatch(current_id)
    runtime.acknowledge(current_id, actor="responder")

    for identifier in original_ids:
        expected = {
            "obligation_owner_id": current_id,
            "effective_ack_status": "ACKED",
            "ack_inherited": identifier != current_id,
            "obligation_resolution_status": "RESOLVED",
            "obligation_resolution_error": None,
        }
        row = runtime.get(identifier)
        assert projection(row) == expected
        assert row["ack_status"] == ("ACKED" if identifier == current_id else None)
        assert row["status"] == ("DELIVERED" if identifier == current_id else "FAILED")
        assert projection(runtime.response(identifier).model_dump(mode="json")) == expected


@pytest.mark.asyncio
async def test_http_and_registered_mcp_expose_inherited_response_changes(state):
    runtime, _, _, _, _ = state
    owner = await runtime.send(request("owner", require_ack=True), principal="producer")
    follower = await runtime.send(request("follower", require_ack=True), principal="producer")
    assert follower.ack_status is None
    expected = {
        "obligation_owner_id": str(owner.notification_id),
        "effective_ack_status": "PENDING",
        "ack_inherited": True,
        "obligation_resolution_status": "RESOLVED",
        "obligation_resolution_error": None,
    }
    await assert_transport_projection(runtime, follower.notification_id, expected)

    runtime.acknowledge(owner.notification_id, actor="responder")
    expected["effective_ack_status"] = "ACKED"
    await assert_transport_projection(runtime, follower.notification_id, expected)
    assert runtime.get(follower.notification_id)["ack_status"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["CYCLE", "MISSING_TARGET", "GROUP_MISMATCH"])
async def test_broken_lineage_is_explicit_without_exposing_partial_ack(state, error):
    runtime, _, _, _, _ = state
    owner = await runtime.send(request("owner", require_ack=True), principal="producer")
    follower = await runtime.send(request("follower", require_ack=True), principal="producer")
    runtime.acknowledge(owner.notification_id, actor="responder")

    if error == "CYCLE":
        target_id = str(follower.notification_id)
    elif error == "MISSING_TARGET":
        target_id = str(uuid4())
    else:
        other = await runtime.send(
            request("other", require_ack=True, dedup_key="another-obligation"),
            principal="producer",
        )
        runtime.acknowledge(other.notification_id, actor="responder")
        target_id = str(other.notification_id)

    # Corrupt a later link after an ACKED row: partial evidence must not be
    # presented as a successfully resolved canonical response.
    with runtime.sessions.begin() as session:
        session.execute(
            update(work)
            .where(work.c.id == str(owner.notification_id))
            .values(dedup_successor_id=target_id)
        )
    expected = {
        "obligation_owner_id": None,
        "effective_ack_status": None,
        "ack_inherited": False,
        "obligation_resolution_status": "UNRESOLVED",
        "obligation_resolution_error": error,
    }
    original_events = runtime.events(owner.notification_id)
    assert projection(runtime.get(owner.notification_id)) == expected
    assert runtime.get(owner.notification_id)["ack_status"] == "ACKED"
    assert projection(runtime.response(follower.notification_id).model_dump(mode="json")) == expected
    await assert_transport_projection(runtime, follower.notification_id, expected)
    assert runtime.events(owner.notification_id) == original_events
    assert runtime.get(owner.notification_id)["dedup_successor_id"] == target_id

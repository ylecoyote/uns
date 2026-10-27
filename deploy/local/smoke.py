"""Verify an authorized persistent localhost recording deployment, including restart."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
import websockets
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HOME = Path.home() / "Library/Application Support/UNS"
SETTINGS = dict(line.split("=", 1) for line in (HOME / "service.env").read_text().splitlines())
RELEASE = Path((HOME / "active-release.txt").read_text().strip())
BASE = "http://127.0.0.1:18080"
CLIENT = httpx.Client(
    base_url=BASE, headers={"Authorization": "Bearer " + SETTINGS["UNS_API_KEY"]}, timeout=15
)
RUN = uuid4().hex[:8]
AGENT = str(uuid4())
CHECKS: list[str] = []
IDS: dict[str, str] = {}


def check(name, condition, detail=None):
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    CHECKS.append(name)
    print("PASS", name, flush=True)


def docker(*args, payload=None):
    result = subprocess.run(
        ["docker", *args], input=payload, capture_output=True, text=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def call(method, path, status=200, **kwargs):
    response = CLIENT.request(method, path, **kwargs)
    check(
        f"{method} {path.split('?')[0]} {status}",
        response.status_code == status,
        response.text[:300],
    )
    return response.json() if "json" in response.headers.get("content-type", "") else response


def request(name, **changes):
    result = {
        "notification_type": "local.smoke.safety",
        "intent": "SAFETY",
        "title": "Local recording verification: " + name,
        "message": "No external notification.",
        "source": "uns-local-smoke",
        "autonomy_context": {"agent_id": AGENT, "autonomy_mode": "LIVE"},
        "idempotency_key": RUN + ":" + name,
        "dedup_key": RUN + ":" + name,
    }
    result.update(changes)
    return result


def row(identifier):
    response = CLIENT.get("/api/v1/runtime/notifications/" + identifier)
    response.raise_for_status()
    return response.json()


def wait_for(predicate, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = predicate()
            if result:
                return result
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.25)
    raise TimeoutError("Local verification condition did not complete")


def send(name, **changes):
    result = call("POST", "/api/v1/notifications", 202, json=request(name, **changes))
    IDS[name] = result["notification_id"]
    return result


def data(result):
    check("MCP response succeeds", not result.isError)
    return (
        result.structuredContent
        if result.structuredContent is not None
        else json.loads(next(c.text for c in result.content if c.type == "text"))
    )


async def transport_checks():
    token = base64.urlsafe_b64encode(SETTINGS["UNS_API_KEY"].encode()).decode().rstrip("=")
    async with websockets.connect(
        "ws://127.0.0.1:18080/ws/agents/" + AGENT,
        subprotocols=["agsignal.v1", "bearer." + token],
        origin=BASE,
    ) as websocket:
        check(
            "WebSocket through local ingress authenticates",
            json.loads(await websocket.recv())["type"] == "connected",
        )
        item = send(
            "websocket",
            notification_type="local.smoke.informational",
            intent="INFORMATIONAL",
            delivery_mode="BEST_EFFORT",
            require_ack=False,
        )
        event = json.loads(await asyncio.wait_for(websocket.recv(), 5))
        check(
            "WebSocket forwards a real network notification",
            event["notification"]["notification_id"] == item["notification_id"],
        )
        acked = send("websocket-ack")
        # SAFETY also fans out through WebSocket before its recording channel.
        while True:
            event = json.loads(await asyncio.wait_for(websocket.recv(), 5))
            if event.get("notification", {}).get("notification_id") == acked["notification_id"]:
                break
        await websocket.send(
            json.dumps({"type": "ack", "notification_id": acked["notification_id"]})
        )
        answer = json.loads(await asyncio.wait_for(websocket.recv(), 5))
        check(
            "WebSocket ACK is durable and attributed",
            answer["ack_status"] == "ACKED" and answer["acked_by"] == "local-operator",
        )
    ro = StdioServerParameters(
        command="docker", args=["exec", "-i", "uns-local", "python", "/profile/local_mcp.py"]
    )
    async with stdio_client(ro) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        check("Read-only MCP exposes 16 tools", len((await client.list_tools()).tools) == 16)
        status = data(await client.call_tool("get_ack_status", {"notification_id": IDS["ack"]}))
        check("MCP sees HTTP ACK", status["ack_status"] == "ACKED")
        rejected = await client.call_tool(
            "send_signal",
            {
                "payload": {
                    **request("ro-rejected"),
                    "deliver": True,
                    "operator_intent": "deliver",
                    "operator_confirmation_token": SETTINGS["UNS_MCP_DELIVERY_CONFIRMATION_TOKEN"],
                }
            },
        )
        check("Default MCP rejects delivery", rejected.isError)
    rw = StdioServerParameters(
        command="docker",
        args=["exec", "-i", "uns-local", "python", "/profile/local_mcp.py", "--enable-writes"],
    )
    async with stdio_client(rw) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        payload = request("mcp")
        sent = data(
            await client.call_tool(
                "send_signal",
                {
                    "payload": {
                        **payload,
                        "deliver": True,
                        "operator_intent": "deliver",
                        "operator_confirmation_token": SETTINGS[
                            "UNS_MCP_DELIVERY_CONFIRMATION_TOKEN"
                        ],
                    }
                },
            )
        )
        check("Write-enabled MCP records delivery", sent["status"] == "DELIVERED")
        repeat = call("POST", "/api/v1/notifications", 202, json=payload)
        check(
            "MCP/HTTP idempotency shares identity",
            repeat["notification_id"] == sent["notification_id"] and repeat["idempotent_replay"],
        )
        data(
            await client.call_tool(
                "ack_notification", {"payload": {"notification_id": sent["notification_id"]}}
            )
        )
        check(
            "MCP acknowledgment visible over HTTP",
            row(sent["notification_id"])["ack_status"] == "ACKED",
        )


def main():
    wait_for(lambda: CLIENT.get("/ready").json().get("status") == "ready")
    status = call("GET", "/local-status")
    check(
        "Persistent recording profile identity",
        status["profile"] == "local-recording" and status["external_delivery"] is False,
    )
    for path in ("/ready", "/local-status", "/metrics", "/ui/audit"):
        check("Unauthenticated " + path + " rejected", httpx.get(BASE + path).status_code == 401)
    check("Public liveness works", httpx.get(BASE + "/health").status_code == 200)
    for path in ("/", "/deliveries", "/policy", "/audit", "/invariants", "/operations"):
        response = call("GET", path)
        check(
            "Recording banner on " + path,
            "Local recording mode." in response.text
            and "No Slack, email or PagerDuty messages are sent." in response.text,
        )
    preview = call("POST", "/api/v1/notifications/simulate", json=request("preview"))
    check(
        "Simulation has no durable work",
        preview["simulated"]
        and CLIENT.get("/api/v1/runtime/notifications/" + preview["notification_id"]).status_code
        == 404,
    )
    first = send("ack")
    check(
        "Slack channel records locally",
        first["status"] == "DELIVERED" and "SLACK" in first["channels_succeeded"],
    )
    observed = [
        e for e in row(first["notification_id"])["events"] if e["kind"] == "CHANNEL_ATTEMPT_RESULT"
    ]
    check(
        "Receipt explicitly identifies recording",
        any(e["payload"]["metadata"].get("recording_only") for e in observed),
    )
    repeat = send("ack")
    check(
        "Idempotent repeat retains identity",
        repeat["notification_id"] == first["notification_id"] and repeat["idempotent_replay"],
    )
    call("POST", "/api/v1/notifications", 409, json=request("ack", message="different"))
    duplicate = send("duplicate", dedup_key=RUN + ":ack")
    check("Semantic duplicate is suppressed", duplicate["status"] == "DEDUPLICATED")
    call(
        "POST",
        "/api/v1/notifications/" + first["notification_id"] + "/ack",
        403,
        json={"acked_by": "imposter"},
    )
    ack = call("POST", "/api/v1/notifications/" + first["notification_id"] + "/ack", json={})
    check("ACK derives actor from credential", ack["acked_by"] == "local-operator")
    call("POST", "/api/v1/notifications/" + first["notification_id"] + "/dismiss", 409, json={})
    dismissed = send("dismiss")
    call("POST", "/api/v1/notifications/" + dismissed["notification_id"] + "/dismiss", json={})
    audit = call("GET", "/ui/audit?notification_id=" + first["notification_id"])
    check(
        "Audit retains LIVE context and UTC",
        all(
            e["autonomy_context"]["autonomy_mode"] == "LIVE"
            and e["event_time"].endswith(("Z", "+00:00"))
            for e in audit["items"]
        ),
    )
    policy_script = """from recording_runtime import make_runtime
from notification.policies import NotificationPolicy
from db.policy_store import SQLAlchemyPolicyStore
import sys
r=make_runtime(); policies=list(r.policy_runtime.registry().get_all().values())
for channel in ('EMAIL','PAGERDUTY','SLACK'):
 policies.append(NotificationPolicy(notification_type='local.smoke.'+sys.argv[1]+'.'+channel,version='1',intent='SAFETY',channels=[channel],delivery_mode='GUARANTEED',require_ack=channel=='SLACK',ack_timeout_minutes=1))
SQLAlchemyPolicyStore(r.sessions).save_snapshot(policies);r.engine.dispose()
"""
    docker("exec", "uns-local", "python", "-c", policy_script, RUN)
    for channel in ("EMAIL", "PAGERDUTY"):
        result = send(channel, notification_type="local.smoke." + RUN + "." + channel)
        check(
            channel + " is recorded, not sent externally",
            result["status"] == "DELIVERED" and result["channels_succeeded"] == [channel],
        )
    timeout = send("timeout", notification_type="local.smoke." + RUN + ".SLACK")
    asyncio.run(transport_checks())
    print("Waiting for the real one-minute ACK deadline...", flush=True)
    wait_for(lambda: row(timeout["notification_id"])["ack_status"] == "TIMED_OUT", 70)
    check(
        "Timeout recovery on persistent profile",
        row(timeout["notification_id"])["actor"] == "uns-timeout-worker",
    )
    wait_for(
        lambda: all(not e["callback_pending"] for e in row(timeout["notification_id"])["events"])
    )
    check(
        "Local callback receipt is durable",
        timeout["notification_id"] in docker("exec", "uns-local", "cat", "/data/responses.jsonl"),
    )
    docker("stop", "-t", "15", "uns-local")
    seed = "from recording_runtime import make_runtime;from agsignal.responses import SendNotificationRequest;import json,sys;r=make_runtime();a=r.accept(SendNotificationRequest(**json.load(sys.stdin)),principal='local-operator');print(a.notification_id);r.engine.dispose()"
    pending = docker(
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--env-file",
        str(HOME / "service.env"),
        "--mount",
        "type=volume,src=uns-local-data,dst=/data",
        "--mount",
        f"type=bind,src={RELEASE}/profile,dst=/profile,readonly",
        "uns:07ef52a",
        "python",
        "-c",
        seed,
        payload=json.dumps(request("restart")),
    )
    docker("start", "uns-local")
    wait_for(lambda: CLIENT.get("/ready").json().get("status") == "ready", 30)
    wait_for(lambda: row(pending)["status"] == "DELIVERED")
    check("Persisted pending work dispatches after restart", row(pending)["attempts"] == 1)
    check("Earlier ACK survives restart", row(first["notification_id"])["ack_status"] == "ACKED")
    call("POST", "/api/v1/notifications/" + pending + "/ack", json={})
    IDS["restart"] = pending
    check(
        "Live profile has no fault injection",
        send("ordinary", metadata={"smoke_fail": True})["status"] == "DELIVERED",
    )
    print("PASS persistent deployment:", len(CHECKS), "checks", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        Path("/private/tmp/uns-persistent-results.json").write_text(
            json.dumps(
                {"status": "failed", "error": str(exc), "checks": CHECKS, "notification_ids": IDS},
                indent=2,
            )
            + "\n"
        )
        raise
    else:
        Path("/private/tmp/uns-persistent-results.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "checks": CHECKS,
                    "notification_ids": IDS,
                    "external_delivery": False,
                },
                indent=2,
            )
            + "\n"
        )

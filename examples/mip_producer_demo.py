"""First-party Market Insights Platform (MIP) producer integration example.

Exercises the canonical MIP UNS sample policy pack (`examples/policies/mip-uns`)
either in standalone local recording mode (`uns.Runtime` + SQLite) or against a
live UNS HTTP server (`--base-url http://127.0.0.1:18080` with
`UNS_PRODUCER_API_KEY` / `UNS_API_KEY`).

Flows verified:
1. Dry-run simulation (`governance.approval_required`) with mode-aware routing.
2. Live intake with rich autonomy context (`safety.kill_switch`) and required ACK.
3. Operator acknowledgment verification and durable audit inspection.
4. Deduplication window coalescing (`execution.slippage`) and obligation lineage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
for _import_path in (REPO_ROOT / "src", REPO_ROOT):
    _path_str = str(_import_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from agsignal.responses import SendNotificationRequest  # noqa: E402
from db.policy_store import SQLAlchemyPolicyStore  # noqa: E402
from notification.adapters.base import (  # noqa: E402
    AdapterStatus,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
)
from notification.models import Channel, Notification  # noqa: E402
from notification.policies import PolicyRegistry  # noqa: E402
from notification.policy_loader import load_policies_from_directory  # noqa: E402
from notification.service import SimpleAdapterRegistry  # noqa: E402
from uns import Client, Runtime  # noqa: E402

DEFAULT_MIP_POLICY_DIR = REPO_ROOT / "examples" / "policies" / "mip-uns"


class RecordingChannelAdapter(BaseAdapter):
    """Local in-memory recording adapter that sends no external network traffic."""

    def __init__(self, channel: Channel) -> None:
        self._channel = channel
        self.delivered: list[UUID] = []

    @property
    def channel(self) -> Channel:
        return self._channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        self.delivered.append(notification.notification_id)
        return DeliveryResult(
            success=True,
            channel=self._channel,
            message_id=f"local-{self._channel.value.lower()}-{notification.notification_id}",
            metadata={"recorded_channel": self._channel.value},
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message=f"Local {self._channel.value} recorder ready",
        )


def build_recording_registry() -> tuple[SimpleAdapterRegistry, dict[str, RecordingChannelAdapter]]:
    """Register local recording adapters for all channels used by MIP policies."""
    registry = SimpleAdapterRegistry()
    recorders: dict[str, RecordingChannelAdapter] = {}
    for channel in (Channel.SLACK, Channel.WEBSOCKET, Channel.PAGERDUTY, Channel.EMAIL):
        adapter = RecordingChannelAdapter(channel)
        registry.register(adapter)
        recorders[channel.value] = adapter
    return registry, recorders


def load_mip_policies(runtime: Runtime, policy_dir: Path | None = None) -> list[str]:
    """Load the MIP YAML policy pack into the runtime's durable policy store."""
    resolved_dir = (policy_dir or DEFAULT_MIP_POLICY_DIR).resolve()
    if not resolved_dir.exists() or not resolved_dir.is_dir():
        raise FileNotFoundError(f"MIP policy directory not found: {resolved_dir}")

    staging = PolicyRegistry(runtime_only=False)
    loaded_count = load_policies_from_directory(resolved_dir, registry=staging)
    if loaded_count == 0:
        raise ValueError(f"No YAML policies found in {resolved_dir}")

    policies = list(staging.get_all().values())
    SQLAlchemyPolicyStore(runtime.sessions).save_snapshot(policies)
    return sorted(policy.notification_type for policy in policies)


def build_mip_requests(
    *,
    agent_id: UUID | None = None,
    run_tag: str | None = None,
) -> dict[str, SendNotificationRequest]:
    """Build representative MIP notification requests for the three mip-uns policy types."""
    resolved_agent_id = agent_id or uuid4()
    tag = run_tag or uuid4().hex[:8]
    plan_id = uuid4()
    decision_snapshot_id = uuid4()
    execution_snapshot_id = uuid4()
    shared_dedup_key = f"mip:slippage:BTC-USD:{tag}"

    return {
        "governance_simulation": SendNotificationRequest(
            notification_type="governance.approval_required",
            intent="GOVERNANCE",
            title="Strategy parameter change requires risk approval",
            message=(
                "MIP regime classifier requested leverage cap adjustment from 1.5x to 2.0x "
                "for desk portfolio alpha-prime."
            ),
            source="mip.governance.gate",
            autonomy_context={
                "agent_id": str(resolved_agent_id),
                "autonomy_mode": "LIVE",
                "plan_id": str(plan_id),
                "decision_snapshot_id": str(decision_snapshot_id),
            },
            idempotency_key=f"mip-gov-sim-{tag}",
            correlation_id=f"mip-corr-gov-{tag}",
            metadata={
                "desk": "alpha-prime",
                "requested_max_leverage": 2.0,
                "current_max_leverage": 1.5,
            },
        ),
        "safety_kill_switch": SendNotificationRequest(
            notification_type="safety.kill_switch",
            intent="SAFETY",
            title="MIP automated kill switch engaged on drawdown breach",
            message=(
                "Intraday portfolio drawdown reached 185 bps (limit 150 bps). "
                "Order router halted and open quotes canceled."
            ),
            source="mip.risk.kill_switch",
            irreversible=True,
            autonomy_context={
                "agent_id": str(resolved_agent_id),
                "autonomy_mode": "LIVE",
                "plan_id": str(plan_id),
                "decision_snapshot_id": str(decision_snapshot_id),
                "execution_snapshot_id": str(execution_snapshot_id),
            },
            idempotency_key=f"mip-kill-switch-{tag}",
            correlation_id=f"mip-corr-safety-{tag}",
            metadata={
                "strategy_id": "momentum-v4",
                "observed_drawdown_bps": 185,
                "threshold_drawdown_bps": 150,
                "orders_canceled": 14,
            },
        ),
        "slippage_primary": SendNotificationRequest(
            notification_type="execution.slippage",
            intent="OPERATIONAL",
            title="Execution slippage above threshold on BTC-USD",
            message="Observed 18.4 bps slippage on venue-alpha (threshold 10.0 bps).",
            source="mip.execution.monitor",
            autonomy_context={
                "agent_id": str(resolved_agent_id),
                "autonomy_mode": "LIVE",
                "execution_snapshot_id": str(execution_snapshot_id),
            },
            dedup_key=shared_dedup_key,
            idempotency_key=f"mip-slippage-1-{tag}",
            correlation_id=f"mip-corr-slip-1-{tag}",
            metadata={
                "symbol": "BTC-USD",
                "venue": "venue-alpha",
                "slippage_bps": 18.4,
            },
        ),
        "slippage_duplicate": SendNotificationRequest(
            notification_type="execution.slippage",
            intent="OPERATIONAL",
            title="Execution slippage above threshold on BTC-USD (follow-up fill)",
            message="Observed 19.1 bps slippage on venue-alpha within active dedup window.",
            source="mip.execution.monitor",
            autonomy_context={
                "agent_id": str(resolved_agent_id),
                "autonomy_mode": "LIVE",
                "execution_snapshot_id": str(execution_snapshot_id),
            },
            dedup_key=shared_dedup_key,
            idempotency_key=f"mip-slippage-2-{tag}",
            correlation_id=f"mip-corr-slip-2-{tag}",
            metadata={
                "symbol": "BTC-USD",
                "venue": "venue-alpha",
                "slippage_bps": 19.1,
            },
        ),
    }


async def run_local_demo(
    *,
    database_url: str | None = None,
    policy_dir: Path | None = None,
    principal: str = "mip-producer",
    responder_principal: str = "mip-risk-operator",
) -> dict[str, Any]:
    """Run the MIP producer flow against a local recording `uns.Runtime`."""
    with TemporaryDirectory() as temp_dir:
        resolved_db_url = database_url or f"sqlite:///{Path(temp_dir) / 'mip_demo.db'}"
        registry, recorders = build_recording_registry()
        runtime = Runtime(resolved_db_url, adapters=registry, create_tables=True)
        try:
            loaded_types = load_mip_policies(runtime, policy_dir=policy_dir)
            client = Client(runtime, principal=principal)
            requests = build_mip_requests()

            # 1. Dry-run simulation of governance.approval_required
            sim_req = requests["governance_simulation"]
            sim_response = await client.simulate(sim_req)
            if not sim_response.simulated or not sim_response.require_ack:
                raise RuntimeError("Unexpected simulation outcome for governance.approval_required")

            # 2. Live intake of safety.kill_switch with autonomy context
            safety_response = await client.send(requests["safety_kill_switch"])
            if safety_response.status.value != "DELIVERED":
                raise RuntimeError(
                    f"Expected safety.kill_switch DELIVERED, got {safety_response.status.value}"
                )
            if not safety_response.require_ack or safety_response.ack_status is None:
                raise RuntimeError("Expected safety.kill_switch to require acknowledgment in LIVE")

            # 3. Acknowledgment verification
            ack_response = runtime.acknowledge(
                safety_response.notification_id,
                actor=responder_principal,
                metadata={"runbook": "MIP-KILL-SWITCH-01", "verified_halt": True},
            )
            safety_events = runtime.events(safety_response.notification_id)
            if ack_response.ack_status.value != "ACKED" or safety_events[-1]["kind"] != "ACKED":
                raise RuntimeError("Expected safety.kill_switch acknowledgment to be committed")

            # 4. Deduplication coalescing on execution.slippage
            slippage_first = await client.send(requests["slippage_primary"])
            slippage_second = await client.send(requests["slippage_duplicate"])
            if slippage_first.status.value != "DELIVERED":
                raise RuntimeError(
                    f"Expected primary execution.slippage DELIVERED, got {slippage_first.status.value}"
                )
            if slippage_second.status.value != "DEDUPLICATED":
                raise RuntimeError(
                    "Expected duplicate execution.slippage DEDUPLICATED, "
                    f"got {slippage_second.status.value}"
                )
            if slippage_second.obligation_owner_id != slippage_first.notification_id:
                raise RuntimeError(
                    "Expected duplicate execution.slippage to link to primary obligation owner"
                )

            return {
                "mode": "local_recording",
                "verified": True,
                "policy_types_loaded": loaded_types,
                "principal": principal,
                "responder_principal": responder_principal,
                "simulation": {
                    "notification_type": sim_req.notification_type,
                    "simulated": sim_response.simulated,
                    "status": sim_response.status.value,
                    "delivery_mode": sim_response.delivery_mode.value,
                    "channels": [ch.value for ch in sim_response.channels_attempted],
                    "require_ack": sim_response.require_ack,
                    "policy_source": sim_response.policy_source,
                },
                "safety_kill_switch": {
                    "notification_id": str(safety_response.notification_id),
                    "status": safety_response.status.value,
                    "channels_succeeded": [ch.value for ch in safety_response.channels_succeeded],
                    "require_ack": safety_response.require_ack,
                    "initial_ack_status": safety_response.ack_status.value,
                    "final_ack_status": ack_response.ack_status.value,
                    "acked_by": ack_response.acked_by,
                    "event_kinds": [event["kind"] for event in safety_events],
                },
                "deduplication": {
                    "notification_type": "execution.slippage",
                    "primary_notification_id": str(slippage_first.notification_id),
                    "primary_status": slippage_first.status.value,
                    "duplicate_notification_id": str(slippage_second.notification_id),
                    "duplicate_status": slippage_second.status.value,
                    "obligation_owner_id": str(slippage_second.obligation_owner_id),
                    "obligation_resolution_status": slippage_second.obligation_resolution_status,
                },
                "recorded_channel_deliveries": {
                    channel_name: len(adapter.delivered)
                    for channel_name, adapter in recorders.items()
                },
            }
        finally:
            runtime.engine.dispose()


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid --base-url {base_url!r}; expected http:// or https:// URL")
    return base_url.rstrip("/")


def _resolve_api_key(explicit_key: str | None) -> str:
    # Credentials come from explicit CLI or environment; never hardcode fallback secrets.
    key = (
        explicit_key
        or os.environ.get("UNS_PRODUCER_API_KEY")
        or os.environ.get("UNS_API_KEY")
        or os.environ.get("AGSIGNAL_PRODUCER_API_KEY")
        or os.environ.get("AGSIGNAL_API_KEY")
    )
    if not key:
        raise ValueError(
            "Live HTTP mode requires UNS_PRODUCER_API_KEY or UNS_API_KEY "
            "(or --api-key) for authentication."
        )
    return key


async def run_http_demo(
    base_url: str,
    *,
    api_key: str | None = None,
    responder_api_key: str | None = None,
    policy_dir: Path | None = None,
    reload_policies: bool = False,
    timeout_seconds: float = 15.0,
    transport: Any = None,
) -> dict[str, Any]:
    """Run the MIP producer flow against a live UNS HTTP server."""
    import httpx

    normalized_url = _validate_base_url(base_url)
    producer_key = _resolve_api_key(api_key)
    responder_key = (
        responder_api_key
        or os.environ.get("UNS_RESPONDER_API_KEY")
        or os.environ.get("UNS_API_KEY")
        or os.environ.get("AGSIGNAL_RESPONDER_API_KEY")
        or os.environ.get("AGSIGNAL_API_KEY")
        or producer_key
    )
    admin_key = (
        os.environ.get("UNS_API_KEY")
        or os.environ.get("AGSIGNAL_API_KEY")
        or producer_key
    )

    producer_headers = {"Authorization": f"Bearer {producer_key}"}
    responder_headers = {"Authorization": f"Bearer {responder_key}"}
    admin_headers = {"Authorization": f"Bearer {admin_key}"}

    requests = build_mip_requests()

    async with httpx.AsyncClient(
        base_url=normalized_url,
        timeout=timeout_seconds,
        transport=transport,
    ) as client:
        loaded_types: list[str] = []
        if reload_policies:
            target_dir = str((policy_dir or DEFAULT_MIP_POLICY_DIR).resolve())
            reload_resp = await client.post(
                "/api/v1/policies/reload",
                json={"policy_dir": target_dir},
                headers=admin_headers,
            )
            reload_resp.raise_for_status()
            loaded_types = reload_resp.json().get("notification_types", [])

        # 1. Dry-run simulation
        sim_resp = await client.post(
            "/api/v1/notifications/simulate",
            json=requests["governance_simulation"].model_dump(mode="json"),
            headers=producer_headers,
        )
        sim_resp.raise_for_status()
        sim_data = sim_resp.json()

        # 2. Live intake of safety.kill_switch
        safety_resp = await client.post(
            "/api/v1/notifications",
            json=requests["safety_kill_switch"].model_dump(mode="json"),
            headers=producer_headers,
        )
        safety_resp.raise_for_status()
        safety_data = safety_resp.json()
        notification_id = safety_data["notification_id"]

        # 3. Operator acknowledgment over HTTP
        ack_resp = await client.post(
            f"/api/v1/notifications/{notification_id}/ack",
            json={"metadata": {"runbook": "MIP-KILL-SWITCH-01", "verified_halt": True}},
            headers=responder_headers,
        )
        ack_resp.raise_for_status()
        ack_data = ack_resp.json()

        status_resp = await client.get(
            f"/api/v1/notifications/{notification_id}",
            headers=responder_headers,
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()

        # 4. Deduplication coalescing on execution.slippage
        slip_first_resp = await client.post(
            "/api/v1/notifications",
            json=requests["slippage_primary"].model_dump(mode="json"),
            headers=producer_headers,
        )
        slip_first_resp.raise_for_status()
        slip_first_data = slip_first_resp.json()

        slip_second_resp = await client.post(
            "/api/v1/notifications",
            json=requests["slippage_duplicate"].model_dump(mode="json"),
            headers=producer_headers,
        )
        slip_second_resp.raise_for_status()
        slip_second_data = slip_second_resp.json()

        if ack_data.get("ack_status") != "ACKED" or status_data.get("ack_status") != "ACKED":
            raise RuntimeError("Expected HTTP acknowledgment status to be ACKED")
        if slip_second_data.get("status") != "DEDUPLICATED":
            raise RuntimeError(
                f"Expected second slippage signal to be DEDUPLICATED, got {slip_second_data.get('status')}"
            )
        if slip_second_data.get("obligation_owner_id") != slip_first_data.get("notification_id"):
            raise RuntimeError("Expected second slippage signal to reference primary owner")

        return {
            "mode": "http",
            "base_url": normalized_url,
            "verified": True,
            "policy_types_loaded": loaded_types,
            "simulation": {
                "notification_type": requests["governance_simulation"].notification_type,
                "simulated": sim_data["simulated"],
                "status": sim_data["status"],
                "delivery_mode": sim_data["delivery_mode"],
                "channels": sim_data["channels_attempted"],
                "require_ack": sim_data["require_ack"],
                "policy_source": sim_data["policy_source"],
            },
            "safety_kill_switch": {
                "notification_id": notification_id,
                "status": safety_data["status"],
                "channels_succeeded": safety_data.get("channels_succeeded", []),
                "require_ack": safety_data["require_ack"],
                "initial_ack_status": safety_data.get("ack_status"),
                "final_ack_status": ack_data["ack_status"],
                "acked_by": ack_data.get("acked_by"),
            },
            "deduplication": {
                "notification_type": "execution.slippage",
                "primary_notification_id": slip_first_data["notification_id"],
                "primary_status": slip_first_data["status"],
                "duplicate_notification_id": slip_second_data["notification_id"],
                "duplicate_status": slip_second_data["status"],
                "obligation_owner_id": slip_second_data.get("obligation_owner_id"),
                "obligation_resolution_status": slip_second_data.get(
                    "obligation_resolution_status"
                ),
            },
        }


def format_receipt(receipt: dict[str, Any]) -> str:
    """Render a concise human-readable summary plus structured JSON receipt."""
    sim = receipt["simulation"]
    safety = receipt["safety_kill_switch"]
    dedup = receipt["deduplication"]
    lines = [
        f"MIP Producer Demo ({receipt['mode']}) - PASS",
        (
            f"  1. Simulate {sim['notification_type']}: "
            f"simulated={sim['simulated']} mode={sim['delivery_mode']} "
            f"channels={','.join(sim['channels'])} require_ack={sim['require_ack']}"
        ),
        (
            f"  2. Live SAFETY safety.kill_switch ({safety['notification_id']}): "
            f"status={safety['status']} ack={safety['initial_ack_status']}->{safety['final_ack_status']} "
            f"by {safety['acked_by']}"
        ),
        (
            f"  3. Dedup {dedup['notification_type']}: "
            f"primary={dedup['primary_status']} ({dedup['primary_notification_id']}) "
            f"duplicate={dedup['duplicate_status']} (owner={dedup['obligation_owner_id']})"
        ),
        "Structured receipt:",
        json.dumps(receipt, indent=2, sort_keys=True),
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the MIP producer UNS integration example (local recording or live HTTP)."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Target live UNS HTTP server (e.g., http://127.0.0.1:18080). Omit for local recording mode.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Producer API key for --base-url (defaults to UNS_PRODUCER_API_KEY or UNS_API_KEY).",
    )
    parser.add_argument(
        "--responder-api-key",
        default=None,
        help="Responder API key for ACK step in --base-url mode (defaults to UNS_RESPONDER_API_KEY or UNS_API_KEY).",
    )
    parser.add_argument(
        "--policy-dir",
        type=Path,
        default=DEFAULT_MIP_POLICY_DIR,
        help="Path to MIP YAML policies directory (default: examples/policies/mip-uns).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional SQLite database URL for standalone local recording mode.",
    )
    parser.add_argument(
        "--principal",
        default="mip-producer",
        help="Authenticated producer principal for standalone local mode.",
    )
    parser.add_argument(
        "--responder-principal",
        default="mip-risk-operator",
        help="Authenticated responder actor for standalone local mode.",
    )
    parser.add_argument(
        "--reload-policies",
        action="store_true",
        help="Reload --policy-dir on the remote server before running HTTP mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the JSON receipt.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.base_url:
        receipt = asyncio.run(
            run_http_demo(
                args.base_url,
                api_key=args.api_key,
                responder_api_key=args.responder_api_key,
                policy_dir=args.policy_dir,
                reload_policies=args.reload_policies,
            )
        )
    else:
        receipt = asyncio.run(
            run_local_demo(
                database_url=args.database_url,
                policy_dir=args.policy_dir,
                principal=args.principal,
                responder_principal=args.responder_principal,
            )
        )

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(format_receipt(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

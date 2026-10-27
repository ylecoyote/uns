"""Opt-in real-channel smoke verifier for Slack, Email/SMTP, and PagerDuty.

Matches the verification contract in `docs/TESTING.md`:
- Real-channel acceptance is an explicit opt-in smoke test requiring configured
  accounts and authorized recipients.
- By default (`--dry-run` or when provider environment variables are absent),
  reports readiness of each external adapter without sending external traffic
  and exits 0.
- When `--execute` is explicitly passed alongside configured provider
  credentials, dispatches a clearly tagged `[UNS OPT-IN SMOKE]` verification
  message through the configured adapter(s) and prints the provider receipt,
  Attempt status, and latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
for _import_path in (REPO_ROOT / "src", REPO_ROOT):
    _path_str = str(_import_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from agsignal.responses import SendNotificationRequest  # noqa: E402
from db.policy_store import SQLAlchemyPolicyStore  # noqa: E402
from notification.adapters.base import (  # noqa: E402
    AdapterConfigurationError,
    AdapterDeliveryError,
    AdapterStatus,
    AdapterTimeoutError,
    BaseAdapter,
    DeliveryResult,
    HealthCheckResult,
    guard_provider_attempt,
)
from notification.adapters.email import EmailAdapter, EmailConfig  # noqa: E402
from notification.adapters.pagerduty import PagerDutyAdapter, PagerDutyConfig  # noqa: E402
from notification.adapters.slack import SlackAdapter, SlackConfig  # noqa: E402
from notification.models import (  # noqa: E402
    Channel,
    DeliveryMode,
    Notification,
    NotificationIntent,
)
from notification.policies import NotificationPolicy  # noqa: E402
from notification.service import SimpleAdapterRegistry  # noqa: E402
from uns.runtime import Runtime  # noqa: E402

SMOKE_TAG = "[UNS OPT-IN SMOKE]"
SUPPORTED_CHANNELS = ("slack", "email", "pagerduty")


def _mask_email(address: str) -> str:
    """Mask an email address so PII is never printed in plain text."""
    cleaned = address.strip()
    if "@" not in cleaned:
        return "***"
    local, _, domain = cleaned.partition("@")
    prefix = local[0] if local else "*"
    return f"{prefix}***@{domain}"


def _env_get(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        val = env.get(name, "").strip()
        if val:
            return val
    return ""


class SlackWebhookSmokeAdapter(BaseAdapter):
    """Slack incoming-webhook adapter for `UNS_SLACK_WEBHOOK_URL` opt-in smoke."""

    guards_provider_attempts = True

    def __init__(self, webhook_url: str, timeout_seconds: float = 15.0) -> None:
        parsed = urlparse(webhook_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise AdapterConfigurationError(
                "UNS_SLACK_WEBHOOK_URL must be a valid https:// (or localhost http://) URL",
                channel=Channel.SLACK,
            )
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise AdapterConfigurationError(
                "UNS_SLACK_WEBHOOK_URL must use https:// for non-loopback hosts",
                channel=Channel.SLACK,
            )
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    @property
    def channel(self) -> Channel:
        return Channel.SLACK

    async def deliver(self, notification: Notification) -> DeliveryResult:
        import httpx

        guard_provider_attempt(self.channel)
        payload = {
            "text": f"{SMOKE_TAG} *{notification.title}*\n{notification.message}",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
            body = response.text.strip() or "ok"
            return DeliveryResult(
                success=True,
                channel=Channel.SLACK,
                message_id=f"slack-webhook-{notification.notification_id}",
                metadata={
                    "transport": "webhook",
                    "http_status": response.status_code,
                    "response": body[:120],
                },
                delivered_at=datetime.now(UTC),
            )
        except httpx.TimeoutException as exc:
            raise AdapterTimeoutError(
                f"Slack webhook request timed out: {exc}",
                channel=Channel.SLACK,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterDeliveryError(
                f"Slack webhook HTTP error: {exc}",
                channel=Channel.SLACK,
                retryable=False,
                original_error=exc,
            ) from exc

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status=AdapterStatus.HEALTHY,
            message="Slack incoming webhook URL configured",
        )


def inspect_channel_readiness(
    env: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Inspect environment variables for Slack, Email/SMTP, and PagerDuty readiness."""
    source_env = os.environ if env is None else env

    # 1. Slack: UNS_SLACK_WEBHOOK_URL (or UNS_SLACK_BOT_TOKEN + UNS_SLACK_CHANNEL)
    slack_webhook = _env_get(source_env, "UNS_SLACK_WEBHOOK_URL", "AGSIGNAL_SLACK_WEBHOOK_URL")
    slack_bot_token = _env_get(source_env, "UNS_SLACK_BOT_TOKEN", "AGSIGNAL_SLACK_BOT_TOKEN")
    slack_channel = _env_get(source_env, "UNS_SLACK_CHANNEL", "AGSIGNAL_SLACK_CHANNEL")
    slack_configured = bool(slack_webhook or (slack_bot_token and slack_channel))
    slack_mode = (
        "webhook"
        if slack_webhook
        else ("bot_token" if (slack_bot_token and slack_channel) else "unconfigured")
    )
    if slack_configured:
        slack_missing: list[str] = []
    elif slack_bot_token and not slack_channel:
        slack_missing = ["UNS_SLACK_CHANNEL"]
    elif slack_channel and not slack_bot_token:
        slack_missing = ["UNS_SLACK_BOT_TOKEN"]
    else:
        slack_missing = ["UNS_SLACK_WEBHOOK_URL"]

    # 2. Email / SMTP: UNS_SMTP_HOST, UNS_SMTP_FROM, UNS_SMOKE_EMAIL_TO
    smtp_host = _env_get(source_env, "UNS_SMTP_HOST", "AGSIGNAL_SMTP_HOST")
    smtp_from = _env_get(
        source_env, "UNS_SMTP_FROM", "UNS_EMAIL_FROM", "AGSIGNAL_SMTP_FROM", "AGSIGNAL_EMAIL_FROM"
    )
    smoke_email_to = _env_get(
        source_env,
        "UNS_SMOKE_EMAIL_TO",
        "UNS_EMAIL_TO",
        "AGSIGNAL_SMOKE_EMAIL_TO",
        "AGSIGNAL_EMAIL_TO",
    )
    email_missing: list[str] = []
    if not smtp_host:
        email_missing.append("UNS_SMTP_HOST")
    if not smtp_from:
        email_missing.append("UNS_SMTP_FROM")
    if not smoke_email_to:
        email_missing.append("UNS_SMOKE_EMAIL_TO")
    email_configured = len(email_missing) == 0
    recipients = [addr.strip() for addr in smoke_email_to.split(",") if addr.strip()]

    # 3. PagerDuty: UNS_PAGERDUTY_ROUTING_KEY
    pd_routing_key = _env_get(
        source_env, "UNS_PAGERDUTY_ROUTING_KEY", "AGSIGNAL_PAGERDUTY_ROUTING_KEY"
    )
    pd_configured = bool(pd_routing_key)
    pd_missing = [] if pd_configured else ["UNS_PAGERDUTY_ROUTING_KEY"]

    return {
        "slack": {
            "channel": "SLACK",
            "configured": slack_configured,
            "mode": slack_mode,
            "required_env": ["UNS_SLACK_WEBHOOK_URL"],
            "missing_env": slack_missing,
        },
        "email": {
            "channel": "EMAIL",
            "configured": email_configured,
            "smtp_host": smtp_host or None,
            "from_address_masked": _mask_email(smtp_from) if smtp_from else None,
            "recipients_masked": [_mask_email(r) for r in recipients],
            "required_env": ["UNS_SMTP_HOST", "UNS_SMTP_FROM", "UNS_SMOKE_EMAIL_TO"],
            "missing_env": email_missing,
        },
        "pagerduty": {
            "channel": "PAGERDUTY",
            "configured": pd_configured,
            "routing_key_length": len(pd_routing_key) if pd_routing_key else 0,
            "required_env": ["UNS_PAGERDUTY_ROUTING_KEY"],
            "missing_env": pd_missing,
        },
    }


def build_channel_adapter(
    channel_name: str,
    env: Mapping[str, str] | None = None,
) -> BaseAdapter:
    """Instantiate the real channel adapter from configured environment variables."""
    source_env = os.environ if env is None else env
    normalized = channel_name.lower()

    if normalized == "slack":
        webhook_url = _env_get(source_env, "UNS_SLACK_WEBHOOK_URL", "AGSIGNAL_SLACK_WEBHOOK_URL")
        bot_token = _env_get(source_env, "UNS_SLACK_BOT_TOKEN", "AGSIGNAL_SLACK_BOT_TOKEN")
        slack_channel = _env_get(source_env, "UNS_SLACK_CHANNEL", "AGSIGNAL_SLACK_CHANNEL")
        if webhook_url:
            return SlackWebhookSmokeAdapter(webhook_url=webhook_url)
        if bot_token and slack_channel:
            return SlackAdapter(
                SlackConfig(
                    bot_token=bot_token,
                    default_channel=slack_channel,
                    retry_attempts=1,
                )
            )
        raise AdapterConfigurationError(
            "Slack is not configured; set UNS_SLACK_WEBHOOK_URL or both UNS_SLACK_BOT_TOKEN and UNS_SLACK_CHANNEL",
            channel=Channel.SLACK,
        )

    if normalized == "email":
        smtp_host = _env_get(source_env, "UNS_SMTP_HOST", "AGSIGNAL_SMTP_HOST")
        smtp_from = _env_get(
            source_env,
            "UNS_SMTP_FROM",
            "UNS_EMAIL_FROM",
            "AGSIGNAL_SMTP_FROM",
            "AGSIGNAL_EMAIL_FROM",
        )
        smoke_to = _env_get(
            source_env,
            "UNS_SMOKE_EMAIL_TO",
            "UNS_EMAIL_TO",
            "AGSIGNAL_SMOKE_EMAIL_TO",
            "AGSIGNAL_EMAIL_TO",
        )
        recipients = [addr.strip() for addr in smoke_to.split(",") if addr.strip()]
        if not (smtp_host and smtp_from and recipients):
            raise AdapterConfigurationError(
                "Email is not configured; set UNS_SMTP_HOST, UNS_SMTP_FROM, and UNS_SMOKE_EMAIL_TO",
                channel=Channel.EMAIL,
            )
        smtp_port = int(_env_get(source_env, "UNS_SMTP_PORT", "AGSIGNAL_SMTP_PORT") or "587")
        smtp_user = _env_get(source_env, "UNS_SMTP_USER", "AGSIGNAL_SMTP_USER")
        smtp_password = _env_get(source_env, "UNS_SMTP_PASSWORD", "AGSIGNAL_SMTP_PASSWORD")
        use_ssl = _env_get(source_env, "UNS_SMTP_USE_SSL").lower() in {"1", "true", "yes", "on"}
        use_tls_raw = _env_get(source_env, "UNS_SMTP_USE_TLS")
        use_tls = (
            not use_ssl
            if not use_tls_raw
            else use_tls_raw.lower() in {"1", "true", "yes", "on"}
        )
        return EmailAdapter(
            EmailConfig(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                username=smtp_user,
                password=smtp_password,
                from_address=smtp_from,
                default_to_addresses=recipients,
                use_tls=use_tls,
                use_ssl=use_ssl,
                retry_attempts=1,
            )
        )

    if normalized == "pagerduty":
        routing_key = _env_get(
            source_env, "UNS_PAGERDUTY_ROUTING_KEY", "AGSIGNAL_PAGERDUTY_ROUTING_KEY"
        )
        if not routing_key:
            raise AdapterConfigurationError(
                "PagerDuty is not configured; set UNS_PAGERDUTY_ROUTING_KEY",
                channel=Channel.PAGERDUTY,
            )
        return PagerDutyAdapter(
            PagerDutyConfig(
                routing_key=routing_key,
                retry_attempts=1,
            )
        )

    raise ValueError(f"Unsupported channel {channel_name!r}; expected one of {SUPPORTED_CHANNELS}")


class _TimedAdapterProxy(BaseAdapter):
    """Wraps a real channel adapter to record wall-clock latency and provider receipt."""

    def __init__(self, inner: BaseAdapter) -> None:
        self._inner = inner
        self.guards_provider_attempts = getattr(inner, "guards_provider_attempts", False)
        self.last_result: DeliveryResult | None = None
        self.last_latency_ms: float | None = None

    @property
    def channel(self) -> Channel:
        return self._inner.channel

    async def deliver(self, notification: Notification) -> DeliveryResult:
        started = time.perf_counter()
        try:
            result = await self._inner.deliver(notification)
        except Exception as exc:
            self.last_latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            self.last_result = DeliveryResult(
                success=False,
                channel=self.channel,
                error=str(exc),
                delivered_at=datetime.now(UTC),
            )
            raise
        self.last_latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        self.last_result = result
        return result

    async def health_check(self) -> HealthCheckResult:
        return await self._inner.health_check()


def _sanitize_receipt_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    sanitized: dict[str, Any] = {}
    for key, val in metadata.items():
        if key == "recipients" and isinstance(val, list):
            sanitized[key] = [_mask_email(str(item)) for item in val]
        else:
            sanitized[key] = val
    return sanitized


async def run_channel_smoke(
    *,
    execute: bool = False,
    selected_channels: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    adapter_overrides: Mapping[str, BaseAdapter] | None = None,
    principal: str = "opt-in-smoke-operator",
) -> dict[str, Any]:
    """Check readiness and optionally execute `[UNS OPT-IN SMOKE]` provider deliveries."""
    readiness = inspect_channel_readiness(env=env)
    targets = [ch.lower() for ch in (selected_channels or list(SUPPORTED_CHANNELS))]
    for target in targets:
        if target not in readiness:
            raise ValueError(
                f"Unknown channel {target!r}; choose from {', '.join(SUPPORTED_CHANNELS)}"
            )

    configured_targets = [
        target
        for target in targets
        if readiness[target]["configured"]
        or (adapter_overrides is not None and target in adapter_overrides)
    ]

    if not execute or not configured_targets:
        mode = "dry_run" if not execute else "unconfigured_skip"
        return {
            "smoke_tag": SMOKE_TAG,
            "mode": mode,
            "execute_requested": execute,
            "external_traffic_sent": False,
            "selected_channels": targets,
            "configured_channels": configured_targets,
            "readiness": {ch: readiness[ch] for ch in targets},
            "attempts": [],
        }

    attempts_report: list[dict[str, Any]] = []
    with TemporaryDirectory() as temp_dir:
        db_url = f"sqlite:///{Path(temp_dir) / 'opt_in_smoke.db'}"
        registry = SimpleAdapterRegistry()
        proxies: dict[str, _TimedAdapterProxy] = {}
        policies: list[NotificationPolicy] = []

        for target in configured_targets:
            try:
                base_adapter = (
                    adapter_overrides[target]
                    if adapter_overrides and target in adapter_overrides
                    else build_channel_adapter(target, env=env)
                )
            except (AdapterConfigurationError, ValueError) as exc:
                attempts_report.append(
                    {
                        "channel": target.upper(),
                        "notification_id": None,
                        "attempt_status": "FAILED",
                        "success": False,
                        "latency_ms": 0.0,
                        "provider_receipt": {
                            "message_id": None,
                            "delivered_at": None,
                            "metadata": {},
                            "error": str(exc),
                        },
                        "event_kinds": ["ADAPTER_CONFIGURATION_ERROR"],
                    }
                )
                continue
            proxy = _TimedAdapterProxy(base_adapter)
            proxies[target] = proxy
            registry.register(proxy)
            policies.append(
                NotificationPolicy(
                    notification_type=f"smoke.opt_in.{target}",
                    version="1.0.0",
                    intent=NotificationIntent.OPERATIONAL,
                    channels=[proxy.channel],
                    delivery_mode=DeliveryMode.BEST_EFFORT,
                    require_ack=False,
                    dedup_window_seconds=60,
                )
            )

        if proxies:
            runtime = Runtime(db_url, adapters=registry, max_attempts=1, create_tables=True)
            try:
                SQLAlchemyPolicyStore(runtime.sessions).save_snapshot(policies)
                agent_id = uuid4()
                run_id = uuid4().hex[:8]

                for target, proxy in proxies.items():
                    request = SendNotificationRequest(
                        notification_type=f"smoke.opt_in.{target}",
                        intent="OPERATIONAL",
                        title=f"{SMOKE_TAG} {target.upper()} verification signal ({run_id})",
                        message=(
                            f"{SMOKE_TAG} Real-channel acceptance verification for "
                            f"channel={target.upper()} run_id={run_id}."
                        ),
                        source="scripts.opt_in_channel_smoke",
                        autonomy_context={
                            "agent_id": str(agent_id),
                            "autonomy_mode": "LIVE",
                        },
                        idempotency_key=f"uns-opt-in-smoke-{target}-{run_id}",
                        correlation_id=f"uns-opt-in-smoke-{run_id}",
                        metadata={"smoke_tag": SMOKE_TAG, "target_channel": target.upper()},
                    )
                    response = await runtime.send(request, principal=principal)
                    events = runtime.events(response.notification_id)
                    delivery_result = proxy.last_result

                    attempts_report.append(
                        {
                            "channel": proxy.channel.value,
                            "notification_id": str(response.notification_id),
                            "attempt_status": response.status.value,
                            "success": bool(delivery_result and delivery_result.success),
                            "latency_ms": proxy.last_latency_ms,
                            "provider_receipt": {
                                "message_id": delivery_result.message_id if delivery_result else None,
                                "delivered_at": (
                                    delivery_result.delivered_at.isoformat()
                                    if delivery_result and delivery_result.delivered_at
                                    else None
                                ),
                                "metadata": _sanitize_receipt_metadata(
                                    delivery_result.metadata if delivery_result else None
                                ),
                                "error": delivery_result.error if delivery_result else None,
                            },
                            "event_kinds": [event["kind"] for event in events],
                        }
                    )
            finally:
                runtime.engine.dispose()

    return {
        "smoke_tag": SMOKE_TAG,
        "mode": "executed",
        "execute_requested": True,
        "external_traffic_sent": bool(proxies),
        "selected_channels": targets,
        "configured_channels": configured_targets,
        "readiness": {ch: readiness[ch] for ch in targets},
        "attempts": attempts_report,
    }


def format_smoke_report(report: dict[str, Any]) -> str:
    """Format a human-readable summary of channel readiness and any executed attempts."""
    lines = [
        f"{SMOKE_TAG} Channel Smoke Report (mode={report['mode']}, "
        f"external_traffic_sent={report['external_traffic_sent']})"
    ]
    lines.append("Channel Readiness:")
    for name in report["selected_channels"]:
        info = report["readiness"][name]
        status_label = "READY" if info["configured"] else "UNCONFIGURED"
        missing_text = (
            f" (missing: {', '.join(info['missing_env'])})" if info["missing_env"] else ""
        )
        lines.append(f"  - {info['channel']}: {status_label}{missing_text}")

    if report["attempts"]:
        lines.append("Provider Delivery Attempts:")
        for attempt in report["attempts"]:
            receipt = attempt["provider_receipt"]
            lines.append(
                f"  - {attempt['channel']}: Attempt status={attempt['attempt_status']} "
                f"success={attempt['success']} latency={attempt['latency_ms']}ms "
                f"message_id={receipt['message_id']} error={receipt['error']}"
            )
    else:
        lines.append(
            "No external provider calls executed "
            "(pass --execute with configured credentials to send live smoke signals)."
        )

    lines.append("Structured report:")
    lines.append(json.dumps(report, indent=2, sort_keys=True))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Opt-in real-provider smoke verifier for Slack, Email/SMTP, and PagerDuty. "
            "Defaults to --dry-run (no external network traffic)."
        )
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Inspect environment readiness without sending external traffic (default).",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Send a [UNS OPT-IN SMOKE] verification signal through configured provider adapter(s).",
    )
    parser.add_argument(
        "--channel",
        action="append",
        choices=SUPPORTED_CHANNELS,
        dest="channels",
        help="Limit inspection/execution to specific channel(s): slack, email, pagerduty.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the JSON report.",
    )
    return parser


def main(argv: list[str] | None = None, *, env: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    execute = bool(args.execute and not args.dry_run)
    report = asyncio.run(
        run_channel_smoke(
            execute=execute,
            selected_channels=args.channels,
            env=env,
        )
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_smoke_report(report))

    if report["mode"] == "executed" and any(
        not item["success"] or item["attempt_status"] != "DELIVERED"
        for item in report["attempts"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

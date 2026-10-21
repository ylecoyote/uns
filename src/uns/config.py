"""Runtime composition shared by HTTP, MCP and the command line."""

from __future__ import annotations

import os
from pathlib import Path

from notification.adapters import (
    EmailAdapter,
    EmailConfig,
    PagerDutyAdapter,
    PagerDutyConfig,
    SlackAdapter,
    SlackConfig,
)
from notification.service import SimpleAdapterRegistry
from uns.runtime import Runtime

_default: Runtime | None = None


def value(name: str, default: str = "") -> str:
    return os.environ.get("UNS_" + name, os.environ.get("AGSIGNAL_" + name, default))


def configured_adapters() -> SimpleAdapterRegistry:
    registry = SimpleAdapterRegistry()
    if value("SLACK_BOT_TOKEN"):
        registry.register(
            SlackAdapter(
                SlackConfig(
                    bot_token=value("SLACK_BOT_TOKEN"), default_channel=value("SLACK_CHANNEL")
                )
            )
        )
    if value("PAGERDUTY_ROUTING_KEY"):
        registry.register(
            PagerDutyAdapter(PagerDutyConfig(routing_key=value("PAGERDUTY_ROUTING_KEY")))
        )
    if value("SMTP_HOST"):
        registry.register(
            EmailAdapter(
                EmailConfig(
                    smtp_host=value("SMTP_HOST"),
                    smtp_port=int(value("SMTP_PORT", "587")),
                    username=value("SMTP_USER"),
                    password=value("SMTP_PASSWORD"),
                    from_address=value("EMAIL_FROM"),
                    default_to_addresses=value("EMAIL_TO").split(","),
                )
            )
        )
    return registry


def build_runtime() -> Runtime:
    url = value("DATABASE_URL", os.environ.get("DATABASE_URL", "sqlite://"))
    runtime = Runtime(
        url,
        adapters=configured_adapters(),
        create_tables=url == "sqlite://" or value("CREATE_TABLES").lower() == "true",
    )
    try:
        configure_runtime_policies(runtime)
    except Exception:
        runtime.engine.dispose()
        raise
    return runtime


def configure_runtime_policies(runtime: Runtime) -> None:
    """Apply an explicitly configured directory through the durable policy authority."""
    policy_dir = value("POLICY_DIR")
    if policy_dir:
        from db.policy_store import SQLAlchemyPolicyStore
        from notification.policies import PolicyRegistry
        from notification.policy_loader import load_policies_from_directory

        registry = PolicyRegistry(runtime_only=False)
        load_policies_from_directory(Path(policy_dir), registry=registry)
        SQLAlchemyPolicyStore(runtime.sessions).save_snapshot(list(registry.get_all().values()))


def get_runtime() -> Runtime:
    global _default
    if _default is None:
        _default = build_runtime()
    return _default

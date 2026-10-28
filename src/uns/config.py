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
from uns.database import is_in_memory_database_url
from uns.runtime import Runtime

_default: Runtime | None = None


def value(name: str, default: str = "") -> str:
    return os.environ.get("UNS_" + name, default)


def database_url(default: str = "") -> str:
    return value("DATABASE_URL", os.environ.get("DATABASE_URL", default)).strip()


def configured_adapters() -> SimpleAdapterRegistry:
    registry = SimpleAdapterRegistry()
    if value("SLACK_BOT_TOKEN"):
        registry.register(
            SlackAdapter(
                SlackConfig(
                    bot_token=value("SLACK_BOT_TOKEN"),
                    default_channel=value("SLACK_CHANNEL") or "#general",
                )
            )
        )
    if value("PAGERDUTY_ROUTING_KEY"):
        registry.register(
            PagerDutyAdapter(PagerDutyConfig(routing_key=value("PAGERDUTY_ROUTING_KEY")))
        )
    if value("SMTP_HOST"):
        to_addresses = [addr.strip() for addr in value("EMAIL_TO").split(",") if addr.strip()]
        registry.register(
            EmailAdapter(
                EmailConfig(
                    smtp_host=value("SMTP_HOST"),
                    smtp_port=int(value("SMTP_PORT", "587")),
                    username=value("SMTP_USER"),
                    password=value("SMTP_PASSWORD"),
                    from_address=value("EMAIL_FROM") or "noreply@uns.local",
                    default_to_addresses=to_addresses,
                )
            )
        )
    return registry


def ensure_daemon_persistence_configured(*, allow_in_memory: bool = False) -> str:
    """Validate that daemon startup has an explicit persistent database or opt-in volatile flag."""
    raw_url = database_url()
    env_allow = value("ALLOW_IN_MEMORY", "false").strip().lower() in {"1", "true", "yes", "on"}
    if is_in_memory_database_url(raw_url) and not (allow_in_memory or env_allow):
        raise RuntimeError(
            "Refusing to start the UNS daemon with volatile in-memory storage. "
            "Set UNS_DATABASE_URL to a persistent SQLite path (for example, "
            "sqlite:////var/lib/uns/uns.db) or pass --in-memory / "
            "UNS_ALLOW_IN_MEMORY=true for ephemeral local testing."
        )
    return raw_url or "sqlite://"


def build_runtime(*, require_persistent: bool = False) -> Runtime:
    if require_persistent:
        url = ensure_daemon_persistence_configured()
    else:
        url = database_url("sqlite://") or "sqlite://"
    runtime = Runtime(
        url,
        adapters=configured_adapters(),
        create_tables=is_in_memory_database_url(url) or value("CREATE_TABLES").lower() == "true",
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

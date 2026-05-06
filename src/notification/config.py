"""Standalone configuration for AGSignal Core."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True)
class NotificationConfig:
    """Environment-backed AGSignal Core configuration with compatibility defaults."""

    redis_url: str = "redis://localhost:6379/0"
    dedup_ttl_seconds: int = 300
    idempotency_ttl_seconds: int = 86_400
    dlq_key: str = "uns:dlq"
    slack_webhook_url: str | None = None
    pagerduty_routing_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    @classmethod
    def from_env(cls) -> NotificationConfig:
        """Create config from current `UNS_*` compatibility environment variables."""
        return cls(
            redis_url=os.environ.get("UNS_REDIS_URL", cls.redis_url),
            dedup_ttl_seconds=_env_int("UNS_DEDUP_TTL_SECONDS", cls.dedup_ttl_seconds),
            idempotency_ttl_seconds=_env_int(
                "UNS_IDEMPOTENCY_TTL_SECONDS", cls.idempotency_ttl_seconds
            ),
            dlq_key=os.environ.get("UNS_DLQ_KEY", cls.dlq_key),
            slack_webhook_url=os.environ.get("UNS_SLACK_WEBHOOK_URL"),
            pagerduty_routing_key=os.environ.get("UNS_PAGERDUTY_ROUTING_KEY"),
            smtp_host=os.environ.get("UNS_SMTP_HOST"),
            smtp_port=_env_int("UNS_SMTP_PORT", cls.smtp_port),
            smtp_user=os.environ.get("UNS_SMTP_USER"),
            smtp_password=os.environ.get("UNS_SMTP_PASSWORD"),
        )


def get_notification_config() -> NotificationConfig:
    """Return current notification config from environment."""
    return NotificationConfig.from_env()

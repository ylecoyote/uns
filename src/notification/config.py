"""Standalone configuration for UNS Core."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class NotificationConfig:
    """Environment-backed UNS Core configuration with defaults."""

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
    websocket_redis_enabled: bool = False
    websocket_redis_channel: str = "uns:websocket"

    @classmethod
    def from_env(cls) -> NotificationConfig:
        """Create config from `UNS_*` environment variables."""
        return cls(
            redis_url=_env("UNS_REDIS_URL", cls.redis_url) or cls.redis_url,
            dedup_ttl_seconds=_env_int("UNS_DEDUP_TTL_SECONDS", cls.dedup_ttl_seconds),
            idempotency_ttl_seconds=_env_int(
                "UNS_IDEMPOTENCY_TTL_SECONDS",
                cls.idempotency_ttl_seconds,
            ),
            dlq_key=_env("UNS_DLQ_KEY", cls.dlq_key) or cls.dlq_key,
            slack_webhook_url=_env("UNS_SLACK_WEBHOOK_URL"),
            pagerduty_routing_key=_env("UNS_PAGERDUTY_ROUTING_KEY"),
            smtp_host=_env("UNS_SMTP_HOST"),
            smtp_port=_env_int("UNS_SMTP_PORT", cls.smtp_port),
            smtp_user=_env("UNS_SMTP_USER"),
            smtp_password=_env("UNS_SMTP_PASSWORD"),
            websocket_redis_enabled=_env_bool(
                "UNS_WEBSOCKET_REDIS_ENABLED",
                cls.websocket_redis_enabled,
            ),
            websocket_redis_channel=_env(
                "UNS_WEBSOCKET_REDIS_CHANNEL",
                cls.websocket_redis_channel,
            )
            or cls.websocket_redis_channel,
        )


def get_notification_config() -> NotificationConfig:
    """Return current notification config from environment."""
    return NotificationConfig.from_env()

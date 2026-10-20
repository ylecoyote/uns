"""Standalone configuration for AGSignal Core."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass


def _legacy_warn(legacy_name: str, modern_name: str, *, stacklevel: int = 3) -> None:
    warnings.warn(
        f"{legacy_name} is deprecated. Use {modern_name} instead. "
        f"UNS_* aliases will be removed in v1.0.",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def _env(
    name: str,
    legacy_name: str,
    default: str | None = None,
    *,
    stacklevel: int = 3,
) -> str | None:
    value = os.environ.get(legacy_name)  # UNS is the canonical product namespace.
    if value is not None:
        return value
    return os.environ.get(name, default)


def _env_int_pair(name: str, legacy_name: str, default: int) -> int:
    raw = _env(name, legacy_name, stacklevel=4)
    return int(raw) if raw is not None else default


def _env_bool_pair(name: str, legacy_name: str, default: bool) -> bool:
    raw = _env(name, legacy_name, stacklevel=4)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


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
    websocket_redis_enabled: bool = False
    websocket_redis_channel: str = "agsignal:websocket"

    @classmethod
    def from_env(cls) -> NotificationConfig:
        """Create config from `AGSIGNAL_*` variables with `UNS_*` compatibility."""
        return cls(
            redis_url=_env("AGSIGNAL_REDIS_URL", "UNS_REDIS_URL", cls.redis_url)
            or cls.redis_url,
            dedup_ttl_seconds=_env_int_pair(
                "AGSIGNAL_DEDUP_TTL_SECONDS",
                "UNS_DEDUP_TTL_SECONDS",
                cls.dedup_ttl_seconds,
            ),
            idempotency_ttl_seconds=_env_int_pair(
                "AGSIGNAL_IDEMPOTENCY_TTL_SECONDS",
                "UNS_IDEMPOTENCY_TTL_SECONDS",
                cls.idempotency_ttl_seconds,
            ),
            dlq_key=_env("AGSIGNAL_DLQ_KEY", "UNS_DLQ_KEY", cls.dlq_key) or cls.dlq_key,
            slack_webhook_url=_env("AGSIGNAL_SLACK_WEBHOOK_URL", "UNS_SLACK_WEBHOOK_URL"),
            pagerduty_routing_key=_env(
                "AGSIGNAL_PAGERDUTY_ROUTING_KEY",
                "UNS_PAGERDUTY_ROUTING_KEY",
            ),
            smtp_host=_env("AGSIGNAL_SMTP_HOST", "UNS_SMTP_HOST"),
            smtp_port=_env_int_pair("AGSIGNAL_SMTP_PORT", "UNS_SMTP_PORT", cls.smtp_port),
            smtp_user=_env("AGSIGNAL_SMTP_USER", "UNS_SMTP_USER"),
            smtp_password=_env("AGSIGNAL_SMTP_PASSWORD", "UNS_SMTP_PASSWORD"),
            websocket_redis_enabled=_env_bool_pair(
                "AGSIGNAL_WEBSOCKET_REDIS_ENABLED",
                "UNS_WEBSOCKET_REDIS_ENABLED",
                cls.websocket_redis_enabled,
            ),
            websocket_redis_channel=_env(
                "AGSIGNAL_WEBSOCKET_REDIS_CHANNEL",
                "UNS_WEBSOCKET_REDIS_CHANNEL",
                cls.websocket_redis_channel,
            )
            or cls.websocket_redis_channel,
        )


def get_notification_config() -> NotificationConfig:
    """Return current notification config from environment."""
    return NotificationConfig.from_env()

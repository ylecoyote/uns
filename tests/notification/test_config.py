from __future__ import annotations

import warnings

import pytest

from notification.config import NotificationConfig


def test_notification_config_uses_standalone_defaults():
    config = NotificationConfig()

    assert config.redis_url == "redis://localhost:6379/0"
    assert config.dedup_ttl_seconds == 300
    assert config.idempotency_ttl_seconds == 86_400
    assert config.dlq_key == "uns:dlq"
    assert config.websocket_redis_enabled is False
    assert config.websocket_redis_channel == "uns:websocket"


def test_notification_config_reads_uns_prefixed_environment(monkeypatch):
    monkeypatch.setenv("UNS_REDIS_URL", "redis://redis.example:6379/4")
    monkeypatch.setenv("UNS_DEDUP_TTL_SECONDS", "900")
    monkeypatch.setenv("UNS_DLQ_KEY", "uns:custom-dlq")

    config = NotificationConfig.from_env()

    assert config.redis_url == "redis://redis.example:6379/4"
    assert config.dedup_ttl_seconds == 900
    assert config.dlq_key == "uns:custom-dlq"


def test_websocket_redis_fanout_can_be_enabled(monkeypatch):
    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_ENABLED", "true")
    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_CHANNEL", "uns:test")

    config = NotificationConfig.from_env()

    assert config.websocket_redis_enabled is True
    assert config.websocket_redis_channel == "uns:test"


def test_uns_env_var_does_not_emit_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading a UNS_* env var must not emit any deprecation warning."""
    monkeypatch.setenv("UNS_REDIS_URL", "redis://uns.example/0")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = NotificationConfig.from_env()

    assert config.redis_url == "redis://uns.example/0"
    legacy_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert not legacy_warnings, "UNS is canonical and must not warn"

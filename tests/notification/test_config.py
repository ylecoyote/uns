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
    assert config.websocket_redis_channel == "agsignal:websocket"


def test_notification_config_reads_uns_prefixed_environment(monkeypatch):
    monkeypatch.setenv("UNS_REDIS_URL", "redis://redis.example:6379/4")
    monkeypatch.setenv("UNS_DEDUP_TTL_SECONDS", "900")

    config = NotificationConfig.from_env()

    assert config.redis_url == "redis://redis.example:6379/4"
    assert config.dedup_ttl_seconds == 900


def test_notification_config_prefers_agsignal_environment(monkeypatch):
    monkeypatch.setenv("UNS_REDIS_URL", "redis://legacy.example:6379/4")
    monkeypatch.setenv("AGSIGNAL_REDIS_URL", "redis://agsignal.example:6379/5")
    monkeypatch.setenv("AGSIGNAL_DLQ_KEY", "agsignal:dlq")

    config = NotificationConfig.from_env()

    assert config.redis_url == "redis://agsignal.example:6379/5"
    assert config.dlq_key == "agsignal:dlq"


def test_websocket_redis_fanout_can_be_enabled(monkeypatch):
    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_ENABLED", "true")
    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_CHANNEL", "agsignal:test")

    config = NotificationConfig.from_env()

    assert config.websocket_redis_enabled is True
    assert config.websocket_redis_channel == "agsignal:test"


def test_uns_env_var_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading a UNS_* env var (without an AGSIGNAL_* override) must warn."""
    from notification.config import NotificationConfig

    monkeypatch.delenv("AGSIGNAL_REDIS_URL", raising=False)
    monkeypatch.setenv("UNS_REDIS_URL", "redis://legacy.example/0")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = NotificationConfig.from_env()

    assert config.redis_url == "redis://legacy.example/0"
    legacy_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert legacy_warnings, "Expected DeprecationWarning when UNS_* is used"
    assert any("UNS_REDIS_URL" in str(w.message) for w in legacy_warnings)


def test_agsignal_env_var_does_not_warn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Using the modern AGSIGNAL_* var must not warn even if UNS_* is also set."""
    from notification.config import NotificationConfig

    monkeypatch.setenv("AGSIGNAL_REDIS_URL", "redis://modern.example/0")
    monkeypatch.setenv("UNS_REDIS_URL", "redis://legacy.example/0")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = NotificationConfig.from_env()

    assert config.redis_url == "redis://modern.example/0"
    legacy_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert not legacy_warnings, "Expected no DeprecationWarning when AGSIGNAL_* is set"

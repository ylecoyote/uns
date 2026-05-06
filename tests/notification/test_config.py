from __future__ import annotations

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


def test_websocket_redis_fanout_can_be_enabled(monkeypatch):
    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_ENABLED", "true")
    monkeypatch.setenv("UNS_WEBSOCKET_REDIS_CHANNEL", "agsignal:test")

    config = NotificationConfig.from_env()

    assert config.websocket_redis_enabled is True
    assert config.websocket_redis_channel == "agsignal:test"

from __future__ import annotations

from uuid import uuid4

from notification.idempotency import IdempotencyService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return int(existed)


def test_idempotency_returns_existing_notification_for_same_source_and_key():
    redis = FakeRedis()
    service = IdempotencyService(redis, ttl_seconds=60)
    notification_id = uuid4()

    assert service.mark_processed("agent_governor", "approval-1", notification_id, "job-1")

    existing = service.get_existing("agent_governor", "approval-1")

    assert existing is not None
    assert existing.notification_id == notification_id
    assert existing.job_id == "job-1"
    assert existing.source == "agent_governor"
    assert existing.idempotency_key == "approval-1"


def test_idempotency_namespaces_keys_by_source():
    redis = FakeRedis()
    service = IdempotencyService(redis, ttl_seconds=60)
    notification_id = uuid4()

    assert service.mark_processed("agent_governor", "same-key", notification_id, "job-1")

    assert service.get_existing("execution_alerts", "same-key") is None


def test_idempotency_sanitizes_colons_in_redis_key():
    redis = FakeRedis()
    service = IdempotencyService(redis, ttl_seconds=60)

    service.mark_processed("agent:governor", "approval:1", uuid4(), "job-1")

    assert "uns:idem:agent_governor:approval_1" in redis.values

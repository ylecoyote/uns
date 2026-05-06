from __future__ import annotations

from uuid import uuid4

from notification.dlq import DLQEntry, DLQService
from notification.models import AutonomyContext, AutonomyMode, Notification, NotificationIntent


class FakeRedisList:
    def __init__(self) -> None:
        self.values: list[str] = []

    def lpush(self, key: str, value: str) -> int:
        self.values.insert(0, value)
        return len(self.values)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        stop = None if end == -1 else end + 1
        return self.values[start:stop]

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        next_values = []
        for item in self.values:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            next_values.append(item)
        self.values = next_values
        return removed

    def llen(self, key: str) -> int:
        return len(self.values)


def _notification() -> Notification:
    return Notification(
        notification_type="safety.kill_switch",
        intent=NotificationIntent.SAFETY,
        autonomy_context=AutonomyContext(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
        ),
        title="Kill switch",
        message="Kill switch engaged",
        source="agent_governor",
    )


def test_dlq_records_notification_failure_with_reason():
    redis = FakeRedisList()
    service = DLQService(redis_client=redis, key="uns:test:dlq")
    notification = _notification()

    entry = service.enqueue(notification, reason="all persistent channels failed")

    assert entry.notification_id == notification.notification_id
    assert entry.notification_type == "safety.kill_switch"
    assert entry.reason == "all persistent channels failed"
    assert service.depth() == 1
    assert service.list_entries()[0] == entry


def test_dlq_remove_deletes_matching_entry():
    redis = FakeRedisList()
    service = DLQService(redis_client=redis, key="uns:test:dlq")
    entry = service.enqueue(_notification(), reason="failed")

    assert service.remove(entry.entry_id)

    assert service.depth() == 0


def test_dlq_entry_roundtrips_json():
    entry = DLQEntry(
        notification_id=uuid4(),
        notification_type="execution.slippage",
        intent="OPERATIONAL",
        source="execution_alerts",
        reason="slack timeout",
    )

    assert DLQEntry.from_json(entry.to_json()) == entry

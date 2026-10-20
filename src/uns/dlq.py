"""Compatibility view of SQL exhausted failures through the existing DLQ API."""

from uuid import UUID

from notification.dlq import DLQEntry, DLQService
from uns.runtime import Runtime


class RuntimeDLQ(DLQService):
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def list_entries(self, start: int = 0, end: int = -1) -> list[DLQEntry]:
        entries = []
        for item in self.runtime.dead_letters():
            row = self.runtime.get(item["notification_id"])
            n = row["notification"]
            entries.append(
                DLQEntry(
                    entry_id=UUID(row["id"]),
                    notification_id=UUID(row["id"]),
                    notification_type=n["notification_type"],
                    intent=n["intent"],
                    source=n["source"],
                    reason="guaranteed_delivery_exhausted",
                    created_at=n["created_at"],
                    metadata=item,
                )
            )
        return entries[start:] if end == -1 else entries[start : end + 1]

    def depth(self) -> int:
        return len(self.runtime.dead_letters())

    def remove(self, entry_id: UUID) -> bool:
        raise ValueError("Use the authenticated operator route to resolve a failure")

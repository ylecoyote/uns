"""In-memory shims for development and testing only.

The classes here mimic the subset of Redis-list semantics that UNS's
DLQ and websocket-replay paths rely on, so the system can run end-to-end
without a real Redis instance during local dev or CI. They are NOT
production-grade.

The leading-underscore module name ('_in_memory') flags this as private
to the uns package: it is intentionally not re-exported from
uns.__init__ and is not part of the SDK surface.
"""

from __future__ import annotations


class InMemoryRedisList:
    """Minimal Redis-list compatible store for standalone local operation.

    Implements lpush, lrange, lrem, llen — the surface that
    DLQService and the websocket-replay store consume. Not thread-safe
    and not durable. For real deployments, configure a real Redis client.
    """

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


__all__ = ["InMemoryRedisList"]

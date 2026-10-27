"""UNS-branded deduplication aliases."""

from notification.deduplication import (
    DeduplicationEngine,
    DeduplicationStrategy,
    InMemoryDeduplicationStore,
    InMemoryDeduplicationStrategy,
    RedisDeduplicationStore,
    RedisDeduplicationStrategy,
    configure_deduplication_engine,
    create_inmemory_deduplication_engine,
    create_redis_deduplication_engine,
    generate_dedup_key,
    get_deduplication_engine,
    reset_deduplication_engine,
    should_deduplicate,
)

__all__ = [
    "DeduplicationEngine",
    "DeduplicationStrategy",
    "InMemoryDeduplicationStore",
    "InMemoryDeduplicationStrategy",
    "RedisDeduplicationStore",
    "RedisDeduplicationStrategy",
    "configure_deduplication_engine",
    "create_inmemory_deduplication_engine",
    "create_redis_deduplication_engine",
    "generate_dedup_key",
    "get_deduplication_engine",
    "reset_deduplication_engine",
    "should_deduplicate",
]

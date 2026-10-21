"""Additive runtime migrations for existing SQLite stores.

SQLite startup migrations take a writer reservation before inspecting columns,
so concurrent processes cannot both apply an ALTER. Historical ownerless dedup
claims remain evidence only: intake never trusts them to suppress new work.
"""

from sqlalchemy import Connection, Engine, inspect, select, update

from db.models import Base

_COLUMNS = {
    "uns_notifications": {
        "cycle": "INTEGER NOT NULL DEFAULT 1",
        "cycle_attempts": "INTEGER NOT NULL DEFAULT 0",
        "dedup_key": "VARCHAR(64)",
        "dedup_owner_id": "VARCHAR(36)",
        "dedup_generation": "INTEGER",
        "dedup_successor_id": "VARCHAR(36)",
    },
    "uns_dedup": {
        "owner_id": "VARCHAR(36)",
        "generation": "INTEGER NOT NULL DEFAULT 1",
    },
}


def migrate_runtime_schema(engine: Engine, *, create_tables: bool = False) -> None:
    """Preserve existing work/history while installing columns and scan indexes."""
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        elif engine.dialect.name == "postgresql":
            # Stable application migration lock, held only for this transaction.
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(1431196485)")
        if create_tables:
            Base.metadata.create_all(connection)
        inspector = inspect(connection)
        present = set(inspector.get_table_names())
        for table_name, columns in _COLUMNS.items():
            if table_name not in present:
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for name, sql_type in columns.items():
                if name not in existing:
                    # Identifiers and types are exclusively static migration constants.
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {name} {sql_type}"
                    )
                    if name == "dedup_successor_id" and "uns_events" in present:
                        _backfill_successors(connection)
                    if name == "cycle_attempts":
                        connection.exec_driver_sql(
                            "UPDATE uns_notifications SET cycle_attempts = attempts"
                        )
        for table_name in ("uns_notifications", "uns_events"):
            if table_name in present:
                for index in Base.metadata.tables[table_name].indexes:
                    index.create(connection, checkfirst=True)

        if "uns_events" in present:
            events = Base.metadata.tables["uns_events"]
            # Old unattempted callbacks used zero, unfairly preceding old retries.
            connection.execute(
                update(events)
                .where(
                    events.c.callback_pending.is_(True),
                    events.c.callback_until == 0,
                    events.c.callback_token.is_(None),
                )
                .values(callback_until=events.c.at)
            )


def _backfill_successors(connection: Connection) -> None:
    """Recover promotion-connected obligations, never infer from a key alone.

    Legacy replay could deliver a failed predecessor after its successors failed.
    Orient failed members toward recorded satisfaction, then unresolved/pruned
    evidence, then live recovery. All-failed complete groups remain recoverable.
    Event timestamps/UUID ordering cannot distinguish tied replay cycles.
    """
    work = Base.metadata.tables["uns_notifications"]
    events = Base.metadata.tables["uns_events"]
    rows = {r["id"]: r for r in connection.execute(select(work)).mappings()}
    links: dict[str, set[str]] = {}
    for event in connection.execute(
        select(events).where(events.c.kind == "DEDUP_OWNER_PROMOTED")
    ).mappings():
        predecessor = event["payload"].get("previous_owner_id")
        successor = event["notification_id"]
        if not isinstance(predecessor, str) or predecessor == successor:
            continue
        old, new = rows.get(predecessor), rows.get(successor)
        if old and new and old["dedup_key"] != new["dedup_key"]:
            continue
        links.setdefault(predecessor, set()).add(successor)
        links.setdefault(successor, set()).add(predecessor)
    seen: set[str] = set()
    for identifier in links:
        if identifier in seen:
            continue
        component: set[str] = set()
        todo = [identifier]
        while todo:
            node = todo.pop()
            if node in component:
                continue
            component.add(node)
            todo.extend(links[node] - component)
        seen.update(component)
        present = [rows[node] for node in component if node in rows]
        # Do not join different effective scopes through a missing intermediate.
        keys = {row["dedup_key"] for row in present}
        missing = sorted(component - rows.keys())
        delivered = sorted(
            row["id"] for row in present if row["status"] in ("DELIVERED", "DEDUPLICATED")
        )
        pending = sorted(row["id"] for row in present if row["status"] == "PENDING")
        failed = sorted(
            (row for row in present if row["status"] == "FAILED"),
            key=lambda row: (row["dedup_generation"] or 0, row["id"]),
        )
        if not failed:
            continue
        if len(keys) != 1:
            # Malformed historical links must not manufacture successful delivery.
            for row in failed:
                connection.execute(
                    update(work).where(work.c.id == row["id"]).values(dedup_successor_id=row["id"])
                )
            continue
        target = (delivered or missing or pending or [failed[-1]["id"]])[0]
        for row in failed:
            connection.execute(
                update(work)
                .where(work.c.id == row["id"])
                .values(dedup_successor_id=target if row["id"] != target else None)
            )

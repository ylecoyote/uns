"""Additive runtime migrations for existing SQLite stores.

SQLite startup migrations take a writer reservation before inspecting columns,
so concurrent processes cannot both apply an ALTER. Historical ownerless dedup
claims remain evidence only: intake never trusts them to suppress new work.
"""

from sqlalchemy import Engine, inspect

from db.models import Base

_COLUMNS = {
    "uns_notifications": {
        "cycle": "INTEGER NOT NULL DEFAULT 1",
        "cycle_attempts": "INTEGER NOT NULL DEFAULT 0",
        "dedup_key": "VARCHAR(64)",
        "dedup_owner_id": "VARCHAR(36)",
        "dedup_generation": "INTEGER",
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
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {name} {sql_type}")
                    if name == "cycle_attempts":
                        connection.exec_driver_sql(
                            "UPDATE uns_notifications SET cycle_attempts = attempts"
                        )
        for table_name in ("uns_notifications", "uns_events"):
            if table_name in present:
                for index in Base.metadata.tables[table_name].indexes:
                    index.create(connection, checkfirst=True)

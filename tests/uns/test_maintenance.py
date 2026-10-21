"""Retention uses temporary SQLite stores and never contacts providers."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, create_mock_engine, insert, inspect, select, update

from db.models import AckAuditRecord, NotificationAuditRecord
from uns.maintenance import main, maintain
from uns.runtime import Runtime, dedup, events, work
from uns.schema import migrate_runtime_schema

NOW = 2_000_000.0
OLD = NOW - 1_000


@pytest.fixture
def store(tmp_path):
    runtime = Runtime(f"sqlite:///{tmp_path}/retention.db", create_tables=True)
    yield runtime
    runtime.engine.dispose()


def add_notification(store, *, at=OLD, **changes):
    identifier = str(uuid4())
    row = {
        "id": identifier,
        "key": identifier,
        "fingerprint": identifier,
        "principal": "producer",
        "notification": {"message": "retained evidence"},
        "status": "DELIVERED",
        "outcome": {"status": "DELIVERED"},
        "attempts": 1,
        "next_attempt": at,
        "lease_until": 0,
        "dead_letter": False,
        "delivered_at": at,
    }
    row.update(changes)
    timestamp = datetime.fromtimestamp(at, UTC)
    with store.engine.begin() as connection:
        connection.execute(insert(work).values(**row))
        connection.execute(
            insert(events).values(
                id=str(uuid4()),
                notification_id=identifier,
                kind="DELIVERY_RESULT",
                at=at,
                payload={"status": row["status"]},
            )
        )
        connection.execute(
            insert(NotificationAuditRecord).values(
                notification_id=UUID(identifier),
                notification_type="test.retention",
                status=row["status"],
                intent="SAFETY",
                delivery_mode="BEST_EFFORT",
                autonomy_mode="LIVE",
                agent_id=uuid4(),
                title="Retention test",
                source="test",
                notification_created_at=timestamp,
                delivered_at=timestamp,
                created_at=timestamp,
            )
        )
    return identifier


def run(store, **changes):
    args = {"cutoff": NOW - 10, "idempotency_seconds": 100, "now": NOW}
    args.update(changes)
    return maintain(store.engine, **args)


def rows(store, table):
    with store.engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(table)).mappings()]


def test_dry_run_is_default_and_does_not_mutate(store):
    identifier = add_notification(store)
    before = rows(store, events)
    report = run(store)
    assert report["applied"] is False
    assert report["notification_ids"] == [identifier]
    assert len(rows(store, work)) == 1
    assert rows(store, events) == before


@pytest.mark.parametrize(
    "arguments",
    [
        {"apply": True},
        {"apply": True, "operator": "   "},
        {"cutoff": NOW + 1},
        {"cutoff": float("nan")},
        {"idempotency_seconds": 0},
        {"idempotency_seconds": float("inf")},
        {"batch_size": 0},
        {"batch_size": 1001},
        {"batch_size": True},
    ],
)
def test_invalid_requests_cannot_mutate(store, arguments):
    add_notification(store)
    with pytest.raises(ValueError):
        run(store, **arguments)
    assert len(rows(store, work)) == 1
    assert len(rows(store, events)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "PENDING"},
        {"status": "UNRECOGNIZED"},
        {"ack_status": "PENDING"},
        {"ack_status": "UNRECOGNIZED"},
        {"dead_letter": True},
        {"lease_until": NOW + 10},
        {"lease_token": "possibly-still-running"},
        {"responded_at": NOW - 50},
        {"delivered_at": NOW - 50},
    ],
)
def test_protects_unsettled_or_recent_notifications(store, changes):
    add_notification(store, **changes)
    assert run(store, apply=True, operator="operator")["notification_ids"] == []
    assert len(rows(store, work)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"callback_pending": True},
        {"callback_pending": True, "callback_attempts": 3},
        {"callback_token": "in-flight"},
        {"callback_until": NOW + 30},
    ],
)
def test_protects_queued_exhausted_and_inflight_callbacks(store, changes):
    identifier = add_notification(store)
    with store.engine.begin() as connection:
        connection.execute(update(events).values(**changes))
    assert run(store, archive=Path("/unused/archive.json"))["notification_ids"] == []
    assert rows(store, work)[0]["id"] == identifier


def test_stricter_cutoff_and_idempotency_horizon_both_apply(store):
    recent = add_notification(store, at=NOW - 50)
    old = add_notification(store)
    assert run(store)["notification_ids"] == [old]
    assert run(store, cutoff=OLD - 1)["notification_ids"] == []
    assert recent in [row["id"] for row in rows(store, work)]


def test_requires_age_evidence_and_preserves_recent_audit(store):
    identifier = add_notification(store)
    with store.engine.begin() as connection:
        connection.execute(
            update(NotificationAuditRecord).values(created_at=datetime.fromtimestamp(NOW - 1, UTC))
        )
    assert run(store)["notification_ids"] == []
    with store.engine.begin() as connection:
        connection.execute(events.delete().where(events.c.notification_id == identifier))
    assert run(store)["notification_ids"] == []


def test_protects_dedup_owner_until_window_expires(store):
    identifier = add_notification(store)
    with store.engine.begin() as connection:
        connection.execute(insert(dedup).values(key="claim", until=NOW + 1, owner_id=identifier))
    assert run(store)["notification_ids"] == []
    with store.engine.begin() as connection:
        connection.execute(update(dedup).values(until=NOW - 1))
    report = run(store, apply=True, operator="operator")
    assert report["notification_ids"] == [identifier]
    assert report["dedup_keys"] == ["claim"]
    assert rows(store, dedup) == []


def test_retained_follower_protects_owner_across_batches(store):
    owner = add_notification(store)
    follower = add_notification(store, status="DEDUPLICATED", dedup_owner_id=owner)
    first = run(store, apply=True, operator="operator")
    assert first["notification_ids"] == [follower]
    assert rows(store, work)[0]["id"] == owner
    assert run(store, apply=True, operator="operator")["notification_ids"] == [owner]


def test_expired_dedup_with_live_owner_and_unexpired_legacy_claim_are_retained(store):
    identifier = add_notification(store, status="PENDING")
    with store.engine.begin() as connection:
        connection.execute(
            insert(dedup),
            [
                {"key": "owned", "until": OLD, "owner_id": identifier},
                {"key": "legacy-live", "until": NOW + 1, "owner_id": None},
                {"key": "legacy-expired", "until": OLD, "owner_id": None},
            ],
        )
    assert run(store, apply=True, operator="operator")["dedup_keys"] == ["legacy-expired"]
    assert {row["key"] for row in rows(store, dedup)} == {"owned", "legacy-live"}


def test_operational_mode_preserves_audit_and_full_removed_state(store):
    identifier = add_notification(store)
    old_events = rows(store, events)
    old_audit = rows(store, NotificationAuditRecord)
    report = run(store, apply=True, operator="cleanup-operator")
    assert rows(store, work) == []
    assert rows(store, NotificationAuditRecord) == old_audit
    retained = rows(store, events)
    assert old_events[0] in retained
    receipt = next(row for row in retained if row["kind"] == "RETENTION_APPLIED")
    assert receipt["payload"]["operator"] == "cleanup-operator"
    assert receipt["payload"]["removed"]["uns_notifications"][0]["id"] == identifier
    assert receipt["id"] == report["receipt_id"]


def test_batch_budget_bounds_all_deleted_rows(store):
    for _ in range(5):
        add_notification(store)
    with store.engine.begin() as connection:
        connection.execute(insert(dedup).values(key="expired", until=OLD))
    report = run(store, apply=True, operator="operator", batch_size=2)
    assert report["deleted_rows"] == 2
    assert len(rows(store, work)) == 3
    assert len(rows(store, dedup)) == 1


def test_archive_is_verified_before_pruning_settled_group(store, tmp_path):
    identifier = add_notification(store, ack_status="ACKED", responded_at=OLD)
    with store.engine.begin() as connection:
        connection.execute(
            insert(AckAuditRecord).values(
                notification_id=UUID(identifier),
                old_status="PENDING",
                new_status="ACKED",
                acked_by="human",
                acked_at=datetime.fromtimestamp(OLD, UTC),
                created_at=datetime.fromtimestamp(OLD, UTC),
            )
        )
    archive = tmp_path / "archive.json"
    preview = run(store, archive=archive)
    assert preview["deleted_rows"] == 4
    assert not archive.exists()
    report = run(store, apply=True, operator="archivist", archive=archive)
    assert archive.stat().st_mode & 0o777 == 0o600
    artifact = json.loads(archive.read_text())
    assert artifact["tables"]["uns_notifications"][0]["id"] == identifier
    assert len(artifact["tables"]["notification_audit_records"]) == 1
    assert len(artifact["tables"]["ack_audit_records"]) == 1
    assert rows(store, work) == []
    assert rows(store, NotificationAuditRecord) == []
    assert rows(store, AckAuditRecord) == []
    receipt = rows(store, events)
    assert len(receipt) == 1
    payload = receipt[0]["payload"]
    assert payload["operator"] == "archivist"
    assert payload["archive"]["sha256"] == report["archive"]["sha256"]
    assert payload["archive"]["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert "removed" not in payload
    assert payload["deleted_rows"] == 4


def test_archive_batch_cannot_partially_delete_large_group(store, tmp_path):
    identifier = add_notification(store)
    archive = tmp_path / "archive.json"
    report = run(store, apply=True, operator="operator", archive=archive, batch_size=2)
    assert report["notification_ids"] == []
    assert report["oversized_notification_ids"] == [identifier]
    assert not archive.exists()
    assert len(rows(store, events)) == 1
    assert len(rows(store, NotificationAuditRecord)) == 1


@pytest.mark.parametrize(
    "boundary", ["write", "file-fsync", "directory-fsync", "verify", "receipt"]
)
def test_archive_failures_never_commit_deletions(store, tmp_path, monkeypatch, boundary):
    from uns import maintenance

    identifier = add_notification(store)
    archive = tmp_path / "failed.json"

    def fail(*args, **kwargs):
        raise OSError(f"injected {boundary}")

    if boundary == "write":
        monkeypatch.setattr(maintenance.os, "write", fail)
    elif boundary in ("file-fsync", "directory-fsync"):
        original = os.fsync
        calls = 0

        def fsync(fd):
            nonlocal calls
            calls += 1
            if calls == (1 if boundary == "file-fsync" else 2):
                fail()
            original(fd)

        monkeypatch.setattr(maintenance.os, "fsync", fsync)
    elif boundary == "verify":
        monkeypatch.setattr(maintenance, "_verify_archive", fail)
    else:
        monkeypatch.setattr(maintenance, "_record_receipt", fail)
    with pytest.raises(OSError, match="injected"):
        run(store, apply=True, operator="operator", archive=archive)
    assert rows(store, work)[0]["id"] == identifier
    assert len(rows(store, events)) == 1
    assert len(rows(store, NotificationAuditRecord)) == 1


@pytest.mark.parametrize("symlink", [False, True])
def test_archive_never_overwrites_existing_file_or_symlink(store, tmp_path, symlink):
    add_notification(store)
    target = tmp_path / "important.json"
    target.write_text("existing")
    archive = tmp_path / "archive.json" if symlink else target
    if symlink:
        archive.symlink_to(target)
    with pytest.raises(FileExistsError):
        run(store, apply=True, operator="operator", archive=archive)
    assert target.read_text() == "existing"
    assert len(rows(store, work)) == 1


def test_archive_holds_sqlite_writer_reservation(store, tmp_path, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from uns import maintenance

    identifier = add_notification(store)
    original = maintenance._write_archive

    def check_lock(*args, **kwargs):
        competitor = create_engine(store.engine.url, connect_args={"timeout": 0})
        try:
            with pytest.raises(OperationalError, match="locked"), competitor.begin() as connection:
                connection.execute(
                    update(work).where(work.c.id == identifier).values(status="PENDING")
                )
        finally:
            competitor.dispose()
        return original(*args, **kwargs)

    monkeypatch.setattr(maintenance, "_write_archive", check_lock)
    run(store, apply=True, operator="operator", archive=tmp_path / "archive.json")
    assert rows(store, work) == []


def test_cli_requires_explicit_window_and_defaults_to_dry_run(store, capsys):
    identifier = add_notification(store)
    main(
        [
            "--database-url",
            str(store.engine.url),
            "--cutoff",
            "1970-02-01T00:00:00Z",
            "--idempotency-seconds",
            "100",
        ]
    )
    assert json.loads(capsys.readouterr().out)["notification_ids"] == [identifier]
    assert len(rows(store, work)) == 1
    with pytest.raises(SystemExit):
        main(["--database-url", str(store.engine.url), "--cutoff", "1970-02-01T00:00:00Z"])


def test_cli_missing_database_does_not_create_file(tmp_path):
    target = tmp_path / "absent.db"
    with pytest.raises(SystemExit):
        main(
            [
                "--database-url",
                f"sqlite:///{target}",
                "--cutoff",
                "1970-02-01T00:00:00Z",
                "--idempotency-seconds",
                "100",
            ]
        )
    assert not target.exists()


def test_forward_schema_fails_closed_instead_of_archiving_incomplete_rows(store):
    add_notification(store)
    with store.engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE uns_notifications ADD COLUMN future_obligation TEXT"
        )
    with pytest.raises(ValueError, match="current schema"):
        run(store, apply=True, operator="operator")
    assert len(rows(store, work)) == 1


def test_postgresql_retention_is_explicitly_unsupported():
    engine = create_mock_engine("postgresql://", lambda *_args, **_kwargs: None)
    with pytest.raises(ValueError, match="SQLite only"):
        maintain(engine, cutoff=OLD, idempotency_seconds=100, now=NOW)


def test_runtime_startup_never_applies_retention(store):
    identifier = add_notification(store)
    restarted = Runtime(str(store.engine.url), create_tables=True)
    try:
        assert restarted.get(identifier)["id"] == identifier
        assert len(restarted.events(identifier)) == 1
    finally:
        restarted.engine.dispose()


def test_old_schema_migration_is_additive_idempotent_and_installs_scan_indexes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE uns_notifications (
            id VARCHAR(36) PRIMARY KEY, key VARCHAR(64) UNIQUE NOT NULL,
            fingerprint VARCHAR(64) NOT NULL, principal VARCHAR(255) NOT NULL,
            notification JSON NOT NULL, status VARCHAR(32) NOT NULL, outcome JSON NOT NULL,
            attempts INTEGER NOT NULL, next_attempt FLOAT NOT NULL, lease_until FLOAT NOT NULL,
            lease_token VARCHAR(36), dead_letter BOOLEAN NOT NULL, delivered_at FLOAT,
            deadline FLOAT, ack_status VARCHAR(32), actor VARCHAR(255), responded_at FLOAT,
            response_metadata JSON)""")
        connection.exec_driver_sql("""CREATE TABLE uns_events (
            id VARCHAR(36) PRIMARY KEY, notification_id VARCHAR(36) NOT NULL,
            kind VARCHAR(50) NOT NULL, at FLOAT NOT NULL, payload JSON NOT NULL,
            callback_pending BOOLEAN NOT NULL, callback_until FLOAT NOT NULL,
            callback_token VARCHAR(36), callback_attempts INTEGER NOT NULL,
            callback_error VARCHAR(2000))""")
        connection.exec_driver_sql(
            "CREATE TABLE uns_dedup (key VARCHAR(64) PRIMARY KEY, until FLOAT NOT NULL)"
        )
        connection.exec_driver_sql("""INSERT INTO uns_notifications
            (id,key,fingerprint,principal,notification,status,outcome,attempts,next_attempt,lease_until,dead_letter)
            VALUES ('legacy','key','fingerprint','producer','{}','PENDING','{}',3,0,0,0)""")
        connection.exec_driver_sql("INSERT INTO uns_dedup VALUES ('historical', 1)")
    migrate_runtime_schema(engine)
    migrate_runtime_schema(engine)
    with engine.connect() as connection:
        row = connection.execute(select(work)).mappings().one()
        assert row["id"] == "legacy"
        assert row["attempts"] == row["cycle_attempts"] == 3
        assert row["cycle"] == 1
        assert connection.execute(select(dedup)).mappings().one()["owner_id"] is None
        assert {
            index["name"] for index in inspect(connection).get_indexes("uns_notifications")
        } >= {
            "ix_uns_dispatch",
            "ix_uns_deadline",
            "ix_uns_dedup_followers",
        }
        plans = [
            (
                "ix_uns_dispatch",
                "SELECT id FROM uns_notifications WHERE status='PENDING' AND dedup_owner_id IS NULL AND next_attempt<=1 AND lease_until<=1 LIMIT 100",
            ),
            (
                "ix_uns_deadline",
                "SELECT id FROM uns_notifications WHERE ack_status='PENDING' AND deadline<=1",
            ),
            (
                "ix_uns_callbacks",
                "SELECT id FROM uns_events WHERE callback_pending=1 AND callback_until<=1 AND callback_attempts<3 LIMIT 100",
            ),
        ]
        for expected, query in plans:
            explanation = connection.exec_driver_sql("EXPLAIN QUERY PLAN " + query).all()
            assert expected in " ".join(str(row) for row in explanation)
    engine.dispose()

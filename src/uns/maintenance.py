"""Explicit, bounded retention for SQLite notification stores.

Nothing runs at startup. The operator chooses both the inactivity cutoff and
the minimum idempotency window. Expiring an outbox row expires its idempotency
key; a subsequent request with that key may create a new notification.

Without an archive, events and delivery/ACK audits remain in the database and
the removal receipt preserves the removed operational rows. With an archive,
whole settled notification groups are exported, fsynced, hash-verified, then
pruned in one SQLite writer transaction. Policy history and retention receipts
are never pruned. This reuses database pages; it does not shrink the SQLite file
or establish an audit/compliance retention policy. Oversized groups are kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, Table, create_engine, exists, func, inspect, or_, select
from sqlalchemy.engine import make_url

from db.models import AckAuditRecord, NotificationAuditRecord
from uns.runtime import dedup, events, work

MAX_BATCH_SIZE = 1_000
_AUDIT = cast(Table, NotificationAuditRecord.__table__)
_ACK = cast(Table, AckAuditRecord.__table__)


def _eligible(cutoff: float, now: float) -> list[Any]:
    follower = work.alias("retained_follower")
    audit_id = func.replace(work.c.id, "-", "")  # SQLite UUID storage is CHAR(32).
    audit_cutoff = datetime.fromtimestamp(cutoff, UTC)
    return [
        work.c.status.in_(("DELIVERED", "SUCCESS", "DEDUPLICATED", "FAILED")),
        or_(
            work.c.ack_status.is_(None), work.c.ack_status.in_(("ACKED", "DISMISSED", "TIMED_OUT"))
        ),
        work.c.dead_letter.is_(False),
        work.c.lease_token.is_(None),
        work.c.lease_until <= now,
        work.c.next_attempt < cutoff,
        or_(work.c.delivered_at.is_(None), work.c.delivered_at < cutoff),
        or_(work.c.responded_at.is_(None), work.c.responded_at < cutoff),
        exists(select(1).where(events.c.notification_id == work.c.id)),
        ~exists(
            select(1).where(
                events.c.notification_id == work.c.id,
                or_(
                    events.c.at >= cutoff,
                    events.c.callback_pending.is_(True),
                    events.c.callback_token.is_not(None),
                    events.c.callback_until > now,
                ),
            )
        ),
        ~exists(
            select(1).where(
                _AUDIT.c.notification_id == audit_id, _AUDIT.c.created_at >= audit_cutoff
            )
        ),
        ~exists(
            select(1).where(_ACK.c.notification_id == audit_id, _ACK.c.created_at >= audit_cutoff)
        ),
        ~exists(select(1).where(dedup.c.owner_id == work.c.id, dedup.c.until > now)),
        ~exists(select(1).where(follower.c.dedup_owner_id == work.c.id)),
    ]


def _schema_check(connection: Connection) -> None:
    inspector = inspect(connection)
    for table in (work, events, dedup, _AUDIT, _ACK):
        if not inspector.has_table(table.name):
            raise ValueError(
                "Retention requires an existing migrated UNS database; run uns-migrate"
            )
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        if set(table.c.keys()) != existing:
            raise ValueError("Retention requires the current schema; run uns-migrate first")


def _group_count(connection: Connection, identifier: str) -> int:
    total = 1
    for table, key in ((events, identifier), (_AUDIT, UUID(identifier)), (_ACK, UUID(identifier))):
        total += connection.execute(
            select(func.count()).select_from(table).where(table.c.notification_id == key)
        ).scalar_one()
    return total


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Cannot archive {type(value).__name__}")


def _verify_archive(path: Path, expected: str) -> None:
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise OSError("Archive readback hash does not match; database deletion was cancelled")


def _write_archive(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Exclusive creation; a failed operation may leave a harmless partial archive."""
    content = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode()
    digest = hashlib.sha256(content).hexdigest()
    # Do not resolve the final path: an existing symlink must fail O_EXCL.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        remaining = memoryview(content)
        while remaining:
            written = os.write(fd, remaining)
            if not written:
                raise OSError("Archive write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    _verify_archive(path, digest)
    return {"path": str(path), "sha256": digest, "bytes": len(content)}


def _record_receipt(connection: Connection, payload: dict[str, Any], now: float) -> str:
    identifier = str(uuid4())
    connection.execute(
        events.insert().values(
            id=identifier,
            notification_id=identifier,
            kind="RETENTION_APPLIED",
            at=now,
            payload=payload,
            callback_pending=False,
        )
    )
    return identifier


def maintain(
    engine: Engine,
    *,
    cutoff: float,
    idempotency_seconds: float,
    batch_size: int = 100,
    apply: bool = False,
    operator: str | None = None,
    archive: Path | None = None,
    after_id: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Plan or apply one batch; every removal shares a transaction with its receipt.

    The row budget includes work and dedup rows, plus all event and audit rows in
    archive mode. It is a row-count bound, not a byte, scan-time or latency bound.
    The cutoff applies to notification inactivity; ownerless dedup claims can be
    removed after their own expiry. Apply always recomputes a dry-run's plan.
    At most batch_size eligible notification candidates are examined. To apply
    a preview, use its input after_id; to continue after applying or deliberately
    skipping that range, use next_after_id. A null next_after_id ends this pass.
    Cursors are ordered ids, not snapshots: start a new pass without after_id to
    revisit oversized, newly eligible, or newly inserted earlier notifications.
    Apply holds SQLite BEGIN IMMEDIATE through selection, archive I/O and commit.
    The archive parent directory must be trusted and already exist. PostgreSQL
    retention is deliberately unsupported until its locking path is validated.
    """
    now = time.time() if now is None else now
    if engine.dialect.name != "sqlite":
        raise ValueError("Retention is validated for SQLite only")
    if not all(math.isfinite(value) for value in (now, cutoff, idempotency_seconds)):
        raise ValueError("Retention timestamps and window must be finite")
    if cutoff > now or idempotency_seconds <= 0:
        raise ValueError("Use a cutoff no later than now and a positive idempotency window")
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be an integer from 1 to {MAX_BATCH_SIZE}")
    if after_id is not None and (
        not isinstance(after_id, str) or not after_id or len(after_id) > 36
    ):
        raise ValueError("after_id must be a nonempty notification id of at most 36 characters")
    if apply and (not operator or not operator.strip()):
        raise ValueError("Apply requires an attributed operator")
    if archive is not None:
        archive = Path(os.path.abspath(archive.expanduser()))
    effective_cutoff = min(cutoff, now - idempotency_seconds)
    report: dict[str, Any] = {
        "applied": apply,
        "operator": operator,
        "cutoff": cutoff,
        "idempotency_seconds": idempotency_seconds,
        "effective_cutoff": effective_cutoff,
        "batch_size": batch_size,
        "after_id": after_id,
        "next_after_id": None,
        "notification_ids": [],
        "dedup_keys": [],
        "oversized_notification_ids": [],
        "deleted_rows": 0,
        "receipt_id": None,
        "archive": {"path": str(archive)} if archive is not None else None,
    }
    with engine.begin() as connection:
        if apply:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        _schema_check(connection)
        conditions = _eligible(effective_cutoff, now)
        if after_id is not None:
            conditions.append(work.c.id > after_id)
        candidates = (
            connection.execute(
                select(work).where(*conditions).order_by(work.c.id).limit(batch_size)
            )
            .mappings()
            .all()
        )
        selected = []
        remaining = batch_size
        resume_after = after_id
        for row in candidates:
            cost = _group_count(connection, row["id"]) if archive is not None else 1
            if cost > batch_size:
                report["oversized_notification_ids"].append(row["id"])
            elif cost <= remaining:
                selected.append(dict(row))
                remaining -= cost
            else:
                # This group fits a fresh batch. Resume before it rather than
                # advancing past a group deferred only by this batch's budget.
                report["next_after_id"] = resume_after
                break
            resume_after = row["id"]
        else:
            if len(candidates) == batch_size:
                report["next_after_id"] = resume_after
        identifiers = [row["id"] for row in selected]
        owner = work.alias("retained_owner")
        # Expired claims are kept while their owner or any follower is retained.
        expired_claims = (
            connection.execute(
                select(dedup)
                .where(
                    dedup.c.until <= now,
                    ~exists(
                        select(1).where(
                            or_(
                                owner.c.id == dedup.c.owner_id,
                                owner.c.dedup_owner_id == dedup.c.owner_id,
                            ),
                            owner.c.id.not_in(identifiers),
                        )
                    ),
                )
                .order_by(dedup.c.key)
                .limit(remaining)
            )
            .mappings()
            .all()
            if remaining
            else []
        )
        claims = [dict(row) for row in expired_claims]
        report.update(
            notification_ids=identifiers,
            dedup_keys=[row["key"] for row in claims],
            deleted_rows=batch_size - remaining + len(claims),
        )
        if not apply or report["deleted_rows"] == 0:
            return report
        removed = {work.name: selected, dedup.name: claims}
        if archive is not None:
            for table, keys in (
                (events, identifiers),
                (_AUDIT, [UUID(i) for i in identifiers]),
                (_ACK, [UUID(i) for i in identifiers]),
            ):
                removed[table.name] = [
                    dict(row)
                    for row in connection.execute(
                        select(table).where(table.c.notification_id.in_(keys)).order_by(table.c.id)
                    ).mappings()
                ]
            archive_receipt = _write_archive(
                archive,
                {
                    "format": "uns-retention-v1",
                    "created_at": now,
                    "operator": operator,
                    "request": report,
                    "tables": removed,
                },
            )
            report["archive"] = archive_receipt
            for table, keys in (
                (_ACK, [UUID(i) for i in identifiers]),
                (_AUDIT, [UUID(i) for i in identifiers]),
                (events, identifiers),
            ):
                connection.execute(table.delete().where(table.c.notification_id.in_(keys)))
        connection.execute(work.delete().where(work.c.id.in_(identifiers)))
        connection.execute(dedup.delete().where(dedup.c.key.in_(report["dedup_keys"])))
        evidence = {
            **report,
            "at": now,
            "table_counts": {name: len(data) for name, data in removed.items()},
        }
        if archive is None:
            evidence["removed"] = removed
        report["receipt_id"] = _record_receipt(connection, evidence, now)
    return report


def _timestamp(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.timestamp()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Use an ISO-8601 timestamp with an explicit timezone"
        ) from exc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("UNS_DATABASE_URL"))
    parser.add_argument("--cutoff", required=True, type=_timestamp)
    parser.add_argument("--idempotency-seconds", required=True, type=float)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--apply", action="store_true", help="Commit one bounded batch")
    parser.add_argument("--operator", help="Attribution required for --apply")
    parser.add_argument(
        "--after-id", help="Continue after a returned next_after_id; omit to start a new pass"
    )
    parser.add_argument(
        "--archive", type=Path, help="New archive file in a trusted existing directory"
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("Provide --database-url or set UNS_DATABASE_URL")
    url = make_url(args.database_url)
    if url.get_backend_name() != "sqlite":
        parser.error("Retention is validated for SQLite only")
    if not url.database or not Path(url.database).is_file():
        parser.error("Retention requires an existing SQLite database file")
    engine = create_engine(url)
    try:
        report = maintain(
            engine,
            cutoff=args.cutoff,
            idempotency_seconds=args.idempotency_seconds,
            batch_size=args.batch_size,
            apply=args.apply,
            operator=args.operator,
            archive=args.archive,
            after_id=args.after_id,
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    finally:
        engine.dispose()
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

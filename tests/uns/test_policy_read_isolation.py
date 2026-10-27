"""Policy inspection stays read-only while intake retains its transaction lock."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, event, insert, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import sessionmaker

from db.models import (
    Base,
    NotificationPolicyRevision,
    NotificationPolicySnapshot,
    PersistedNotificationPolicy,
)
from db.policy_store import SQLAlchemyPolicyStore
from notification.models import Channel
from notification.policies import NotificationPolicy
from notification.policy_loader import compute_policy_content_hash
from uns.policy_runtime import PolicyRuntime
from uns.responses import SendNotificationRequest


def policy(version="1", channel=Channel.SLACK):
    return NotificationPolicy(
        notification_type="policy.reads", version=version, channels=[channel]
    )


def request():
    return SendNotificationRequest(
        notification_type="policy.reads",
        intent="SAFETY",
        title="Read-only simulation",
        message="Test",
        source="test",
        autonomy_context={"agent_id": str(uuid4()), "autonomy_mode": "LIVE"},
    )


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path / 'policy-reads.db'}"
    engine = create_engine(url, connect_args={"timeout": 0.2})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    store = SQLAlchemyPolicyStore(sessions)
    store.save_snapshot([policy()])
    runtime = PolicyRuntime(sessions)
    yield url, engine, sessions, store, runtime
    engine.dispose()


@pytest.mark.parametrize("operation", ["snapshot", "registry", "simulation"])
@pytest.mark.parametrize("populated", [False, True])
def test_steady_state_policy_reads_do_not_issue_dml(database, operation, populated):
    _, engine, _, store, runtime = database
    if not populated:
        store.save_snapshot([])
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        if operation == "snapshot":
            assert store.load_snapshot().revision == (1 if populated else 2)
        elif operation == "registry":
            assert len(runtime.registry()) == (1 if populated else 0)
        else:
            notification = runtime.resolve(request(), principal="p")
            assert notification.metadata["uns_resolution"]["snapshot_revision"] == (
                1 if populated else 2
            )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements
    assert set(statements) == {"SELECT"}, statements


def test_policy_reads_complete_while_another_transaction_holds_writer(database):
    _, _, sessions, store, runtime = database
    with sessions.begin() as writer, ThreadPoolExecutor(max_workers=1) as pool:
        writer.execute(
            update(NotificationPolicyRevision).values(revision=NotificationPolicyRevision.revision)
        )
        # Stage an activation without committing it. Readers must see the old
        # committed pair, and must not wait for the activation's write lock.
        store._write_snapshot(writer, 2, [policy("2", Channel.EMAIL)])
        snapshot = pool.submit(store.load_snapshot).result(timeout=2)
        registry = pool.submit(runtime.registry).result(timeout=2)
        notification = pool.submit(runtime.resolve, request(), principal="p").result(timeout=2)
        assert snapshot.revision == 1
        assert registry.get_sync("policy.reads").channels == [Channel.SLACK]
        assert notification.metadata["uns_resolution"]["snapshot_revision"] == 1
    assert store.load_snapshot().revision == 2
    assert runtime.registry().get_sync("policy.reads").channels == [Channel.EMAIL]
    current = runtime.resolve(request(), principal="p")
    assert current.channels == [Channel.EMAIL]
    assert current.metadata["uns_resolution"]["snapshot_revision"] == 2


def test_snapshot_content_hash_and_revision_stay_consistent_during_activation(database):
    url, engine, _, store, _ = database
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    other_engine = create_engine(url, connect_args={"timeout": 0.2})
    other_store = SQLAlchemyPolicyStore(sessionmaker(other_engine))
    changed = False

    def activate_after_select(conn, cursor, statement, parameters, context, executemany):
        nonlocal changed
        if not changed and statement.lstrip().startswith("SELECT"):
            changed = True
            other_store.save_snapshot([policy("2", Channel.EMAIL)])

    event.listen(engine, "after_cursor_execute", activate_after_select)
    try:
        snapshot = store.load_snapshot()
    finally:
        event.remove(engine, "after_cursor_execute", activate_after_select)
        other_engine.dispose()
    assert changed
    assert snapshot.revision == 1
    assert snapshot.registry().get_sync("policy.reads").channels == [Channel.SLACK]
    assert snapshot.content_hash == compute_policy_content_hash(
        {"policies": json.loads(snapshot.content_json)}
    )
    current = store.load_snapshot()
    assert current.revision == 2
    assert current.registry().get_sync("policy.reads").channels == [Channel.EMAIL]


def test_readiness_does_not_update_policy_authority(tmp_path):
    from fastapi.testclient import TestClient

    from uns.app import create_app
    from uns.runtime import Runtime

    runtime = Runtime(f"sqlite:///{tmp_path / 'readiness.db'}", create_tables=True)
    app = create_app(runtime=runtime, skip_persistence_config=True)
    app.state.uns_api_key = "policy-read-test"
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(runtime.engine, "before_cursor_execute", record)
    try:
        response = TestClient(app).get(
            "/ready", headers={"Authorization": "Bearer policy-read-test"}
        )
        assert response.status_code == 200, response.text
    finally:
        event.remove(runtime.engine, "before_cursor_execute", record)
        runtime.engine.dispose()
    assert statements
    assert set(statements) == {"SELECT"}, statements


@pytest.mark.parametrize("legacy", [False, True])
def test_concurrent_cold_snapshot_reads_initialize_after_closing_read_transactions(tmp_path, legacy):
    url = f"sqlite:///{tmp_path / 'cold.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    if legacy:
        with engine.begin() as connection:
            connection.execute(
                insert(PersistedNotificationPolicy).values(
                    notification_type="policy.reads",
                    version="legacy",
                    status="ACTIVE",
                    channels={"DEFAULT": ["EMAIL"]},
                    delivery_mode="GUARANTEED",
                    require_ack={"DEFAULT": True},
                    mode_overrides={},
                )
            )
    program = """
import json, sys
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from db.policy_store import SQLAlchemyPolicyStore
engine = create_engine(sys.argv[1])
@event.listens_for(engine, "connect")
def explicit_transactions(connection, record):
    connection.isolation_level = None
@event.listens_for(engine, "begin")
def begin(connection):
    connection.exec_driver_sql("BEGIN")
gated = False
@event.listens_for(engine, "after_cursor_execute")
def gate(conn, cursor, statement, parameters, context, executemany):
    global gated
    if not gated and statement.lstrip().startswith("SELECT"):
        gated = True
        print("reading", flush=True)
        sys.stdin.readline()
snapshot = SQLAlchemyPolicyStore(sessionmaker(engine)).load_snapshot()
print(json.dumps({"revision": snapshot.revision, "content": json.loads(snapshot.content_json)}), flush=True)
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", program, url],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=5), "cold reader did not reach snapshot SELECT"
            assert child.stdout.readline().strip() == "reading"
        for child in children:
            child.stdin.write("\n")
            child.stdin.flush()
        results = []
        for child in children:
            output, error = child.communicate(timeout=10)
            assert child.returncode == 0, error
            results.append(json.loads(output))
        assert results[0] == results[1]
        assert results[0]["revision"] == (1 if legacy else 0)
        if legacy:
            assert results[0]["content"][0]["channels"] == ["EMAIL"]
        else:
            assert results[0]["content"] == []
        with engine.connect() as connection:
            assert connection.execute(select(NotificationPolicySnapshot.revision)).all() == [
                (1 if legacy else 0,)
            ]
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()
        engine.dispose()


def test_missing_referenced_snapshot_fails_without_resetting_authority(database):
    _, _, sessions, store, _ = database
    with sessions.begin() as session:
        session.execute(delete(NotificationPolicySnapshot).where(NotificationPolicySnapshot.revision == 1))
    with pytest.raises(NoResultFound):
        store.load_snapshot()
    with sessions() as session:
        assert session.scalar(select(NotificationPolicyRevision.revision)) == 1
        assert session.scalars(select(NotificationPolicySnapshot.revision)).all() == [0]

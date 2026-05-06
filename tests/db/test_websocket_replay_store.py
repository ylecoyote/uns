"""Tests for SQLAlchemy-backed WebSocket replay storage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, WebSocketReplayRecord
from db.websocket_replay_store import SQLAlchemyWebSocketReplayStore


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_sqlalchemy_replay_store_persists_payload_and_cursor() -> None:
    session_factory = _session_factory()
    store = SQLAlchemyWebSocketReplayStore(session_factory)
    agent_id = uuid4()
    first_cursor = store.record(
        agent_id,
        {"notification_id": str(uuid4()), "title": "old"},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    new_payload = {"notification_id": str(uuid4()), "title": "new"}
    new_cursor = store.record(
        agent_id,
        new_payload,
        created_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )

    assert store.missed(agent_id, first_cursor) == [
        {**new_payload, "replay_cursor": new_cursor}
    ]

    session = session_factory()
    try:
        rows = session.query(WebSocketReplayRecord).all()
        assert len(rows) == 2
        assert rows[1].payload["title"] == "new"
        assert rows[1].replay_cursor == new_cursor
    finally:
        session.close()


def test_sqlalchemy_replay_store_scopes_missed_notifications_by_agent() -> None:
    store = SQLAlchemyWebSocketReplayStore(_session_factory())
    target_agent = uuid4()
    other_agent = uuid4()
    cursor = store.record(
        target_agent,
        {"notification_id": str(uuid4()), "title": "old"},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    store.record(
        other_agent,
        {"notification_id": str(uuid4()), "title": "other"},
        created_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )

    assert store.missed(target_agent, cursor) == []

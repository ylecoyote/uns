"""SQLAlchemy-backed WebSocket replay store."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, WebSocketReplayRecord
from notification.websocket_runtime import (
    _format_replay_cursor,
    _normalize_cursor_time,
    _parse_replay_cursor,
)


class SQLAlchemyWebSocketReplayStore:
    """Durable replay read model for standalone WebSocket reconnects."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _get_session(self) -> Session:
        return self._session_factory()

    def record(
        self,
        agent_id: UUID,
        notification: Mapping[str, object],
        created_at: datetime | None = None,
    ) -> str:
        replay_time = _normalize_cursor_time(created_at or datetime.now(UTC))
        replay_cursor = _format_replay_cursor(replay_time)
        payload = dict(notification)
        payload["replay_cursor"] = replay_cursor
        session = self._get_session()
        try:
            row = WebSocketReplayRecord(
                agent_id=agent_id,
                notification_id=UUID(str(notification["notification_id"])),
                replay_cursor=replay_cursor,
                payload=payload,
                created_at=replay_time,
            )
            session.add(row)
            session.commit()
            return replay_cursor
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def missed(
        self,
        agent_id: UUID,
        last_seen: str | None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        since = _parse_replay_cursor(last_seen)
        if since is None:
            return []

        session = self._get_session()
        try:
            rows = (
                session.execute(
                    select(WebSocketReplayRecord)
                    .where(
                        WebSocketReplayRecord.agent_id == agent_id,
                        WebSocketReplayRecord.created_at > since,
                    )
                    .order_by(WebSocketReplayRecord.created_at)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [dict(row.payload) for row in rows]
        finally:
            session.close()


def create_sqlalchemy_websocket_replay_store(
    database_url: str,
    create_tables: bool = True,
) -> SQLAlchemyWebSocketReplayStore:
    """Factory function to create a SQLAlchemy WebSocket replay store."""
    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    if create_tables:
        Base.metadata.create_all(engine)
    return SQLAlchemyWebSocketReplayStore(sessionmaker(bind=engine))

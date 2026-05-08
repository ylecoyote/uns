"""WebSocket replay read-model table.

Stores durable WebSocket payloads keyed by replay cursor so reconnecting
clients can be brought up to date deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.models._base import Base


class WebSocketReplayRecord(Base):
    """SQLAlchemy model for reconnect replay of WebSocket notifications."""

    __tablename__ = "websocket_replay_records"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, comment="Unique replay row ID"
    )
    agent_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="Target agent identifier"
    )
    notification_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False, index=True, comment="Notification identifier"
    )
    replay_cursor: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="Reconnect replay cursor"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, comment="WebSocket notification payload"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When the replay payload was recorded",
    )

    __table_args__ = (
        Index("ix_websocket_replay_agent_created", "agent_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            "WebSocketReplayRecord("
            f"notification_id={self.notification_id}, agent_id={self.agent_id})"
        )

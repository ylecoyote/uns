"""SQLAlchemy-based audit store implementation.

This module provides a database-backed implementation of the AuditStore
interface for production use. It persists audit records using SQLAlchemy
and supports the full query interface.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AckAuditRecord as AckAuditRecordDB
from db.models import NotificationAuditRecord
from notification.audit import (
    AckAuditRecord,
    AuditPersistenceError,
    AuditRecord,
    AuditStore,
)
from notification.models import AckStatus, Channel, DeliveryStatus

logger = logging.getLogger(__name__)


class SQLAlchemyAuditStore(AuditStore):
    """SQLAlchemy-backed audit store for production use.

    Uses a database session to persist and query audit records.
    Supports both delivery and acknowledgment audit records.
    """

    def __init__(self, session_factory: Any) -> None:
        """Initialize with SQLAlchemy session factory.

        Args:
            session_factory: Callable that returns a SQLAlchemy Session
                            (e.g., sessionmaker or scoped_session)
        """
        self._session_factory = session_factory

    def _get_session(self) -> Session:
        """Get a new session from the factory."""
        return cast(Session, self._session_factory())

    def save_delivery_audit(self, record: AuditRecord) -> None:
        """Save a delivery audit record to the database.

        Args:
            record: The audit record to persist

        Raises:
            AuditPersistenceError: If the record cannot be saved
        """
        session = self._get_session()
        try:
            db_record = delivery_audit_row(record)
            session.add(db_record)
            session.commit()
            logger.debug(
                "Saved delivery audit to database: audit_id=%s, notification_id=%s",
                record.audit_id,
                record.notification_id,
            )
        except Exception as e:
            session.rollback()
            raise AuditPersistenceError(
                f"Failed to save delivery audit: {e}",
                record=record,
                original_error=e,
            ) from e
        finally:
            session.close()

    def save_ack_audit(self, record: AckAuditRecord) -> None:
        """Save an acknowledgment audit record to the database.

        Args:
            record: The ack audit record to persist

        Raises:
            AuditPersistenceError: If the record cannot be saved
        """
        session = self._get_session()
        try:
            db_record = AckAuditRecordDB(
                id=record.audit_id,
                notification_id=record.notification_id,
                old_status=record.old_status.value if record.old_status else None,
                new_status=record.new_status.value,
                acked_by=record.acked_by,
                acked_at=record.acked_at,
                created_at=record.audit_created_at,
                ack_metadata=record.metadata,
            )
            session.add(db_record)
            session.commit()
            logger.debug(
                "Saved ack audit to database: audit_id=%s, notification_id=%s",
                record.audit_id,
                record.notification_id,
            )
        except Exception as e:
            session.rollback()
            raise AuditPersistenceError(
                f"Failed to save ack audit: {e}",
                record=record,
                original_error=e,
            ) from e
        finally:
            session.close()

    def get_delivery_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AuditRecord]:
        """Retrieve all delivery audit records for a notification.

        Args:
            notification_id: The notification ID to query

        Returns:
            List of audit records, ordered by created_at descending
        """
        session = self._get_session()
        try:
            stmt = (
                select(NotificationAuditRecord)
                .where(NotificationAuditRecord.notification_id == notification_id)
                .order_by(NotificationAuditRecord.created_at.desc())
            )
            results = session.execute(stmt).scalars().all()

            return [
                AuditRecord(
                    audit_id=r.id,
                    notification_id=r.notification_id,
                    notification_type=r.notification_type,
                    status=DeliveryStatus(r.status),
                    channels_attempted=tuple(Channel(c) for c in r.channels_attempted),
                    channels_succeeded=tuple(Channel(c) for c in r.channels_succeeded),
                    channels_failed=tuple(Channel(c) for c in r.channels_failed),
                    error_message=r.error_message,
                    intent=r.intent,
                    delivery_mode=r.delivery_mode,
                    autonomy_mode=r.autonomy_mode,
                    agent_id=r.agent_id,
                    plan_id=r.plan_id,
                    decision_snapshot_id=r.decision_snapshot_id,
                    execution_snapshot_id=r.execution_snapshot_id,
                    skip_snapshot_id=r.skip_snapshot_id,
                    policy_config_id=r.policy_config_id,
                    policy_config_hash=r.policy_config_hash,
                    policy_evaluation_id=r.policy_evaluation_id,
                    title=r.title,
                    source=r.source,
                    correlation_id=r.correlation_id,
                    metadata=r.notification_metadata,
                    audit_metadata=r.audit_metadata,
                    notification_created_at=r.notification_created_at,
                    delivered_at=r.delivered_at,
                    audit_created_at=r.created_at,
                )
                for r in results
            ]
        finally:
            session.close()

    def get_ack_audits_for_notification(
        self, notification_id: UUID
    ) -> list[AckAuditRecord]:
        """Retrieve all ack audit records for a notification.

        Args:
            notification_id: The notification ID to query

        Returns:
            List of ack audit records, ordered by created_at descending
        """
        session = self._get_session()
        try:
            stmt = (
                select(AckAuditRecordDB)
                .where(AckAuditRecordDB.notification_id == notification_id)
                .order_by(AckAuditRecordDB.created_at.desc())
            )
            results = session.execute(stmt).scalars().all()

            return [
                AckAuditRecord(
                    audit_id=r.id,
                    notification_id=r.notification_id,
                    old_status=AckStatus(r.old_status) if r.old_status else None,
                    new_status=AckStatus(r.new_status),
                    acked_by=r.acked_by,
                    acked_at=r.acked_at,
                    audit_created_at=r.created_at,
                    metadata=r.ack_metadata,
                )
                for r in results
            ]
        finally:
            session.close()


def create_sqlalchemy_audit_store(
    database_url: str,
    create_tables: bool = False,
) -> SQLAlchemyAuditStore:
    """Factory function to create a SQLAlchemy audit store.

    Args:
        database_url: SQLAlchemy database URL
        create_tables: Whether to create tables if they don't exist

    Returns:
        Configured SQLAlchemyAuditStore instance
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base

    engine = create_engine(database_url)

    if create_tables:
        Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine)

    return SQLAlchemyAuditStore(session_factory=session_factory)


def delivery_audit_row(record: AuditRecord) -> NotificationAuditRecord:
    """Build an audit row for a caller-owned transaction."""
    return NotificationAuditRecord(
        id=record.audit_id,
        notification_id=record.notification_id,
        notification_type=record.notification_type,
        status=record.status.value,
        channels_attempted=[c.value for c in record.channels_attempted],
        channels_succeeded=[c.value for c in record.channels_succeeded],
        channels_failed=[c.value for c in record.channels_failed],
        error_message=record.error_message,
        intent=record.intent,
        delivery_mode=record.delivery_mode,
        autonomy_mode=record.autonomy_mode,
        agent_id=record.agent_id,
        plan_id=record.plan_id,
        decision_snapshot_id=record.decision_snapshot_id,
        execution_snapshot_id=record.execution_snapshot_id,
        skip_snapshot_id=record.skip_snapshot_id,
        policy_config_id=record.policy_config_id,
        policy_config_hash=record.policy_config_hash,
        policy_evaluation_id=record.policy_evaluation_id,
        title=record.title,
        source=record.source,
        correlation_id=record.correlation_id,
        notification_metadata=record.metadata,
        audit_metadata=record.audit_metadata,
        notification_created_at=record.notification_created_at,
        delivered_at=record.delivered_at,
        created_at=record.audit_created_at,
    )

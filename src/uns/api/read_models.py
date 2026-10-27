"""Read model adapters for UI endpoints.

This module provides read model adapters that connect the UI endpoints
to the underlying persistence/audit stores. These adapters abstract the
data access layer, allowing for different backend implementations:

- InMemoryReadModelAdapter: In-memory storage for local demo and testing
- SQLAlchemyReadModelAdapter: Database-backed storage for production

Limitations of in-memory adapter (documented clearly):
- Data is lost on process restart
- No persistence across sessions
- Suitable only for local demo and testing
- Not recommended for production use

For production, use SQLAlchemyReadModelAdapter with a proper database.
"""

from __future__ import annotations

import base64
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from notification.audit import (
    AckAuditRecord,
    AuditRecord,
    InMemoryAuditStore,
)
from notification.models import (
    AckStatus,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Filter and Result Types
# =============================================================================


@dataclass(frozen=True)
class DeliveryFilter:
    """Filter criteria for delivery timeline queries."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    status: DeliveryStatus | None = None
    intent: NotificationIntent | None = None
    delivery_mode: DeliveryMode | None = None
    agent_id: UUID | None = None
    autonomy_mode: AutonomyMode | None = None
    notification_type: str | None = None
    channel: Channel | None = None


@dataclass(frozen=True)
class AuditEventFilter:
    """Filter criteria for audit event queries."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    event_type: str | None = None
    notification_id: UUID | None = None
    agent_id: UUID | None = None
    autonomy_mode: AutonomyMode | None = None
    correlation_id: str | None = None


@dataclass
class PaginatedResult:
    """Generic paginated result container."""

    items: list[Any]
    next_cursor: str | None
    has_more: bool
    total_count: int | None = None


@dataclass
class DeliverySummary:
    """Summary view of a delivery for list responses."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None
    channels_attempted: list[Channel]
    channels_succeeded: list[Channel]
    autonomy_mode: AutonomyMode
    agent_id: UUID


@dataclass
class DeliveryAttemptRecord:
    """Record of a single channel delivery attempt."""

    attempt_id: UUID
    channel: Channel
    status: str  # SUCCESS, FAILED, RATE_LIMITED, SKIPPED
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    error_message: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class DeliveryTimeline:
    """Full delivery timeline for a notification."""

    notification_id: UUID
    notification_type: str
    intent: NotificationIntent
    delivery_mode: DeliveryMode
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None
    attempts: list[DeliveryAttemptRecord]
    channels_attempted: list[Channel]
    channels_succeeded: list[Channel]
    channels_failed: list[Channel]
    autonomy_mode: AutonomyMode
    agent_id: UUID
    plan_id: UUID | None = None
    decision_snapshot_id: UUID | None = None
    execution_snapshot_id: UUID | None = None
    skip_snapshot_id: UUID | None = None


@dataclass
class AuditEvent:
    """Single audit event record."""

    audit_id: UUID
    event_type: str
    event_time: datetime
    notification_id: UUID
    notification_type: str
    autonomy_mode: AutonomyMode
    agent_id: UUID
    plan_id: UUID | None = None
    decision_snapshot_id: UUID | None = None
    execution_snapshot_id: UUID | None = None
    skip_snapshot_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


# =============================================================================
# Read Model Adapter Interface
# =============================================================================


class ReadModelAdapter(ABC):
    """Abstract interface for read model adapters.

    Read model adapters provide read access to notification delivery
    and audit data for the UI dashboard. They abstract the underlying
    storage mechanism to allow for different backends.
    """

    @abstractmethod
    def get_deliveries(
        self,
        filter_criteria: DeliveryFilter,
        cursor: str | None = None,
        limit: int = 25,
    ) -> PaginatedResult:
        """Get paginated list of delivery summaries.

        Args:
            filter_criteria: Filter criteria for the query
            cursor: Pagination cursor (opaque string)
            limit: Maximum number of items to return (1-100)

        Returns:
            PaginatedResult containing DeliverySummary items
        """
        ...

    @abstractmethod
    def get_delivery_timeline(
        self,
        notification_id: UUID,
    ) -> DeliveryTimeline | None:
        """Get full delivery timeline for a specific notification.

        Args:
            notification_id: The notification ID to query

        Returns:
            DeliveryTimeline or None if not found
        """
        ...

    @abstractmethod
    def get_audit_events(
        self,
        filter_criteria: AuditEventFilter,
        cursor: str | None = None,
        limit: int = 25,
    ) -> PaginatedResult:
        """Get paginated list of audit events.

        Args:
            filter_criteria: Filter criteria for the query
            cursor: Pagination cursor (opaque string)
            limit: Maximum number of items to return (1-100)

        Returns:
            PaginatedResult containing AuditEvent items
        """
        ...


# =============================================================================
# In-Memory Read Model Adapter
# =============================================================================


_AUDIT_EVENT_STAGE_RANK: dict[str, int] = {
    "notification.created": 10,
    "delivery.started": 20,
    "delivery.channel_attempted": 30,
    "delivery.deduplicated": 40,
    "delivery.rate_limited": 40,
    "delivery.failed": 40,
    "delivery.succeeded": 40,
    "ack.pending": 50,
    "escalation.triggered": 60,
    "ack.received": 70,
    "ack.dismissed": 70,
    "ack.timed_out": 70,
}


def _audit_event_sort_key(event: AuditEvent) -> tuple[datetime, int, str]:
    """Deterministic descending sort key for merged audit events."""
    stage_rank = _AUDIT_EVENT_STAGE_RANK.get(event.event_type, 35)
    return (event.event_time, stage_rank, str(event.audit_id))


class InMemoryReadModelAdapter(ReadModelAdapter):
    """In-memory read model adapter for local demo and testing.

    LIMITATIONS:
    - Data is lost on process restart
    - No persistence across sessions
    - Suitable only for local demo and testing
    - Not recommended for production use
    - Limited query capabilities (full scan for filtering)

    This adapter wraps an InMemoryAuditStore and provides read access
    to the stored audit records. For production use, switch to
    SQLAlchemyReadModelAdapter with a proper database backend.
    """

    def __init__(self, audit_store: InMemoryAuditStore | None = None) -> None:
        """Initialize the in-memory adapter.

        Args:
            audit_store: Optional InMemoryAuditStore to use.
                        If not provided, creates a new one.
        """
        self._audit_store = audit_store or InMemoryAuditStore()
        logger.warning(
            "InMemoryReadModelAdapter initialized. "
            "Data will not persist across restarts. "
            "Use SQLAlchemyReadModelAdapter for production."
        )

    @property
    def audit_store(self) -> InMemoryAuditStore:
        """Get the underlying audit store for writes."""
        return self._audit_store

    def _encode_cursor(self, offset: int) -> str:
        """Encode an offset into an opaque cursor string."""
        return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()

    def _decode_cursor(self, cursor: str | None) -> int:
        """Decode a cursor string into an offset."""
        if cursor is None:
            return 0
        try:
            data = json.loads(base64.b64decode(cursor))
            offset = data.get("offset", 0)
            return min(max(int(offset), 0), 10_000) if offset is not None else 0
        except (ValueError, KeyError):
            logger.warning("Invalid cursor: %s", cursor)
            return 0

    def _matches_delivery_filter(
        self, record: AuditRecord, filter_criteria: DeliveryFilter
    ) -> bool:
        """Check if an audit record matches the delivery filter criteria."""
        if (
            filter_criteria.start_time
            and record.notification_created_at < filter_criteria.start_time
        ):
            return False
        if filter_criteria.end_time and record.notification_created_at >= filter_criteria.end_time:
            return False
        if filter_criteria.status and record.status != filter_criteria.status:
            return False
        if filter_criteria.intent and record.intent != filter_criteria.intent.value:
            return False
        if (
            filter_criteria.delivery_mode
            and record.delivery_mode != filter_criteria.delivery_mode.value
        ):
            return False
        if filter_criteria.agent_id and record.agent_id != filter_criteria.agent_id:
            return False
        if (
            filter_criteria.autonomy_mode
            and record.autonomy_mode != filter_criteria.autonomy_mode.value
        ):
            return False
        if (
            filter_criteria.notification_type
            and record.notification_type != filter_criteria.notification_type
        ):
            return False
        return not (
            filter_criteria.channel and filter_criteria.channel not in record.channels_attempted
        )

    def _matches_audit_filter(self, record: AuditRecord, filter_criteria: AuditEventFilter) -> bool:
        """Check if an audit record matches the audit event filter criteria."""
        if filter_criteria.start_time and record.audit_created_at < filter_criteria.start_time:
            return False
        if filter_criteria.end_time and record.audit_created_at >= filter_criteria.end_time:
            return False
        if (
            filter_criteria.notification_id
            and record.notification_id != filter_criteria.notification_id
        ):
            return False
        if filter_criteria.agent_id and record.agent_id != filter_criteria.agent_id:
            return False
        if (
            filter_criteria.autonomy_mode
            and record.autonomy_mode != filter_criteria.autonomy_mode.value
        ):
            return False
        # event_type filtering is handled separately as we derive it from status
        return not (
            filter_criteria.correlation_id
            and record.correlation_id != filter_criteria.correlation_id
        )

    def _audit_record_to_delivery_summary(self, record: AuditRecord) -> DeliverySummary:
        """Convert an AuditRecord to a DeliverySummary."""
        return DeliverySummary(
            notification_id=record.notification_id,
            notification_type=record.notification_type,
            intent=NotificationIntent(record.intent),
            delivery_mode=DeliveryMode(record.delivery_mode),
            status=record.status,
            created_at=record.notification_created_at,
            delivered_at=record.delivered_at,
            channels_attempted=list(record.channels_attempted),
            channels_succeeded=list(record.channels_succeeded),
            autonomy_mode=AutonomyMode(record.autonomy_mode),
            agent_id=record.agent_id,
        )

    def _audit_record_to_delivery_timeline(self, record: AuditRecord) -> DeliveryTimeline:
        """Convert an AuditRecord to a DeliveryTimeline."""
        # Build attempts from channel information
        # Note: In-memory store doesn't track individual attempt timing,
        # so we use the delivered_at timestamp for all attempts
        attempts: list[DeliveryAttemptRecord] = []
        from uuid import uuid4

        for channel in record.channels_attempted:
            status = "SUCCESS" if channel in record.channels_succeeded else "FAILED"
            attempts.append(
                DeliveryAttemptRecord(
                    attempt_id=uuid4(),  # Generated as we don't store attempt IDs
                    channel=channel,
                    status=status,
                    started_at=record.delivered_at,
                    completed_at=record.delivered_at,
                    duration_ms=0,  # Not tracked in basic audit records
                    error_message=record.error_message if status == "FAILED" else None,
                )
            )

        return DeliveryTimeline(
            notification_id=record.notification_id,
            notification_type=record.notification_type,
            intent=NotificationIntent(record.intent),
            delivery_mode=DeliveryMode(record.delivery_mode),
            status=record.status,
            created_at=record.notification_created_at,
            delivered_at=record.delivered_at,
            attempts=attempts,
            channels_attempted=list(record.channels_attempted),
            channels_succeeded=list(record.channels_succeeded),
            channels_failed=list(record.channels_failed),
            autonomy_mode=AutonomyMode(record.autonomy_mode),
            agent_id=record.agent_id,
            plan_id=record.plan_id,
            decision_snapshot_id=record.decision_snapshot_id,
            execution_snapshot_id=record.execution_snapshot_id,
            skip_snapshot_id=record.skip_snapshot_id,
        )

    def _derive_event_type(self, record: AuditRecord) -> str:
        """Derive the event type from an audit record's status."""
        status_to_event = {
            DeliveryStatus.DELIVERED: "delivery.succeeded",
            DeliveryStatus.SUCCESS: "delivery.succeeded",
            DeliveryStatus.FAILED: "delivery.failed",
            DeliveryStatus.DEDUPLICATED: "delivery.deduplicated",
            DeliveryStatus.RATE_LIMITED: "delivery.rate_limited",
            DeliveryStatus.PENDING: "delivery.started",
        }
        return status_to_event.get(record.status, "delivery.unknown")

    def _audit_record_to_event(self, record: AuditRecord) -> AuditEvent:
        """Convert an AuditRecord to an AuditEvent."""
        return AuditEvent(
            audit_id=record.audit_id,
            event_type=self._derive_event_type(record),
            event_time=record.audit_created_at,
            notification_id=record.notification_id,
            notification_type=record.notification_type,
            autonomy_mode=AutonomyMode(record.autonomy_mode),
            agent_id=record.agent_id,
            plan_id=record.plan_id,
            decision_snapshot_id=record.decision_snapshot_id,
            execution_snapshot_id=record.execution_snapshot_id,
            skip_snapshot_id=record.skip_snapshot_id,
            payload={
                "status": record.status.value,
                "channels_attempted": [c.value for c in record.channels_attempted],
                "channels_succeeded": [c.value for c in record.channels_succeeded],
                "channels_failed": [c.value for c in record.channels_failed],
                "error_message": record.error_message,
            },
            correlation_id=record.correlation_id,
        )

    def _ack_record_to_event(self, record: AckAuditRecord) -> AuditEvent:
        """Convert an AckAuditRecord to an AuditEvent."""
        status_to_event = {
            AckStatus.PENDING: "ack.pending",
            AckStatus.ACKED: "ack.received",
            AckStatus.DISMISSED: "ack.dismissed",
            AckStatus.TIMED_OUT: "ack.timed_out",
        }
        from uuid import UUID

        records = self._audit_store.get_delivery_audits_for_notification(record.notification_id)
        context = records[0] if records else None
        return AuditEvent(
            audit_id=record.audit_id,
            event_type=status_to_event.get(record.new_status, "ack.unknown"),
            event_time=record.audit_created_at,
            notification_id=record.notification_id,
            notification_type=context.notification_type if context else "",
            autonomy_mode=AutonomyMode(context.autonomy_mode) if context else AutonomyMode.PREVIEW,
            agent_id=context.agent_id if context else UUID("00000000-0000-0000-0000-000000000000"),
            plan_id=context.plan_id if context else None,
            decision_snapshot_id=context.decision_snapshot_id if context else None,
            execution_snapshot_id=context.execution_snapshot_id if context else None,
            skip_snapshot_id=context.skip_snapshot_id if context else None,
            correlation_id=context.correlation_id if context else None,
            payload={
                "old_status": record.old_status.value if record.old_status else None,
                "new_status": record.new_status.value,
                "acked_by": record.acked_by,
                "acked_at": record.acked_at.isoformat(),
                **record.metadata,
                "context_unavailable": context is None,
            },
        )

    def get_deliveries(
        self,
        filter_criteria: DeliveryFilter,
        cursor: str | None = None,
        limit: int = 25,
    ) -> PaginatedResult:
        """Get paginated list of delivery summaries from in-memory store."""
        # Deduplicate by notification_id using the latest audit record per notification
        latest_by_notification: dict[UUID, tuple[tuple[datetime, int, int], AuditRecord]] = {}
        for idx, record in enumerate(self._audit_store.delivery_audits):
            rank = (
                record.audit_created_at,
                0 if record.status == DeliveryStatus.PENDING else 1,
                idx,
            )
            existing = latest_by_notification.get(record.notification_id)
            if existing is None or rank >= existing[0]:
                latest_by_notification[record.notification_id] = (rank, record)
        deduped_records = [pair[1] for pair in latest_by_notification.values()]

        # Filter deduplicated records
        filtered = [
            r for r in deduped_records if self._matches_delivery_filter(r, filter_criteria)
        ]

        # Sort by created_at descending (most recent first)
        filtered.sort(
            key=lambda r: (r.notification_created_at, r.audit_created_at, str(r.audit_id)),
            reverse=True,
        )

        # Apply pagination
        offset = self._decode_cursor(cursor)
        total_count = len(filtered)
        page = filtered[offset : offset + limit]
        has_more = (offset + limit < total_count) and (offset + limit <= 10_000)

        # Convert to summaries
        items = [self._audit_record_to_delivery_summary(r) for r in page]

        return PaginatedResult(
            items=items,
            next_cursor=self._encode_cursor(offset + limit) if has_more else None,
            has_more=has_more,
            total_count=total_count,
        )

    def get_delivery_timeline(
        self,
        notification_id: UUID,
    ) -> DeliveryTimeline | None:
        """Get full delivery timeline for a specific notification."""
        records = self._audit_store.get_delivery_audits_for_notification(notification_id)
        if not records:
            return None

        # Return the most recent audit record as the timeline
        # (most recent is first due to sorting in get_delivery_audits_for_notification)
        return self._audit_record_to_delivery_timeline(records[0])

    def get_audit_events(
        self,
        filter_criteria: AuditEventFilter,
        cursor: str | None = None,
        limit: int = 25,
    ) -> PaginatedResult:
        """Get paginated list of audit events from in-memory store."""
        # Combine delivery and ack audits
        all_events: list[AuditEvent] = []

        # Add delivery audit events
        for record in self._audit_store.delivery_audits:
            if not self._matches_audit_filter(record, filter_criteria):
                continue
            event = self._audit_record_to_event(record)
            # Filter by event_type if specified
            if filter_criteria.event_type and event.event_type != filter_criteria.event_type:
                continue
            all_events.append(event)

        # Add ack audit events (if no event_type filter or it's an ack type)
        if filter_criteria.event_type is None or filter_criteria.event_type.startswith("ack."):
            for ack_record in self._audit_store.ack_audits:
                # Filter by notification_id if specified
                if (
                    filter_criteria.notification_id
                    and ack_record.notification_id != filter_criteria.notification_id
                ):
                    continue
                # Filter by time range
                if (
                    filter_criteria.start_time
                    and ack_record.audit_created_at < filter_criteria.start_time
                ):
                    continue
                if filter_criteria.end_time and ack_record.audit_created_at >= filter_criteria.end_time:
                    continue
                event = self._ack_record_to_event(ack_record)
                if filter_criteria.agent_id and event.agent_id != filter_criteria.agent_id:
                    continue
                if filter_criteria.autonomy_mode and event.autonomy_mode != filter_criteria.autonomy_mode:
                    continue
                if filter_criteria.correlation_id and event.correlation_id != filter_criteria.correlation_id:
                    continue
                if filter_criteria.event_type and event.event_type != filter_criteria.event_type:
                    continue
                all_events.append(event)

        # Sort by event_time descending with deterministic lifecycle stage tie-breaker
        all_events.sort(key=_audit_event_sort_key, reverse=True)

        # Apply pagination
        offset = self._decode_cursor(cursor)
        total_count = len(all_events)
        page = all_events[offset : offset + limit]
        has_more = (offset + limit < total_count) and (offset + limit <= 10_000)

        return PaginatedResult(
            items=page,
            next_cursor=self._encode_cursor(offset + limit) if has_more else None,
            has_more=has_more,
            total_count=total_count,
        )


# =============================================================================
# SQLAlchemy Read Model Adapter
# =============================================================================


def _utc(value: datetime) -> datetime:
    """SQLite strips timezone metadata from UTC audit columns; restore it on reads."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SQLAlchemyReadModelAdapter(ReadModelAdapter):
    """SQLAlchemy-backed read model adapter for production use.

    This adapter provides read access to notification delivery and audit
    data stored in a relational database via SQLAlchemy. It supports
    efficient querying with proper indexing and pagination.

    Use this adapter for production deployments where data persistence
    and scalable querying are required.
    """

    def __init__(self, session_factory: Any, *, runtime: Any = None) -> None:
        """Initialize with SQLAlchemy session factory.

        Args:
            session_factory: Callable that returns a SQLAlchemy Session
                            (e.g., sessionmaker or scoped_session)
        """
        self.runtime = runtime
        self._session_factory = session_factory
        logger.info("SQLAlchemyReadModelAdapter initialized")

    def _get_session(self) -> Any:
        """Get a new session from the factory."""
        return self._session_factory()

    def _encode_cursor(self, offset: int) -> str:
        """Encode an offset into an opaque cursor string."""
        return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()

    def _decode_cursor(self, cursor: str | None) -> int:
        """Decode a cursor string into an offset."""
        if cursor is None:
            return 0
        try:
            data = json.loads(base64.b64decode(cursor))
            offset = data.get("offset", 0)
            return min(max(int(offset), 0), 10_000) if offset is not None else 0
        except (ValueError, KeyError):
            logger.warning("Invalid cursor: %s", cursor)
            return 0

    def get_deliveries(
        self,
        filter_criteria: DeliveryFilter,
        cursor: str | None = None,
        limit: int = 25,
    ) -> PaginatedResult:
        """Get paginated list of delivery summaries from database."""
        from sqlalchemy import case, func, select

        from db.models import NotificationAuditRecord

        session = self._get_session()
        try:
            # Deduplicate by notification_id, selecting the latest audit row per notification
            # before applying status/channel filters, counting, or paginating.
            status_rank = case(
                (NotificationAuditRecord.status == "PENDING", 0),
                else_=1,
            )
            ranked = (
                select(
                    NotificationAuditRecord.id.label("latest_id"),
                    func.row_number()
                    .over(
                        partition_by=NotificationAuditRecord.notification_id,
                        order_by=(
                            NotificationAuditRecord.created_at.desc(),
                            status_rank.desc(),
                            NotificationAuditRecord.id.desc(),
                        ),
                    )
                    .label("rn"),
                )
                .subquery("ranked_delivery_audits")
            )
            stmt = select(NotificationAuditRecord).join(
                ranked,
                (NotificationAuditRecord.id == ranked.c.latest_id) & (ranked.c.rn == 1),
            )

            # Apply filters on the latest row per notification_id
            if filter_criteria.start_time:
                stmt = stmt.where(
                    NotificationAuditRecord.notification_created_at >= filter_criteria.start_time
                )
            if filter_criteria.end_time:
                stmt = stmt.where(
                    NotificationAuditRecord.notification_created_at < filter_criteria.end_time
                )
            if filter_criteria.status:
                stmt = stmt.where(NotificationAuditRecord.status == filter_criteria.status.value)
            if filter_criteria.intent:
                stmt = stmt.where(NotificationAuditRecord.intent == filter_criteria.intent.value)
            if filter_criteria.delivery_mode:
                stmt = stmt.where(
                    NotificationAuditRecord.delivery_mode == filter_criteria.delivery_mode.value
                )
            if filter_criteria.agent_id:
                stmt = stmt.where(NotificationAuditRecord.agent_id == filter_criteria.agent_id)
            if filter_criteria.autonomy_mode:
                stmt = stmt.where(
                    NotificationAuditRecord.autonomy_mode == filter_criteria.autonomy_mode.value
                )
            if filter_criteria.notification_type:
                stmt = stmt.where(
                    NotificationAuditRecord.notification_type == filter_criteria.notification_type
                )
            if filter_criteria.channel:
                stmt = stmt.where(_channel_membership(
                    NotificationAuditRecord.channels_attempted,
                    filter_criteria.channel,
                    session.get_bind().dialect.name,
                ))

            # Count total unique matching notifications
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_count = session.execute(count_stmt).scalar() or 0

            # Apply ordering and pagination
            offset = self._decode_cursor(cursor)
            stmt = stmt.order_by(
                NotificationAuditRecord.notification_created_at.desc(),
                NotificationAuditRecord.created_at.desc(),
                NotificationAuditRecord.id.desc(),
            )
            stmt = stmt.offset(offset).limit(limit)

            results = session.execute(stmt).scalars().all()

            # Convert to summaries
            items = [
                DeliverySummary(
                    notification_id=r.notification_id,
                    notification_type=r.notification_type,
                    intent=NotificationIntent(r.intent),
                    delivery_mode=DeliveryMode(r.delivery_mode),
                    status=DeliveryStatus(r.status),
                    created_at=_utc(r.notification_created_at),
                    delivered_at=_utc(r.delivered_at) if r.delivered_at else None,
                    channels_attempted=[Channel(c) for c in r.channels_attempted],
                    channels_succeeded=[Channel(c) for c in r.channels_succeeded],
                    autonomy_mode=AutonomyMode(r.autonomy_mode),
                    agent_id=r.agent_id,
                )
                for r in results
            ]

            has_more = (offset + limit < total_count) and (offset + limit <= 10_000)

            return PaginatedResult(
                items=items,
                next_cursor=self._encode_cursor(offset + limit) if has_more else None,
                has_more=has_more,
                total_count=total_count,
            )
        finally:
            session.close()

    def get_delivery_timeline(
        self,
        notification_id: UUID,
    ) -> DeliveryTimeline | None:
        """Get full delivery timeline for a specific notification."""
        from sqlalchemy import case, select

        from db.models import NotificationAuditRecord

        session = self._get_session()
        try:
            status_rank = case(
                (NotificationAuditRecord.status == "PENDING", 0),
                else_=1,
            )
            stmt = (
                select(NotificationAuditRecord)
                .where(NotificationAuditRecord.notification_id == notification_id)
                .order_by(
                    NotificationAuditRecord.created_at.desc(),
                    status_rank.desc(),
                    NotificationAuditRecord.id.desc(),
                )
                .limit(1)
            )
            result = session.execute(stmt).scalar_one_or_none()

            if not result:
                return None

            # Build attempts from channel information
            from uuid import uuid4

            attempts: list[DeliveryAttemptRecord] = []
            for channel_str in result.channels_attempted:
                channel = Channel(channel_str)
                status = "SUCCESS" if channel_str in result.channels_succeeded else "FAILED"
                attempts.append(
                    DeliveryAttemptRecord(
                        attempt_id=uuid4(),
                        channel=channel,
                        status=status,
                        started_at=_utc(result.delivered_at),
                        completed_at=_utc(result.delivered_at),
                        duration_ms=0,
                        error_message=result.error_message if status == "FAILED" else None,
                    )
                )

            return DeliveryTimeline(
                notification_id=result.notification_id,
                notification_type=result.notification_type,
                intent=NotificationIntent(result.intent),
                delivery_mode=DeliveryMode(result.delivery_mode),
                status=DeliveryStatus(result.status),
                created_at=_utc(result.notification_created_at),
                delivered_at=_utc(result.delivered_at) if result.delivered_at else None,
                attempts=attempts,
                channels_attempted=[Channel(c) for c in result.channels_attempted],
                channels_succeeded=[Channel(c) for c in result.channels_succeeded],
                channels_failed=[Channel(c) for c in result.channels_failed],
                autonomy_mode=AutonomyMode(result.autonomy_mode),
                agent_id=result.agent_id,
                plan_id=result.plan_id,
                decision_snapshot_id=result.decision_snapshot_id,
                execution_snapshot_id=result.execution_snapshot_id,
                skip_snapshot_id=result.skip_snapshot_id,
            )
        finally:
            session.close()

    def get_audit_events(
        self,
        filter_criteria: AuditEventFilter,
        cursor: str | None = None,
        limit: int = 25,
    ) -> PaginatedResult:
        """Get paginated list of audit events from database."""
        from sqlalchemy import func, select

        from db.models import AckAuditRecord as AckAuditRecordDB
        from db.models import NotificationAuditRecord

        session = self._get_session()
        try:
            # Build events from bounded pages from both tables. Each side fetches
            # enough rows to satisfy the merged offset without loading all history.
            offset = self._decode_cursor(cursor)
            fetch_limit = offset + limit + 1
            all_events: list[AuditEvent] = []
            total_count = 0

            # Query delivery audits
            delivery_stmt = select(NotificationAuditRecord)

            if filter_criteria.start_time:
                delivery_stmt = delivery_stmt.where(
                    NotificationAuditRecord.created_at >= filter_criteria.start_time
                )
            if filter_criteria.end_time:
                delivery_stmt = delivery_stmt.where(
                    NotificationAuditRecord.created_at < filter_criteria.end_time
                )
            if filter_criteria.notification_id:
                delivery_stmt = delivery_stmt.where(
                    NotificationAuditRecord.notification_id == filter_criteria.notification_id
                )
            if filter_criteria.agent_id:
                delivery_stmt = delivery_stmt.where(
                    NotificationAuditRecord.agent_id == filter_criteria.agent_id
                )
            if filter_criteria.autonomy_mode:
                delivery_stmt = delivery_stmt.where(
                    NotificationAuditRecord.autonomy_mode == filter_criteria.autonomy_mode.value
                )
            if filter_criteria.correlation_id:
                delivery_stmt = delivery_stmt.where(
                    NotificationAuditRecord.correlation_id == filter_criteria.correlation_id
                )

            status_to_event = {
                "DELIVERED": "delivery.succeeded",
                "SUCCESS": "delivery.succeeded",
                "FAILED": "delivery.failed",
                "DEDUPLICATED": "delivery.deduplicated",
                "RATE_LIMITED": "delivery.rate_limited",
                "PENDING": "delivery.started",
            }
            event_to_delivery_statuses = {
                "delivery.succeeded": ("DELIVERED", "SUCCESS"),
                "delivery.failed": ("FAILED",),
                "delivery.deduplicated": ("DEDUPLICATED",),
                "delivery.rate_limited": ("RATE_LIMITED",),
                "delivery.started": ("PENDING",),
            }

            if filter_criteria.event_type is None or filter_criteria.event_type.startswith(
                "delivery."
            ):
                if filter_criteria.event_type is not None:
                    matching_statuses = event_to_delivery_statuses.get(
                        filter_criteria.event_type, ()
                    )
                    delivery_stmt = delivery_stmt.where(
                        NotificationAuditRecord.status.in_(matching_statuses)
                    )
                total_count += (
                    session.execute(
                        select(func.count()).select_from(delivery_stmt.subquery())
                    ).scalar()
                    or 0
                )
                delivery_results = (
                    session.execute(
                        delivery_stmt.order_by(
                            NotificationAuditRecord.created_at.desc(),
                            NotificationAuditRecord.id.desc(),
                        ).limit(fetch_limit)
                    )
                    .scalars()
                    .all()
                )

                for r in delivery_results:
                    event_type = status_to_event.get(r.status, "delivery.unknown")
                    if filter_criteria.event_type and event_type != filter_criteria.event_type:
                        continue
                    all_events.append(
                        AuditEvent(
                            audit_id=r.id,
                            event_type=event_type,
                            event_time=_utc(r.created_at),
                            notification_id=r.notification_id,
                            notification_type=r.notification_type,
                            autonomy_mode=AutonomyMode(r.autonomy_mode),
                            agent_id=r.agent_id,
                            plan_id=r.plan_id,
                            decision_snapshot_id=r.decision_snapshot_id,
                            execution_snapshot_id=r.execution_snapshot_id,
                            skip_snapshot_id=r.skip_snapshot_id,
                            payload={
                                "status": r.status,
                                "channels_attempted": r.channels_attempted,
                                "channels_succeeded": r.channels_succeeded,
                                "channels_failed": r.channels_failed,
                                "error_message": r.error_message,
                            },
                            correlation_id=r.correlation_id,
                        )
                    )

            # Query ack audits (if not filtering for delivery-only events)
            if filter_criteria.event_type is None or filter_criteria.event_type.startswith("ack."):
                latest_context = (
                    select(NotificationAuditRecord.id)
                    .where(NotificationAuditRecord.notification_id == AckAuditRecordDB.notification_id)
                    .order_by(NotificationAuditRecord.created_at.desc(), NotificationAuditRecord.id.desc())
                    .limit(1).correlate(AckAuditRecordDB).scalar_subquery()
                )
                ack_stmt = select(AckAuditRecordDB, NotificationAuditRecord).outerjoin(
                    NotificationAuditRecord, NotificationAuditRecord.id == latest_context
                )
                if filter_criteria.agent_id:
                    ack_stmt = ack_stmt.where(NotificationAuditRecord.agent_id == filter_criteria.agent_id)
                if filter_criteria.autonomy_mode:
                    ack_stmt = ack_stmt.where(NotificationAuditRecord.autonomy_mode == filter_criteria.autonomy_mode.value)
                if filter_criteria.correlation_id:
                    ack_stmt = ack_stmt.where(NotificationAuditRecord.correlation_id == filter_criteria.correlation_id)

                if filter_criteria.start_time:
                    ack_stmt = ack_stmt.where(
                        AckAuditRecordDB.created_at >= filter_criteria.start_time
                    )
                if filter_criteria.end_time:
                    ack_stmt = ack_stmt.where(
                        AckAuditRecordDB.created_at < filter_criteria.end_time
                    )
                if filter_criteria.notification_id:
                    ack_stmt = ack_stmt.where(
                        AckAuditRecordDB.notification_id == filter_criteria.notification_id
                    )

                ack_status_to_event = {
                    "PENDING": "ack.pending",
                    "ACKED": "ack.received",
                    "DISMISSED": "ack.dismissed",
                    "TIMED_OUT": "ack.timed_out",
                }
                event_to_ack_statuses = {
                    "ack.pending": ("PENDING",),
                    "ack.received": ("ACKED",),
                    "ack.dismissed": ("DISMISSED",),
                    "ack.timed_out": ("TIMED_OUT",),
                }
                if filter_criteria.event_type is not None:
                    matching_ack_statuses = event_to_ack_statuses.get(
                        filter_criteria.event_type, ()
                    )
                    ack_stmt = ack_stmt.where(
                        AckAuditRecordDB.new_status.in_(matching_ack_statuses)
                    )
                total_count += (
                    session.execute(
                        select(func.count()).select_from(ack_stmt.subquery())
                    ).scalar()
                    or 0
                )

                ack_results = (
                    session.execute(
                        ack_stmt.order_by(
                            AckAuditRecordDB.created_at.desc(),
                            AckAuditRecordDB.acked_at.desc(),
                            AckAuditRecordDB.id.desc(),
                        ).limit(fetch_limit)
                    ).all()
                )

                # Use UUID directly since it's already imported at module level
                nil_uuid = UUID("00000000-0000-0000-0000-000000000000")

                for r, context in ack_results:
                    event_type = ack_status_to_event.get(r.new_status, "ack.unknown")
                    if filter_criteria.event_type and event_type != filter_criteria.event_type:
                        continue
                    all_events.append(
                        AuditEvent(
                            audit_id=r.id,
                            event_type=event_type,
                            event_time=_utc(r.created_at),
                            notification_id=r.notification_id,
                            notification_type=context.notification_type if context else "",
                            autonomy_mode=AutonomyMode(context.autonomy_mode) if context else AutonomyMode.PREVIEW,
                            agent_id=context.agent_id if context else nil_uuid,
                            plan_id=context.plan_id if context else None,
                            decision_snapshot_id=context.decision_snapshot_id if context else None,
                            execution_snapshot_id=context.execution_snapshot_id if context else None,
                            skip_snapshot_id=context.skip_snapshot_id if context else None,
                            correlation_id=context.correlation_id if context else None,
                            payload={
                                **(r.ack_metadata if isinstance(r.ack_metadata, dict) else {}),
                                "old_status": r.old_status,
                                "new_status": r.new_status,
                                "acked_by": r.acked_by,
                                "acked_at": _utc(r.acked_at).isoformat() if r.acked_at else None,
                                "context_unavailable": context is None,
                            },
                        )
                    )

            # Sort by event_time descending with deterministic lifecycle stage tie-breaker
            all_events.sort(key=_audit_event_sort_key, reverse=True)

            # Apply pagination
            page = all_events[offset : offset + limit]
            has_more = (offset + limit < total_count) and (offset + limit <= 10_000)

            return PaginatedResult(
                items=page,
                next_cursor=self._encode_cursor(offset + limit) if has_more else None,
                has_more=has_more,
                total_count=total_count,
            )
        finally:
            session.close()


# =============================================================================
# Global Read Model Instance Management
# =============================================================================

_read_model_adapter: ReadModelAdapter | None = None


def get_read_model_adapter() -> ReadModelAdapter:
    """Get the global read model adapter instance.

    Returns an InMemoryReadModelAdapter by default if not configured.
    Call configure_read_model_adapter() to use a different backend.

    Returns:
        The singleton ReadModelAdapter instance
    """
    global _read_model_adapter
    if _read_model_adapter is None:
        _read_model_adapter = InMemoryReadModelAdapter()
    return _read_model_adapter


def configure_read_model_adapter(adapter: ReadModelAdapter) -> ReadModelAdapter:
    """Configure the global read model adapter.

    Args:
        adapter: The ReadModelAdapter implementation to use

    Returns:
        The configured ReadModelAdapter instance
    """
    global _read_model_adapter
    _read_model_adapter = adapter
    logger.info("Read model adapter configured: %s", type(adapter).__name__)
    return _read_model_adapter


def create_in_memory_adapter(
    audit_store: InMemoryAuditStore | None = None,
) -> InMemoryReadModelAdapter:
    """Factory function to create an in-memory read model adapter.

    Args:
        audit_store: Optional InMemoryAuditStore to use

    Returns:
        Configured InMemoryReadModelAdapter instance
    """
    return InMemoryReadModelAdapter(audit_store)


def create_sqlalchemy_adapter(
    database_url: str,
    create_tables: bool = False,
) -> SQLAlchemyReadModelAdapter:
    """Factory function to create a SQLAlchemy read model adapter.

    Args:
        database_url: SQLAlchemy database URL
        create_tables: Whether to create tables if they don't exist

    Returns:
        Configured SQLAlchemyReadModelAdapter instance
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base

    engine = create_engine(database_url)

    if create_tables:
        Base.metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine)

    return SQLAlchemyReadModelAdapter(session_factory=session_factory)


def _channel_membership(column: Any, channel: Channel, dialect: str) -> Any:
    """Match an enum element, not a serialized JSON-array substring."""
    from sqlalchemy import cast, func, select

    if dialect == "sqlite":
        members = func.json_each(column).table_valued("value")
        return select(1).select_from(members).where(members.c.value == channel.value).exists()
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB
        return cast(column, JSONB).contains([channel.value])
    if dialect in {"mysql", "mariadb"}:
        return func.json_contains(column, json.dumps(channel.value)) == 1
    raise ValueError(f"Channel membership is not implemented for SQL dialect {dialect!r}")

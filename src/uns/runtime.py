"""Transactional notification outbox and acknowledgment runtime.

All public transports use this service. Database state, outbox work and audit
commit together. Network effects happen outside transactions under a fenced
lease; provider acceptance before a crash can therefore be retried.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    String,
    Table,
    case,
    create_engine,
    event,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from db.audit_store import SQLAlchemyAuditStore, delivery_audit_row
from db.models import AckAuditRecord as AckRow
from db.models import Base
from db.policy_learning_store import SQLAlchemyPolicyLearningStore
from notification.adapters.base import DeliveryLeaseLostError, DeliveryResult
from notification.audit import create_audit_record
from notification.models import (
    AckStatus,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationResult,
)
from notification.service import (
    DeliveryError,
    DeliveryEvidenceError,
    DeliveryService,
    SimpleAdapterRegistry,
)
from uns.database import is_in_memory_database_url
from uns.policy_runtime import PolicyRuntime
from uns.responses import AckResponse, SendNotificationRequest, SendNotificationResponse
from uns.schema import migrate_runtime_schema
from uns.shadow_evaluator import ShadowPolicyEvaluator

log = logging.getLogger(__name__)

work = Table(
    "uns_notifications",
    Base.metadata,
    Column("id", String(36), primary_key=True),
    Column("key", String(64), unique=True, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("principal", String(255), nullable=False),
    Column("notification", JSON, nullable=False),
    Column("status", String(32), nullable=False),
    Column("outcome", JSON, nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("cycle", Integer, nullable=False, default=1, server_default="1"),
    Column("cycle_attempts", Integer, nullable=False, default=0, server_default="0"),
    Column("dedup_key", String(64)),
    Column("dedup_owner_id", String(36)),
    Column("dedup_generation", Integer),
    Column("dedup_successor_id", String(36)),
    Column("next_attempt", Float, nullable=False),
    Column("lease_until", Float, nullable=False, default=0),
    Column("lease_token", String(36)),
    Column("dead_letter", Boolean, nullable=False, default=False),
    Column("delivered_at", Float),
    Column("deadline", Float),
    Column("ack_status", String(32)),
    Column("actor", String(255)),
    Column("responded_at", Float),
    Column("response_metadata", JSON),
)
events = Table(
    "uns_events",
    Base.metadata,
    Column("id", String(36), primary_key=True),
    Column("notification_id", String(36), nullable=False, index=True),
    Column("kind", String(50), nullable=False),
    Column("at", Float, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("callback_pending", Boolean, nullable=False, default=False),
    Column("callback_until", Float, nullable=False, default=0),
    Column("callback_token", String(36)),
    Column("callback_attempts", Integer, nullable=False, default=0),
    Column("callback_error", String(2000)),
)
dedup = Table(
    "uns_dedup",
    Base.metadata,
    Column("key", String(64), primary_key=True),
    Column("until", Float, nullable=False),
    Column("owner_id", String(36)),
    Column("generation", Integer, nullable=False, default=1, server_default="1"),
)
Index(
    "ix_uns_dispatch", work.c.status, work.c.dedup_owner_id, work.c.next_attempt, work.c.lease_until
)
Index("ix_uns_deadline", work.c.ack_status, work.c.deadline)
Index("ix_uns_dedup_followers", work.c.dedup_owner_id, work.c.dedup_generation)
Index("ix_uns_dedup_successor", work.c.dedup_successor_id)
Index(
    "ix_uns_callbacks",
    events.c.callback_pending,
    events.c.callback_until,
    events.c.callback_attempts,
)


class Conflict(ValueError):  # noqa: N818 - retained public exception name
    """Request identity or state conflicts with a committed operation."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class Runtime:
    """One service for intake, dispatch, status, response and timeout recovery."""

    def __init__(
        self,
        database_url: str,
        *,
        adapters: SimpleAdapterRegistry | None = None,
        create_tables: bool = False,
        max_attempts: int = 3,
        retry_seconds: float = 1,
        clock: Callable[[], float] = time.time,
        callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        shadow_evaluation_enabled: bool | None = None,
        shadow_min_samples: int | None = None,
        shadow_accuracy_threshold: float | None = None,
    ) -> None:
        options: dict[str, Any] = {}
        is_in_memory = is_in_memory_database_url(database_url)
        if is_in_memory:
            options = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
        elif database_url.startswith("sqlite"):
            options = {"connect_args": {"timeout": 30.0}}
        self.database_url = database_url
        self.persistence_mode = "in_memory" if is_in_memory else "persistent"
        self.engine = create_engine(database_url, **options)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def _configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA busy_timeout=30000")
                    if not is_in_memory:
                        cursor.execute("PRAGMA journal_mode=WAL")
                        cursor.execute("PRAGMA synchronous=NORMAL")
                finally:
                    cursor.close()

        migrate_runtime_schema(self.engine, create_tables=create_tables)
        self.sessions = sessionmaker(self.engine)
        self.audit_store = SQLAlchemyAuditStore(self.sessions)
        self.adapters = adapters or SimpleAdapterRegistry()
        self.policy_runtime = PolicyRuntime(self.sessions, adapters=self.adapters)
        self.learning_store = SQLAlchemyPolicyLearningStore(self.sessions)
        self.shadow_evaluator = ShadowPolicyEvaluator(
            self.policy_runtime.store,
            self.learning_store,
            enabled=shadow_evaluation_enabled,
            min_samples=shadow_min_samples,
            accuracy_threshold=shadow_accuracy_threshold,
        )
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.max_attempts = max_attempts
        self.retry_seconds = retry_seconds
        self.clock = clock
        self.callback = callback
        self.lease_seconds = 60.0
        self.delivery = DeliveryService(
            self.adapters, check_deduplication=False, check_rate_limit=False
        )

    def _event(
        self, session: Session, notification_id: str, kind: str, payload: dict[str, Any]
    ) -> None:
        session.execute(
            insert(events).values(
                id=str(uuid4()),
                notification_id=notification_id,
                kind=kind,
                at=self.clock(),
                callback_until=self.clock(),
                payload=payload,
                callback_pending=self.callback is not None
                and kind in ("ACKED", "DISMISSED", "TIMED_OUT"),
            )
        )

    def _audit(
        self,
        session: Session,
        notification: Notification,
        result: NotificationResult,
        **metadata: Any,
    ) -> None:
        record = create_audit_record(notification, result, metadata=metadata)
        record = replace(record, audit_created_at=datetime.fromtimestamp(self.clock(), UTC))
        session.add(delivery_audit_row(record))

    def _resolve_obligation_owner(
        self, session: Session, row: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Resolve the complete lineage without treating a broken link as an owner."""
        current = row
        seen = {str(row["id"])}
        while True:
            next_id = current.get("dedup_owner_id") or current.get("dedup_successor_id")
            if not next_id:
                return current, None
            if str(next_id) in seen:
                return None, "CYCLE"
            seen.add(str(next_id))
            candidate = (
                session.execute(select(work).where(work.c.id == str(next_id)))
                .mappings()
                .first()
            )
            if candidate is None:
                return None, "MISSING_TARGET"
            if row["dedup_key"] is None or candidate["dedup_key"] != row["dedup_key"]:
                return None, "GROUP_MISMATCH"
            current = dict(candidate)

    def get(self, notification_id: UUID | str) -> dict[str, Any]:
        with self.sessions() as session:
            row = (
                session.execute(select(work).where(work.c.id == str(notification_id)))
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError(str(notification_id))
            result = dict(row)
            owner, resolution_error = self._resolve_obligation_owner(session, result)
            inherited = owner is not None and str(owner["id"]) != str(result["id"])
            result["obligation_owner_id"] = str(owner["id"]) if owner is not None else None
            result["effective_status"] = owner["status"] if owner is not None else result["status"]
            result["effective_ack_status"] = owner["ack_status"] if owner is not None else None
            result["ack_inherited"] = inherited
            result["obligation_resolution_status"] = "RESOLVED" if owner is not None else "UNRESOLVED"
            result["obligation_resolution_error"] = resolution_error
            blocker = self._replay_blocker(session, result) if result.get("dead_letter") else None
            result["replay_blocked_by"] = blocker[0] if blocker else None
            result["replay_block_reason"] = blocker[1] if blocker else None
            return result

    def events(self, notification_id: UUID | str) -> list[dict[str, Any]]:
        with self.sessions() as session:
            return [
                dict(r)
                for r in session.execute(
                    select(events)
                    .where(events.c.notification_id == str(notification_id))
                    .order_by(events.c.at)
                ).mappings()
            ]

    def response(
        self, notification_id: UUID | str, *, replay: bool = False
    ) -> SendNotificationResponse:
        row = self.get(notification_id)
        n = Notification.model_validate(row["notification"])
        result = NotificationResult.model_validate(row["outcome"])
        owner_id = row.get("obligation_owner_id")
        effective_ack = row.get("effective_ack_status")
        return SendNotificationResponse(
            notification_id=n.notification_id,
            status=DeliveryStatus(row["status"]),
            channels_attempted=result.channels_attempted,
            channels_succeeded=result.channels_succeeded,
            channels_failed=result.channels_failed,
            require_ack=bool(n.require_ack),
            ack_status=AckStatus(row["ack_status"]) if row["ack_status"] else None,
            obligation_owner_id=UUID(str(owner_id)) if owner_id else None,
            effective_ack_status=AckStatus(effective_ack) if effective_ack else None,
            ack_inherited=bool(row.get("ack_inherited", False)),
            obligation_resolution_status=row["obligation_resolution_status"],
            obligation_resolution_error=row["obligation_resolution_error"],
            idempotent_replay=replay,
            created_at=n.created_at,
            message=(
                f"{row['status'].lower()}: obligation lineage unresolved "
                f"({row['obligation_resolution_error']})"
                if row["obligation_resolution_status"] == "UNRESOLVED"
                else (
                    f"{row['status'].lower()}: delivery obligation {owner_id}"
                    if row["ack_inherited"]
                    else row["status"].lower()
                )
            ),
        )

    def accept(
        self, request: SendNotificationRequest, *, principal: str, _retry: int = 0
    ) -> SendNotificationResponse:
        if not principal:
            raise ValueError("An authenticated principal is required")
        fingerprint = digest(request.model_dump(mode="json"))
        key = digest([principal, request.source, request.idempotency_key or str(uuid4())])
        with self.sessions() as session:
            existing = session.execute(select(work).where(work.c.key == key)).mappings().first()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise Conflict("Idempotency key reused with different request content")
                return self.response(existing["id"], replay=True)
        try:
            with self.sessions.begin() as session:
                # Policy revision and accepted obligation linearize together.
                n = self.policy_runtime.resolve(request, session=session, principal=principal)
                provenance = n.metadata["uns_resolution"]
                effective = provenance["effective"]
                now = self.clock()
                identifier = str(n.notification_id)
                # Unique claim prevents concurrent intake from creating duplicate work.
                result = NotificationResult(
                    notification_id=n.notification_id, status=DeliveryStatus.PENDING
                )
                session.execute(
                    insert(work).values(
                        id=identifier,
                        key=key,
                        fingerprint=fingerprint,
                        principal=principal,
                        notification=n.model_dump(mode="json"),
                        status="PENDING",
                        outcome=result.model_dump(mode="json"),
                        attempts=0,
                        next_attempt=now,
                        lease_until=0,
                        dead_letter=False,
                    )
                )
                # Coalescing is scoped to the same effective delivery obligation.
                dedup_key = digest(
                    [principal, request.source, n.dedup_key, provenance["effective_hash"]]
                )
                current = (
                    session.execute(select(dedup).where(dedup.c.key == dedup_key).with_for_update())
                    .mappings()
                    .first()
                )
                now = self.clock()
                owner = None
                failed_owner = None
                if current and current["owner_id"]:
                    candidate = (
                        session.execute(
                            select(work).where(
                                work.c.id == current["owner_id"],
                                work.c.dedup_generation == current["generation"],
                                work.c.dedup_owner_id.is_(None),
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if candidate and candidate["status"] in ("PENDING", "DELIVERED"):
                        owner = candidate
                    elif (
                        candidate
                        and candidate["status"] == "FAILED"
                        and candidate["dedup_successor_id"] is None
                        and current["until"] > now
                    ):
                        failed_owner = candidate
                if owner and current and owner["status"] == "DELIVERED" and current["until"] <= now:
                    owner = None
                generation = (
                    current["generation"]
                    if owner is not None and current is not None
                    else (current["generation"] + 1 if current else 1)
                )
                values = {"dedup_key": dedup_key, "dedup_generation": generation}
                if owner:
                    values["dedup_owner_id"] = owner["id"]
                    if owner["status"] == "DELIVERED":
                        result = result.model_copy(update={"status": DeliveryStatus.DEDUPLICATED})
                        values.update(status="DEDUPLICATED", outcome=result.model_dump(mode="json"))
                    self._event(
                        session,
                        identifier,
                        "DEDUP_LINKED",
                        {
                            "owner_id": owner["id"],
                            "generation": generation,
                            "owner_status": owner["status"],
                        },
                    )
                else:
                    claim = {
                        "owner_id": identifier,
                        "generation": generation,
                        "until": now + effective["dedup_window_seconds"],
                    }
                    if current:
                        session.execute(
                            update(dedup).where(dedup.c.key == dedup_key).values(**claim)
                        )
                    else:
                        session.execute(insert(dedup).values(key=dedup_key, **claim))
                    if failed_owner:
                        session.execute(
                            update(work)
                            .where(
                                work.c.id == failed_owner["id"],
                                work.c.dedup_successor_id.is_(None),
                            )
                            .values(dedup_successor_id=identifier)
                        )
                        self._event(
                            session,
                            failed_owner["id"],
                            "OBLIGATION_HANDED_OFF",
                            {
                                "successor_id": identifier,
                                "generation": generation,
                            },
                        )
                session.execute(update(work).where(work.c.id == identifier).values(**values))
                self._audit(session, n, result, event="accepted", principal=principal)
                self._event(session, identifier, "ACCEPTED", provenance)
        except IntegrityError:
            # Another process won intake or dedup claim; re-read committed state.
            if _retry >= 3:
                raise
            return self.accept(request, principal=principal, _retry=_retry + 1)
        if self.shadow_evaluator.enabled:
            with contextlib.suppress(Exception):
                self.shadow_evaluator.evaluate_intake(request, decision_id=identifier)
        return self.response(identifier)

    async def send(
        self, request: SendNotificationRequest, *, principal: str
    ) -> SendNotificationResponse:
        response = self.accept(request, principal=principal)
        if not response.idempotent_replay:
            await self.dispatch(response.notification_id)
        return self.response(response.notification_id, replay=response.idempotent_replay)

    def _before_attempt(
        self, identifier: str, token: str, channel: Channel, *, record_start: bool = True
    ) -> None:
        """Fence every new external call; effects already in flight remain uncertain."""
        now = self.clock()
        with self.sessions.begin() as session:
            owned = (
                session.connection()
                .execute(
                    update(work)
                    .where(
                        work.c.id == identifier,
                        work.c.status == "PENDING",
                        work.c.lease_token == token,
                        work.c.lease_until > now,
                    )
                    .values(lease_until=work.c.lease_until)
                )
                .rowcount
            )
            if not owned:
                raise DeliveryLeaseLostError("Delivery lease expired or belongs to another worker")
            row = session.execute(select(work).where(work.c.id == identifier)).mappings().one()
            if row["lease_until"] <= self.clock():
                raise DeliveryLeaseLostError("Delivery lease expired while waiting for storage")
            if record_start:
                self._event(
                    session,
                    identifier,
                    "CHANNEL_ATTEMPT_STARTED",
                    {
                        "channel": channel.value,
                        "lease_token": token,
                        "attempt": row["attempts"],
                        "cycle": row["cycle"],
                        "cycle_attempt": row["cycle_attempts"],
                        "provider_effect_may_have_occurred": True,
                    },
                )
        if row["lease_until"] <= self.clock():
            raise DeliveryLeaseLostError("Delivery lease expired while committing attempt evidence")

    def _record_lease_loss(self, identifier: str, token: str, row: dict[str, Any]) -> None:
        with self.sessions.begin() as session:
            self._event(
                session,
                identifier,
                "LEASE_LOST",
                {
                    "lease_token": token,
                    "attempt": row["attempts"],
                    "provider_effect_may_have_occurred": True,
                },
            )

    def _channel_result(
        self, identifier: str, token: str, row: dict[str, Any], result: DeliveryResult
    ) -> None:
        # Append-only observations are attributed to the original lease. They
        # never overwrite a replacement worker's state or claim delivery success.
        with self.sessions.begin() as session:
            self._event(
                session,
                identifier,
                "CHANNEL_ATTEMPT_RESULT",
                {
                    "lease_token": token,
                    "attempt": row["attempts"],
                    "cycle": row["cycle"],
                    "cycle_attempt": row["cycle_attempts"],
                    "channel": result.channel.value,
                    "success": result.success,
                    "message_id": result.message_id,
                    "error": result.error,
                    "metadata": result.metadata or {},
                    "provider_observed_at": result.delivered_at.isoformat()
                    if result.delivered_at
                    else None,
                },
            )

    def _current_owner(self, session: Session, claim: Any, now: float) -> Any:
        if not claim or not claim["owner_id"]:
            return None
        owner = (
            session.execute(
                select(work).where(
                    work.c.id == claim["owner_id"],
                    work.c.dedup_generation == claim["generation"],
                    work.c.dedup_owner_id.is_(None),
                )
            )
            .mappings()
            .first()
        )
        if owner and (
            owner["status"] == "PENDING"
            or (owner["status"] == "DELIVERED" and claim["until"] > now)
        ):
            return owner
        return None

    def _settle_followers(
        self, session: Session, owner: dict[str, Any], *, succeeded: bool
    ) -> None:
        followers = list(
            session.execute(
                select(work)
                .where(
                    work.c.status == "PENDING",
                    work.c.dedup_owner_id == owner["id"],
                    work.c.dedup_generation == owner["dedup_generation"],
                )
                .order_by(work.c.id)
            ).mappings()
        )
        claim = (
            session.execute(
                select(dedup).where(dedup.c.key == owner["dedup_key"]).with_for_update()
            )
            .mappings()
            .first()
        )
        current = self._current_owner(session, claim, self.clock())
        target = owner if succeeded else current
        if target and target["id"] == owner["id"] and not succeeded:
            target = None
        if not target and not followers:
            return
        if not target:
            # Election is legal only after locking and observing the live claim.
            # Pending owners remain live after TTL expiry; delivered owners do not.
            successor = followers[0]
            generation = (
                max(owner["dedup_generation"] or 0, claim["generation"] if claim else 0) + 1
            )
            target = {**successor, "dedup_generation": generation}
            values = {
                "owner_id": target["id"],
                "generation": generation,
                # Promotion transfers ownership, not the suppression window.
                "until": claim["until"] if claim else self.clock(),
            }
            if claim:
                session.execute(
                    update(dedup)
                    .where(
                        dedup.c.key == owner["dedup_key"],
                        dedup.c.owner_id == claim["owner_id"],
                        dedup.c.generation == claim["generation"],
                    )
                    .values(**values)
                )
            else:
                session.execute(insert(dedup).values(key=owner["dedup_key"], **values))
        satisfied = succeeded or target["status"] == "DELIVERED"
        if not succeeded:
            # Durable lineage survives expiration/replacement of the live claim.
            session.execute(
                update(work).where(work.c.id == owner["id"]).values(dedup_successor_id=target["id"])
            )
            self._event(
                session,
                owner["id"],
                "OBLIGATION_HANDED_OFF",
                {
                    "successor_id": target["id"],
                    "generation": target["dedup_generation"],
                },
            )
        for follower in followers:
            n = Notification.model_validate(follower["notification"])
            result = NotificationResult.model_validate(follower["outcome"])
            promoted = follower["id"] == target["id"]
            values = {
                "dedup_owner_id": None if promoted else target["id"],
                "dedup_generation": target["dedup_generation"],
            }
            payload = {
                "previous_owner_id": owner["id"],
                "owner_id": target["id"],
                "generation": target["dedup_generation"],
            }
            if satisfied:
                result = result.model_copy(update={"status": DeliveryStatus.DEDUPLICATED})
                values.update(status="DEDUPLICATED", outcome=result.model_dump(mode="json"))
                kind = "DEDUP_SATISFIED"
            else:
                values["next_attempt"] = self.clock()
                kind = "DEDUP_OWNER_PROMOTED" if promoted else "DEDUP_RELINKED"
            session.execute(update(work).where(work.c.id == follower["id"]).values(**values))
            self._audit(session, n, result, event=kind, **payload)
            self._event(session, follower["id"], kind, payload)

    async def dispatch(
        self,
        notification_id: UUID | str | None = None,
        *,
        limit: int | None = None,
    ) -> bool | int:
        if notification_id is None:
            batch_limit = limit if limit is not None else 100
            if batch_limit <= 0:
                return 0
            candidate_limit = max(batch_limit * 4, 32)
            now = self.clock()
            with self.sessions() as session:
                ids = list(
                    session.execute(
                        select(work.c.id)
                        .where(
                            work.c.status == "PENDING",
                            work.c.dedup_owner_id.is_(None),
                            work.c.next_attempt <= now,
                            work.c.lease_until <= now,
                        )
                        .order_by(work.c.next_attempt, work.c.id)
                        .limit(candidate_limit)
                    ).scalars()
                )
            dispatched = 0
            for identifier in ids:
                if await self.dispatch(identifier):
                    dispatched += 1
                    if dispatched >= batch_limit:
                        break
            return dispatched

        identifier, token, now = str(notification_id), str(uuid4()), self.clock()
        with self.sessions.begin() as session:
            claimed = (
                session.connection()
                .execute(
                    update(work)
                    .where(
                        work.c.id == identifier,
                        work.c.status == "PENDING",
                        work.c.dedup_owner_id.is_(None),
                        work.c.lease_until <= now,
                        work.c.next_attempt <= now,
                    )
                    .values(
                        lease_token=token,
                        lease_until=now + self.lease_seconds,
                        attempts=work.c.attempts + 1,
                        cycle_attempts=work.c.cycle_attempts + 1,
                    )
                )
                .rowcount
            )
            if not claimed:
                return False
            row = dict(
                session.execute(select(work).where(work.c.id == identifier)).mappings().one()
            )
            self._event(
                session,
                identifier,
                "ATTEMPT_STARTED",
                {
                    "attempt": row["attempts"],
                    "cycle": row["cycle"],
                    "cycle_attempt": row["cycle_attempts"],
                    "recovery_may_repeat_provider_effect": row["attempts"] > 1,
                },
            )
        n = Notification.model_validate(row["notification"])
        try:
            if row["cycle_attempts"] > self.max_attempts:
                result = NotificationResult(
                    notification_id=n.notification_id,
                    status=DeliveryStatus.FAILED,
                    error_message="Provider outcome unknown: recovery exhausted the attempt budget",
                )
            else:
                result = await self.delivery.deliver(
                    n,
                    before_attempt=lambda channel: self._before_attempt(identifier, token, channel),
                    check_lease=lambda channel: self._before_attempt(
                        identifier, token, channel, record_start=False
                    ),
                    after_attempt=lambda result: self._channel_result(
                        identifier, token, row, result
                    ),
                )
        except DeliveryLeaseLostError:
            self._record_lease_loss(identifier, token, row)
            return False
        except DeliveryEvidenceError:
            # The provider may have succeeded. Do not turn an evidence-store
            # failure into a provider failure or trigger another fallback here.
            log.exception("Channel evidence commit failed; lease recovery retains uncertainty")
            return False
        except DeliveryError as exc:
            result = exc.result or NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.FAILED,
                channels_attempted=list(exc.channel_errors),
                channels_failed=list(exc.channel_errors),
                error_message=str(exc),
            )
        except Exception as exc:
            result = NotificationResult(
                notification_id=n.notification_id,
                status=DeliveryStatus.FAILED,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        succeeded = result.status in (DeliveryStatus.SUCCESS, DeliveryStatus.DELIVERED)
        exhausted = not succeeded and (
            row["cycle_attempts"] >= self.max_attempts
            or n.delivery_mode == DeliveryMode.BEST_EFFORT
        )
        next_status = "DELIVERED" if succeeded else ("FAILED" if exhausted else "PENDING")
        with self.sessions.begin() as session:
            # Intake and settlement share dedup -> owner lock order. This also
            # protects followers on PostgreSQL, which has no SQLite writer lock.
            session.execute(
                select(dedup).where(dedup.c.key == row["dedup_key"]).with_for_update()
            ).first()
            # Acquire the row's write lock before reading the clock; a lock wait
            # must not make an already-expired lease look valid at commit.
            owned = (
                session.connection()
                .execute(
                    update(work)
                    .where(work.c.id == identifier, work.c.lease_token == token)
                    .values(lease_until=work.c.lease_until)
                )
                .rowcount
            )
            if not owned or row["lease_until"] <= self.clock():
                self._event(
                    session,
                    identifier,
                    "LEASE_LOST",
                    {
                        "lease_token": token,
                        "attempt": row["attempts"],
                        "provider_effect_may_have_occurred": True,
                    },
                )
                return False
            now = self.clock()
            changes: dict[str, Any] = {
                "status": next_status,
                "outcome": result.model_dump(mode="json"),
                "lease_until": 0,
                "lease_token": None,  # nosec B105
                "next_attempt": now + self.retry_seconds * 2 ** min(row["cycle_attempts"] - 1, 10),
                "dead_letter": exhausted and n.delivery_mode == DeliveryMode.GUARANTEED,
            }
            if succeeded:
                changes["delivered_at"] = now
                if n.require_ack:
                    changes.update(
                        ack_status="PENDING", deadline=now + 60 * (n.ack_timeout_minutes or 15)
                    )
            session.execute(update(work).where(work.c.id == identifier).values(**changes))
            self._audit(
                session,
                n,
                result,
                attempt=row["attempts"],
                cycle=row["cycle"],
                cycle_attempt=row["cycle_attempts"],
                terminal=next_status,
                effective=n.metadata["uns_resolution"],
            )
            self._event(
                session,
                identifier,
                "DELIVERY_RESULT",
                {
                    "status": next_status,
                    "attempt": row["attempts"],
                    "cycle": row["cycle"],
                    "cycle_attempt": row["cycle_attempts"],
                    "dead_letter": changes["dead_letter"],
                    "outcome": result.model_dump(mode="json"),
                },
            )
            if succeeded or exhausted:
                self._settle_followers(session, row, succeeded=succeeded)
        return True

    async def run_once(self, *, limit: int = 100) -> None:
        await self.dispatch(limit=limit)
        self.expire()

    async def worker(self) -> None:
        async def dispatch_loop() -> None:
            while True:
                try:
                    await self.run_once()
                except Exception:
                    log.exception("UNS recovery worker iteration failed")
                await asyncio.sleep(1)

        async def timeout_loop() -> None:
            while True:
                try:
                    self.expire()
                except Exception:
                    log.exception("UNS response recovery iteration failed")
                await asyncio.sleep(1)

        async def callback_loop() -> None:
            while True:
                try:
                    await self.deliver_callbacks()
                except Exception:
                    log.exception("UNS callback recovery iteration failed")
                await asyncio.sleep(1)

        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(dispatch_loop())
            tasks.create_task(timeout_loop())
            tasks.create_task(callback_loop())

    def acknowledge(
        self,
        notification_id: UUID | str,
        *,
        actor: str,
        dismiss: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> AckResponse:
        if not actor:
            raise ValueError("An authenticated actor is required")
        return self._respond(
            str(notification_id), "DISMISSED" if dismiss else "ACKED", actor, metadata or {}
        )

    def _respond(
        self,
        identifier: str,
        target: str,
        actor: str,
        metadata: dict[str, Any],
        now: float | None = None,
    ) -> AckResponse:
        now = self.clock() if now is None else now
        with self.sessions.begin() as session:
            condition = [work.c.id == identifier, work.c.ack_status == "PENDING"]
            condition.append(
                work.c.deadline <= now if target == "TIMED_OUT" else work.c.deadline > now
            )
            changed = (
                session.connection()
                .execute(
                    update(work)
                    .where(*condition)
                    .values(
                        ack_status=target, actor=actor, responded_at=now, response_metadata=metadata
                    )
                )
                .rowcount
            )
            row = session.execute(select(work).where(work.c.id == identifier)).mappings().first()
            if row is None:
                raise KeyError(identifier)
            if not changed and row["ack_status"] != target:
                raise Conflict("Notification is not awaiting this response or its deadline elapsed")
            if not changed and row["actor"] != actor:
                raise Conflict("Terminal response belongs to another actor")
            if changed:
                session.add(
                    AckRow(
                        notification_id=UUID(identifier),
                        old_status="PENDING",
                        new_status=target,
                        acked_by=actor,
                        acked_at=datetime.fromtimestamp(now, UTC),
                        ack_metadata=metadata,
                        created_at=datetime.fromtimestamp(now, UTC),
                    )
                )
                self._event(session, identifier, target, {"actor": actor, "metadata": metadata})
            return AckResponse(
                notification_id=UUID(identifier),
                ack_status=AckStatus(target),
                acked_by=row["actor"],
                acked_at=datetime.fromtimestamp(row["responded_at"], UTC),
                metadata=row["response_metadata"] or {},
            )

    def resolve_pagerduty_target(
        self,
        *,
        dedup_key: str | None = None,
        notification_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a PagerDuty incident dedup_key or notification_id to a Runtime work row."""
        candidates: list[str] = []
        if notification_id:
            candidates.append(notification_id.strip())
        raw_dedup = (dedup_key or "").strip()
        stripped_dedup = raw_dedup[4:] if raw_dedup.startswith("uns-") else raw_dedup
        if stripped_dedup and stripped_dedup not in candidates:
            candidates.append(stripped_dedup)

        for candidate in candidates:
            with contextlib.suppress(ValueError, KeyError):
                parsed = UUID(candidate)
                return self.get(parsed)

        if not raw_dedup:
            raise KeyError("No matching PagerDuty notification found")

        normalized_keys = {raw_dedup, f"uns-{stripped_dedup}"}
        with self.sessions() as session:
            event_rows = list(
                session.execute(
                    select(events.c.notification_id, events.c.payload)
                    .where(events.c.kind == "CHANNEL_ATTEMPT_RESULT")
                    .order_by(events.c.at.desc())
                    .limit(500)
                ).mappings()
            )
            for ev in event_rows:
                payload = ev["payload"] or {}
                if payload.get("channel") == Channel.PAGERDUTY.value and (
                    payload.get("message_id") in normalized_keys
                    or (payload.get("metadata") or {}).get("pagerduty_dedup_key") in normalized_keys
                ):
                    return self.get(ev["notification_id"])

            work_rows = list(
                session.execute(
                    select(work.c.id, work.c.notification)
                    .where(work.c.dedup_owner_id.is_(None))
                    .order_by(work.c.delivered_at.desc(), work.c.id)
                    .limit(500)
                ).mappings()
            )
            for wr in work_rows:
                notif_json = wr["notification"] or {}
                if notif_json.get("dedup_key") == stripped_dedup:
                    return self.get(wr["id"])

        raise KeyError(raw_dedup)

    async def sync_pagerduty_incident(
        self,
        notification_id: UUID | str,
        *,
        resolve: bool = False,
    ) -> DeliveryResult | None:
        """Best-effort outbound propagation of an UNS response to PagerDuty Events API v2."""
        adapter = self.adapters.get_adapter(Channel.PAGERDUTY)
        if adapter is None:
            return None
        method_name = "resolve_incident" if resolve else "acknowledge_incident"
        method = getattr(adapter, method_name, None)
        if not callable(method):
            return None
        try:
            row = self.get(notification_id)
            outcome = row.get("outcome") or {}
            channels_succeeded = outcome.get("channels_succeeded") or []
            if Channel.PAGERDUTY.value not in channels_succeeded:
                return None
            notif = Notification.model_validate(row["notification"])
            pd_dedup_key = f"uns-{notif.dedup_key}" if notif.dedup_key else f"uns-{notif.notification_id}"
            result = await method(pd_dedup_key)
            with self.sessions.begin() as session:
                self._event(
                    session,
                    str(notification_id),
                    "PAGERDUTY_OUTBOUND_SYNC",
                    {
                        "action": "resolve" if resolve else "acknowledge",
                        "dedup_key": pd_dedup_key,
                        "success": bool(getattr(result, "success", False)),
                    },
                )
            return cast(DeliveryResult | None, result)
        except Exception:
            log.warning(
                "Best-effort PagerDuty outbound sync failed for notification_id=%s",
                notification_id,
                exc_info=True,
            )
            return None

    def expire(self, *, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        with self.sessions() as session:
            ids = list(
                session.execute(
                    select(work.c.id)
                    .where(work.c.ack_status == "PENDING", work.c.deadline <= now)
                    .order_by(work.c.deadline, work.c.id)
                    .limit(100)
                ).scalars()
            )
        for identifier in ids:
            with contextlib.suppress(Conflict):
                self._respond(
                    identifier,
                    "TIMED_OUT",
                    "uns-timeout-worker",
                    {"escalation_required": True},
                    now,
                )

    def _replay_blocker(self, session: Session, row: Any) -> tuple[str, str] | None:
        identifier = row["dedup_successor_id"]
        seen = {row["id"]}
        while identifier:
            if identifier in seen:
                return identifier, "UNRESOLVED_LINEAGE"
            seen.add(identifier)
            successor = (
                session.execute(select(work).where(work.c.id == identifier)).mappings().first()
            )
            if not successor or successor["dedup_key"] != row["dedup_key"]:
                return identifier, "UNRESOLVED_LINEAGE"
            if successor["status"] in ("PENDING", "DELIVERED", "DEDUPLICATED"):
                return identifier, successor["status"]
            identifier = successor["dedup_successor_id"]
        claim = (
            session.execute(select(dedup).where(dedup.c.key == row["dedup_key"])).mappings().first()
        )
        current = self._current_owner(session, claim, self.clock())
        if current and current["id"] != row["id"]:
            return current["id"], current["status"]
        return None

    def _replay_block(self, row: Any) -> tuple[str | None, str | None]:
        if "dead_letter" in row and not row["dead_letter"]:
            return None, None
        with self.sessions() as session:
            blocker = self._replay_blocker(session, row)
            return (blocker[0], blocker[1]) if blocker else (None, None)

    def replay(self, notification_id: UUID | str, *, actor: str) -> None:
        if not actor:
            raise ValueError("An authenticated actor is required")
        identifier = str(notification_id)
        with self.sessions.begin() as session:
            if self.engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = session.execute(select(work).where(work.c.id == identifier)).mappings().first()
            if not row:
                raise Conflict("Only exhausted dead-letter notifications can be replayed")
            claim = (
                session.execute(
                    select(dedup).where(dedup.c.key == row["dedup_key"]).with_for_update()
                )
                .mappings()
                .first()
            )
            row = (
                session.execute(select(work).where(work.c.id == identifier).with_for_update())
                .mappings()
                .one()
            )
            if not row["dead_letter"] or row["status"] != "FAILED":
                raise Conflict("Only exhausted dead-letter notifications can be replayed")
            blocker = self._replay_blocker(session, row)
            if blocker:
                target, status = blocker
                if status == "PENDING":
                    raise Conflict(f"Obligation recovery is pending under {target}")
                raise Conflict(
                    f"Obligation already satisfied or lineage unresolved: {target} ({status})"
                )
            # Replaying an earlier failed owner transfers its failed descendants
            # to this new recovery cycle, preserving satisfaction evidence later.
            successor_id = row["dedup_successor_id"]
            while successor_id:
                successor = (
                    session.execute(select(work).where(work.c.id == successor_id)).mappings().one()
                )
                next_successor = successor["dedup_successor_id"]
                session.execute(
                    update(work)
                    .where(work.c.id == successor_id)
                    .values(dedup_successor_id=identifier)
                )
                successor_id = next_successor
            generation = max(row["dedup_generation"] or 0, claim["generation"] if claim else 0) + 1
            if row["dedup_key"]:
                n = Notification.model_validate(row["notification"])
                values = {
                    "owner_id": identifier,
                    "generation": generation,
                    "until": self.clock()
                    + (n.metadata["uns_resolution"]["effective"]["dedup_window_seconds"]),
                }
                if claim:
                    session.execute(
                        update(dedup).where(dedup.c.key == row["dedup_key"]).values(**values)
                    )
                else:
                    session.execute(insert(dedup).values(key=row["dedup_key"], **values))
            session.execute(
                update(work)
                .where(work.c.id == identifier)
                .values(
                    status="PENDING",
                    cycle=work.c.cycle + 1,
                    cycle_attempts=0,
                    dead_letter=False,
                    lease_token=None,
                    next_attempt=self.clock(),
                    lease_until=0,
                    dedup_owner_id=None,
                    dedup_successor_id=None,
                    dedup_generation=generation,
                )
            )
            self._event(
                session,
                identifier,
                "REPLAY_REQUESTED",
                {
                    "actor": actor,
                    "cycle": row["cycle"] + 1,
                    "cumulative_attempts": row["attempts"],
                },
            )

    def dead_letters(self) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = list(
                session.execute(select(work).where(work.c.dead_letter.is_(True))).mappings()
            )
            result = []
            for row in rows:
                blocker = self._replay_blocker(session, row)
                result.append(
                    {
                        "notification_id": row["id"],
                        "status": row["status"],
                        "attempts": row["attempts"],
                        "cycle": row["cycle"],
                        "cycle_attempts": row["cycle_attempts"],
                        "outcome": row["outcome"],
                        "replay_blocked_by": blocker[0] if blocker else None,
                        "replay_block_reason": blocker[1] if blocker else None,
                    }
                )
            return result

    async def deliver_callbacks(self) -> None:
        """Retry terminal-event callbacks separately from committed state.

        Consumers deduplicate by event id: external callback delivery is at least
        once, including a crash between callback acceptance and local commit.
        """
        if self.callback is None:
            return
        now = self.clock()
        with self.sessions.begin() as session:
            session.connection().execute(
                update(events)
                .where(
                    events.c.callback_pending.is_(True),
                    events.c.callback_until <= now,
                    events.c.callback_attempts >= 3,
                )
                .values(
                    callback_pending=False,
                    callback_token=None,
                    callback_until=now,
                )
            )
            identifiers = list(
                session.execute(
                    select(events.c.id)
                    .where(
                        events.c.callback_pending.is_(True),
                        events.c.callback_until <= now,
                        events.c.callback_attempts < 3,
                    )
                    .order_by(events.c.callback_until, events.c.at, events.c.id)
                    .limit(100)
                ).scalars()
            )
        for identifier in identifiers:
            token = str(uuid4())
            claim_now = self.clock()
            with self.sessions.begin() as session:
                changed = (
                    session.connection()
                    .execute(
                        update(events)
                        .where(
                            events.c.id == identifier,
                            events.c.callback_pending.is_(True),
                            events.c.callback_until <= claim_now,
                            events.c.callback_attempts < 3,
                        )
                        .values(
                            callback_token=token,
                            callback_until=claim_now + 30,
                            callback_attempts=events.c.callback_attempts + 1,
                        )
                    )
                    .rowcount
                )
                if not changed:
                    continue
                event = dict(
                    session.execute(select(events).where(events.c.id == identifier))
                    .mappings()
                    .one()
                )
            error = None
            try:
                async with asyncio.timeout(10):
                    await self.callback(event)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:2000]
            with self.sessions.begin() as session:
                finish_now = self.clock()
                exhausted = int(event["callback_attempts"]) >= 3
                session.connection().execute(
                    update(events)
                    .where(events.c.id == identifier, events.c.callback_token == token)
                    .values(
                        callback_pending=error is not None and not exhausted,
                        callback_error=error,
                        callback_until=(
                            finish_now
                            if error is None or exhausted
                            else finish_now + 2 ** event["callback_attempts"]
                        ),
                        callback_token=None,
                    )
                )

    def resolve_failure(self, notification_id: UUID, *, actor: str) -> bool:
        if not actor:
            raise ValueError("An authenticated actor is required")
        with self.sessions.begin() as session:
            changed = (
                session.connection()
                .execute(
                    update(work)
                    .where(work.c.id == str(notification_id), work.c.dead_letter.is_(True))
                    .values(dead_letter=False)
                )
                .rowcount
            )
            if changed:
                self._event(session, str(notification_id), "FAILURE_RESOLVED", {"actor": actor})
            return bool(changed)

    def operational_progress(self) -> dict[str, Any]:
        """Aggregate retained operational evidence without loading work histories.

        Pending age starts at durable acceptance, independently of retry backoff.
        UNKNOWN counts retained channel-result observations, not unique obligations.
        """
        now = self.clock()
        pending = (work.c.status == "PENDING", work.c.dedup_owner_id.is_(None))
        callbacks = (
            events.c.callback_pending.is_(True),
            events.c.callback_attempts < 3,
        )
        attempt_available_at = case(
            (work.c.lease_until > work.c.next_attempt, work.c.lease_until),
            else_=work.c.next_attempt,
        )
        summary = select(
            select(func.count()).select_from(work).where(*pending)
            .scalar_subquery().label("pending_count"),
            select(func.min(events.c.at))
            .select_from(work.join(events, work.c.id == events.c.notification_id))
            .where(*pending, events.c.kind == "ACCEPTED")
            .scalar_subquery().label("oldest_accepted_at"),
            select(func.min(attempt_available_at))
            .where(*pending, work.c.next_attempt <= now, work.c.lease_until <= now)
            .scalar_subquery().label("oldest_due_attempt_at"),
            select(func.count()).select_from(work)
            .where(work.c.ack_status == "PENDING", work.c.deadline <= now)
            .scalar_subquery().label("overdue_ack_count"),
            select(func.count()).select_from(events).where(*callbacks)
            .scalar_subquery().label("pending_callback_count"),
            select(func.min(events.c.callback_until))
            .where(*callbacks, events.c.callback_until <= now)
            .scalar_subquery().label("oldest_due_callback_at"),
            select(func.count()).select_from(work).where(work.c.dead_letter.is_(True))
            .scalar_subquery().label("unresolved_failure_count"),
            select(func.count()).select_from(events)
            .where(
                events.c.kind == "CHANNEL_ATTEMPT_RESULT",
                events.c.payload["metadata"]["provider_outcome"].as_string() == "UNKNOWN",
            )
            .scalar_subquery().label("unknown_attempt_count"),
        )
        with self.sessions() as session:
            row = session.execute(summary).mappings().one()

        def age(timestamp: float | None) -> float | None:
            return round(max(0.0, now - timestamp), 3) if timestamp is not None else None

        return {
            "pending_count": row["pending_count"],
            "oldest_pending_age_seconds": age(row["oldest_accepted_at"]),
            "oldest_due_attempt_lateness_seconds": age(row["oldest_due_attempt_at"]),
            "overdue_ack_count": row["overdue_ack_count"],
            "pending_callback_count": row["pending_callback_count"],
            "oldest_callback_retry_age_seconds": age(row["oldest_due_callback_at"]),
            "unresolved_failure_count": row["unresolved_failure_count"],
            "unknown_attempt_count": row["unknown_attempt_count"],
        }

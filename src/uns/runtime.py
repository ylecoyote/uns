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
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Integer,
    String,
    Table,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agsignal.responses import AckResponse, SendNotificationRequest, SendNotificationResponse
from agsignal.signaling import _resolve_notification
from db.audit_store import SQLAlchemyAuditStore, delivery_audit_row
from db.models import AckAuditRecord as AckRow
from db.models import Base
from notification.audit import create_audit_record
from notification.models import (
    AckStatus,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationResult,
)
from notification.policies import get_policy_registry
from notification.service import DeliveryError, DeliveryService, SimpleAdapterRegistry

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
    ) -> None:
        options: dict[str, Any] = {}
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            options = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
        self.engine = create_engine(database_url, **options)
        if create_tables:
            Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine)
        self.audit_store = SQLAlchemyAuditStore(self.sessions)
        self.adapters = adapters or SimpleAdapterRegistry()
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.max_attempts = max_attempts
        self.retry_seconds = retry_seconds
        self.clock = clock
        self.callback = callback
        self.lease_seconds = 60.0
        self.delivery = DeliveryService(self.adapters, check_deduplication=False)

    def _event(
        self, session: Session, notification_id: str, kind: str, payload: dict[str, Any]
    ) -> None:
        session.execute(
            insert(events).values(
                id=str(uuid4()),
                notification_id=notification_id,
                kind=kind,
                at=self.clock(),
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
        session.add(
            delivery_audit_row(create_audit_record(notification, result, metadata=metadata))
        )

    def get(self, notification_id: UUID | str) -> dict[str, Any]:
        with self.sessions() as session:
            row = (
                session.execute(select(work).where(work.c.id == str(notification_id)))
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError(str(notification_id))
            return dict(row)

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
        return SendNotificationResponse(
            notification_id=n.notification_id,
            status=DeliveryStatus(row["status"]),
            channels_attempted=result.channels_attempted,
            channels_succeeded=result.channels_succeeded,
            channels_failed=result.channels_failed,
            require_ack=bool(n.require_ack),
            ack_status=AckStatus(row["ack_status"]) if row["ack_status"] else None,
            idempotent_replay=replay,
            created_at=n.created_at,
            message=row["status"].lower(),
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
        _, n = _resolve_notification(request)
        if not n.channels:
            raise ValueError("A notification requires at least one delivery channel")
        if n.delivery_mode == DeliveryMode.GUARANTEED and not any(
            c != Channel.WEBSOCKET for c in n.channels
        ):
            raise ValueError(
                "GUARANTEED requires a persistent channel; choose BEST_EFFORT for WebSocket-only preview"
            )
        policy = get_policy_registry().get_sync(n.notification_type)
        base_hash = n.policy_config_hash or digest(
            policy.model_dump(mode="json") if policy else {"defaults_version": 1}
        )
        effective = {
            k: n.model_dump(mode="json")[k]
            for k in ("channels", "delivery_mode", "require_ack", "ack_timeout_minutes", "priority")
        }
        effective["dedup_window_seconds"] = get_policy_registry().get_dedup_window(
            n.notification_type
        )
        provenance = {
            "policy_hash": base_hash,
            "defaults_version": 1 if policy is None else None,
            "effective": effective,
            "effective_hash": digest(effective),
            "principal": principal,
            "overrides": {
                k: request.model_dump(mode="json").get(k)
                for k in ("delivery_mode", "require_ack", "priority")
            },
        }
        n = n.model_copy(
            update={
                "policy_config_hash": base_hash,
                "policy_config_id": n.policy_config_id or uuid5(NAMESPACE_URL, base_hash),
                "policy_evaluation_id": n.policy_evaluation_id or uuid4(),
                "metadata": {**n.metadata, "uns_resolution": provenance},
            }
        )
        now = self.clock()
        identifier = str(n.notification_id)
        try:
            with self.sessions.begin() as session:
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
                dedup_key = digest([principal, request.source, n.dedup_key])
                current = (
                    session.execute(select(dedup).where(dedup.c.key == dedup_key))
                    .mappings()
                    .first()
                )
                suppressed = current is not None and current["until"] > now
                if not suppressed:
                    if current:
                        changed = (
                            session.connection()
                            .execute(
                                update(dedup)
                                .where(dedup.c.key == dedup_key, dedup.c.until <= now)
                                .values(until=now + effective["dedup_window_seconds"])
                            )
                            .rowcount
                        )
                        suppressed = not changed
                    else:
                        session.execute(
                            insert(dedup).values(
                                key=dedup_key, until=now + effective["dedup_window_seconds"]
                            )
                        )
                if suppressed:
                    result = result.model_copy(update={"status": DeliveryStatus.DEDUPLICATED})
                    session.connection().execute(
                        update(work)
                        .where(work.c.id == identifier)
                        .values(status="DEDUPLICATED", outcome=result.model_dump(mode="json"))
                    )
                self._audit(session, n, result, event="accepted", principal=principal)
                self._event(session, identifier, "ACCEPTED", provenance)
        except IntegrityError:
            # Another process won intake or dedup claim; re-read committed state.
            if _retry >= 3:
                raise
            return self.accept(request, principal=principal, _retry=_retry + 1)
        return self.response(identifier)

    async def send(
        self, request: SendNotificationRequest, *, principal: str
    ) -> SendNotificationResponse:
        response = self.accept(request, principal=principal)
        if not response.idempotent_replay:
            await self.dispatch(response.notification_id)
        return self.response(response.notification_id, replay=response.idempotent_replay)

    async def dispatch(self, notification_id: UUID | str) -> bool:
        identifier, token, now = str(notification_id), str(uuid4()), self.clock()
        with self.sessions.begin() as session:
            claimed = (
                session.connection()
                .execute(
                    update(work)
                    .where(
                        work.c.id == identifier,
                        work.c.status == "PENDING",
                        work.c.lease_until <= now,
                        work.c.next_attempt <= now,
                    )
                    .values(
                        lease_token=token,
                        lease_until=now + self.lease_seconds,
                        attempts=work.c.attempts + 1,
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
                    "recovery_may_repeat_provider_effect": row["attempts"] > 1,
                },
            )
        n = Notification.model_validate(row["notification"])
        try:
            if row["attempts"] > self.max_attempts:
                result = NotificationResult(
                    notification_id=n.notification_id,
                    status=DeliveryStatus.FAILED,
                    error_message="Provider outcome unknown: recovery exhausted the attempt budget",
                )
            else:
                result = await self.delivery.deliver(n)
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
            row["attempts"] >= self.max_attempts or n.delivery_mode == DeliveryMode.BEST_EFFORT
        )
        next_status = "DELIVERED" if succeeded else ("FAILED" if exhausted else "PENDING")
        now = self.clock()
        changes: dict[str, Any] = {
            "status": next_status,
            "outcome": result.model_dump(mode="json"),
            "lease_until": 0,
            "lease_token": None,  # nosec B105
            "next_attempt": now + self.retry_seconds * 2 ** min(row["attempts"] - 1, 10),
            "dead_letter": exhausted and n.delivery_mode == DeliveryMode.GUARANTEED,
        }
        if succeeded:
            changes["delivered_at"] = now
            if n.require_ack:
                changes.update(
                    ack_status="PENDING", deadline=now + 60 * (n.ack_timeout_minutes or 15)
                )
        with self.sessions.begin() as session:
            changed = (
                session.connection()
                .execute(
                    update(work)
                    .where(work.c.id == identifier, work.c.lease_token == token)
                    .values(**changes)
                )
                .rowcount
            )
            if not changed:
                return False  # A recovered worker owns the result now.
            self._audit(
                session,
                n,
                result,
                attempt=row["attempts"],
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
                    "dead_letter": changes["dead_letter"],
                    "outcome": result.model_dump(mode="json"),
                },
            )
        return True

    async def run_once(self) -> None:
        now = self.clock()
        with self.sessions() as session:
            ids = list(
                session.execute(
                    select(work.c.id)
                    .where(
                        work.c.status == "PENDING",
                        work.c.next_attempt <= now,
                        work.c.lease_until <= now,
                    )
                    .limit(100)
                ).scalars()
            )
        for identifier in ids:
            await self.dispatch(identifier)
        self.expire()
        await self.deliver_callbacks()

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
                    await self.deliver_callbacks()
                except Exception:
                    log.exception("UNS response recovery iteration failed")
                await asyncio.sleep(1)

        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(dispatch_loop())
            tasks.create_task(timeout_loop())

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
            if changed:
                session.add(
                    AckRow(
                        notification_id=UUID(identifier),
                        old_status="PENDING",
                        new_status=target,
                        acked_by=actor,
                        acked_at=datetime.fromtimestamp(now, UTC),
                        ack_metadata=metadata,
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

    def expire(self, *, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        with self.sessions() as session:
            ids = list(
                session.execute(
                    select(work.c.id).where(work.c.ack_status == "PENDING", work.c.deadline <= now)
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

    def replay(self, notification_id: UUID | str, *, actor: str) -> None:
        if not actor:
            raise ValueError("An authenticated actor is required")
        with self.sessions.begin() as session:
            changed = (
                session.connection()
                .execute(
                    update(work)
                    .where(work.c.id == str(notification_id), work.c.dead_letter.is_(True))
                    .values(
                        status="PENDING",
                        dead_letter=False,
                        next_attempt=self.clock(),
                        lease_until=0,
                    )
                )
                .rowcount
            )
            if not changed:
                raise Conflict("Only exhausted dead-letter notifications can be replayed")
            self._event(session, str(notification_id), "REPLAY_REQUESTED", {"actor": actor})

    def dead_letters(self) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = session.execute(select(work).where(work.c.dead_letter.is_(True))).mappings()
            return [
                {
                    "notification_id": r["id"],
                    "status": r["status"],
                    "attempts": r["attempts"],
                    "outcome": r["outcome"],
                }
                for r in rows
            ]

    async def deliver_callbacks(self) -> None:
        """Retry terminal-event callbacks separately from committed state.

        Consumers deduplicate by event id: external callback delivery is at least
        once, including a crash between callback acceptance and local commit.
        """
        if self.callback is None:
            return
        now = self.clock()
        with self.sessions() as session:
            identifiers = list(
                session.execute(
                    select(events.c.id)
                    .where(
                        events.c.callback_pending.is_(True),
                        events.c.callback_until <= now,
                        events.c.callback_attempts < 3,
                    )
                    .limit(100)
                ).scalars()
            )
        for identifier in identifiers:
            token = str(uuid4())
            with self.sessions.begin() as session:
                changed = (
                    session.connection()
                    .execute(
                        update(events)
                        .where(
                            events.c.id == identifier,
                            events.c.callback_pending.is_(True),
                            events.c.callback_until <= now,
                            events.c.callback_attempts < 3,
                        )
                        .values(
                            callback_token=token,
                            callback_until=now + 30,
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
                await asyncio.wait_for(self.callback(event), timeout=10)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:2000]
            with self.sessions.begin() as session:
                session.connection().execute(
                    update(events)
                    .where(events.c.id == identifier, events.c.callback_token == token)
                    .values(
                        callback_pending=error is not None,
                        callback_error=error,
                        callback_until=self.clock() + 2 ** event["callback_attempts"],
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

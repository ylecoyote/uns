"""AGSignal write-side service layer.

Async orchestration functions for governance-signal mutations: send_signal,
acknowledge, dismiss, simulate_signal. Async — no FastAPI imports. HTTP
route handlers and MCP tools both call these. There is no other source
of truth for the write path.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

# NOTE: response models (`AckResponse`) currently live in
# `mcp_server.routes_notification` alongside the legacy route handlers.
# Phase 5 of the v0.2 refactor relocates them to a dedicated module (likely
# `mcp_server.read_models` or a new `agsignal.responses` module). Until then
# we import from their current home.
from mcp_server.routes_notification import AckResponse  # legacy location; Phase 5 relocates
from notification.acknowledgment import get_ack_engine
from notification.audit import (
    AuditPersistenceError,
    AuditStore,
    create_ack_audit_record,
)
from notification.models import AckStatus

logger = logging.getLogger(__name__)

__all__ = ["acknowledge"]


async def acknowledge(
    *,
    notification_id: UUID,
    acked_by: str,
    metadata: dict[str, Any] | None = None,
    audit_store: AuditStore,
) -> AckResponse:
    """Acknowledge a notification, persisting the audit row before state mutation.

    The audit row is written before the engine state mutates. If audit
    persistence fails, the engine state is not advanced and the caller
    receives :class:`AuditPersistenceError` — no HTTPException; the route
    layer translates to 503. ``KeyError`` (notification not found) is
    similarly raised as the typed domain error; the route translates to
    404. :class:`InvalidAckTransitionError` propagates unchanged for the
    route to translate to 409.

    Args:
        notification_id: UUID of the notification to acknowledge.
        acked_by: Identifier of the acknowledging user/system. The route
            layer derives this from the authenticated principal (and any
            override from the request body) before calling.
        metadata: Optional additional metadata recorded with the ack event.
        audit_store: Audit storage backend used to persist the ack audit
            row before the engine state transition is committed.

    Returns:
        :class:`AckResponse` describing the acknowledgment.

    Raises:
        KeyError: If the notification is not found in the ack engine.
        InvalidAckTransitionError: If the requested transition is invalid.
        AuditPersistenceError: If the audit row cannot be persisted; the
            engine state is not advanced in this case.
    """
    engine = get_ack_engine()

    event = engine.ack(
        notification_id=notification_id,
        ack_status=AckStatus.ACKED,
        acked_by=acked_by,
        metadata=metadata or {},
        before_commit=lambda old_status, ack_event: _persist_ack_audit(
            audit_store=audit_store,
            notification_id=notification_id,
            old_status=old_status,
            new_status=ack_event.ack_status,
            acked_by=ack_event.acked_by,
            acked_at=ack_event.acked_at,
            metadata=ack_event.metadata,
        ),
    )

    logger.info(
        "Notification acknowledged via service: notification_id=%s acked_by=%s",
        notification_id,
        acked_by,
    )
    return AckResponse(
        notification_id=event.notification_id,
        ack_status=event.ack_status,
        acked_by=event.acked_by,
        acked_at=event.acked_at,
        metadata=event.metadata,
    )


def _persist_ack_audit(
    *,
    audit_store: AuditStore | None,
    notification_id: UUID,
    old_status: AckStatus | None,
    new_status: AckStatus,
    acked_by: str | None,
    acked_at: datetime,
    metadata: dict[str, Any],
) -> None:
    """Persist an ack audit row before the engine commits the state transition.

    Mirrors the route-layer ``_persist_ack_audit`` helper at
    ``mcp_server/routes_notification.py:343-382`` but raises the typed
    :class:`AuditPersistenceError` instead of a FastAPI ``HTTPException`` —
    the route layer translates the typed error to a 503. Task 7 deletes
    the duplicate route-side helper once both write routes delegate here.

    The ``audit_store`` parameter is typed ``AuditStore | None`` and the
    isinstance guard preserved for parity with the route-layer helper that
    sources the store via ``getattr(request.app.state, ...)`` (which can
    return ``None``). All Phase 2 callers pass a non-``None`` store, so the
    guard is effectively dead but kept to ease verbatim Task 7 deletion.
    """
    # Idempotent re-ack: no transition, no audit row written.
    if old_status == new_status:
        return
    # Defensive: route-layer parity (see docstring). Phase 2 callers always
    # supply a non-None audit_store.
    if not isinstance(audit_store, AuditStore):
        return
    try:
        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notification_id,
                old_status=old_status,
                new_status=new_status,
                acked_by=acked_by,
                acked_at=acked_at,
                metadata=metadata,
            )
        )
    except AuditPersistenceError:
        logger.error(
            "Failed to persist ack audit: notification_id=%s",
            notification_id,
        )
        raise

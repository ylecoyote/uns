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

from agsignal.responses import (
    AckResponse,
    SendNotificationRequest,
    SendNotificationResponse,
    SimulateNotificationResponse,
)
from notification.acknowledgment import configure_ack_engine, get_ack_engine
from notification.audit import (
    AuditPersistenceError,
    AuditStore,
    create_ack_audit_record,
    create_audit_record,
)
from notification.models import (
    AckStatus,
    Notification,
    NotificationResult,
)
from notification.policies import DEFAULT_DEDUP_WINDOW_SECONDS, get_policy_registry
from notification.sdk import NotificationSDK

logger = logging.getLogger(__name__)

__all__ = ["acknowledge", "dismiss", "send_signal", "simulate_signal"]


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
            new_status=AckStatus(ack_event.ack_status),
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


async def dismiss(
    *,
    notification_id: UUID,
    dismissed_by: str,
    metadata: dict[str, Any] | None = None,
    audit_store: AuditStore,
) -> AckResponse:
    """Dismiss a notification, persisting the audit row before state mutation.

    Mirrors :func:`acknowledge` but transitions to ``AckStatus.DISMISSED``.
    Dismissal indicates the operator saw the notification but chose not to
    formally acknowledge it; this is a terminal state.

    Args:
        notification_id: UUID of the notification to dismiss.
        dismissed_by: Identifier of the dismissing user/system. The route
            layer derives this from the authenticated principal (and any
            override from the request body) before calling.
        metadata: Optional additional metadata recorded with the dismiss event.
        audit_store: Audit storage backend used to persist the ack audit
            row before the engine state transition is committed.

    Returns:
        :class:`AckResponse` describing the dismissal.

    Raises:
        KeyError: If the notification is not found in the ack engine.
        InvalidAckTransitionError: If the requested transition is invalid.
        AuditPersistenceError: If the audit row cannot be persisted; the
            engine state is not advanced in this case.
    """
    engine = get_ack_engine()

    event = engine.ack(
        notification_id=notification_id,
        ack_status=AckStatus.DISMISSED,
        acked_by=dismissed_by,
        metadata=metadata or {},
        before_commit=lambda old_status, ack_event: _persist_ack_audit(
            audit_store=audit_store,
            notification_id=notification_id,
            old_status=old_status,
            new_status=AckStatus(ack_event.ack_status),
            acked_by=ack_event.acked_by,
            acked_at=ack_event.acked_at,
            metadata=ack_event.metadata,
        ),
    )

    logger.info(
        "Notification dismissed via service: notification_id=%s dismissed_by=%s",
        notification_id,
        dismissed_by,
    )
    return AckResponse(
        notification_id=event.notification_id,
        ack_status=event.ack_status,
        acked_by=event.acked_by,
        acked_at=event.acked_at,
        metadata=event.metadata,
    )


async def send_signal(
    *,
    request: SendNotificationRequest,
    audit_store: AuditStore,
    idempotency_store: Any,
    transport_metadata: dict[str, Any] | None = None,
) -> SendNotificationResponse:
    """Accept and persist an AGSignal governance signal.

    Canonical accept path that consolidates the previously duplicated
    accept-side logic. The legacy HTTP and MCP send paths now both delegate
    here.

    Idempotency is preserved via the caller-supplied ``idempotency_store``.
    Each transport keeps its own store (in-process dict on ``RuntimeState``
    for MCP; ``app.state.http_idempotency_records`` dict for HTTP). Phase 5
    consolidates onto a Redis-backed :class:`IdempotencyService`. The
    parameter is duck-typed (``.get`` / item assignment) so both back-ends
    work without a type change in this task.

    The ``transport_metadata`` argument is the verbatim ``audit_metadata``
    dict written into the delivery audit record. Operator audit forensics
    rely on the distinction between ``{"runtime": "standalone_http"}`` and
    ``{"runtime": "agsignal_mcp"}`` — the function does not unify the tags,
    only round-trips what the caller supplies.

    Note: this function ACCEPTS the signal (resolves the notification,
    registers with the ack engine if ``require_ack``, persists the audit
    row, returns the response). It does NOT perform actual channel
    delivery — Slack/PagerDuty/email dispatch lives in
    ``notification.service.dispatch_notification``, and DLQ-on-failure is
    wired there for ``GUARANTEED``-mode failures. Unifying the accept-only
    path with the dispatch+DLQ path is tracked in
    ``docs/post-v0.2-followups.md`` item F-1, deferred until after
    v0.2 Phase 5 ships.

    The route-layer ``send_notification`` additionally performs websocket
    fanout (replay store, connection manager, fanout publisher). That
    dispatch stays in the route layer because the websocket runtime state
    is FastAPI-app-scoped; the route adapter calls this function then
    performs the websocket dispatch on the returned notification.

    Args:
        request: Validated send-notification request from the producer.
        audit_store: Delivery audit storage backend.
        idempotency_store: Per-transport idempotency cache. Looked up via
            ``.get(key)``; populated via item assignment when a new
            response is produced.
        transport_metadata: Optional audit metadata round-tripped onto the
            delivery audit record. Each transport supplies its own
            ``{"runtime": ...}`` tag.

    Returns:
        :class:`SendNotificationResponse` summarizing the accepted signal.

    Raises:
        ValidationError: If the SDK rejects the resolved notification.
        AuditPersistenceError: If the delivery audit cannot be persisted.
    """
    # TODO(post-v0.2): channel delivery + DLQ-on-failure live in
    # notification.service.dispatch_notification. Unifying the two send
    # paths and re-introducing a dlq_service parameter with real behavior
    # is tracked in docs/plans/post-v0.2-followups.md item F-1.

    # Idempotency replay: if a prior response is recorded, return it with
    # idempotent_replay flipped on. Keyed on (source, idempotency_key) to
    # match both legacy paths.
    if request.idempotency_key is not None:
        record_key = f"{request.source}:{request.idempotency_key}"
        existing_response = _idempotency_get(idempotency_store, record_key)
        if isinstance(existing_response, SendNotificationResponse):
            return existing_response.model_copy(update={"idempotent_replay": True})

    result, notification = _resolve_notification(request)

    # Metric tag derived from the supplied transport metadata; preserves the
    # legacy split (route -> "http", runtime -> "mcp"). Unknown tags fall
    # back to "unknown" rather than guessing.
    runtime_tag = (transport_metadata or {}).get("runtime", "")
    if runtime_tag == "standalone_http":
        metric_transport = "http"
    elif runtime_tag == "agsignal_mcp":
        metric_transport = "mcp"
    else:
        metric_transport = "unknown"

    from notification.metrics import record_signal_received

    record_signal_received(
        intent=notification.intent.value,
        autonomy_mode=notification.autonomy_context.autonomy_mode.value,
        transport=metric_transport,
    )

    ack_status: AckStatus | None = None
    if notification.require_ack:
        try:
            engine = get_ack_engine()
        except RuntimeError:
            engine = configure_ack_engine()
        engine.register_notification(
            notification_id=notification.notification_id,
            intent=notification.intent,
            autonomy_context=notification.autonomy_context,
            timeout_minutes=notification.ack_timeout_minutes,
            created_at=notification.created_at,
        )
        ack_status = engine.get_status(notification.notification_id)

    logger.info(
        "Accepted AGSignal notification: id=%s type=%s intent=%s",
        notification.notification_id,
        notification.notification_type,
        notification.intent.value,
    )

    try:
        audit_store.save_delivery_audit(
            create_audit_record(
                notification,
                result,
                metadata=transport_metadata,
            )
        )
    except AuditPersistenceError:
        logger.error(
            "Failed to persist delivery audit: notification_id=%s",
            notification.notification_id,
        )
        raise

    response = SendNotificationResponse(
        notification_id=result.notification_id,
        status=result.status,
        channels_attempted=result.channels_attempted,
        channels_succeeded=result.channels_succeeded,
        channels_failed=result.channels_failed,
        require_ack=bool(notification.require_ack),
        ack_status=ack_status,
        idempotency_key=request.idempotency_key,
        idempotent_replay=False,
        created_at=notification.created_at,
        message="notification accepted",
    )
    if request.idempotency_key is not None:
        _idempotency_set(
            idempotency_store,
            f"{request.source}:{request.idempotency_key}",
            response,
        )
    return response


async def simulate_signal(
    *,
    request: SendNotificationRequest,
) -> SimulateNotificationResponse:
    """Preview routing and acknowledgment behavior without delivery side effects.

    Mirrors :func:`notification.routes.simulate_notification` but with no
    FastAPI plumbing. Read-only: no audit row, no ack-engine registration,
    no idempotency store interaction.

    Args:
        request: Validated send-notification request from the producer.

    Returns:
        :class:`SimulateNotificationResponse` describing the simulated
        outcome and any human-readable caveats.

    Raises:
        ValidationError: If the SDK rejects the resolved notification.
    """
    result, notification = _resolve_notification(request)
    policy = get_policy_registry().get_sync(notification.notification_type)
    policy_source = "policy" if policy is not None else "default"
    warnings = [
        f"resolved via {policy_source} routing; no delivery, replay, or ack side effects were recorded"
    ]
    from notification.models import DeliveryMode

    if notification.delivery_mode == DeliveryMode.BEST_EFFORT:
        warnings.append("best-effort delivery does not raise on channel failure")

    return SimulateNotificationResponse(
        notification_id=result.notification_id,
        simulated=True,
        status=result.status,
        channels_attempted=result.channels_attempted,
        delivery_mode=notification.delivery_mode,
        require_ack=bool(notification.require_ack),
        ack_status=None,
        dedup_key=notification.dedup_key or "",
        dedup_window_seconds=(
            policy.dedup_window_seconds
            if policy is not None and policy.dedup_window_seconds is not None
            else DEFAULT_DEDUP_WINDOW_SECONDS
        ),
        policy_source=policy_source,
        warnings=warnings,
        message="notification simulated",
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

    Service-layer twin of the route-layer ``_persist_ack_audit`` helper in
    ``agsignal.api.routes_notification``: this raises the typed
    :class:`AuditPersistenceError` while the route-layer helper translates
    that error to HTTP 503. The route-layer helper continues to exist
    because it owns the HTTP-status translation responsibility; this one
    is the canonical service-layer call for both transports.

    The ``audit_store`` parameter is typed ``AuditStore | None`` and the
    isinstance guard preserved for parity with the route-layer helper that
    sources the store via ``getattr(request.app.state, ...)`` (which can
    return ``None``). All current callers pass a non-``None`` store, so the
    guard is effectively dead but kept for defense-in-depth.
    """
    # Idempotent re-ack: no transition, no audit row written.
    if old_status == new_status:
        return
    # Defensive: route-layer parity (see docstring). Phase 2 callers always
    # supply a non-None audit_store.
    if not isinstance(audit_store, AuditStore):  # pragma: no cover - defensive parity
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


def _resolve_notification(
    request: SendNotificationRequest,
) -> tuple[NotificationResult, Notification]:
    """Resolve a send-notification request into a (result, notification) pair.

    Canonical service-layer resolver. Raises the typed
    :class:`notification.sdk.ValidationError` directly instead of a FastAPI
    ``HTTPException``; the route layer catches the typed error and
    translates to HTTP 422.
    """
    captured: dict[str, Notification] = {}

    def _capture_delivery(notification: Notification) -> NotificationResult:
        captured["notification"] = notification
        from notification.models import DeliveryStatus

        return NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.SUCCESS,
            channels_attempted=notification.channels,
            channels_succeeded=[],
            channels_failed=[],
        )

    sdk = NotificationSDK(delivery_handler=_capture_delivery)

    # ValidationError propagates unchanged; route layer translates to 422.
    result = sdk.send(
        notification_type=request.notification_type,
        intent=request.intent,
        title=request.title,
        message=request.message,
        source=request.source,
        autonomy_context=request.autonomy_context.to_domain(),
        irreversible=request.irreversible,
        metadata=request.metadata,
        correlation_id=request.correlation_id,
        delivery_mode_override=request.delivery_mode,
        require_ack_override=request.require_ack,
        priority_override=request.priority,
        dedup_key=request.dedup_key,
    )
    return result, captured["notification"]


def _idempotency_get(store: Any, key: str) -> Any:
    """Duck-typed read from a dict-like idempotency store.

    Both legacy paths use a plain ``dict`` keyed by
    ``f"{source}:{idempotency_key}"``. Phase 5 swaps in a Redis-backed
    :class:`IdempotencyService`; this accessor accepts either by preferring
    a ``.get`` method then falling back to item access.
    """
    getter = getattr(store, "get", None)
    if callable(getter):
        return getter(key)
    try:  # pragma: no cover - defensive; Phase 5 firms up typing
        return store[key]
    except (KeyError, TypeError):
        return None


def _idempotency_set(store: Any, key: str, value: Any) -> None:
    """Duck-typed write into a dict-like idempotency store."""
    setter = getattr(store, "set", None)
    if callable(setter):
        setter(key, value)
        return
    try:
        store[key] = value
    except TypeError:  # pragma: no cover - defensive; Phase 5 firms up typing
        logger.warning(
            "Idempotency store does not support write semantics; "
            "key=%s value not cached",
            key,
        )

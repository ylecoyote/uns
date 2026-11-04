"""Standalone HTTP routes for producing UNS notifications.

Per Phase 2 Tasks 6/7/8, the write routes (``send_notification`` and
``simulate_notification``) are thin HTTP adapters that delegate to
``uns.signaling.*``. The route handlers contain only parameter
parsing + observability + delegation + error translation. The websocket
dispatch (replay store, connection manager, fanout publisher) remains in
the route layer because the websocket runtime state is FastAPI-app-scoped
and is a transport-layer concern.

Per Phase 3 Task 1, the Pydantic Request/Response DTOs that previously
lived in this module have been relocated to :mod:`uns.responses`.
The ``__all__`` re-export block at the bottom preserves the historical
import path so external callers (notably ``uns_mcp.tools``) continue
to work without code changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from uns.runtime import Runtime

import logging
from pathlib import Path
from threading import RLock
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from notification.audit import AuditPersistenceError, AuditRecord, AuditStore
from notification.channel_health import ChannelHealthSummary, ChannelHealthTracker
from notification.dlq import DLQEntry, DLQService
from notification.policies import (
    PolicyRegistry,
    configure_policy_registry,
)
from notification.policy_loader import (
    load_policies_from_directory,
)
from notification.sdk import ValidationError
from notification.websocket_runtime import (
    WebSocketConnectionManager,
    WebSocketFanoutEnvelope,
    WebSocketReplayStore,
)
from uns.api.auth import (
    WritePrincipal,
    principal_allows_record,
    require_admin_principal,
    require_producer_principal,
    require_read_principal,
    require_source_and_namespace,
)
from uns.responses import (
    AutonomyContextRequest,
    DeliveryAuditItem,
    DeliveryStatusResponse,
    DLQListResponse,
    DLQRemoveResponse,
    PolicyPromotionResponse,
    PolicyProposalActionRequest,
    PolicyProposalCreateRequest,
    PolicyProposalListResponse,
    PolicyProposalSummary,
    PolicyReloadRequest,
    PolicyReloadResponse,
    SendNotificationRequest,
    SendNotificationResponse,
    SimulateNotificationResponse,
)
from uns.shadow_evaluator import resolve_shadow_evaluator
from uns.signaling import send_signal as service_send_signal
from uns.signaling import simulate_signal as service_simulate_signal

logger = logging.getLogger(__name__)
_policy_reload_lock = RLock()

router = APIRouter(
    prefix="/api/v1/notifications", tags=["signals"], dependencies=[Depends(require_read_principal)]
)
ops_router = APIRouter(
    prefix="/api/v1", tags=["operations"], dependencies=[Depends(require_read_principal)]
)


@router.post(
    "",
    response_model=SendNotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_notification(
    http_request: Request,
    request: SendNotificationRequest,
    principal: WritePrincipal = Depends(require_producer_principal),
) -> SendNotificationResponse:
    """HTTP adapter — delegates to uns.signaling.send_signal.

    Translates typed signaling errors to HTTP responses:
    - :class:`ValidationError` -> 422 validation_error
    - :class:`AuditPersistenceError` -> 503 audit_persistence_failed

    The websocket dispatch (replay store, connection manager, fanout
    publisher) is performed in this route layer after the signaling call
    succeeds because the websocket runtime state is FastAPI-app-scoped
    transport infrastructure that does not belong in the service layer.
    """
    require_source_and_namespace(
        principal,
        source=request.source,
        notification_type=request.notification_type,
    )
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    if runtime is not None:
        from uns.runtime import Conflict

        try:
            return await runtime.send(request, principal=principal.subject)
        except Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_store = http_request.app.state.audit_store
    idempotency_store = http_request.app.state.http_idempotency_records

    try:
        response = await service_send_signal(
            request=request,
            audit_store=audit_store,
            idempotency_store=idempotency_store,
            transport_metadata={"runtime": "standalone_http"},
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
    except AuditPersistenceError as exc:
        record = getattr(exc, "record", None)
        notification_id = getattr(record, "notification_id", None) if record is not None else None
        logger.error(
            "Failed to persist delivery audit: notification_id=%s error=%s",
            notification_id,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "audit_persistence_failed",
                "message": "notification accepted but delivery audit could not be persisted",
                "notification_id": str(notification_id) if notification_id else None,
            },
        ) from exc

    # Replay shortcut: if signaling returned an idempotent replay, skip the
    # websocket dispatch (the original send already fanned out).
    if response.idempotent_replay:
        return response

    # Websocket dispatch is transport-layer; stays in the route after the
    # signaling call returns successfully. The websocket payload is
    # reconstructed from the response + request because signaling no longer
    # exposes the resolved Notification domain object.
    websocket_payload: dict[str, object] = {
        "notification_id": str(response.notification_id),
        "notification_type": request.notification_type,
        "intent": request.intent.value,
        "title": request.title,
        "message": request.message,
        "source": request.source,
        "require_ack": bool(response.require_ack),
        "ack_status": response.ack_status.value if response.ack_status is not None else None,
    }
    agent_id = request.autonomy_context.agent_id
    replay_store = getattr(http_request.app.state, "websocket_replay_store", None)
    if isinstance(replay_store, WebSocketReplayStore):
        replay_cursor = replay_store.record(
            agent_id, websocket_payload, created_at=response.created_at
        )
        websocket_payload["replay_cursor"] = replay_cursor
    manager = getattr(http_request.app.state, "websocket_manager", None)
    if isinstance(manager, WebSocketConnectionManager):
        await manager.send_to_agent(
            agent_id,
            {"type": "notification", "notification": websocket_payload},
        )
    fanout = getattr(http_request.app.state, "websocket_fanout", None)
    if fanout is not None:
        fanout.publish(
            WebSocketFanoutEnvelope(
                type="notification",
                agent_id=agent_id,
                notification=websocket_payload,
            )
        )
    return response


@router.post("/simulate", response_model=SimulateNotificationResponse)
async def simulate_notification(
    request: SendNotificationRequest,
    http_request: Request,
    principal: WritePrincipal = Depends(require_producer_principal),
) -> SimulateNotificationResponse:
    """HTTP adapter — delegates to uns.signaling.simulate_signal.

    Translates typed signaling errors to HTTP responses:
    - :class:`ValidationError` -> 422 validation_error
    """
    require_source_and_namespace(
        principal,
        source=request.source,
        notification_type=request.notification_type,
    )
    try:
        runtime = getattr(http_request.app.state, "runtime", None)
        return await service_simulate_signal(
            request=request,
            policy_runtime=runtime.policy_runtime if runtime is not None else None,
            principal=principal.subject,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc


def _delivery_audit_item(record: AuditRecord) -> DeliveryAuditItem:
    return DeliveryAuditItem(
        audit_id=record.audit_id,
        status=record.status,
        channels_attempted=list(record.channels_attempted),
        channels_succeeded=list(record.channels_succeeded),
        channels_failed=list(record.channels_failed),
        error_message=record.error_message,
        policy_config_id=record.policy_config_id,
        policy_config_hash=record.policy_config_hash,
        policy_evaluation_id=record.policy_evaluation_id,
        delivered_at=record.delivered_at,
        audit_created_at=record.audit_created_at,
    )


def _resolve_notification_bounds_from_request(
    http_request: Request,
    notification_id: UUID,
    audits: list[AuditRecord] | None = None,
) -> tuple[str | None, str | None]:
    source: str | None = None
    notification_type: str | None = None
    if audits:
        latest = audits[0]
        source = getattr(latest, "source", None) or None
        notification_type = getattr(latest, "notification_type", None) or None
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    if (not source or not notification_type) and runtime is not None:
        try:
            row = runtime.get(notification_id)
        except Exception:
            row = None
        if isinstance(row, dict):
            raw_notif = row.get("notification")
            notif: dict[str, object] = raw_notif if isinstance(raw_notif, dict) else {}
            raw_src = source or notif.get("source") or row.get("source")
            source = str(raw_src) if raw_src is not None else None
            raw_nt = (
                notification_type or notif.get("notification_type") or row.get("notification_type")
            )
            notification_type = str(raw_nt) if raw_nt is not None else None
    if (not source or not notification_type) and audits is None:
        audit_store = getattr(http_request.app.state, "audit_store", None)
        if isinstance(audit_store, AuditStore):
            try:
                found_audits = audit_store.get_delivery_audits_for_notification(notification_id)
            except Exception:
                found_audits = []
            if found_audits:
                source = source or getattr(found_audits[0], "source", None)
                notification_type = notification_type or getattr(
                    found_audits[0], "notification_type", None
                )
    return (
        str(source) if isinstance(source, str) and source else None,
        str(notification_type)
        if isinstance(notification_type, str) and notification_type
        else None,
    )


def _extract_dlq_entry_bounds(
    entry: object,
    runtime: Runtime | None = None,
) -> tuple[str | None, str | None]:
    source = getattr(entry, "source", None)
    notification_type = getattr(entry, "notification_type", None)
    notif = getattr(entry, "notification", None)
    if isinstance(notif, dict):
        source = source or notif.get("source")
        notification_type = notification_type or notif.get("notification_type")
    elif notif is not None:
        source = source or getattr(notif, "source", None)
        notification_type = notification_type or getattr(notif, "notification_type", None)
    if isinstance(entry, dict):
        source = source or entry.get("source")
        notification_type = notification_type or entry.get("notification_type")
        raw_entry_notif = entry.get("notification")
        row_notif: dict[str, object] = raw_entry_notif if isinstance(raw_entry_notif, dict) else {}
        source = source or row_notif.get("source")
        notification_type = notification_type or row_notif.get("notification_type")
    if (not source or not notification_type) and runtime is not None:
        nid = (
            entry.get("notification_id")
            if isinstance(entry, dict)
            else getattr(entry, "notification_id", None)
        )
        if nid is not None:
            try:
                row = runtime.get(UUID(str(nid)))
            except Exception:
                row = None
            if isinstance(row, dict):
                raw_row_notif = row.get("notification")
                row_notif_dict: dict[str, object] = (
                    raw_row_notif if isinstance(raw_row_notif, dict) else {}
                )
                source = source or row_notif_dict.get("source") or row.get("source")
                notification_type = (
                    notification_type
                    or row_notif_dict.get("notification_type")
                    or row.get("notification_type")
                )
    return (
        str(source) if isinstance(source, str) and source else None,
        str(notification_type)
        if isinstance(notification_type, str) and notification_type
        else None,
    )


@router.get("/{notification_id}/delivery", response_model=DeliveryStatusResponse)
async def get_delivery_status(
    http_request: Request,
    notification_id: UUID,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> DeliveryStatusResponse:
    """Return persisted delivery status for a notification."""
    audit_store = getattr(http_request.app.state, "audit_store", None)
    if not isinstance(audit_store, AuditStore):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "audit_store_unavailable",
                "message": "delivery audit storage is not configured",
            },
        )

    audits = audit_store.get_delivery_audits_for_notification(notification_id)
    if not audits:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "delivery_audit_not_found",
                "message": f"no delivery audit exists for notification {notification_id}",
            },
        )

    source, notification_type = _resolve_notification_bounds_from_request(
        http_request,
        notification_id,
        audits=audits,
    )
    require_source_and_namespace(
        principal,
        source=source,
        notification_type=notification_type,
    )

    latest = audits[0]
    return DeliveryStatusResponse(
        notification_id=notification_id,
        notification_type=latest.notification_type,
        delivery_status=latest.status,
        channels_attempted=list(latest.channels_attempted),
        channels_succeeded=list(latest.channels_succeeded),
        channels_failed=list(latest.channels_failed),
        error_message=latest.error_message,
        delivered_at=latest.delivered_at,
        audit_count=len(audits),
        audits=[_delivery_audit_item(record) for record in audits],
    )


@router.get(
    "/{notification_id}/audit",
    response_model=DeliveryStatusResponse,
    include_in_schema=False,
)
async def get_notification_audit(
    http_request: Request,
    notification_id: UUID,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> DeliveryStatusResponse:
    """Return persisted audit records for a notification after scope validation."""
    return await get_delivery_status(
        http_request=http_request,
        notification_id=notification_id,
        principal=principal,
    )


@ops_router.get("/dlq", response_model=DLQListResponse)
async def list_dlq(
    request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> DLQListResponse:
    """List visible dead-lettered delivery failures."""
    dlq_service: DLQService = request.app.state.dlq_service
    runtime = cast("Runtime | None", getattr(request.app.state, "runtime", None))
    entries = dlq_service.list_entries()
    if principal is not None and (
        not principal.has_wildcard_sources or not principal.has_wildcard_namespaces
    ):
        filtered = [
            entry
            for entry in entries
            if principal_allows_record(
                principal,
                source=_extract_dlq_entry_bounds(entry, runtime)[0],
                notification_type=_extract_dlq_entry_bounds(entry, runtime)[1],
            )
        ]
        return DLQListResponse(
            depth=len(filtered),
            items=filtered,
        )
    return DLQListResponse(
        depth=dlq_service.depth(),
        items=entries,
    )


@ops_router.get(
    "/dlq/{entry_id}",
    response_model=DLQEntry,
    include_in_schema=False,
)
async def get_dlq_entry(
    request: Request,
    entry_id: UUID,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> DLQEntry:
    """Return a single visible DLQ entry after scope verification."""
    dlq_service: DLQService = request.app.state.dlq_service
    runtime = cast("Runtime | None", getattr(request.app.state, "runtime", None))
    for entry in dlq_service.list_entries():
        if entry.entry_id == entry_id or entry.notification_id == entry_id:
            source, notification_type = _extract_dlq_entry_bounds(entry, runtime)
            require_source_and_namespace(
                principal,
                source=source,
                notification_type=notification_type,
            )
            return entry
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "dlq_entry_not_found",
            "message": f"DLQ entry not found: {entry_id}",
            "entry_id": str(entry_id),
        },
    )


@ops_router.delete("/dlq/{entry_id}", response_model=DLQRemoveResponse)
async def remove_dlq_entry(
    request: Request,
    entry_id: UUID,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> DLQRemoveResponse:
    """Remove a visible DLQ entry after external remediation."""
    runtime = cast("Runtime | None", getattr(request.app.state, "runtime", None))
    dlq_service: DLQService | None = getattr(request.app.state, "dlq_service", None)
    if principal is not None and (
        not principal.has_wildcard_sources or not principal.has_wildcard_namespaces
    ):
        matched_entry: object | None = None
        if dlq_service is not None:
            for entry in dlq_service.list_entries():
                if entry.entry_id == entry_id or entry.notification_id == entry_id:
                    matched_entry = entry
                    break
        if matched_entry is None and runtime is not None:
            for item in runtime.dead_letters():
                if str(item.get("id")) == str(entry_id) or str(item.get("notification_id")) == str(
                    entry_id
                ):
                    matched_entry = item
                    break
        if matched_entry is not None:
            source, notification_type = _extract_dlq_entry_bounds(matched_entry, runtime)
            require_source_and_namespace(
                principal,
                source=source,
                notification_type=notification_type,
            )
    if runtime is not None:
        removed = runtime.resolve_failure(entry_id, actor=principal.subject)
        if not removed:
            raise HTTPException(status_code=404, detail="Dead-letter entry not found")
        return DLQRemoveResponse(entry_id=entry_id, removed=True, depth=len(runtime.dead_letters()))
    if dlq_service is None:
        raise HTTPException(status_code=503, detail="Dead-letter service unavailable")
    if not dlq_service.remove(entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "dlq_entry_not_found",
                "message": f"DLQ entry not found: {entry_id}",
                "entry_id": str(entry_id),
            },
        )
    return DLQRemoveResponse(
        entry_id=entry_id,
        removed=True,
        depth=dlq_service.depth(),
    )


@ops_router.get("/channels/health", response_model=ChannelHealthSummary)
async def get_channel_health(request: Request) -> ChannelHealthSummary:
    """Return runtime channel health without changing process readiness."""
    runtime = cast("Runtime | None", getattr(request.app.state, "runtime", None))
    tracker: ChannelHealthTracker = (
        getattr(request.app.state, "channel_health", None)
        or getattr(request.app.state, "channel_health_tracker", None)
        or (getattr(runtime, "channel_health", None) if runtime is not None else None)
        or ChannelHealthTracker()
    )
    sync_fn = getattr(tracker, "sync_from_runtime", None)
    if callable(sync_fn) and runtime is not None:
        sync_fn(runtime)
    return tracker.get_summary()


@ops_router.post("/policies/reload", response_model=PolicyReloadResponse)
async def reload_policies(
    reload_request: PolicyReloadRequest,
    http_request: Request,
    _principal: WritePrincipal = Depends(require_admin_principal),
) -> PolicyReloadResponse:
    """Reload notification policies from YAML files."""
    import os
    import tempfile

    configured_policy_dir = os.environ.get("UNS_POLICY_DIR")
    configured_root = getattr(http_request.app.state, "policy_dir", None) or configured_policy_dir
    if reload_request.policy_dir:
        raw_policy_dir = Path(reload_request.policy_dir)
    elif configured_root:
        raw_policy_dir = Path(str(configured_root))
    else:
        default_dir = Path("config/notification_policies")
        raw_policy_dir = (
            default_dir
            if default_dir.exists() or not Path("config/policies").exists()
            else Path("config/policies")
        )
    if ".." in raw_policy_dir.parts:
        raise HTTPException(status_code=422, detail="Path traversal is not permitted in policy_dir")
    if raw_policy_dir.is_symlink():
        raise HTTPException(status_code=422, detail="Symlinked policy_dir is not permitted")
    resolved_dir = raw_policy_dir.resolve()
    if configured_root:
        allowed_root = Path(str(configured_root)).resolve()
        if resolved_dir != allowed_root and allowed_root not in resolved_dir.parents:
            raise HTTPException(
                status_code=422,
                detail="policy_dir must reside within the configured UNS_POLICY_DIR",
            )
    else:
        temp_base = Path(tempfile.gettempdir()).resolve()
        allowed_roots = [
            Path.cwd().resolve(),
            temp_base,
        ]
        if not any(resolved_dir == root or root in resolved_dir.parents for root in allowed_roots):
            raise HTTPException(
                status_code=422,
                detail="policy_dir must reside within the configured UNS_POLICY_DIR",
            )
    policy_dir = resolved_dir
    with _policy_reload_lock:
        registry = PolicyRegistry(runtime_only=False)
        try:
            loaded_count = load_policies_from_directory(policy_dir, registry=registry)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, NotADirectoryError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if loaded_count == 0:
            raise HTTPException(
                status_code=422,
                detail=f"Policy directory contains no YAML policy files: {policy_dir}",
            )
        from notification.policies import PolicyStatus

        runtime_registry = PolicyRegistry()
        for policy in registry.get_all().values():
            if policy.status == PolicyStatus.ACTIVE:
                runtime_registry.register(policy)
        policy_store = getattr(http_request.app.state, "policy_store", None)
        try:
            persisted_count = (
                policy_store.save_snapshot(list(registry.get_all().values())) if policy_store else 0
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if getattr(http_request.app.state, "runtime", None) is None:
            configure_policy_registry(registry=runtime_registry)
        return PolicyReloadResponse(
            loaded_count=loaded_count,
            persisted_count=persisted_count,
            policy_count=len(runtime_registry),
            notification_types=sorted(runtime_registry.list_notification_types()),
        )


@ops_router.get("/policies/proposals", response_model=PolicyProposalListResponse)
async def list_policy_proposals_api(
    http_request: Request,
    policy_type: str | None = None,
    state: str | None = None,
    limit: int = 50,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> PolicyProposalListResponse:
    """List policy delta proposals and shadow evaluation aggregates."""
    from notification.policy_learning import DeltaState

    if policy_type:
        require_source_and_namespace(
            principal,
            notification_type=policy_type,
            require_source=False,
        )
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        return PolicyProposalListResponse(items=[], total_count=0)
    try:
        state_enum = DeltaState(state.upper()) if state else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid proposal state: {state}") from exc
    deltas = evaluator.learning_store.list_deltas(
        policy_type=policy_type,
        state=state_enum,
        limit=max(1, min(limit, 200)),
    )
    items = [
        evaluator.format_proposal_summary(d, include_samples=False)
        for d in deltas
        if principal is None or principal.allows_namespace(d.policy_type)
    ]
    return PolicyProposalListResponse(items=items, total_count=len(items))


@ops_router.get("/policies/proposals/{delta_id}", response_model=PolicyProposalSummary)
async def get_policy_proposal_api(
    delta_id: UUID,
    http_request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> PolicyProposalSummary:
    """Return full detail for one policy delta proposal including shadow samples."""
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(status_code=404, detail="Policy proposal not found")
    delta = evaluator.learning_store.get_delta(delta_id)
    if delta is None:
        raise HTTPException(status_code=404, detail="Policy proposal not found")
    require_source_and_namespace(
        principal,
        notification_type=delta.policy_type,
        require_source=False,
    )
    return evaluator.format_proposal_summary(delta, include_samples=True)


@ops_router.post(
    "/policies/proposals",
    response_model=PolicyProposalSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_policy_proposal(
    proposal: PolicyProposalCreateRequest,
    http_request: Request,
    principal: WritePrincipal = Depends(require_producer_principal),
) -> PolicyProposalSummary:
    """Create a governed PolicyDelta proposal and optionally promote to SHADOW (PREVIEW)."""
    require_source_and_namespace(
        principal,
        notification_type=proposal.policy_type,
        require_source=False,
    )
    if proposal.promote_to_shadow and "admin" not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "message": "Promoting a proposal to SHADOW requires admin capability.",
            },
        )
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy learning store is not available",
        )
    try:
        delta = evaluator.propose_delta(
            policy_type=proposal.policy_type,
            field_path=proposal.field_path,
            proposed_value=proposal.proposed_value,
            reasoning=proposal.reasoning,
            actor=principal.subject,
            confidence=proposal.confidence,
            evidence_count=proposal.evidence_count,
            promote_to_shadow=proposal.promote_to_shadow,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return evaluator.format_proposal_summary(delta, include_samples=True)


@ops_router.post(
    "/policies/proposals/{delta_id}/shadow",
    response_model=PolicyProposalSummary,
)
async def promote_proposal_to_shadow(
    delta_id: UUID,
    http_request: Request,
    body: PolicyProposalActionRequest | None = None,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> PolicyProposalSummary:
    """Promote a PROPOSED delta to SHADOW and materialize a PREVIEW policy revision."""
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(status_code=503, detail="Policy learning store is not available")
    existing = evaluator.learning_store.get_delta(delta_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Policy proposal not found")
    require_source_and_namespace(
        principal,
        notification_type=existing.policy_type,
        require_source=False,
    )
    try:
        promoted = evaluator.promote_to_shadow(
            delta_id,
            actor=principal.subject,
            reason=body.reason if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return evaluator.format_proposal_summary(promoted, include_samples=True)


@ops_router.post(
    "/policies/proposals/{delta_id}/approve",
    response_model=PolicyPromotionResponse,
)
async def approve_proposal_to_draft(
    delta_id: UUID,
    http_request: Request,
    body: PolicyProposalActionRequest | None = None,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> PolicyPromotionResponse:
    """Verify shadow evidence and guard gates, approve SHADOW -> APPROVED, and create a DRAFT revision."""
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(status_code=503, detail="Policy learning store is not available")
    existing = evaluator.learning_store.get_delta(delta_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Policy proposal not found")
    require_source_and_namespace(
        principal,
        notification_type=existing.policy_type,
        require_source=False,
    )
    try:
        approved, save_result, draft_policy = evaluator.approve_to_draft(
            delta_id,
            actor=principal.subject,
            reason=body.reason if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PolicyPromotionResponse(
        delta=evaluator.format_proposal_summary(approved, include_samples=True),
        policy_id=save_result.policy_id,
        notification_type=draft_policy.notification_type,
        version=draft_policy.version,
        status=draft_policy.status.value,
        config_hash=save_result.content_hash,
        message=(
            f"Approved delta {delta_id} into DRAFT revision "
            f"{draft_policy.notification_type} v{draft_policy.version}"
        ),
    )


@ops_router.post(
    "/policies/proposals/{delta_id}/activate",
    response_model=PolicyPromotionResponse,
)
async def activate_approved_proposal(
    delta_id: UUID,
    http_request: Request,
    body: PolicyProposalActionRequest | None = None,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> PolicyPromotionResponse:
    """Explicitly promote an approved proposal's DRAFT revision to ACTIVE (DRAFT -> ACTIVE)."""
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(status_code=503, detail="Policy learning store is not available")
    existing = evaluator.learning_store.get_delta(delta_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Policy proposal not found")
    require_source_and_namespace(
        principal,
        notification_type=existing.policy_type,
        require_source=False,
    )
    try:
        save_result, active_policy, applied_delta = evaluator.activate_draft(
            actor=principal.subject,
            delta_id=delta_id,
            reason=body.reason if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PolicyPromotionResponse(
        delta=(
            evaluator.format_proposal_summary(applied_delta, include_samples=True)
            if applied_delta is not None
            else None
        ),
        policy_id=save_result.policy_id,
        notification_type=active_policy.notification_type,
        version=active_policy.version,
        status=active_policy.status.value,
        config_hash=save_result.content_hash,
        message=(
            f"Activated {active_policy.notification_type} v{active_policy.version} "
            f"(DRAFT -> ACTIVE)"
        ),
    )


@ops_router.post(
    "/policies/proposals/{delta_id}/reject",
    response_model=PolicyProposalSummary,
)
async def reject_policy_proposal(
    delta_id: UUID,
    http_request: Request,
    body: PolicyProposalActionRequest | None = None,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> PolicyProposalSummary:
    """Reject a policy delta proposal."""
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(status_code=503, detail="Policy learning store is not available")
    existing = evaluator.learning_store.get_delta(delta_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Policy proposal not found")
    require_source_and_namespace(
        principal,
        notification_type=existing.policy_type,
        require_source=False,
    )
    try:
        rejected = evaluator.reject_delta(
            delta_id,
            actor=principal.subject,
            reason=(body.reason if body and body.reason else "Rejected by operator"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return evaluator.format_proposal_summary(rejected, include_samples=True)


@ops_router.post(
    "/policies/revisions/{policy_id}/activate",
    response_model=PolicyPromotionResponse,
)
async def activate_draft_policy_revision(
    policy_id: UUID,
    http_request: Request,
    body: PolicyProposalActionRequest | None = None,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> PolicyPromotionResponse:
    """Explicitly promote a persisted DRAFT policy revision to ACTIVE by policy_id."""
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        raise HTTPException(status_code=503, detail="Policy store is not available")
    found = evaluator.policy_store.get_policy_by_id(policy_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Policy revision not found")
    require_source_and_namespace(
        principal,
        notification_type=found[1].notification_type,
        require_source=False,
    )
    try:
        save_result, active_policy, applied_delta = evaluator.activate_draft(
            actor=principal.subject,
            policy_id=policy_id,
            reason=body.reason if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PolicyPromotionResponse(
        delta=(
            evaluator.format_proposal_summary(applied_delta, include_samples=True)
            if applied_delta is not None
            else None
        ),
        policy_id=save_result.policy_id,
        notification_type=active_policy.notification_type,
        version=active_policy.version,
        status=active_policy.status.value,
        config_hash=save_result.content_hash,
        message=(
            f"Activated {active_policy.notification_type} v{active_policy.version} "
            f"(DRAFT -> ACTIVE)"
        ),
    )


# Re-export for backward compatibility. uns_mcp.tools and any other
# downstream caller that does ``from notification.routes import
# SendNotificationRequest`` (etc.) continues to work. Canonical home is
# ``uns.responses``.
__all__ = [
    "AutonomyContextRequest",
    "DLQListResponse",
    "DLQRemoveResponse",
    "DeliveryAuditItem",
    "DeliveryStatusResponse",
    "PolicyReloadRequest",
    "PolicyReloadResponse",
    "SendNotificationRequest",
    "SendNotificationResponse",
    "SimulateNotificationResponse",
    "ops_router",
    "router",
]

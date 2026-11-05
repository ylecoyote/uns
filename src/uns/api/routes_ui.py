"""Read-only UI HTTP route adapters for UNS Console.

This module provides the HTTP endpoints for the UI dashboard per
``docs/ui/ui-data-contracts.md``:

- GET /ui/deliveries - List delivery timelines with filtering
- GET /ui/deliveries/{id} - Get single delivery timeline
- GET /ui/policies/effective - Get effective policy resolution
- GET /ui/invariants - List system invariants
- GET /ui/invariants/summary - Aggregate invariant summary
- GET /ui/audit - List audit events with filtering

All endpoints are READ-ONLY. No mutating actions are permitted.

Architecture (post-Phase-2 Task 3, post-Phase-3 Task 1):
- Each route handler is a thin adapter: parameter parsing (Query/Depends)
  + log_endpoint_call observability + ``await uns.queries.X(...)``.
- The canonical implementation of each read operation lives in
  :mod:`uns.queries`. Routes do not contain business logic.
- Pydantic response models live in :mod:`uns.responses`; this
  module re-exports them at the bottom for backward compatibility.

Authentication/Authorization:
- All endpoints require read-only permissions (stub: no auth enforcement yet)
- Future: integrate with auth middleware for proper RBAC

Observability:
- All endpoints emit request metrics via ObservabilityMiddleware
- Structured logs include request IDs for correlation
- Error metrics are recorded for 4xx/5xx responses
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from notification.policies import PolicyStatus
from notification.policy_learning import DeltaState
from uns.api.auth import (
    WritePrincipal,
    principal_allows_record,
    require_authenticated_observer,
    require_read_principal,
    require_source_and_namespace,
)
from uns.api.observability import (
    create_error_response_with_request_id,
    get_structured_logger,
    log_endpoint_call,
    record_endpoint_error,
)
from uns.errors import NotFoundError
from uns.queries import (
    get_delivery_timeline as _query_delivery_timeline,
)
from uns.queries import (
    get_effective_policy as _query_effective_policy,
)
from uns.queries import (
    get_invariants_summary as _query_invariants_summary,
)
from uns.queries import (
    list_audit_events as _query_list_audit_events,
)
from uns.queries import (
    list_deliveries as _query_list_deliveries,
)
from uns.queries import (
    list_invariants as _query_list_invariants,
)
from uns.responses import (
    ActivePolicyListResponse,
    ActivePolicySummary,
    AuditEvent,
    AuditEventListResponse,
    AuditEventType,
    AutonomyContextResponse,
    ConsoleSessionResponse,
    DeliveryAttempt,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    EnforcementType,
    ErrorDetail,
    EvidenceLink,
    InvariantEnforcement,
    InvariantEntry,
    InvariantListResponse,
    InvariantSeverity,
    InvariantStatus,
    InvariantSummaryResponse,
    PaginationInfo,
    PolicyProposalListResponse,
    PolicyProposalSummary,
    PolicyRevisionListResponse,
    PolicyRevisionSummary,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)
from uns.responses import (
    UIErrorResponse as ErrorResponse,
)
from uns.shadow_evaluator import resolve_shadow_evaluator

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/ui", tags=["ui"], dependencies=[Depends(require_read_principal)])


_TItem = TypeVar("_TItem")


def _utc_opt(value: datetime | None) -> datetime | None:
    """Ensure persisted timestamps are timezone-aware UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _encode_cursor(offset: int) -> str:
    return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        data = json.loads(base64.b64decode(cursor))
        offset = data.get("offset", 0)
        return min(max(int(offset), 0), 10_000) if offset is not None else 0
    except Exception:
        return 0


def _principal_has_record_bounds(principal: WritePrincipal | None) -> bool:
    return principal is not None and (
        not principal.has_wildcard_sources or not principal.has_wildcard_namespaces
    )


def _resolve_ui_notification_bounds(
    http_request: Request,
    notification_id: UUID | None,
    *,
    item: object | None = None,
    bounds_cache: dict[UUID, tuple[str | None, str | None]] | None = None,
) -> tuple[str | None, str | None]:
    source: str | None = None
    notification_type: str | None = None
    if item is not None:
        raw_src = getattr(item, "source", None)
        if isinstance(raw_src, str) and raw_src:
            source = raw_src
        raw_nt = getattr(item, "notification_type", None)
        if isinstance(raw_nt, str) and raw_nt:
            notification_type = raw_nt
        meta = getattr(item, "metadata", None)
        if isinstance(meta, dict):
            if not source and isinstance(meta.get("source"), str):
                source = meta["source"]
            if not notification_type and isinstance(meta.get("notification_type"), str):
                notification_type = meta["notification_type"]
    if notification_id is None:
        return source, notification_type
    if bounds_cache is not None and notification_id in bounds_cache:
        cached_src, cached_nt = bounds_cache[notification_id]
        return source or cached_src, notification_type or cached_nt

    runtime = getattr(http_request.app.state, "runtime", None)
    if (not source or not notification_type) and runtime is not None:
        try:
            row = runtime.get(notification_id)
        except Exception:
            row = None
        if isinstance(row, dict):
            raw_notif = row.get("notification")
            notif: dict[str, object] = raw_notif if isinstance(raw_notif, dict) else {}
            n_src = notif.get("source")
            r_src = row.get("source")
            if not source and isinstance(n_src, str):
                source = n_src
            elif not source and isinstance(r_src, str):
                source = r_src
            n_nt = notif.get("notification_type")
            r_nt = row.get("notification_type")
            if not notification_type and isinstance(n_nt, str):
                notification_type = n_nt
            elif not notification_type and isinstance(r_nt, str):
                notification_type = r_nt

    from uns.api.read_models import get_read_model_adapter

    read_adapter = (
        getattr(http_request.app.state, "read_model_adapter", None) or get_read_model_adapter()
    )
    audit_store = getattr(http_request.app.state, "audit_store", None) or getattr(
        read_adapter, "audit_store", None
    )
    if (not source or not notification_type) and audit_store is not None:
        get_audits = getattr(audit_store, "get_delivery_audits_for_notification", None)
        if callable(get_audits):
            try:
                audits = get_audits(notification_id)
            except Exception:
                audits = []
            if audits:
                first = audits[0]
                if not source and isinstance(getattr(first, "source", None), str):
                    source = first.source
                if not notification_type and isinstance(
                    getattr(first, "notification_type", None), str
                ):
                    notification_type = first.notification_type

    if (not source or not notification_type) and read_adapter is not None:
        get_session = getattr(read_adapter, "_get_session", None)
        if callable(get_session):
            session = get_session()
            if session is not None:
                try:
                    from sqlalchemy import select

                    from db.models import NotificationAuditRecord

                    stmt = (
                        select(
                            NotificationAuditRecord.source,
                            NotificationAuditRecord.notification_type,
                        )
                        .where(NotificationAuditRecord.notification_id == notification_id)
                        .limit(1)
                    )
                    rec = session.execute(stmt).first()
                    if rec is not None:
                        if not source and isinstance(rec[0], str):
                            source = rec[0]
                        if not notification_type and isinstance(rec[1], str):
                            notification_type = rec[1]
                except Exception:  # nosec B110
                    pass
                finally:
                    session.close()

    if bounds_cache is not None:
        bounds_cache[notification_id] = (source, notification_type)
    return source, notification_type


def _apply_source_and_namespace_bounds(
    http_request: Request,
    principal: WritePrincipal | None,
    items: list[_TItem],
) -> list[_TItem]:
    if not _principal_has_record_bounds(principal):
        return items
    bounds_cache: dict[UUID, tuple[str | None, str | None]] = {}
    filtered: list[_TItem] = []
    for item in items:
        raw_nid = getattr(item, "notification_id", None)
        nid = raw_nid if isinstance(raw_nid, UUID) else None
        source, notification_type = _resolve_ui_notification_bounds(
            http_request,
            nid,
            item=item,
            bounds_cache=bounds_cache,
        )
        if principal_allows_record(
            principal,
            source=source,
            notification_type=notification_type,
        ):
            filtered.append(item)
    return filtered


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/session",
    response_model=ConsoleSessionResponse,
    responses={
        200: {"description": "Authenticated console principal and capability scopes"},
        401: {"description": "Missing or invalid API credential"},
        403: {"description": "Credential lacks observer authority"},
    },
    summary="Get console session capabilities",
    description="Return the authenticated principal subject and capability scopes.",
)
async def get_console_session(
    http_request: Request,
    principal: WritePrincipal = Depends(require_authenticated_observer),
) -> ConsoleSessionResponse:
    """Return server-verified identity and capability scopes for the console."""
    log_endpoint_call(logger, "get_console_session", subject=principal.subject)
    runtime = getattr(http_request.app.state, "runtime", None)
    persistence_mode = runtime.persistence_mode if runtime is not None else "in_memory"
    return ConsoleSessionResponse(
        subject=principal.subject,
        scopes=sorted(principal.scopes),
        persistence_mode=persistence_mode,
    )


@router.get(
    "/deliveries",
    response_model=DeliveryTimelineListResponse,
    responses={
        200: {"description": "List of delivery timelines"},
        400: {"description": "Invalid parameters"},
    },
    summary="List delivery timelines",
    description="Query delivery timelines with optional filtering. Read-only endpoint.",
)
async def list_deliveries(
    http_request: Request,
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    start_time: datetime | None = Query(default=None, description="Filter by created_at >="),
    end_time: datetime | None = Query(default=None, description="Filter by created_at <"),
    status: DeliveryStatus | None = Query(default=None, description="Filter by delivery status"),
    intent: NotificationIntent | None = Query(default=None, description="Filter by intent"),
    delivery_mode: DeliveryMode | None = Query(default=None, description="Filter by delivery mode"),
    agent_id: UUID | None = Query(default=None, description="Filter by agent UUID"),
    autonomy_mode: AutonomyMode | None = Query(default=None, description="Filter by autonomy mode"),
    notification_type: str | None = Query(default=None, description="Filter by notification type"),
    channel: Channel | None = Query(default=None, description="Filter by channel attempted"),
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> DeliveryTimelineListResponse:
    """HTTP adapter - delegates to uns.queries.list_deliveries."""
    if notification_type is not None:
        require_source_and_namespace(
            principal,
            notification_type=notification_type,
            require_source=False,
        )
    log_endpoint_call(
        logger,
        "list_deliveries",
        cursor=cursor,
        limit=limit,
        status=status.value if status else None,
        intent=intent.value if intent else None,
        delivery_mode=delivery_mode.value if delivery_mode else None,
        autonomy_mode=autonomy_mode.value if autonomy_mode else None,
    )

    read_adapter = getattr(http_request.app.state, "read_model_adapter", None)
    if _principal_has_record_bounds(principal):
        unpaged = await _query_list_deliveries(
            cursor=None,
            limit=10_000,
            start_time=start_time,
            end_time=end_time,
            status=status,
            intent=intent,
            delivery_mode=delivery_mode,
            agent_id=agent_id,
            autonomy_mode=autonomy_mode,
            notification_type=notification_type,
            channel=channel,
            read_adapter=read_adapter,
        )
        filtered = _apply_source_and_namespace_bounds(
            http_request,
            principal,
            unpaged.items,
        )
        offset = _decode_cursor(cursor)
        page_items = filtered[offset : offset + limit]
        has_more = (offset + limit) < len(filtered)
        next_cursor = _encode_cursor(offset + limit) if has_more else None
        return DeliveryTimelineListResponse(
            items=page_items,
            pagination=PaginationInfo(
                next_cursor=next_cursor,
                has_more=has_more,
                total_count=len(filtered),
            ),
        )

    return await _query_list_deliveries(
        cursor=cursor,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        status=status,
        intent=intent,
        delivery_mode=delivery_mode,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        notification_type=notification_type,
        channel=channel,
        read_adapter=read_adapter,
    )


@router.get(
    "/deliveries/{notification_id}",
    response_model=DeliveryTimelineResponse,
    responses={
        200: {"description": "Delivery timeline details"},
        404: {"description": "Notification not found"},
    },
    summary="Get delivery timeline",
    description="Get full delivery timeline for a specific notification. Read-only endpoint.",
)
async def get_delivery_timeline(
    notification_id: UUID,
    http_request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> DeliveryTimelineResponse:
    """HTTP adapter - delegates to uns.queries.get_delivery_timeline.

    Translates the typed :class:`uns.errors.NotFoundError` raised by
    the service layer to an HTTP 404 response with the standard error
    envelope. Observability metric emission for the 404 path lives here
    in the route adapter (not in the service layer).
    """
    log_endpoint_call(
        logger,
        "get_delivery_timeline",
        notification_id=str(notification_id),
    )

    try:
        timeline = await _query_delivery_timeline(
            notification_id=notification_id,
            read_adapter=getattr(http_request.app.state, "read_model_adapter", None),
        )
    except NotFoundError as exc:
        message = f"Delivery timeline not found for notification {notification_id}"
        error_response = create_error_response_with_request_id(
            code="not_found",
            message=message,
        )
        record_endpoint_error(
            endpoint="/ui/deliveries/{id}",
            error_code="not_found",
            error_message=message,
            status_code=404,
        )
        # Preserve traceback chain (matches routes_notification.py convention
        # for typed-domain-error → HTTP-status translation).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response,
        ) from exc
    source, resolved_ntype = _resolve_ui_notification_bounds(
        http_request,
        notification_id,
        item=timeline,
    )
    require_source_and_namespace(
        principal,
        source=source,
        notification_type=timeline.notification_type or resolved_ntype,
    )
    return timeline


get_delivery_detail = get_delivery_timeline


@router.get(
    "/policies/effective",
    response_model=EffectivePolicyResponse,
    responses={
        200: {"description": "Effective policy resolution"},
        400: {"description": "Invalid parameters"},
    },
    summary="Get effective policy",
    description="Get effective policy resolution for a notification type. Read-only endpoint.",
)
async def get_effective_policy(
    http_request: Request,
    notification_type: str = Query(..., description="The notification type to resolve"),
    intent: NotificationIntent | None = Query(
        default=None,
        description="The notification intent (defaults to active policy intent when registered)",
    ),
    autonomy_mode: AutonomyMode = Query(..., description="The autonomy mode"),
    irreversible: bool = Query(default=False, description="Whether the action is irreversible"),
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> EffectivePolicyResponse:
    """HTTP adapter - delegates to uns.queries.get_effective_policy."""
    require_source_and_namespace(
        principal,
        notification_type=notification_type,
        require_source=False,
    )
    log_endpoint_call(
        logger,
        "get_effective_policy",
        notification_type=notification_type,
        intent=intent.value if intent is not None else None,
        autonomy_mode=autonomy_mode.value,
        irreversible=irreversible,
    )

    try:
        return await _query_effective_policy(
            notification_type=notification_type,
            intent=intent,
            autonomy_mode=autonomy_mode,
            irreversible=irreversible,
            policy_registry=(
                http_request.app.state.runtime.policy_runtime.registry()
                if getattr(http_request.app.state, "runtime", None) is not None
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/policies/active",
    response_model=ActivePolicyListResponse,
    summary="List active notification policies",
    description="Return the catalog of currently active notification routing policies.",
)
async def list_active_policies(
    http_request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> ActivePolicyListResponse:
    """Return all active notification policies from the runtime or process registry."""
    from notification.policies import DEFAULT_DEDUP_WINDOW_SECONDS, get_policy_registry

    log_endpoint_call(logger, "list_active_policies")
    runtime = getattr(http_request.app.state, "runtime", None)
    registry = runtime.policy_runtime.registry() if runtime is not None else get_policy_registry()
    items: list[ActivePolicySummary] = []
    for policy in sorted(registry.get_all().values(), key=lambda p: p.notification_type):
        if principal is not None and not principal.allows_namespace(policy.notification_type):
            continue
        default_intent = policy.intent or NotificationIntent.OPERATIONAL
        channels = policy.get_channels_for_mode(AutonomyMode.LIVE, default_intent) or list(
            policy.channels
        )
        delivery_mode = (
            policy.get_delivery_mode_for_mode(AutonomyMode.LIVE, default_intent)
            if policy.intent
            else policy.delivery_mode
        )
        require_ack = policy.get_require_ack_for_mode(AutonomyMode.LIVE, policy.intent)
        ack_timeout_minutes = (
            policy.get_ack_timeout_minutes_for_mode(AutonomyMode.LIVE, default_intent)
            if policy.intent
            else policy.ack_timeout_minutes
        )
        ack_timeout_seconds = ack_timeout_minutes * 60 if ack_timeout_minutes is not None else None
        dedup_window_seconds = (
            policy.dedup_window_seconds
            if policy.dedup_window_seconds is not None
            else DEFAULT_DEDUP_WINDOW_SECONDS
        )
        items.append(
            ActivePolicySummary(
                notification_type=policy.notification_type,
                version=policy.version,
                status=policy.status.value,
                intent=policy.intent,
                channels=channels,
                delivery_mode=delivery_mode,
                require_ack=require_ack,
                ack_timeout_minutes=ack_timeout_minutes,
                ack_timeout_seconds=ack_timeout_seconds,
                dedup_window_seconds=dedup_window_seconds,
            )
        )
    return ActivePolicyListResponse(items=items, total_count=len(items))


@router.get(
    "/policies/revisions",
    response_model=PolicyRevisionListResponse,
    summary="List notification policy revisions",
    description="Return stored notification policy revisions across lifecycle statuses (ACTIVE, DRAFT, PREVIEW, RETIRED).",
)
async def list_policy_revisions(
    http_request: Request,
    notification_type: str | None = Query(default=None, description="Filter by notification_type"),
    policy_status: PolicyStatus | None = Query(
        default=None, alias="status", description="Filter by policy lifecycle status"
    ),
    limit: int = Query(default=200, ge=1, le=500, description="Maximum revisions to return"),
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> PolicyRevisionListResponse:
    """Return stored notification policy revisions across lifecycle statuses."""
    from notification.policies import DEFAULT_DEDUP_WINDOW_SECONDS, get_policy_registry
    from notification.policy_loader import compute_policy_content_hash

    if notification_type:
        require_source_and_namespace(
            principal,
            notification_type=notification_type,
            require_source=False,
        )
    log_endpoint_call(
        logger,
        "list_policy_revisions",
        notification_type=notification_type,
        status=policy_status.value if policy_status else None,
        limit=limit,
    )
    runtime = getattr(http_request.app.state, "runtime", None)
    policy_store = getattr(http_request.app.state, "policy_store", None)
    if policy_store is None and runtime is not None:
        policy_store = runtime.policy_runtime.store

    items: list[PolicyRevisionSummary] = []
    if policy_store is not None:
        revisions = policy_store.list_revisions(
            notification_type=notification_type,
            status=policy_status,
            limit=limit,
        )
        for row, policy in revisions:
            default_intent = policy.intent or NotificationIntent.OPERATIONAL
            channels = policy.get_channels_for_mode(AutonomyMode.LIVE, default_intent) or list(
                policy.channels
            )
            delivery_mode = (
                policy.get_delivery_mode_for_mode(AutonomyMode.LIVE, default_intent)
                if policy.intent
                else policy.delivery_mode
            )
            require_ack = policy.get_require_ack_for_mode(AutonomyMode.LIVE, policy.intent)
            ack_timeout_minutes = (
                policy.get_ack_timeout_minutes_for_mode(AutonomyMode.LIVE, default_intent)
                if policy.intent
                else policy.ack_timeout_minutes
            )
            ack_timeout_seconds = (
                ack_timeout_minutes * 60 if ack_timeout_minutes is not None else None
            )
            dedup_window_seconds = (
                policy.dedup_window_seconds
                if policy.dedup_window_seconds is not None
                else DEFAULT_DEDUP_WINDOW_SECONDS
            )
            config_hash = (
                row.content_hash
                or policy.config_hash
                or compute_policy_content_hash(
                    policy.model_dump(mode="json", exclude={"config_id", "config_hash"})
                )
            )
            items.append(
                PolicyRevisionSummary(
                    policy_id=row.policy_id,
                    notification_type=row.notification_type,
                    version=row.version,
                    status=row.status,
                    config_hash=config_hash,
                    previous_version_id=row.previous_version_id,
                    intent=policy.intent,
                    channels=channels,
                    delivery_mode=delivery_mode,
                    require_ack=require_ack,
                    ack_timeout_minutes=ack_timeout_minutes,
                    ack_timeout_seconds=ack_timeout_seconds,
                    dedup_window_seconds=dedup_window_seconds,
                    created_at=_utc_opt(row.created_at),
                    updated_at=_utc_opt(row.updated_at),
                    activated_at=_utc_opt(row.activated_at),
                    retired_at=_utc_opt(row.retired_at),
                )
            )
    else:
        registry = (
            runtime.policy_runtime.registry() if runtime is not None else get_policy_registry()
        )
        candidates = list(registry.get_all().values())
        if notification_type:
            candidates = [p for p in candidates if p.notification_type == notification_type]
        if policy_status is not None:
            candidates = [p for p in candidates if p.status == policy_status]
        candidates.sort(key=lambda p: p.version, reverse=True)
        candidates.sort(key=lambda p: p.notification_type)
        for policy in candidates[:limit]:
            default_intent = policy.intent or NotificationIntent.OPERATIONAL
            channels = policy.get_channels_for_mode(AutonomyMode.LIVE, default_intent) or list(
                policy.channels
            )
            delivery_mode = (
                policy.get_delivery_mode_for_mode(AutonomyMode.LIVE, default_intent)
                if policy.intent
                else policy.delivery_mode
            )
            require_ack = policy.get_require_ack_for_mode(AutonomyMode.LIVE, policy.intent)
            ack_timeout_minutes = (
                policy.get_ack_timeout_minutes_for_mode(AutonomyMode.LIVE, default_intent)
                if policy.intent
                else policy.ack_timeout_minutes
            )
            ack_timeout_seconds = (
                ack_timeout_minutes * 60 if ack_timeout_minutes is not None else None
            )
            dedup_window_seconds = (
                policy.dedup_window_seconds
                if policy.dedup_window_seconds is not None
                else DEFAULT_DEDUP_WINDOW_SECONDS
            )
            config_hash = policy.config_hash or compute_policy_content_hash(
                policy.model_dump(mode="json", exclude={"config_id", "config_hash"})
            )
            items.append(
                PolicyRevisionSummary(
                    policy_id=policy.config_id,
                    notification_type=policy.notification_type,
                    version=policy.version,
                    status=policy.status.value,
                    config_hash=config_hash,
                    previous_version_id=None,
                    intent=policy.intent,
                    channels=channels,
                    delivery_mode=delivery_mode,
                    require_ack=require_ack,
                    ack_timeout_minutes=ack_timeout_minutes,
                    ack_timeout_seconds=ack_timeout_seconds,
                    dedup_window_seconds=dedup_window_seconds,
                )
            )
    if principal is not None and principal.allowed_namespaces:
        items = [item for item in items if principal.allows_namespace(item.notification_type)]
    return PolicyRevisionListResponse(items=items, total_count=len(items))


@router.get(
    "/policies/proposals",
    response_model=PolicyProposalListResponse,
    summary="List policy delta proposals and shadow evaluation evidence",
    description="Return governed policy delta proposals, shadow evaluation aggregates, and guard results.",
)
async def list_policy_proposals(
    http_request: Request,
    policy_type: str | None = Query(
        default=None, description="Filter by notification_type / policy_type"
    ),
    state: DeltaState | None = Query(default=None, description="Filter by delta lifecycle state"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum proposals to return"),
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> PolicyProposalListResponse:
    """Return governed policy delta proposals and shadow evaluation summaries."""
    if policy_type:
        require_source_and_namespace(
            principal,
            notification_type=policy_type,
            require_source=False,
        )
    log_endpoint_call(
        logger,
        "list_policy_proposals",
        policy_type=policy_type,
        state=state.value if state else None,
        limit=limit,
    )
    evaluator = resolve_shadow_evaluator(http_request.app.state)
    if evaluator is None:
        return PolicyProposalListResponse(items=[], total_count=0)

    deltas = evaluator.learning_store.list_deltas(
        policy_type=policy_type,
        state=state,
        limit=limit,
    )
    items: list[PolicyProposalSummary] = []
    for delta in deltas:
        if principal is not None and not principal.allows_namespace(delta.policy_type):
            continue
        items.append(evaluator.format_proposal_summary(delta, include_samples=False))
    return PolicyProposalListResponse(items=items, total_count=len(items))


@router.get(
    "/policies/proposals/{delta_id}",
    response_model=PolicyProposalSummary,
    summary="Inspect a policy delta proposal and shadow evaluation samples",
    description="Return full detail for a policy delta proposal, including shadow decision samples and guard history.",
)
async def get_policy_proposal(
    delta_id: UUID,
    http_request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> PolicyProposalSummary:
    """Return full detail for one policy delta proposal."""
    log_endpoint_call(logger, "get_policy_proposal", delta_id=str(delta_id))
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
    summary = evaluator.format_proposal_summary(delta, include_samples=True)
    if principal is not None and not principal.has_wildcard_sources and summary.shadow_results:
        filtered_samples = []
        bounds_cache: dict[UUID, tuple[str | None, str | None]] = {}
        for sample in summary.shadow_results:
            src = (
                sample.original_outcome.get("source")
                if isinstance(sample.original_outcome, dict)
                else None
            )
            if src is None:
                try:
                    sample_uuid: UUID | None = UUID(str(sample.decision_id))
                except (ValueError, TypeError):
                    sample_uuid = None
                src, _ = _resolve_ui_notification_bounds(
                    http_request,
                    sample_uuid,
                    bounds_cache=bounds_cache,
                )
            if principal.allows_source(src):
                filtered_samples.append(sample)
        summary = summary.model_copy(update={"shadow_results": filtered_samples})
    return summary


@router.get(
    "/invariants",
    response_model=InvariantListResponse,
    responses={
        200: {"description": "List of invariants"},
        400: {"description": "Invalid parameters"},
    },
    summary="List system invariants",
    description="Get the system invariant registry. Read-only endpoint.",
)
async def list_invariants(
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    severity: InvariantSeverity | None = Query(default=None, description="Filter by severity"),
    enforcement_type: EnforcementType | None = Query(
        default=None, description="Filter by enforcement type"
    ),
    invariant_status: InvariantStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    search: str | None = Query(default=None, description="Full-text search on statement"),
) -> InvariantListResponse:
    """HTTP adapter - delegates to uns.queries.list_invariants."""
    log_endpoint_call(
        logger,
        "list_invariants",
        cursor=cursor,
        limit=limit,
        severity=severity.value if severity else None,
        enforcement_type=enforcement_type.value if enforcement_type else None,
        status=invariant_status.value if invariant_status else None,
        search=search,
    )

    return await _query_list_invariants(
        cursor=cursor,
        limit=limit,
        severity=severity,
        enforcement_type=enforcement_type,
        invariant_status=invariant_status,
        search=search,
    )


@router.get(
    "/invariants/summary",
    response_model=InvariantSummaryResponse,
    responses={
        200: {"description": "Invariant summary statistics"},
    },
    summary="Get invariant summary",
    description="Get summary statistics for system invariants. Read-only endpoint.",
)
async def get_invariants_summary() -> InvariantSummaryResponse:
    """HTTP adapter - delegates to uns.queries.get_invariants_summary."""
    log_endpoint_call(logger, "get_invariants_summary")

    return await _query_invariants_summary()


@router.get(
    "/audit",
    response_model=AuditEventListResponse,
    responses={
        200: {"description": "List of audit events"},
        400: {"description": "Invalid parameters"},
    },
    summary="List audit events",
    description="Query audit event stream with filtering. Read-only endpoint.",
)
async def list_audit_events(
    http_request: Request,
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=25, ge=1, le=100, description="Items per page"),
    start_time: datetime | None = Query(default=None, description="Filter by event_time >="),
    end_time: datetime | None = Query(default=None, description="Filter by event_time <"),
    event_type: AuditEventType | None = Query(default=None, description="Filter by event type"),
    notification_id: UUID | None = Query(default=None, description="Filter by notification UUID"),
    agent_id: UUID | None = Query(default=None, description="Filter by agent UUID"),
    autonomy_mode: AutonomyMode | None = Query(default=None, description="Filter by autonomy mode"),
    correlation_id: str | None = Query(default=None, description="Filter by correlation ID"),
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> AuditEventListResponse:
    """HTTP adapter - delegates to uns.queries.list_audit_events."""
    log_endpoint_call(
        logger,
        "list_audit_events",
        cursor=cursor,
        limit=limit,
        event_type=event_type.value if event_type else None,
        notification_id=str(notification_id) if notification_id else None,
        agent_id=str(agent_id) if agent_id else None,
        autonomy_mode=autonomy_mode.value if autonomy_mode else None,
        correlation_id=correlation_id,
    )

    read_adapter = getattr(http_request.app.state, "read_model_adapter", None)
    if _principal_has_record_bounds(principal):
        unpaged = await _query_list_audit_events(
            cursor=None,
            limit=10_000,
            start_time=start_time,
            end_time=end_time,
            event_type=event_type,
            notification_id=notification_id,
            agent_id=agent_id,
            autonomy_mode=autonomy_mode,
            correlation_id=correlation_id,
            read_adapter=read_adapter,
        )
        filtered = _apply_source_and_namespace_bounds(
            http_request,
            principal,
            unpaged.items,
        )
        offset = _decode_cursor(cursor)
        page_items = filtered[offset : offset + limit]
        has_more = (offset + limit) < len(filtered)
        next_cursor = _encode_cursor(offset + limit) if has_more else None
        return AuditEventListResponse(
            items=page_items,
            pagination=PaginationInfo(
                next_cursor=next_cursor,
                has_more=has_more,
                total_count=len(filtered),
            ),
        )

    return await _query_list_audit_events(
        cursor=cursor,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
        notification_id=notification_id,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        correlation_id=correlation_id,
        read_adapter=read_adapter,
    )


get_audit_timeline = list_audit_events


def create_ui_router() -> APIRouter:
    """Factory function to create the UI router.

    Returns:
        Configured APIRouter with UI endpoints
    """
    return router


# Re-export for backward compatibility. tests/ui_contract/test_ui_contracts.py
# and scripts/generate_ui_contracts.py historically imported these classes
# directly from this module; the alias preserves their import path while the
# canonical home is now :mod:`uns.responses`.
__all__ = [
    "AuditEvent",
    "AuditEventListResponse",
    "AuditEventType",
    "AutonomyContextResponse",
    "ConsoleSessionResponse",
    "DeliveryAttempt",
    "DeliveryTimelineListResponse",
    "DeliveryTimelineResponse",
    "DeliveryTimelineSummary",
    "EffectivePolicyResponse",
    "EffectivePolicyValues",
    "EnforcementType",
    "ErrorDetail",
    "ErrorResponse",  # alias for UIErrorResponse
    "EvidenceLink",
    "InvariantEnforcement",
    "InvariantEntry",
    "InvariantListResponse",
    "InvariantSeverity",
    "InvariantStatus",
    "InvariantSummaryResponse",
    "PaginationInfo",
    "PolicyRevisionListResponse",
    "PolicyRevisionSummary",
    "ResolutionContext",
    "ResolutionSource",
    "ResolutionStep",
    "router",
]

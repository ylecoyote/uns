"""Read-only UI HTTP route adapters for AGSignal Console.

This module provides the HTTP endpoints for the UI dashboard per
``docs/ui/ui-data-contracts.md``:

- GET /ui/deliveries — List delivery timelines with filtering
- GET /ui/deliveries/{id} — Get single delivery timeline
- GET /ui/policies/effective — Get effective policy resolution
- GET /ui/invariants — List system invariants
- GET /ui/invariants/summary — Aggregate invariant summary
- GET /ui/audit — List audit events with filtering

All endpoints are READ-ONLY. No mutating actions are permitted.

Architecture (post-Phase-2 Task 3, post-Phase-3 Task 1):
- Each route handler is a thin adapter: parameter parsing (Query/Depends)
  + log_endpoint_call observability + ``await agsignal.queries.X(...)``.
- The canonical implementation of each read operation lives in
  :mod:`agsignal.queries`. Routes do not contain business logic.
- Pydantic response models live in :mod:`agsignal.responses`; this
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

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from agsignal.api.auth import (
    WritePrincipal,
    require_authenticated_observer,
    require_read_principal,
)
from agsignal.api.observability import (
    create_error_response_with_request_id,
    get_structured_logger,
    log_endpoint_call,
    record_endpoint_error,
)
from agsignal.errors import NotFoundError
from agsignal.queries import (
    get_delivery_timeline as _query_delivery_timeline,
)
from agsignal.queries import (
    get_effective_policy as _query_effective_policy,
)
from agsignal.queries import (
    get_invariants_summary as _query_invariants_summary,
)
from agsignal.queries import (
    list_audit_events as _query_list_audit_events,
)
from agsignal.queries import (
    list_deliveries as _query_list_deliveries,
)
from agsignal.queries import (
    list_invariants as _query_list_invariants,
)
from agsignal.responses import (
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
    PolicyRevisionListResponse,
    PolicyRevisionSummary,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)
from agsignal.responses import (
    UIErrorResponse as ErrorResponse,
)
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from notification.policies import PolicyStatus

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/ui", tags=["ui"], dependencies=[Depends(require_read_principal)])


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
) -> DeliveryTimelineListResponse:
    """HTTP adapter — delegates to agsignal.queries.list_deliveries."""
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
        read_adapter=getattr(http_request.app.state, "read_model_adapter", None),
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
) -> DeliveryTimelineResponse:
    """HTTP adapter — delegates to agsignal.queries.get_delivery_timeline.

    Translates the typed :class:`agsignal.errors.NotFoundError` raised by
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
        return await _query_delivery_timeline(
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
    intent: NotificationIntent = Query(..., description="The notification intent"),
    autonomy_mode: AutonomyMode = Query(..., description="The autonomy mode"),
    irreversible: bool = Query(default=False, description="Whether the action is irreversible"),
) -> EffectivePolicyResponse:
    """HTTP adapter — delegates to agsignal.queries.get_effective_policy."""
    log_endpoint_call(
        logger,
        "get_effective_policy",
        notification_type=notification_type,
        intent=intent.value,
        autonomy_mode=autonomy_mode.value,
        irreversible=irreversible,
    )

    try:
        return await _query_effective_policy(
            notification_type=notification_type,
            intent=intent,
            autonomy_mode=autonomy_mode,
            irreversible=irreversible,
            policy_registry=(http_request.app.state.runtime.policy_runtime.registry()
                             if getattr(http_request.app.state, "runtime", None) is not None else None),
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
) -> ActivePolicyListResponse:
    """Return all active notification policies from the runtime or process registry."""
    from notification.policies import DEFAULT_DEDUP_WINDOW_SECONDS, get_policy_registry

    log_endpoint_call(logger, "list_active_policies")
    runtime = getattr(http_request.app.state, "runtime", None)
    registry = (
        runtime.policy_runtime.registry()
        if runtime is not None
        else get_policy_registry()
    )
    items: list[ActivePolicySummary] = []
    for policy in sorted(registry.get_all().values(), key=lambda p: p.notification_type):
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
    notification_type: str | None = Query(
        default=None, description="Filter by notification_type"
    ),
    policy_status: PolicyStatus | None = Query(
        default=None, alias="status", description="Filter by policy lifecycle status"
    ),
) -> PolicyRevisionListResponse:
    """Return stored notification policy revisions across lifecycle statuses."""
    from sqlalchemy import select

    from db.models.policy import PersistedNotificationPolicy
    from notification.policies import DEFAULT_DEDUP_WINDOW_SECONDS, get_policy_registry
    from notification.policy_loader import compute_policy_content_hash

    log_endpoint_call(
        logger,
        "list_policy_revisions",
        notification_type=notification_type,
        status=policy_status.value if policy_status else None,
    )
    runtime = getattr(http_request.app.state, "runtime", None)
    policy_store = getattr(http_request.app.state, "policy_store", None)
    if policy_store is None and runtime is not None:
        policy_store = runtime.policy_runtime.store

    items: list[PolicyRevisionSummary] = []
    if policy_store is not None:
        policy_store.ensure_snapshot_schema()
        with policy_store._get_session() as session:
            stmt = select(PersistedNotificationPolicy)
            if notification_type:
                stmt = stmt.where(
                    PersistedNotificationPolicy.notification_type == notification_type
                )
            if policy_status is not None:
                stmt = stmt.where(
                    PersistedNotificationPolicy.status == policy_status.value
                )
            stmt = stmt.order_by(
                PersistedNotificationPolicy.notification_type.asc(),
                PersistedNotificationPolicy.version.desc(),
                PersistedNotificationPolicy.updated_at.desc(),
            )
            rows = session.execute(stmt).scalars().all()
            for row in rows:
                policy = policy_store._hydrate_policy(session, row)
                default_intent = policy.intent or NotificationIntent.OPERATIONAL
                channels = policy.get_channels_for_mode(
                    AutonomyMode.LIVE, default_intent
                ) or list(policy.channels)
                delivery_mode = (
                    policy.get_delivery_mode_for_mode(
                        AutonomyMode.LIVE, default_intent
                    )
                    if policy.intent
                    else policy.delivery_mode
                )
                require_ack = policy.get_require_ack_for_mode(
                    AutonomyMode.LIVE, policy.intent
                )
                ack_timeout_minutes = (
                    policy.get_ack_timeout_minutes_for_mode(
                        AutonomyMode.LIVE, default_intent
                    )
                    if policy.intent
                    else policy.ack_timeout_minutes
                )
                ack_timeout_seconds = (
                    ack_timeout_minutes * 60
                    if ack_timeout_minutes is not None
                    else None
                )
                dedup_window_seconds = (
                    policy.dedup_window_seconds
                    if policy.dedup_window_seconds is not None
                    else DEFAULT_DEDUP_WINDOW_SECONDS
                )
                config_hash = row.content_hash or policy.config_hash or compute_policy_content_hash(
                    policy.model_dump(mode="json", exclude={"config_id", "config_hash"})
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
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        activated_at=row.activated_at,
                        retired_at=row.retired_at,
                    )
                )
    else:
        registry = get_policy_registry()
        candidates = list(registry.get_all().values())
        if notification_type:
            candidates = [
                p for p in candidates if p.notification_type == notification_type
            ]
        if policy_status is not None:
            candidates = [p for p in candidates if p.status == policy_status]
        candidates.sort(key=lambda p: p.version, reverse=True)
        candidates.sort(key=lambda p: p.notification_type)
        for policy in candidates:
            default_intent = policy.intent or NotificationIntent.OPERATIONAL
            channels = policy.get_channels_for_mode(
                AutonomyMode.LIVE, default_intent
            ) or list(policy.channels)
            delivery_mode = (
                policy.get_delivery_mode_for_mode(AutonomyMode.LIVE, default_intent)
                if policy.intent
                else policy.delivery_mode
            )
            require_ack = policy.get_require_ack_for_mode(
                AutonomyMode.LIVE, policy.intent
            )
            ack_timeout_minutes = (
                policy.get_ack_timeout_minutes_for_mode(
                    AutonomyMode.LIVE, default_intent
                )
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
    return PolicyRevisionListResponse(items=items, total_count=len(items))


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
    """HTTP adapter — delegates to agsignal.queries.list_invariants."""
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
    """HTTP adapter — delegates to agsignal.queries.get_invariants_summary."""
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
) -> AuditEventListResponse:
    """HTTP adapter — delegates to agsignal.queries.list_audit_events."""
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
        read_adapter=getattr(http_request.app.state, "read_model_adapter", None),
    )


def create_ui_router() -> APIRouter:
    """Factory function to create the UI router.

    Returns:
        Configured APIRouter with UI endpoints
    """
    return router


# Re-export for backward compatibility. tests/ui_contract/test_ui_contracts.py
# and scripts/generate_ui_contracts.py historically imported these classes
# directly from this module; the alias preserves their import path while the
# canonical home is now :mod:`agsignal.responses`.
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

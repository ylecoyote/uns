"""AGSignal read-side service layer.

Stateless async query functions that read state from the configured stores
and return typed Pydantic responses. These functions can be called from any
caller (HTTP route handlers, MCP tools, future CLI). Routes become thin
adapters that parse `Request`, delegate here, and return the response.

Each function in this module is the canonical implementation of its
operation. `agsignal.api.routes_ui` and `agsignal_mcp.tools` both call
into these — there is no other source of truth.

Service-layer error handling: these functions raise typed domain errors
from :mod:`agsignal.errors` (e.g. :class:`~agsignal.errors.NotFoundError`)
instead of HTTP-shaped exceptions. Route adapters translate the typed
errors to HTTP status codes; non-HTTP transports handle them as Python
exceptions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from agsignal.api.observability import (
    get_structured_logger,
    record_endpoint_error,
)
from agsignal.api.read_models import (  # internal adapter types; Phase 5 relocates
    AuditEventFilter,
    DeliveryFilter,
    get_read_model_adapter,
)
from agsignal.errors import NotFoundError

# CAUTION: agsignal.responses.AuditEvent is the Pydantic class (relocated from
# routes_ui); agsignal.api.read_models.AuditEvent is a different @dataclass. They
# are not interchangeable. The import below is the Pydantic version; if your
# code needs the dataclass, import it explicitly from agsignal.api.read_models.
from agsignal.responses import (
    AckStatusResponse,
    AuditEvent,
    AuditEventListResponse,
    AuditEventType,
    AutonomyContextResponse,
    DeliveryAttempt,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    EnforcementType,
    EvidenceLink,
    InvariantEnforcement,
    InvariantEntry,
    InvariantListResponse,
    InvariantSeverity,
    InvariantStatus,
    InvariantSummaryResponse,
    NotificationStatusResponse,
    PaginationInfo,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)
from notification.acknowledgment import (
    AcknowledgmentEngine,
    configure_ack_engine,
    get_ack_engine,
)
from notification.models import (
    AckStatus,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from notification.policies import (
    DEFAULT_DEDUP_WINDOW_SECONDS,
    PolicyOverrideError,
    PolicyRegistry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_delivery_mode,
    get_default_require_ack,
    get_policy_registry,
)

logger = get_structured_logger(__name__)

__all__ = [
    "get_ack_status",
    "get_delivery_timeline",
    "get_effective_policy",
    "get_engine",
    "get_invariants_summary",
    "get_notification_status",
    "list_audit_events",
    "list_deliveries",
    "list_invariants",
]


def get_engine() -> AcknowledgmentEngine:
    """Get the acknowledgment engine, initializing if needed.

    Phase 3 Task 1 relocated this factory from
    ``agsignal.api.routes_notification`` into the service layer to break a
    circular import (the routes module now imports the queries that use
    this factory; previously the queries module imported the factory from
    the routes module). Behavior is unchanged.
    """
    try:
        return get_ack_engine()
    except RuntimeError:
        # Auto-configure with defaults for convenience
        return configure_ack_engine()


async def list_deliveries(
    cursor: str | None = None,
    limit: int = 25,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    status: DeliveryStatus | None = None,  # noqa: A002 — preserves route signature
    intent: NotificationIntent | None = None,
    delivery_mode: DeliveryMode | None = None,
    agent_id: UUID | None = None,
    autonomy_mode: AutonomyMode | None = None,
    notification_type: str | None = None,
    channel: Channel | None = None,
) -> DeliveryTimelineListResponse:
    """List delivery timelines with filtering.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Queries the read model adapter for delivery summaries matching the
    provided filter criteria. Returns paginated results.

    Note: Default adapter is InMemoryReadModelAdapter (data not persisted).
    Configure SQLAlchemyReadModelAdapter for production persistence.
    """
    # Body extracted verbatim from agsignal.api.routes_ui.list_deliveries
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).

    # Build filter criteria
    filter_criteria = DeliveryFilter(
        start_time=start_time,
        end_time=end_time,
        status=status,
        intent=intent,
        delivery_mode=delivery_mode,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        notification_type=notification_type,
        channel=channel,
    )

    # Query read model adapter
    adapter = get_read_model_adapter()
    result = adapter.get_deliveries(filter_criteria, cursor, limit)

    # Convert to response model
    items = [
        DeliveryTimelineSummary(
            notification_id=item.notification_id,
            notification_type=item.notification_type,
            intent=item.intent,
            delivery_mode=item.delivery_mode,
            status=item.status,
            created_at=item.created_at,
            delivered_at=item.delivered_at,
            channels_attempted=item.channels_attempted,
            channels_succeeded=item.channels_succeeded,
            autonomy_mode=item.autonomy_mode,
            agent_id=item.agent_id,
        )
        for item in result.items
    ]

    return DeliveryTimelineListResponse(
        items=items,
        pagination=PaginationInfo(
            next_cursor=result.next_cursor,
            has_more=result.has_more,
            total_count=result.total_count,
        ),
    )


async def get_delivery_timeline(
    notification_id: UUID,
) -> DeliveryTimelineResponse:
    """Get delivery timeline for a specific notification.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Queries the read model adapter for the full delivery timeline
    of a specific notification, including all channel attempts.

    Note: Default adapter is InMemoryReadModelAdapter (data not persisted).
    Configure SQLAlchemyReadModelAdapter for production persistence.
    """
    # Body extracted verbatim from agsignal.api.routes_ui.get_delivery_timeline
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).

    # Query read model adapter
    adapter = get_read_model_adapter()
    timeline = adapter.get_delivery_timeline(notification_id)

    if timeline is None:
        raise NotFoundError(
            resource="delivery_timeline",
            identifier=str(notification_id),
        )

    # Convert attempts to response model
    attempts = [
        DeliveryAttempt(
            attempt_id=attempt.attempt_id,
            channel=attempt.channel,
            status=attempt.status,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            duration_ms=attempt.duration_ms,
            error_message=attempt.error_message,
            error_code=attempt.error_code,
            metadata=attempt.metadata,
        )
        for attempt in timeline.attempts
    ]

    runtime_state = None
    runtime = getattr(adapter, "runtime", None)
    if runtime is not None:
        try:
            row = runtime.get(notification_id)
            runtime_state = {
                "delivery_status": row["status"],
                "ack_status": row["ack_status"],
                "deadline": row["deadline"],
                "dead_letter": row["dead_letter"],
                "policy_config_hash": row["notification"]["policy_config_hash"],
                "policy_evaluation_id": row["notification"]["policy_evaluation_id"],
            }
        except KeyError:
            pass  # Historical audit rows predate durable runtime state.

    return DeliveryTimelineResponse(
        runtime_state=runtime_state,
        notification_id=timeline.notification_id,
        notification_type=timeline.notification_type,
        intent=timeline.intent,
        delivery_mode=timeline.delivery_mode,
        status=timeline.status,
        created_at=timeline.created_at,
        delivered_at=timeline.delivered_at,
        attempts=attempts,
        channels_attempted=timeline.channels_attempted,
        channels_succeeded=timeline.channels_succeeded,
        channels_failed=timeline.channels_failed,
        autonomy_context=AutonomyContextResponse(
            autonomy_mode=timeline.autonomy_mode,
            agent_id=timeline.agent_id,
            plan_id=timeline.plan_id,
            decision_snapshot_id=timeline.decision_snapshot_id,
            execution_snapshot_id=timeline.execution_snapshot_id,
            skip_snapshot_id=timeline.skip_snapshot_id,
        ),
    )


async def get_effective_policy(
    notification_type: str,
    intent: NotificationIntent,
    autonomy_mode: AutonomyMode,
    irreversible: bool = False,
    *,
    policy_registry: PolicyRegistry | None = None,
) -> EffectivePolicyResponse:
    """Get effective policy resolution for a notification type.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Shows how policy values are resolved through the resolution chain:
    1. explicit_override - Values passed directly (not applicable here)
    2. mode_override - Policy mode-specific override
    3. policy_base - Policy base value
    4. sdk_default - SDK default derived from intent + autonomy_mode
    """
    # Body extracted verbatim from agsignal.api.routes_ui.get_effective_policy
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).

    registry = policy_registry if policy_registry is not None else get_policy_registry()
    policy = registry.get_sync(notification_type)

    if (
        policy is not None
        and policy.is_runtime_enforced
        and policy.intent is not None
        and intent != policy.intent
    ):
        raise PolicyOverrideError("intent differs from ACTIVE policy")

    # Use the same precedence as the SDK: explicit mode values, policy base,
    # then intent defaults. Preserve false/empty values rather than truthiness.
    defaults: dict[str, Any] = {
        "delivery_mode": get_default_delivery_mode(intent),
        "channels": get_default_channels(intent, autonomy_mode, irreversible),
        "require_ack": get_default_require_ack(intent, autonomy_mode),
        "ack_timeout_minutes": get_default_ack_timeout(intent),
        "dedup_window_seconds": DEFAULT_DEDUP_WINDOW_SECONDS,
    }
    base: dict[str, Any] = dict.fromkeys(defaults)
    mode: dict[str, Any] = dict.fromkeys(defaults)
    if policy is not None:
        base = {
            "delivery_mode": policy.delivery_mode,
            "channels": policy.channels or None,
            "require_ack": policy.require_ack,
            "ack_timeout_minutes": policy.ack_timeout_minutes,
            "dedup_window_seconds": policy.dedup_window_seconds,
        }
        override = policy._get_mode_override(autonomy_mode)
        if override is not None:
            mode.update(
                {
                    "delivery_mode": override.delivery_mode,
                    "channels": override.channels,
                    "require_ack": override.require_ack,
                    "ack_timeout_minutes": override.ack_timeout_minutes,
                }
            )
        if mode["channels"] is None and policy.channels_by_mode:
            mode["channels"] = policy.channels_by_mode.get(autonomy_mode)

    effective: dict[str, Any] = {}
    resolution: dict[str, list[ResolutionStep]] = {}
    for field in defaults:
        selected = False
        effective[field] = None
        resolution[field] = []
        for source, candidate in (
            (ResolutionSource.MODE_OVERRIDE, mode[field]),
            (ResolutionSource.POLICY_BASE, base[field]),
            (ResolutionSource.SDK_DEFAULT, defaults[field]),
        ):
            applied = candidate is not None and not selected
            if applied:
                effective[field] = candidate
                selected = True
            resolution[field].append(
                ResolutionStep(
                    source=source,
                    value=candidate,
                    applied=applied,
                    reason="Not configured" if candidate is None else None,
                )
            )
    if not effective["require_ack"]:
        # Notification's domain validator retains the intent timeout default
        # even without an ACK obligation. Match the serialized notification;
        # runtime deadline scheduling still depends on require_ack.
        effective["ack_timeout_minutes"] = defaults["ack_timeout_minutes"]
        resolution["ack_timeout_minutes"] = [
            step.model_copy(
                update={
                    "applied": step.source == ResolutionSource.SDK_DEFAULT
                    and step.value is not None,
                    "reason": "No acknowledgment deadline is scheduled",
                }
            )
            for step in resolution["ack_timeout_minutes"]
        ]

    return EffectivePolicyResponse(
        notification_type=notification_type,
        effective=EffectivePolicyValues(**effective),
        resolution=resolution,
        resolution_context=ResolutionContext(
            intent=intent,
            autonomy_mode=autonomy_mode,
            irreversible=irreversible,
            policy_found=policy is not None,
            policy_notification_type=notification_type if policy is not None else None,
        ),
    )


async def list_invariants(
    cursor: str | None = None,
    limit: int = 25,
    severity: InvariantSeverity | None = None,
    enforcement_type: EnforcementType | None = None,
    invariant_status: InvariantStatus | None = None,
    search: str | None = None,
) -> InvariantListResponse:
    """List system invariants from the registry.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Returns invariants from docs/verification/invariants.yml.
    Filters can be applied to narrow results.
    """
    # Body extracted verbatim from agsignal.api.routes_ui.list_invariants
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).

    # Load invariants from YAML file
    # This is a simplified implementation - in production you might
    # cache this or use a proper data store
    try:
        from pathlib import Path

        import yaml  # type: ignore[import-untyped]

        invariants_path = (
            Path(__file__).parent.parent.parent / "docs" / "verification" / "invariants.yml"
        )
        if invariants_path.exists():
            with open(invariants_path) as f:
                data = yaml.safe_load(f)

            items: list[InvariantEntry] = []
            for inv in data.get("invariants", []):
                # Parse enforcement
                enforcement_data = inv.get("enforcement", {})
                enforcement = InvariantEnforcement(
                    type=EnforcementType(enforcement_data.get("type", "test")),
                    description=enforcement_data.get("description", ""),
                )

                # Parse evidence
                evidence = [
                    EvidenceLink(
                        path=e.get("path", ""),
                        note=e.get("note", ""),
                        line_ref=e.get("line_ref"),
                    )
                    for e in inv.get("evidence", [])
                ]

                entry = InvariantEntry(
                    id=inv.get("id", ""),
                    statement=inv.get("statement", "").strip(),
                    severity=InvariantSeverity(inv.get("severity", "MEDIUM")),
                    status=InvariantStatus(inv.get("status", "active")),
                    enforcement=enforcement,
                    evidence=evidence,
                    owner=inv.get("owner", ""),
                    last_reviewed=inv.get("last_reviewed", ""),
                    mitigation=inv.get("mitigation"),
                )

                # Apply filters (check hasattr in case called internally without FastAPI resolution)
                if severity and hasattr(severity, "value") and entry.severity != severity:
                    continue
                if (
                    enforcement_type
                    and hasattr(enforcement_type, "value")
                    and entry.enforcement.type != enforcement_type
                ):
                    continue
                if (
                    invariant_status
                    and hasattr(invariant_status, "value")
                    and entry.status != invariant_status
                ):
                    continue
                if (
                    search
                    and isinstance(search, str)
                    and search.lower() not in entry.statement.lower()
                ):
                    continue

                items.append(entry)

            # Apply pagination (simple offset-based for stub)
            total = len(items)
            items = items[:limit]

            return InvariantListResponse(
                items=items,
                pagination=PaginationInfo(
                    next_cursor=None if len(items) < limit else "stub-cursor",
                    has_more=total > limit,
                    total_count=total,
                ),
            )
        else:
            logger.warning(
                "Invariants file not found",
                extra={"path": str(invariants_path)},
            )
    except Exception as e:
        logger.error(
            "Error loading invariants",
            extra={"error": str(e)},
        )
        record_endpoint_error(
            endpoint="/ui/invariants",
            error_code="invariants_load_error",
            error_message=str(e),
            status_code=200,  # Still returns empty response, not a 500
        )

    # Fallback empty response
    return InvariantListResponse(
        items=[],
        pagination=PaginationInfo(
            next_cursor=None,
            has_more=False,
            total_count=0,
        ),
    )


async def get_invariants_summary() -> InvariantSummaryResponse:
    """Return summary statistics for system invariants.

    Canonical implementation: HTTP routes and MCP tools both delegate here.
    """
    # Body extracted verbatim from agsignal.api.routes_ui.get_invariants_summary
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).
    result = await list_invariants(limit=100)

    by_severity: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_enforcement: dict[str, int] = {"guard": 0, "isolation": 0, "test": 0, "exception": 0}
    by_status: dict[str, int] = {"active": 0, "inactive": 0}
    exceptions_count = 0

    for item in result.items:
        by_severity[item.severity.value] = by_severity.get(item.severity.value, 0) + 1
        by_enforcement[item.enforcement.type.value] = (
            by_enforcement.get(item.enforcement.type.value, 0) + 1
        )
        by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
        if item.enforcement.type == EnforcementType.EXCEPTION:
            exceptions_count += 1

    return InvariantSummaryResponse(
        total_count=len(result.items),
        by_severity=by_severity,
        by_enforcement_type=by_enforcement,
        by_status=by_status,
        exceptions_requiring_review=exceptions_count,
        last_updated=datetime.now().isoformat(),
    )


async def list_audit_events(
    cursor: str | None = None,
    limit: int = 25,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    event_type: AuditEventType | None = None,
    notification_id: UUID | None = None,
    agent_id: UUID | None = None,
    autonomy_mode: AutonomyMode | None = None,
    correlation_id: str | None = None,
) -> AuditEventListResponse:
    """List audit events with filtering.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Queries the read model adapter for audit events matching the
    provided filter criteria. Returns paginated results.

    Note: Default adapter is InMemoryReadModelAdapter (data not persisted).
    Configure SQLAlchemyReadModelAdapter for production persistence.
    """
    # Body extracted verbatim from agsignal.api.routes_ui.list_audit_events
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).

    # Build filter criteria
    filter_criteria = AuditEventFilter(
        start_time=start_time,
        end_time=end_time,
        event_type=event_type.value if event_type else None,
        notification_id=notification_id,
        agent_id=agent_id,
        autonomy_mode=autonomy_mode,
        correlation_id=correlation_id,
    )

    # Query read model adapter
    adapter = get_read_model_adapter()
    result = adapter.get_audit_events(filter_criteria, cursor, limit)

    # Convert to response model
    items = [
        AuditEvent(
            audit_id=item.audit_id,
            event_type=AuditEventType(item.event_type),
            event_time=item.event_time,
            notification_id=item.notification_id,
            notification_type=item.notification_type,
            autonomy_context=AutonomyContextResponse(
                autonomy_mode=item.autonomy_mode,
                agent_id=item.agent_id,
                plan_id=item.plan_id,
                decision_snapshot_id=item.decision_snapshot_id,
                execution_snapshot_id=item.execution_snapshot_id,
                skip_snapshot_id=item.skip_snapshot_id,
            ),
            payload=item.payload,
            correlation_id=item.correlation_id,
        )
        for item in result.items
    ]

    return AuditEventListResponse(
        items=items,
        pagination=PaginationInfo(
            next_cursor=result.next_cursor,
            has_more=result.has_more,
            total_count=result.total_count,
        ),
    )


async def get_notification_status(
    notification_id: UUID,
) -> NotificationStatusResponse:
    """Get the status of a notification.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Returns notification details including the current acknowledgment status.
    If the notification is not found, returns a response with found=False.

    Note: The engine only stores ack state, not full notification details.
    So this endpoint returns ack state info only.
    """
    # Body extracted verbatim from agsignal.api.routes_notification.get_notification_status
    # (minus the @router.get decorator).
    engine = get_engine()

    state = engine.get_state(notification_id)

    if state is None:
        return NotificationStatusResponse(
            notification_id=notification_id,
            found=False,
            ack_status=None,
        )

    return NotificationStatusResponse(
        notification_id=notification_id,
        intent=state.intent.value if state.intent else None,
        ack_status=state.status,
        created_at=state.created_at,
        found=True,
    )


async def get_ack_status(
    notification_id: UUID,
) -> AckStatusResponse:
    """Get the acknowledgment status of a notification.

    Canonical implementation: HTTP routes and MCP tools both delegate here.

    Returns just the ack status for a notification.
    Returns null ack_status if the notification is not being tracked.
    """
    # Body extracted verbatim from agsignal.api.routes_notification.get_ack_status
    # (minus the @router.get decorator; an explicit `AckStatus | None` type
    # annotation has been added on the local for clarity — behavior-equivalent).
    engine = get_engine()
    ack_status: AckStatus | None = engine.get_status(notification_id)

    return AckStatusResponse(
        notification_id=notification_id,
        ack_status=ack_status,
    )

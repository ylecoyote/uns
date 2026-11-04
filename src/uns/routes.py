"""Operator inspection of durable work and recovery events."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from uns.api.auth import (
    WritePrincipal,
    principal_allows_record,
    require_admin_principal,
    require_authenticated_observer,
    require_read_principal,
    require_source_and_namespace,
)
from uns.runtime import Conflict

router = APIRouter(prefix="/api/v1/runtime", dependencies=[Depends(require_authenticated_observer)])


def _extract_row_bounds(row: dict[str, Any]) -> tuple[str | None, str | None]:
    raw_notif = row.get("notification")
    notif: dict[str, Any] = raw_notif if isinstance(raw_notif, dict) else {}
    source = notif.get("source") or row.get("source")
    notification_type = notif.get("notification_type") or row.get("notification_type")
    return (
        str(source) if source is not None else None,
        str(notification_type) if notification_type is not None else None,
    )


@router.get("/notifications/{notification_id}")
def inspect_notification(
    notification_id: UUID,
    request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> dict[str, Any]:
    try:
        row = request.app.state.runtime.get(notification_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Notification not found") from exc
    source, notification_type = _extract_row_bounds(row)
    require_source_and_namespace(
        principal,
        source=source,
        notification_type=notification_type,
    )
    return {**row, "events": request.app.state.runtime.events(notification_id)}


@router.get("/dead-letters")
def dead_letters(
    request: Request,
    principal: WritePrincipal | None = Depends(require_read_principal),
) -> list[dict[str, Any]]:
    runtime = request.app.state.runtime
    items = list(runtime.dead_letters())
    if principal is None or (principal.allows_source(None) and principal.allows_namespace(None)):
        return items
    filtered: list[dict[str, Any]] = []
    for item in items:
        source, notification_type = _extract_row_bounds(item)
        if (source is None or notification_type is None) and item.get(
            "notification_id"
        ) is not None:
            try:
                row = runtime.get(item["notification_id"])
                row_source, row_type = _extract_row_bounds(row)
                source = source or row_source
                notification_type = notification_type or row_type
            except KeyError:
                pass
        if principal_allows_record(principal, source=source, notification_type=notification_type):
            filtered.append(item)
    return filtered


@router.post("/notifications/{notification_id}/replay")
def replay(
    notification_id: UUID,
    request: Request,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> dict[str, str]:
    runtime = request.app.state.runtime
    if not (principal.allows_source(None) and principal.allows_namespace(None)):
        try:
            row = runtime.get(notification_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Notification not found") from exc
        source, notification_type = _extract_row_bounds(row)
        require_source_and_namespace(
            principal,
            source=source,
            notification_type=notification_type,
        )
    try:
        runtime.replay(notification_id, actor=principal.subject)
        return {"notification_id": str(notification_id), "status": "PENDING"}
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

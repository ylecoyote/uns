"""Operator inspection of durable work and recovery events."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from uns.api.auth import (
    WritePrincipal,
    require_admin_principal,
    require_authenticated_observer,
)
from uns.runtime import Conflict

router = APIRouter(prefix="/api/v1/runtime", dependencies=[Depends(require_authenticated_observer)])


@router.get("/notifications/{notification_id}")
def inspect_notification(notification_id: UUID, request: Request) -> dict[str, Any]:
    try:
        row = request.app.state.runtime.get(notification_id)
        return {**row, "events": request.app.state.runtime.events(notification_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Notification not found") from exc


@router.get("/dead-letters")
def dead_letters(request: Request) -> list[dict[str, Any]]:
    return list(request.app.state.runtime.dead_letters())


@router.post("/notifications/{notification_id}/replay")
def replay(
    notification_id: UUID,
    request: Request,
    principal: WritePrincipal = Depends(require_admin_principal),
) -> dict[str, str]:
    try:
        request.app.state.runtime.replay(notification_id, actor=principal.subject)
        return {"notification_id": str(notification_id), "status": "PENDING"}
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

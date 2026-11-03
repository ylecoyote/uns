"""Inbound signed provider webhook routes for Slack and PagerDuty.

Implements:
- ``POST /api/v1/webhooks/slack``: Signed Slack Block Kit interactivity receiver
  (``X-Slack-Signature`` + ``X-Slack-Request-Timestamp`` HMAC-SHA256 verification
  with a 5-minute replay guard, follower-to-owner obligation resolution, and
  in-place Block Kit status update).
- ``POST /api/v1/webhooks/pagerduty``: Signed PagerDuty v3 webhook receiver
  (``X-PagerDuty-Signature`` HMAC-SHA256 verification, mapping
  ``incident.acknowledged`` and ``incident.resolved`` events to canonical UNS
  obligation acknowledgment).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from notification.acknowledgment import InvalidAckTransitionError
from notification.audit import AuditStore
from notification.models import AckStatus
from uns.signaling import acknowledge as signaling_acknowledge
from uns.signaling import dismiss as signaling_dismiss

if TYPE_CHECKING:
    from uns.runtime import Runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

MAX_WEBHOOK_BODY_BYTES = 262_144
SLACK_REPLAY_WINDOW_SECONDS = 300
_SAFE_ACTOR_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")


def _slack_signing_secret() -> str:
    return os.environ.get("UNS_SLACK_SIGNING_SECRET", "").strip()


def _pagerduty_webhook_secret() -> str:
    return os.environ.get("UNS_PAGERDUTY_WEBHOOK_SECRET", "").strip()


def _current_timestamp(runtime: Runtime | None) -> float:
    if runtime is not None and hasattr(runtime, "clock"):
        return float(runtime.clock())
    return time.time()


def _sanitize_actor_component(raw: Any, fallback: str = "unknown") -> str:
    text = str(raw or "").strip()
    if not text:
        return fallback
    if _SAFE_ACTOR_TOKEN_RE.match(text):
        return text
    cleaned = re.sub(r"[^A-Za-z0-9_.:@-]", "_", text)[:64]
    return cleaned or fallback


async def _read_bounded_body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Webhook payload exceeds maximum allowed size",
        )
    return body


def verify_slack_signature(
    *,
    signing_secret: str,
    timestamp_header: str | None,
    signature_header: str | None,
    raw_body: bytes,
    now: float,
) -> None:
    """Verify Slack ``v0`` HMAC-SHA256 signature and 5-minute replay window."""
    if not signing_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack webhook signing secret is not configured",
        )
    if not timestamp_header or not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature or timestamp header",
        )
    try:
        request_ts = int(timestamp_header.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack request timestamp",
        ) from exc

    if abs(now - request_ts) > SLACK_REPLAY_WINDOW_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Slack request timestamp is outside the allowed replay window",
        )

    try:
        decoded_body = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack webhook body must be valid UTF-8",
        ) from exc

    basestring = f"v0:{request_ts}:{decoded_body}".encode()
    expected = (
        "v0="
        + hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack webhook signature",
        )


def verify_pagerduty_signature(
    *,
    webhook_secret: str,
    signature_header: str | None,
    raw_body: bytes,
) -> None:
    """Verify PagerDuty v3 ``v1=<hex>`` HMAC-SHA256 webhook signature."""
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PagerDuty webhook secret is not configured",
        )
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-PagerDuty-Signature header",
        )

    expected = (
        "v1="
        + hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    )
    candidates = [
        token.strip()
        for token in signature_header.split(",")
        if token.strip().startswith("v1=")
    ]
    if not candidates or not any(
        hmac.compare_digest(expected, candidate) for candidate in candidates
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PagerDuty webhook signature",
        )


def _parse_slack_payload(raw_body: bytes, content_type: str) -> dict[str, Any]:
    media_type = content_type.split(";", 1)[0].strip().lower()
    try:
        decoded = raw_body.decode("utf-8")
        if media_type == "application/x-www-form-urlencoded":
            form = parse_qs(decoded, keep_blank_values=True)
            payload_list = form.get("payload")
            if not payload_list or not payload_list[0]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing 'payload' field in Slack form body",
                )
            data = json.loads(payload_list[0])
        else:
            data = json.loads(decoded)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed Slack webhook payload",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack webhook payload must be a JSON object",
        )
    return data


def _extract_slack_action(payload: dict[str, Any]) -> tuple[bool, UUID, str]:
    """Return ``(is_dismiss, notification_id, action_id)`` from Slack ``actions``."""
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack block_actions payload contains no actions",
        )
    for item in actions:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id") or "").strip()
        value = str(item.get("value") or "").strip()
        if action_id.startswith("ack_"):
            raw_uuid = action_id[4:] or value
            is_dismiss = False
        elif action_id.startswith("dismiss_"):
            raw_uuid = action_id[8:] or value
            is_dismiss = True
        elif action_id in {"ack", "dismiss"} and value:
            raw_uuid = value
            is_dismiss = action_id == "dismiss"
        else:
            continue
        try:
            return is_dismiss, UUID(raw_uuid), action_id
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid notification UUID in Slack action",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported Slack action_id",
    )


def _build_slack_settled_blocks(
    *,
    notification_id: UUID,
    obligation_owner_id: UUID,
    ack_status: AckStatus,
    actor: str,
    acked_at_iso: str,
) -> dict[str, Any]:
    verb = "Dismissed" if ack_status == AckStatus.DISMISSED else "Acknowledged"
    badge = ":no_bell:" if ack_status == AckStatus.DISMISSED else ":white_check_mark:"
    text = (
        f"{badge} *{verb}* by `{actor}` at `{acked_at_iso}` "
        f"(Obligation `{obligation_owner_id}`)"
    )
    return {
        "ok": True,
        "replace_original": True,
        "response_type": "in_channel",
        "notification_id": str(notification_id),
        "obligation_owner_id": str(obligation_owner_id),
        "ack_status": ack_status.value,
        "acked_by": actor,
        "acked_at": acked_at_iso,
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Notification ID: `{notification_id}` | "
                            f"Canonical Obligation: `{obligation_owner_id}` | "
                            f"Status: *{ack_status.value}*"
                        ),
                    }
                ],
            },
        ],
    }


@router.post("/slack")
async def slack_interactivity_webhook(http_request: Request) -> dict[str, Any]:
    """Handle signed Slack interactivity callbacks (Block Kit Acknowledge/Dismiss)."""
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    raw_body = await _read_bounded_body(http_request)
    verify_slack_signature(
        signing_secret=_slack_signing_secret(),
        timestamp_header=http_request.headers.get("X-Slack-Request-Timestamp"),
        signature_header=http_request.headers.get("X-Slack-Signature"),
        raw_body=raw_body,
        now=_current_timestamp(runtime),
    )

    payload = _parse_slack_payload(
        raw_body,
        http_request.headers.get("Content-Type", "application/json"),
    )
    payload_type = str(payload.get("type") or "").strip()

    if payload_type == "url_verification":
        return {"challenge": str(payload.get("challenge") or "")}

    if payload_type != "block_actions":
        return {"ok": True, "status": "ignored", "type": payload_type}

    raw_user = payload.get("user")
    user_info: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
    raw_team = payload.get("team")
    team_info: dict[str, Any] = raw_team if isinstance(raw_team, dict) else {}
    user_id = _sanitize_actor_component(user_info.get("id"), fallback="")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack block_actions payload is missing user.id",
        )
    team_id = _sanitize_actor_component(
        team_info.get("id") or user_info.get("team_id"),
        fallback="",
    )
    actor = f"slack:{team_id}:{user_id}" if team_id else f"slack:{user_id}"

    is_dismiss, notification_id, action_id = _extract_slack_action(payload)
    metadata: dict[str, Any] = {
        "source": "slack_webhook",
        "slack_action_id": action_id,
        "slack_user_id": user_id,
    }
    if team_id:
        metadata["slack_team_id"] = team_id
    username = user_info.get("username") or user_info.get("name")
    if isinstance(username, str) and username.strip():
        metadata["slack_username"] = username.strip()[:128]
    if str(notification_id):
        metadata["clicked_notification_id"] = str(notification_id)

    if runtime is not None:
        from uns.runtime import Conflict

        try:
            row = runtime.get(notification_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            ) from exc

        if row.get("obligation_resolution_status") == "UNRESOLVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Obligation lineage unresolved: {row.get('obligation_resolution_error')}",
            )

        owner_raw = row.get("obligation_owner_id")
        target_id = UUID(str(owner_raw)) if owner_raw else notification_id
        try:
            ack_resp = runtime.acknowledge(
                target_id,
                actor=actor,
                dismiss=is_dismiss,
                metadata=metadata,
            )
        except Conflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        await runtime.sync_pagerduty_incident(target_id, resolve=is_dismiss)
        return _build_slack_settled_blocks(
            notification_id=notification_id,
            obligation_owner_id=target_id,
            ack_status=ack_resp.ack_status,
            actor=ack_resp.acked_by or actor,
            acked_at_iso=ack_resp.acked_at.isoformat() if ack_resp.acked_at else "",
        )

    audit_store = getattr(http_request.app.state, "audit_store", None)
    try:
        if is_dismiss:
            ack_resp = await signaling_dismiss(
                notification_id=notification_id,
                dismissed_by=actor,
                metadata=metadata,
                audit_store=cast(AuditStore, audit_store),
            )
        else:
            ack_resp = await signaling_acknowledge(
                notification_id=notification_id,
                acked_by=actor,
                metadata=metadata,
                audit_store=cast(AuditStore, audit_store),
            )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        ) from exc
    except InvalidAckTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return _build_slack_settled_blocks(
        notification_id=notification_id,
        obligation_owner_id=notification_id,
        ack_status=ack_resp.ack_status,
        actor=ack_resp.acked_by or actor,
        acked_at_iso=ack_resp.acked_at.isoformat() if ack_resp.acked_at else "",
    )


@router.post("/pagerduty")
async def pagerduty_v3_webhook(http_request: Request) -> dict[str, Any]:
    """Handle signed PagerDuty v3 incident webhooks for bi-directional ACK/Resolve sync."""
    runtime = cast("Runtime | None", getattr(http_request.app.state, "runtime", None))
    raw_body = await _read_bounded_body(http_request)
    verify_pagerduty_signature(
        webhook_secret=_pagerduty_webhook_secret(),
        signature_header=http_request.headers.get("X-PagerDuty-Signature"),
        raw_body=raw_body,
    )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed PagerDuty webhook JSON payload",
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("event"), dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PagerDuty webhook payload must contain an 'event' object",
        )

    event_obj: dict[str, Any] = payload["event"]
    event_type = str(event_obj.get("event_type") or "").strip()
    if event_type not in {"incident.acknowledged", "incident.resolved"}:
        return {
            "status": "ignored",
            "event_type": event_type,
        }

    raw_agent = event_obj.get("agent")
    agent: dict[str, Any] = raw_agent if isinstance(raw_agent, dict) else {}
    agent_id = _sanitize_actor_component(agent.get("id"), fallback="webhook")
    actor = f"pagerduty:{agent_id}"

    raw_data = event_obj.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_custom_details = data.get("custom_details")
    custom_details: dict[str, Any] = (
        raw_custom_details if isinstance(raw_custom_details, dict) else {}
    )
    raw_notification_id = str(
        custom_details.get("notification_id") or data.get("notification_id") or ""
    ).strip()
    raw_dedup_key = str(
        data.get("dedup_key")
        or data.get("incident_key")
        or data.get("alert_key")
        or custom_details.get("dedup_key")
        or ""
    ).strip()

    if not raw_notification_id and not raw_dedup_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PagerDuty event data is missing dedup_key / incident_key / notification_id",
        )

    metadata: dict[str, Any] = {
        "source": "pagerduty_webhook",
        "pagerduty_event_type": event_type,
    }
    if event_obj.get("id"):
        metadata["pagerduty_event_id"] = str(event_obj["id"])[:128]
    if data.get("id"):
        metadata["pagerduty_incident_id"] = str(data["id"])[:128]
    if raw_dedup_key:
        metadata["pagerduty_dedup_key"] = raw_dedup_key[:128]
    agent_summary = agent.get("summary") or agent.get("name")
    if isinstance(agent_summary, str) and agent_summary.strip():
        metadata["pagerduty_agent_summary"] = agent_summary.strip()[:128]

    if runtime is not None:
        from uns.runtime import Conflict

        try:
            row = runtime.resolve_pagerduty_target(
                dedup_key=raw_dedup_key or None,
                notification_id=raw_notification_id or None,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Matching UNS notification not found for PagerDuty incident",
            ) from exc

        if row.get("obligation_resolution_status") == "UNRESOLVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Obligation lineage unresolved: {row.get('obligation_resolution_error')}",
            )

        owner_raw = row.get("obligation_owner_id")
        target_id = UUID(str(owner_raw)) if owner_raw else UUID(str(row["id"]))
        owner_row = runtime.get(target_id) if str(target_id) != str(row["id"]) else row

        # If the obligation was already ACKED (e.g., incident.acknowledged followed
        # by incident.resolved, or ACKed in UNS Console first), return 200 idempotently.
        if owner_row.get("ack_status") == AckStatus.ACKED.value:
            return {
                "status": "settled",
                "already_settled": True,
                "event_type": event_type,
                "notification_id": str(row["id"]),
                "obligation_owner_id": str(target_id),
                "ack_status": AckStatus.ACKED.value,
                "acked_by": owner_row.get("actor"),
            }

        try:
            ack_resp = runtime.acknowledge(
                target_id,
                actor=actor,
                dismiss=False,
                metadata=metadata,
            )
        except Conflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        return {
            "status": "settled",
            "already_settled": False,
            "event_type": event_type,
            "notification_id": str(row["id"]),
            "obligation_owner_id": str(target_id),
            "ack_status": ack_resp.ack_status.value,
            "acked_by": ack_resp.acked_by,
        }

    # Legacy fixture fallback
    candidate_uuid_str = raw_notification_id or (
        raw_dedup_key[4:] if raw_dedup_key.startswith("uns-") else raw_dedup_key
    )
    try:
        target_id = UUID(candidate_uuid_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching UNS notification not found for PagerDuty incident",
        ) from exc

    audit_store = getattr(http_request.app.state, "audit_store", None)
    try:
        ack_resp = await signaling_acknowledge(
            notification_id=target_id,
            acked_by=actor,
            metadata=metadata,
            audit_store=cast(AuditStore, audit_store),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching UNS notification not found for PagerDuty incident",
        ) from exc
    except InvalidAckTransitionError as exc:
        if exc.current_status == AckStatus.ACKED:
            return {
                "status": "settled",
                "already_settled": True,
                "event_type": event_type,
                "notification_id": str(target_id),
                "obligation_owner_id": str(target_id),
                "ack_status": AckStatus.ACKED.value,
            }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return {
        "status": "settled",
        "already_settled": False,
        "event_type": event_type,
        "notification_id": str(target_id),
        "obligation_owner_id": str(target_id),
        "ack_status": ack_resp.ack_status.value,
        "acked_by": ack_resp.acked_by,
    }


__all__ = [
    "router",
    "verify_pagerduty_signature",
    "verify_slack_signature",
]

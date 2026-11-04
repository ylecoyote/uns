"""Approval workflow bridge connecting ``REQUIRE_APPROVAL`` decisions to UNS obligations.

Implements ADR Approval Workflow Semantics:
- Correlates ``DecisionRecord`` instances with ``decision == REQUIRE_APPROVAL`` to
  durable ``uns.Runtime`` notification obligations (``decision_snapshot_id = decision_id``).
- Synchronizes terminal obligation responses into ``ApprovalStatus``:
  - ``ACKED`` -> ``APPROVED``
  - ``DISMISSED`` -> ``REJECTED``
  - ``TIMED_OUT`` -> ``TIMED_OUT`` (terminal timeout, distinct from explicit rejection)
- Signs outbound resume callback payloads with HMAC-SHA256
  (``X-UNS-Signature: sha256=<hex>`` and ``X-UNS-Timestamp: <unix_epoch>``)
  and provides constant-time ``verify_approval_callback()`` verification with
  configurable replay skew protection (default ±300 seconds).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from notification.models import AutonomyMode, NotificationIntent
from uns.governance.decision_record import Decision, DecisionRecord
from uns.governance.errors import GovernanceError
from uns.responses import SendNotificationRequest
from uns.runtime import digest, events, work

if TYPE_CHECKING:
    from uns.runtime import Runtime


class ApprovalConflictError(GovernanceError):
    """Raised when a decision_id is reused with different bound governance content."""


def _approval_bound_fingerprint(record: DecisionRecord) -> str:
    """Compute a canonical bound-content fingerprint for an approval decision."""
    matched_rule_ids = [
        r.rule_id for r in record.reasons if r.matched and r.then == record.decision
    ]
    matched_rule_id = (
        matched_rule_ids[0] if matched_rule_ids else getattr(record, "matched_rule_id", None)
    )
    return digest(
        {
            "tenant_id": record.tenant_id or "",
            "resource_type": record.resource_type or "",
            "resource_id": record.resource_id or "",
            "subject_id": record.subject_id or "",
            "policy_config_hash": record.policy_config_hash,
            "context_hash": record.context_hash,
            "matched_rule_id": matched_rule_id or "",
            "decision": (
                record.decision.value
                if isinstance(record.decision, Decision)
                else str(record.decision)
            ),
        }
    )


class ApprovalStatus(str, Enum):
    """Lifecycle states for a governance approval request."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    LOST_ON_RESTART = "LOST_ON_RESTART"


class ApprovalRequestRecord(BaseModel):
    """Durable/in-memory correlation record between a DecisionRecord and a UNS obligation."""

    model_config = ConfigDict(extra="forbid")

    approval_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    decision_id: uuid.UUID
    notification_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING_APPROVAL
    decision_record: DecisionRecord
    target_reviewer_role: str | None = None
    reason: str | None = None
    callback_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    callback_headers: dict[str, str] | None = None

    def canonical_callback_bytes(self) -> bytes:
        """Return canonical UTF-8 JSON bytes for callback signing (with ``callback_headers=None``)."""
        return self.model_copy(update={"callback_headers": None}).model_dump_json().encode("utf-8")

    @property
    def is_terminal(self) -> bool:
        """Return True if the approval request has reached a terminal decision state."""
        return self.status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.TIMED_OUT,
        )


def sign_approval_callback(
    payload_bytes: bytes,
    secret: str,
    *,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Generate ``X-UNS-Signature`` and ``X-UNS-Timestamp`` headers for a callback payload."""
    if not secret:
        raise GovernanceError("Callback signing secret must not be empty")
    ts = int(timestamp if timestamp is not None else time.time())
    signing_input = f"{ts}.".encode() + payload_bytes
    digest = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    return {
        "X-UNS-Signature": f"sha256={digest}",
        "X-UNS-Timestamp": str(ts),
    }


def verify_approval_callback(
    payload_bytes: bytes,
    headers: Mapping[str, str],
    secret: str,
    *,
    max_skew_seconds: int = 300,
    now_epoch: int | None = None,
) -> bool:
    """Verify ``X-UNS-Signature`` and ``X-UNS-Timestamp`` headers in constant time."""
    if not secret:
        return False

    lowered = {k.lower(): v for k, v in headers.items()}
    sig_header = lowered.get("x-uns-signature", "")
    ts_header = lowered.get("x-uns-timestamp", "")
    if not sig_header.startswith("sha256=") or not ts_header:
        return False

    try:
        ts_val = int(ts_header)
    except ValueError:
        return False

    now_val = int(now_epoch if now_epoch is not None else time.time())
    if abs(now_val - ts_val) > max_skew_seconds:
        return False

    expected = sign_approval_callback(payload_bytes, secret, timestamp=ts_val)["X-UNS-Signature"]
    if hmac.compare_digest(sig_header, expected):
        return True

    try:
        record = ApprovalRequestRecord.model_validate_json(payload_bytes)
    except Exception:
        return False
    canonical_expected = sign_approval_callback(
        record.canonical_callback_bytes(), secret, timestamp=ts_val
    )["X-UNS-Signature"]
    return hmac.compare_digest(sig_header, canonical_expected)


def _deterministic_agent_uuid(subject_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(subject_id)
    except ValueError:
        digest = hashlib.sha256(f"uns-gov-agent:{subject_id}".encode()).digest()[:16]
        return uuid.UUID(bytes=digest, version=4)


class GovernanceApprovalBridge:
    """Bridges ``REQUIRE_APPROVAL`` decisions to durable ``uns.Runtime`` obligations."""

    def __init__(
        self,
        runtime: Runtime | None = None,
        *,
        notification_type: str = "governance.approval_required",
        default_intent: NotificationIntent = NotificationIntent.SAFETY,
        signing_secret: str | None = None,
        principal: str = "uns-governance",
        on_settled: Callable[[ApprovalRequestRecord], Any] | None = None,
    ) -> None:
        self.runtime = runtime
        self.notification_type = notification_type
        self.default_intent = default_intent
        self.signing_secret = signing_secret
        self.principal = principal
        self.on_settled = on_settled
        self._by_decision_id: dict[uuid.UUID, ApprovalRequestRecord] = {}
        self._by_notification_id: dict[str, uuid.UUID] = {}
        self._callback_completed: set[str] = set()

    def request_approval(
        self,
        record: DecisionRecord,
        *,
        target_reviewer_role: str | None = None,
        reason: str | None = None,
        callback_url: str | None = None,
    ) -> ApprovalRequestRecord:
        """Create or return an idempotent approval request backed by a UNS notification obligation."""
        if record.decision != Decision.REQUIRE_APPROVAL:
            raise GovernanceError(
                f"request_approval requires Decision.REQUIRE_APPROVAL, got {record.decision.value}"
            )

        fingerprint = _approval_bound_fingerprint(record)
        existing = self._by_decision_id.get(record.decision_id)
        if existing is not None:
            if _approval_bound_fingerprint(existing.decision_record) != fingerprint:
                raise ApprovalConflictError(
                    f"Decision ID {record.decision_id} is already bound to a different approval context"
                )
            return existing
        recovered = self._recover_from_runtime(record.decision_id)
        if recovered is not None:
            if _approval_bound_fingerprint(recovered.decision_record) != fingerprint:
                raise ApprovalConflictError(
                    f"Decision ID {record.decision_id} is already bound to a different approval context"
                )
            return recovered

        approval_id = uuid.uuid4()
        created_at = datetime.now(UTC)
        notification_id: str | None = None
        if self.runtime is not None:
            agent_uuid = _deterministic_agent_uuid(record.subject_id)
            title = f"Approval required: {record.policy_id} (v{record.policy_version})"
            msg_parts = [
                f"Decision {record.decision_id} for subject '{record.subject_id}' requires approval."
            ]
            if reason:
                msg_parts.append(f"Reason: {reason}")
            if target_reviewer_role:
                msg_parts.append(f"Reviewer role: {target_reviewer_role}")

            req = SendNotificationRequest(
                notification_type=self.notification_type,
                intent=self.default_intent,
                title=title,
                message=" ".join(msg_parts),
                source="uns.governance",
                correlation_id=record.correlation_id or str(record.decision_id),
                idempotency_key=f"gov-approval:{record.decision_id}",
                dedup_key=f"gov-approval:{record.decision_id}:{fingerprint[:16]}",
                autonomy_context={
                    "agent_id": agent_uuid,
                    "autonomy_mode": AutonomyMode.LIVE,
                    "decision_snapshot_id": record.decision_id,
                },
                metadata={
                    "decision_id": str(record.decision_id),
                    "approval_fingerprint": fingerprint,
                    "policy_id": record.policy_id,
                    "policy_version": record.policy_version,
                    "policy_config_hash": record.policy_config_hash,
                    "context_hash": record.context_hash,
                    "target_reviewer_role": target_reviewer_role,
                    "uns_governance_approval": {
                        "approval_id": str(approval_id),
                        "decision_id": str(record.decision_id),
                        "approval_fingerprint": fingerprint,
                        "decision_record": record.model_dump(mode="json"),
                        "target_reviewer_role": target_reviewer_role,
                        "reason": reason,
                        "callback_url": callback_url,
                        "created_at": created_at.isoformat(),
                    },
                },
            )
            accepted = self.runtime.accept(req, principal=self.principal)
            notification_id = str(accepted.notification_id)

        approval = ApprovalRequestRecord(
            approval_id=approval_id,
            decision_id=record.decision_id,
            notification_id=notification_id,
            status=ApprovalStatus.PENDING_APPROVAL,
            decision_record=record,
            target_reviewer_role=target_reviewer_role,
            reason=reason,
            callback_url=callback_url,
            created_at=created_at,
        )
        self._by_decision_id[record.decision_id] = approval
        if notification_id is not None:
            self._by_notification_id[notification_id] = record.decision_id
        return approval

    def emit_operational_alert(
        self,
        record: DecisionRecord,
        *,
        fail_type: str,
        detail: str,
    ) -> str | None:
        """Emit a best-effort operational alert when an INFORMATIONAL policy fails open."""
        if self.runtime is None:
            return None
        with contextlib.suppress(Exception):
            agent_uuid = _deterministic_agent_uuid(record.subject_id)
            req = SendNotificationRequest(
                notification_type="governance.fail_open_alert",
                intent=NotificationIntent.OPERATIONAL,
                title=f"Governance fail-open alert: {record.policy_id}",
                message=f"Policy '{record.policy_id}' failed open ({fail_type}): {detail[:256]}",
                source="uns.governance",
                correlation_id=record.correlation_id or str(record.decision_id),
                idempotency_key=f"gov-fail-open:{record.decision_id}",
                dedup_key=f"gov-fail-open:{record.policy_id}:{fail_type}",
                autonomy_context={
                    "agent_id": agent_uuid,
                    "autonomy_mode": AutonomyMode.LIVE,
                    "decision_snapshot_id": record.decision_id,
                },
                metadata={
                    "decision_id": str(record.decision_id),
                    "policy_id": record.policy_id,
                    "fail_mode_type": fail_type,
                },
            )
            accepted = self.runtime.accept(req, principal=self.principal)
            return str(accepted.notification_id)
        return None

    def _recover_from_runtime(self, decision_id: uuid.UUID) -> ApprovalRequestRecord | None:
        """Recover a durable approval request from ``uns.Runtime`` across process restarts."""
        if self.runtime is None:
            return None
        key = digest([self.principal, "uns.governance", f"gov-approval:{decision_id}"])
        with contextlib.suppress(Exception), self.runtime.sessions() as session:
            row = session.execute(select(work).where(work.c.key == key)).mappings().first()
            if row is None:
                return None
            notif_payload: dict[str, Any] = (
                row["notification"] if isinstance(row["notification"], dict) else {}
            )
            raw_meta = notif_payload.get("metadata")
            meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
            raw_envelope = meta.get("uns_governance_approval")
            envelope: dict[str, Any] | None = (
                raw_envelope if isinstance(raw_envelope, dict) else None
            )
            if envelope is None:
                return None
            recovered_decision = DecisionRecord.model_validate(envelope["decision_record"])
            stored_fp = envelope.get("approval_fingerprint") or meta.get("approval_fingerprint")
            if isinstance(stored_fp, str) and stored_fp != _approval_bound_fingerprint(
                recovered_decision
            ):
                return None
            recovered = ApprovalRequestRecord(
                approval_id=uuid.UUID(str(envelope["approval_id"])),
                decision_id=uuid.UUID(str(envelope["decision_id"])),
                notification_id=str(row["id"]),
                status=ApprovalStatus.PENDING_APPROVAL,
                decision_record=recovered_decision,
                target_reviewer_role=envelope.get("target_reviewer_role"),
                reason=envelope.get("reason"),
                callback_url=envelope.get("callback_url"),
                created_at=datetime.fromisoformat(str(envelope["created_at"])),
            )
            cb_done = (
                session.execute(
                    select(events.c.id).where(
                        events.c.notification_id == str(row["id"]),
                        events.c.kind == "GOV_APPROVAL_CALLBACK_DELIVERED",
                    )
                )
                .scalars()
                .first()
            )
            if cb_done is not None:
                self._callback_completed.add(str(decision_id))
            self._by_decision_id[decision_id] = recovered
            self._by_notification_id[str(row["id"])] = decision_id
            return recovered
        return None

    def query_approval(self, decision_id: uuid.UUID) -> ApprovalRequestRecord | None:
        """Return the current approval state for ``decision_id``, syncing from Runtime if bound."""
        if (
            decision_id not in self._by_decision_id
            and self._recover_from_runtime(decision_id) is None
        ):
            return None
        return self.sync_from_runtime(decision_id)

    def sync_from_runtime(self, decision_id: uuid.UUID) -> ApprovalRequestRecord:
        """Synchronize approval state from the underlying ``uns.Runtime`` notification obligation."""
        approval = self._by_decision_id.get(decision_id) or self._recover_from_runtime(decision_id)
        if approval is None:
            raise GovernanceError(f"Unknown approval decision_id: {decision_id}")

        if (
            approval.status != ApprovalStatus.PENDING_APPROVAL
            or self.runtime is None
            or approval.notification_id is None
        ):
            if approval.is_terminal:
                self._deliver_settled_callback(approval)
            return approval

        with contextlib.suppress(Exception):
            self.runtime.expire()

        try:
            status_row = self.runtime.get(uuid.UUID(approval.notification_id))
        except KeyError:
            return approval

        ack_state = str(
            status_row.get("effective_ack_status") or status_row.get("ack_status") or "PENDING"
        ).upper()
        if ack_state == "ACKED":
            new_status = ApprovalStatus.APPROVED
        elif ack_state == "DISMISSED":
            new_status = ApprovalStatus.REJECTED
        elif ack_state == "TIMED_OUT":
            new_status = ApprovalStatus.TIMED_OUT
        else:
            return approval

        return self._finalize(
            approval,
            status=new_status,
            actor=status_row.get("actor"),
            resolved_at=datetime.now(UTC),
            note=(status_row.get("response_metadata") or {}).get("note")
            if isinstance(status_row.get("response_metadata"), dict)
            else None,
        )

    def resolve_approval(
        self,
        decision_id: uuid.UUID,
        *,
        status: ApprovalStatus,
        actor: str,
        note: str | None = None,
    ) -> ApprovalRequestRecord:
        """Explicitly settle an approval request and propagate to ``uns.Runtime`` when bound."""
        if status not in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.TIMED_OUT,
        ):
            raise GovernanceError(f"Invalid terminal approval status: {status}")

        approval = self._by_decision_id.get(decision_id) or self._recover_from_runtime(decision_id)
        if approval is None:
            raise GovernanceError(f"Unknown approval decision_id: {decision_id}")
        if approval.status != ApprovalStatus.PENDING_APPROVAL:
            if approval.is_terminal:
                self._deliver_settled_callback(approval)
            return approval

        if self.runtime is not None and approval.notification_id is not None:
            meta = {"note": note} if note else {}
            if status == ApprovalStatus.APPROVED:
                self.runtime.acknowledge(approval.notification_id, actor=actor, metadata=meta)
            elif status == ApprovalStatus.REJECTED:
                self.runtime.acknowledge(
                    approval.notification_id, actor=actor, dismiss=True, metadata=meta
                )
            elif status == ApprovalStatus.TIMED_OUT:
                with contextlib.suppress(Exception):
                    self.runtime.expire()

        return self._finalize(
            approval,
            status=status,
            actor=actor,
            resolved_at=datetime.now(UTC),
            note=note,
        )

    def _deliver_settled_callback(self, approval: ApprovalRequestRecord) -> None:
        key = str(approval.decision_id)
        if self.on_settled is None or key in self._callback_completed:
            return
        self.on_settled(approval)
        self._callback_completed.add(key)
        if self.runtime is not None and approval.notification_id is not None:
            with contextlib.suppress(Exception), self.runtime.sessions.begin() as session:
                self.runtime._event(
                    session,
                    str(approval.notification_id),
                    "GOV_APPROVAL_CALLBACK_DELIVERED",
                    {"decision_id": key, "approval_id": str(approval.approval_id)},
                )

    def _finalize(
        self,
        approval: ApprovalRequestRecord,
        *,
        status: ApprovalStatus,
        actor: str | None,
        resolved_at: datetime,
        note: str | None,
    ) -> ApprovalRequestRecord:
        updated = approval.model_copy(
            update={
                "status": status,
                "resolved_by": actor,
                "resolved_at": resolved_at,
                "resolution_note": note,
            }
        )
        if self.signing_secret:
            payload_bytes = updated.canonical_callback_bytes()
            headers = sign_approval_callback(payload_bytes, self.signing_secret)
            updated = updated.model_copy(update={"callback_headers": headers})

        self._by_decision_id[approval.decision_id] = updated
        if updated.notification_id is not None:
            self._by_notification_id[updated.notification_id] = approval.decision_id
        self._deliver_settled_callback(updated)
        return updated

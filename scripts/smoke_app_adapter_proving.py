"""Smoke test UNS's generic host-application adapter boundary.

The smoke proves that a host application can emit a governance signal through
UNS public imports without shipping application-specific integration code.

Usage:
    python scripts/smoke_app_adapter_proving.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
for import_path in (REPO_ROOT / "src", REPO_ROOT):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine  # noqa: E402
from notification.audit import (  # noqa: E402
    InMemoryAuditStore,
    PersistentAuditLogger,
    create_ack_audit_record,
)
from notification.models import AckStatus, Notification  # noqa: E402
from uns.integrations import (  # noqa: E402
    AppEvidenceContext,
    AppSignalAdapter,
    AppSignalRequest,
    DefaultAppSignalContextProvider,
)
from uns.models import (  # noqa: E402
    AutonomyMode,
    DeliveryStatus,
    NotificationResult,
    SignalIntent,
)
from uns.sdk import SignalClient  # noqa: E402


def build_proving_request(agent_id: UUID) -> AppSignalRequest:
    """Build a generic host-app signal request for the proving smoke."""
    return AppSignalRequest(
        notification_type="app.governor.circuit_breaker_engaged",
        intent=SignalIntent.SAFETY,
        title="Circuit breaker engaged",
        message="Host application reported a safety halt.",
        source="smoke:app-adapter-proving",
        evidence=AppEvidenceContext(
            plan_id=uuid4(),
            decision_snapshot_id=uuid4(),
            execution_snapshot_id=uuid4(),
            metadata={
                "host_event": "circuit_breaker_engaged",
                "agent_id": str(agent_id),
            },
        ),
    )


def run_smoke() -> dict[str, Any]:
    """Run the app adapter proving smoke and return a compact result."""
    agent_id = uuid4()
    request = build_proving_request(agent_id)
    audit_store = InMemoryAuditStore()
    audit_logger = PersistentAuditLogger(store=audit_store)
    ack_engine = configure_ack_engine(storage=InMemoryAckStorage())

    captured: dict[str, Notification] = {}

    def deliver(notification: Notification) -> NotificationResult:
        captured["notification"] = notification
        ack_engine.register_notification(
            notification_id=notification.notification_id,
            intent=notification.intent,
            autonomy_context=notification.autonomy_context,
            timeout_minutes=notification.ack_timeout_minutes,
            created_at=notification.created_at,
        )
        result = NotificationResult(
            notification_id=notification.notification_id,
            status=DeliveryStatus.SUCCESS,
            channels_attempted=notification.channels,
            channels_succeeded=notification.channels,
            channels_failed=[],
        )
        audit_logger.log_delivery(
            notification,
            result,
            metadata={"smoke": "app_adapter_proving"},
        )
        audit_store.save_ack_audit(
            create_ack_audit_record(
                notification_id=notification.notification_id,
                old_status=None,
                new_status=AckStatus.PENDING,
                metadata={"smoke": "app_adapter_proving"},
            )
        )
        return result

    adapter = AppSignalAdapter(
        sdk=SignalClient(delivery_handler=deliver),
        context_provider=DefaultAppSignalContextProvider(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        ),
    )
    result = adapter.send(request)
    notification = captured["notification"]
    app_evidence = notification.metadata.get("app_evidence")
    ack_status = ack_engine.get_status(result.notification_id)
    if ack_status is None:
        raise RuntimeError("Expected app adapter smoke to register ack state")
    evidence = request.evidence
    if evidence is None:
        raise RuntimeError("Expected app adapter smoke request to include evidence")

    return {
        "agent_id": str(agent_id),
        "notification_id": str(result.notification_id),
        "status": result.status.value,
        "ack_status": ack_status.value,
        "delivery_audits": len(audit_store.delivery_audits),
        "ack_audits": len(audit_store.ack_audits),
        "decision_snapshot_attached": (
            notification.autonomy_context.decision_snapshot_id == evidence.decision_snapshot_id
        ),
        "app_evidence_attached": isinstance(app_evidence, dict)
        and app_evidence.get("decision_snapshot_id")
        == str(evidence.decision_snapshot_id),
    }


def main() -> None:
    result = run_smoke()
    print("UNS app adapter proving smoke passed")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

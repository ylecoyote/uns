"""MIP-shaped adapter templates built on AGSignal's generic app boundary.

This module intentionally imports no MIP or ATP runtime code. It preserves the
MIP integration event shape while leaving all host-owned behavior in the host
application.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from notification.integrations.app_boundary import (
    AppEvidenceContext,
    AppSignalAdapter,
    AppSignalRequest,
)
from notification.models import AutonomyContext, AutonomyMode, NotificationIntent

SYSTEM_AGENT_ID = UUID("00000000-0000-0000-0000-000000000000")

MIPAlertSeverity = Literal["critical", "high", "medium", "low"]


class MIPExecutionAlert(BaseModel):
    """MIP-style execution alert input carried through AGSignal."""

    model_config = ConfigDict(frozen=True)

    severity: MIPAlertSeverity = "low"
    metric: str = Field(default="unknown", min_length=1)
    value: float | int | None = None
    threshold: float | int | None = None
    message: str = Field(default="Execution alert", min_length=1)
    strategy_name: str | None = None


class MIPExecutionSummary(BaseModel):
    """Optional MIP-style execution summary metadata."""

    model_config = ConfigDict(frozen=True)

    fills: int | None = None
    traded_notional: float | None = None
    avg_slippage_bps: float | None = None
    fill_rate: float | None = None
    error_rate: float | None = None


class _AppAdapter(Protocol):
    def send(self, request: AppSignalRequest) -> object: ...


def _severity_to_intent(severity: str, metric: str | None = None) -> NotificationIntent:
    severity = severity.lower()
    if severity == "critical":
        return NotificationIntent.SAFETY
    if severity == "high" and metric in {"error_rate", "kill_switch"}:
        return NotificationIntent.SAFETY
    if severity in {"high", "medium"}:
        return NotificationIntent.OPERATIONAL
    return NotificationIntent.INFORMATIONAL


def _metric_to_notification_type(severity: str, metric: str) -> str:
    base_types = {
        "avg_slippage": "execution.slippage",
        "strategy_slippage": "execution.slippage.strategy",
        "error_rate": "execution.error_rate",
        "fill_rate": "execution.fill_rate",
        "costs": "execution.costs",
        "kill_switch": "safety.kill_switch",
    }
    notification_type = base_types.get(metric, f"execution.{metric}")
    if severity.lower() == "critical":
        return f"{notification_type}.critical"
    return notification_type


def _context(
    *,
    agent_id: UUID,
    autonomy_mode: AutonomyMode | str = AutonomyMode.LIVE,
    plan_id: UUID | None = None,
    decision_snapshot_id: UUID | None = None,
    execution_snapshot_id: UUID | None = None,
    skip_snapshot_id: UUID | None = None,
) -> AutonomyContext:
    mode = autonomy_mode if isinstance(autonomy_mode, AutonomyMode) else AutonomyMode(autonomy_mode)
    return AutonomyContext(
        autonomy_mode=mode,
        agent_id=agent_id,
        plan_id=plan_id,
        decision_snapshot_id=decision_snapshot_id,
        execution_snapshot_id=execution_snapshot_id,
        skip_snapshot_id=skip_snapshot_id,
    )


def _evidence(
    *,
    plan_id: UUID | None = None,
    decision_snapshot_id: UUID | None = None,
    execution_snapshot_id: UUID | None = None,
    skip_snapshot_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AppEvidenceContext:
    return AppEvidenceContext(
        plan_id=plan_id,
        decision_snapshot_id=decision_snapshot_id,
        execution_snapshot_id=execution_snapshot_id,
        skip_snapshot_id=skip_snapshot_id,
        metadata=metadata or {},
    )


class MIPSignalAdapter:
    """MIP-shaped facade over AGSignal's generic app signal adapter."""

    def __init__(self, app_adapter: _AppAdapter | None = None) -> None:
        self._app_adapter = app_adapter or AppSignalAdapter()

    def approval_required(
        self,
        *,
        contract_id: UUID,
        capability: str,
        agent_id: UUID,
        autonomy_mode: AutonomyMode | str,
        plan_id: UUID | None = None,
        decision_snapshot_id: UUID | None = None,
        context_summary: str | None = None,
    ) -> object:
        message = f"Agent '{agent_id}' requests approval for {capability}."
        if context_summary:
            message = f"{message}\n\nContext: {context_summary}"

        return self._app_adapter.send(
            AppSignalRequest(
                notification_type="governance.approval_required",
                intent=NotificationIntent.GOVERNANCE,
                title=f"Approval Required: {capability}",
                message=message,
                source="agent_governor",
                autonomy_context=_context(
                    agent_id=agent_id,
                    autonomy_mode=autonomy_mode,
                    plan_id=plan_id,
                    decision_snapshot_id=decision_snapshot_id,
                ),
                evidence=_evidence(
                    plan_id=plan_id,
                    decision_snapshot_id=decision_snapshot_id,
                ),
                metadata={
                    "contract_id": str(contract_id),
                    "capability": capability,
                    "agent_id": str(agent_id),
                    "decision_snapshot_id": str(decision_snapshot_id)
                    if decision_snapshot_id
                    else None,
                },
                correlation_id=str(contract_id),
                require_ack_override=True,
            )
        )

    def contract_approved(
        self,
        *,
        contract_id: UUID,
        capability: str,
        agent_id: UUID,
        approved_by: str,
        autonomy_mode: AutonomyMode | str,
        plan_id: UUID | None = None,
    ) -> object:
        return self._app_adapter.send(
            AppSignalRequest(
                notification_type="governance.approved",
                intent=NotificationIntent.GOVERNANCE,
                title=f"Approved: {capability}",
                message=f"Contract for {capability} approved by {approved_by}.",
                source="agent_governor",
                autonomy_context=_context(
                    agent_id=agent_id,
                    autonomy_mode=autonomy_mode,
                    plan_id=plan_id,
                ),
                evidence=_evidence(plan_id=plan_id),
                metadata={
                    "contract_id": str(contract_id),
                    "capability": capability,
                    "agent_id": str(agent_id),
                    "approved_by": approved_by,
                },
                correlation_id=str(contract_id),
            )
        )

    def contract_rejected(
        self,
        *,
        contract_id: UUID,
        capability: str,
        agent_id: UUID,
        rejected_by: str,
        autonomy_mode: AutonomyMode | str,
        reason: str | None = None,
        plan_id: UUID | None = None,
    ) -> object:
        message = f"Contract for {capability} rejected by {rejected_by}."
        if reason:
            message = f"{message}\n\nReason: {reason}"

        return self._app_adapter.send(
            AppSignalRequest(
                notification_type="governance.rejected",
                intent=NotificationIntent.GOVERNANCE,
                title=f"Rejected: {capability}",
                message=message,
                source="agent_governor",
                autonomy_context=_context(
                    agent_id=agent_id,
                    autonomy_mode=autonomy_mode,
                    plan_id=plan_id,
                ),
                evidence=_evidence(plan_id=plan_id),
                metadata={
                    "contract_id": str(contract_id),
                    "capability": capability,
                    "agent_id": str(agent_id),
                    "rejected_by": rejected_by,
                    "reason": reason,
                },
                correlation_id=str(contract_id),
            )
        )

    def autonomy_changed(
        self,
        *,
        new_mode: AutonomyMode | str,
        previous_mode: AutonomyMode | str,
        triggered_by: str,
        agent_id: UUID,
    ) -> object:
        mode = new_mode if isinstance(new_mode, AutonomyMode) else AutonomyMode(new_mode)
        previous = (
            previous_mode.value
            if isinstance(previous_mode, AutonomyMode)
            else str(previous_mode)
        )
        is_live = mode == AutonomyMode.LIVE

        return self._app_adapter.send(
            AppSignalRequest(
                notification_type="governance.autonomy_change",
                intent=NotificationIntent.GOVERNANCE,
                title=f"Autonomy Mode: {previous} -> {mode.value}",
                message=(
                    f"Execution mode changed from {previous} to {mode.value} "
                    f"by {triggered_by}"
                ),
                source="agent_governor",
                autonomy_context=_context(agent_id=agent_id, autonomy_mode=mode),
                irreversible=is_live,
                require_ack_override=is_live,
                metadata={
                    "previous_mode": previous,
                    "new_mode": mode.value,
                    "triggered_by": triggered_by,
                    "agent_id": str(agent_id),
                },
            )
        )

    def circuit_breaker_engaged(
        self,
        *,
        breaker_type: str,
        agent_id: UUID,
        trigger_reason: str,
        metrics: dict[str, Any] | None = None,
        plan_id: UUID | None = None,
        autonomy_mode: AutonomyMode | str = AutonomyMode.LIVE,
    ) -> object:
        return self._app_adapter.send(
            AppSignalRequest(
                notification_type="safety.circuit_breaker_engaged",
                intent=NotificationIntent.SAFETY,
                title=f"Circuit Breaker Engaged: {breaker_type}",
                message=(
                    f"Circuit breaker '{breaker_type}' has been ENGAGED.\n"
                    f"Agent: {agent_id}\n"
                    f"Reason: {trigger_reason}\n\n"
                    "Trading activity is HALTED until recovery."
                ),
                source="circuit_breaker",
                autonomy_context=_context(
                    agent_id=agent_id,
                    autonomy_mode=autonomy_mode,
                    plan_id=plan_id,
                ),
                evidence=_evidence(plan_id=plan_id),
                irreversible=True,
                require_ack_override=True,
                metadata={
                    "breaker_type": breaker_type,
                    "agent_id": str(agent_id),
                    "trigger_reason": trigger_reason,
                    "metrics": metrics or {},
                    "plan_id": str(plan_id) if plan_id else None,
                    "event": "engaged",
                },
                dedup_key=f"circuit_breaker:{breaker_type}:{agent_id}:engaged",
            )
        )

    def circuit_breaker_recovered(
        self,
        *,
        breaker_type: str,
        agent_id: UUID,
        duration_seconds: int,
        resolved_by: str,
        plan_id: UUID | None = None,
        autonomy_mode: AutonomyMode | str = AutonomyMode.LIVE,
        recovery_reason: str | None = None,
    ) -> object:
        return self._app_adapter.send(
            AppSignalRequest(
                notification_type="safety.circuit_breaker_recovered",
                intent=NotificationIntent.SAFETY,
                title=f"Circuit Breaker Recovered: {breaker_type}",
                message=(
                    f"Circuit breaker '{breaker_type}' has RECOVERED.\n"
                    f"Agent: {agent_id}\n"
                    f"Duration: {duration_seconds}s\n"
                    f"Resolved by: {resolved_by}"
                ),
                source="circuit_breaker",
                autonomy_context=_context(
                    agent_id=agent_id,
                    autonomy_mode=autonomy_mode,
                    plan_id=plan_id,
                ),
                evidence=_evidence(plan_id=plan_id),
                metadata={
                    "breaker_type": breaker_type,
                    "agent_id": str(agent_id),
                    "duration_seconds": duration_seconds,
                    "resolved_by": resolved_by,
                    "recovery_reason": recovery_reason,
                    "plan_id": str(plan_id) if plan_id else None,
                    "event": "recovered",
                },
                dedup_key=f"circuit_breaker:{breaker_type}:{agent_id}:recovered",
            )
        )

    def execution_alert(
        self,
        alert: MIPExecutionAlert,
        *,
        summary: MIPExecutionSummary | None = None,
        autonomy_context: AutonomyContext | None = None,
        agent_id: UUID | None = None,
        execution_snapshot_id: UUID | None = None,
    ) -> object:
        resolved_context = autonomy_context or _context(
            agent_id=agent_id or SYSTEM_AGENT_ID,
            autonomy_mode=AutonomyMode.LIVE,
            execution_snapshot_id=execution_snapshot_id,
        )
        intent = _severity_to_intent(alert.severity, alert.metric)
        require_ack = (
            intent == NotificationIntent.SAFETY
            and resolved_context.autonomy_mode == AutonomyMode.LIVE
        )
        metadata: dict[str, Any] = {
            "severity": alert.severity,
            "metric": alert.metric,
            "value": alert.value,
            "threshold": alert.threshold,
            "date": str(date.today()),
        }
        if alert.strategy_name is not None:
            metadata["strategy_name"] = alert.strategy_name
        if summary is not None:
            metadata["summary"] = summary.model_dump(exclude_none=True)

        return self._app_adapter.send(
            AppSignalRequest(
                notification_type=_metric_to_notification_type(alert.severity, alert.metric),
                intent=intent,
                title=f"Execution Alert: {alert.metric.replace('_', ' ').title()}",
                message=alert.message,
                source="execution_alerts",
                autonomy_context=resolved_context,
                evidence=_evidence(execution_snapshot_id=execution_snapshot_id),
                metadata=metadata,
                require_ack_override=require_ack,
            )
        )


__all__ = [
    "MIPExecutionAlert",
    "MIPExecutionSummary",
    "MIPSignalAdapter",
    "SYSTEM_AGENT_ID",
]


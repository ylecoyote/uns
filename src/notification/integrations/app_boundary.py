"""Generic host-application integration boundary for AGSignal."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from notification.models import (
    AutonomyContext,
    AutonomyMode,
    DeliveryMode,
    NotificationIntent,
    NotificationResult,
    Priority,
)
from notification.sdk import NotificationSDK


class AppEvidenceContext(BaseModel):
    """Optional host-application evidence references carried by AGSignal."""

    model_config = ConfigDict(frozen=True)

    plan_id: UUID | None = Field(default=None, description="Optional host plan identifier")
    decision_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional host decision evidence identifier",
    )
    execution_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional host execution evidence identifier",
    )
    skip_snapshot_id: UUID | None = Field(
        default=None,
        description="Optional host skip/defer evidence identifier",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Host-owned evidence metadata copied into notification metadata",
    )

    def to_metadata(self) -> dict[str, Any]:
        """Return JSON-safe evidence metadata for Notification.metadata."""
        payload: dict[str, Any] = {}
        for field in (
            "plan_id",
            "decision_snapshot_id",
            "execution_snapshot_id",
            "skip_snapshot_id",
        ):
            value = getattr(self, field)
            if value is not None:
                payload[field] = str(value)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class AppSignalRequest(BaseModel):
    """Host-application request for sending an AGSignal signal."""

    model_config = ConfigDict(frozen=True)

    notification_type: str = Field(description="Namespaced signal type", min_length=1)
    intent: NotificationIntent = Field(description="AGSignal intent")
    title: str = Field(description="Signal title", min_length=1)
    message: str = Field(description="Signal body", min_length=1)
    source: str = Field(description="Host application producer identifier", min_length=1)
    autonomy_context: AutonomyContext | None = Field(
        default=None,
        description="Optional fully resolved AGSignal autonomy context",
    )
    evidence: AppEvidenceContext | None = Field(
        default=None,
        description="Optional host-owned evidence references",
    )
    irreversible: bool = Field(
        default=False,
        description="Whether this signal describes an irreversible action",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None)
    delivery_mode_override: DeliveryMode | None = Field(default=None)
    require_ack_override: bool | None = Field(default=None)
    priority_override: Priority | None = Field(default=None)
    dedup_key: str | None = Field(default=None)


@runtime_checkable
class AppSignalContextProvider(Protocol):
    """Protocol implemented by host applications that resolve AGSignal context."""

    def build_context(self, request: AppSignalRequest) -> AutonomyContext: ...


class DefaultAppSignalContextProvider:
    """Default context provider for apps with one current agent/mode."""

    def __init__(
        self,
        autonomy_mode: AutonomyMode = AutonomyMode.PREVIEW,
        agent_id: UUID | None = None,
    ) -> None:
        self._autonomy_mode = autonomy_mode
        self._agent_id = agent_id

    def build_context(self, request: AppSignalRequest) -> AutonomyContext:
        """Resolve an AGSignal AutonomyContext from request/default app state."""
        if request.autonomy_context is not None:
            return request.autonomy_context
        if self._agent_id is None:
            raise RuntimeError("No app agent_id configured")

        evidence = request.evidence
        return AutonomyContext(
            autonomy_mode=self._autonomy_mode,
            agent_id=self._agent_id,
            plan_id=evidence.plan_id if evidence is not None else None,
            decision_snapshot_id=evidence.decision_snapshot_id if evidence is not None else None,
            execution_snapshot_id=evidence.execution_snapshot_id if evidence is not None else None,
            skip_snapshot_id=evidence.skip_snapshot_id if evidence is not None else None,
        )


class AppSignalAdapter:
    """Thin host-application facade over NotificationSDK.

    This adapter owns no host domain behavior. It only translates the generic
    boundary request into an AGSignal SDK call.
    """

    def __init__(
        self,
        sdk: NotificationSDK | None = None,
        context_provider: AppSignalContextProvider | None = None,
    ) -> None:
        self._sdk = sdk or NotificationSDK()
        self._context_provider = context_provider or DefaultAppSignalContextProvider()

    def send(self, request: AppSignalRequest) -> NotificationResult:
        """Send a host-application signal through the AGSignal SDK."""
        context = self._context_provider.build_context(request)
        metadata = dict(request.metadata)
        if request.evidence is not None:
            metadata["app_evidence"] = request.evidence.to_metadata()

        return self._sdk.send(
            notification_type=request.notification_type,
            intent=request.intent,
            title=request.title,
            message=request.message,
            source=request.source,
            autonomy_context=context,
            irreversible=request.irreversible,
            metadata=metadata,
            correlation_id=request.correlation_id,
            delivery_mode_override=request.delivery_mode_override,
            require_ack_override=request.require_ack_override,
            priority_override=request.priority_override,
            dedup_key=request.dedup_key,
        )

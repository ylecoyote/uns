"""UNS public API.

The implementation lives across ``uns.signaling`` (write), ``uns.queries``
(read), ``uns.sdk`` / ``uns.client`` (high-level clients), ``uns.runtime``
(durable SQLite/SQLAlchemy runtime), and ``uns.policies`` / ``uns.models`` /
``uns.interfaces``. Domain types under ``notification.*`` are re-exported
here so SDK consumers and operators can import directly from ``uns.*``.

Service-layer write functions (``send_signal``, ``simulate_signal``,
``acknowledge``, ``dismiss``) are exported at top level alongside ``Client``
and ``SignalClient``. Service-layer read functions (``get_invariants_summary``,
``list_deliveries``, etc.) remain scoped to ``uns.queries.X`` by design.
"""

from typing import Any

__version__ = "0.2.0"

from notification.acknowledgment import (
    AcknowledgmentEngine,
    AckState,
    AckStorageProtocol,
    EscalationHandler,
    InMemoryAckStorage,
    LoggingEscalationHandler,
)
from notification.audit import (
    AckAuditRecord,
    AuditPersistenceError,
    AuditRecord,
    AuditStore,
    FileAuditStore,
    InMemoryAuditStore,
    PersistentAcknowledgmentAuditCallback,
    PersistentAuditLogger,
    configure_audit_logger,
    create_ack_audit_record,
    create_audit_record,
    get_audit_logger,
)
from notification.models import (
    get_default_ack_timeout_minutes,
    get_default_delivery_mode,
    get_default_priority,
    get_default_require_ack,
)
from notification.policies import (
    get_default_registry,
    set_default_registry,
)
from notification.policy_config import (
    PolicyConfigEnvelope,
    PolicyEvaluationRecord,
    apply_policy_delta,
    canonical_config_json,
    compute_config_hash,
)
from notification.policy_learning import (
    DeltaRejectionReason,
    DeltaState,
    FieldBound,
    GuardResult,
    GuardStage,
    PolicyDelta,
    PolicyDeltaTransition,
    ShadowEvaluationAggregate,
    ShadowEvaluationResult,
    ShadowStatus,
)
from notification.sdk import (
    NotificationSDK,
    ValidationError,
    configure_sdk,
    create_sdk,
    get_sdk,
)
from uns import signaling  # noqa: F401 - submodule access
from uns.interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
    SignalContextProvider,
)
from uns.models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    GovernanceSignal,
    Notification,
    NotificationIntent,
    NotificationResult,
    Priority,
    SignalIntent,
)
from uns.policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    SignalPolicy,
    configure_policy_registry,
    get_default_ack_timeout,
    get_default_channels,
    get_policy_registry,
    resolve_channels,
    resolve_delivery_mode,
    resolve_require_ack,
)
from uns.sdk import (
    SignalClient,
    configure_signal_client,
    create_signal_client,
    get_signal_client,
)
from uns.signaling import (
    acknowledge,
    dismiss,
    send_signal,
    simulate_signal,
)

__all__ = [
    "AckAuditRecord",
    "AckEvent",
    "AckState",
    "AckStatus",
    "AckStorageProtocol",
    "AcknowledgmentCallback",
    "AcknowledgmentEngine",
    "AuditPersistenceError",
    "AuditRecord",
    "AuditStore",
    "AutonomyContext",
    "AutonomyMode",
    "Channel",
    "Client",
    "CompositeAcknowledgmentCallback",
    "DefaultContextProvider",
    "DeliveryMode",
    "DeliveryStatus",
    "DeltaRejectionReason",
    "DeltaState",
    "EscalationHandler",
    "FieldBound",
    "FileAuditStore",
    "GovernanceSignal",
    "GuardResult",
    "GuardStage",
    "InMemoryAckStorage",
    "InMemoryAuditStore",
    "LoggingAcknowledgmentCallback",
    "LoggingEscalationHandler",
    "ModeOverride",
    "NoOpAcknowledgmentCallback",
    "Notification",
    "NotificationContextProvider",
    "NotificationIntent",
    "NotificationPolicy",
    "NotificationResult",
    "NotificationSDK",
    "PersistentAcknowledgmentAuditCallback",
    "PersistentAuditLogger",
    "PolicyConfigEnvelope",
    "PolicyDelta",
    "PolicyDeltaTransition",
    "PolicyEvaluationRecord",
    "PolicyRegistry",
    "Priority",
    "Runtime",
    "ShadowEvaluationAggregate",
    "ShadowEvaluationResult",
    "ShadowStatus",
    "SignalClient",
    "SignalContextProvider",
    "SignalIntent",
    "SignalPolicy",
    "ValidationError",
    "__version__",
    "acknowledge",
    "apply_policy_delta",
    "canonical_config_json",
    "compute_config_hash",
    "configure_audit_logger",
    "configure_policy_registry",
    "configure_sdk",
    "configure_signal_client",
    "create_ack_audit_record",
    "create_audit_record",
    "create_sdk",
    "create_signal_client",
    "dismiss",
    "get_audit_logger",
    "get_default_ack_timeout",
    "get_default_ack_timeout_minutes",
    "get_default_channels",
    "get_default_delivery_mode",
    "get_default_priority",
    "get_default_registry",
    "get_default_require_ack",
    "get_policy_registry",
    "get_sdk",
    "get_signal_client",
    "resolve_channels",
    "resolve_delivery_mode",
    "resolve_require_ack",
    "send_signal",
    "set_default_registry",
    "simulate_signal",
]


def __getattr__(name: str) -> Any:
    """Load optional runtime/HTTP/read-model dependencies lazily."""
    if name == "Client":
        from uns.client import Client

        return Client
    if name == "Runtime":
        from uns.runtime import Runtime

        return Runtime
    if name == "queries":
        from importlib import import_module

        module = import_module("uns.queries")
        globals()[name] = module
        return module
    raise AttributeError(name)

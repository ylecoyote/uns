"""AGSignal public API.

The implementation lives across ``agsignal.signaling`` (write),
``agsignal.queries`` (read), ``agsignal.sdk`` (high-level client), and
``agsignal.policies`` / ``agsignal.models`` / ``agsignal.interfaces``. Some
domain types still live under ``notification.*``; those are re-exported
here so SDK consumers and operators can import exclusively from
``agsignal.*``.

This module re-exports the symbols intended for direct ``from agsignal
import …`` consumption. Service-layer write functions (``send_signal``,
``simulate_signal``, ``acknowledge``, ``dismiss``) are exported because
they parallel the ``SignalClient`` SDK affordance — callers reach for the
canonical implementation without dropping into ``agsignal.signaling.X``.
Service-layer read functions (``get_invariants_summary``, ``list_deliveries``,
etc.) are NOT exported at the top level — reach for them as
``agsignal.queries.X``. The console/operational nature of read access is
intentional in the import path.
"""

# Re-exports forwarded through the agsignal-branded shim modules.
from agsignal import (
    queries,  # noqa: F401  (sub-module access via agsignal.queries.foo)
    signaling,  # noqa: F401  (sub-module access via agsignal.signaling.foo)
)
from agsignal.interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
    SignalContextProvider,
)
from agsignal.models import (
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
from agsignal.policies import (
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
from agsignal.sdk import (
    SignalClient,
    configure_signal_client,
    create_signal_client,
    get_signal_client,
)

# Service-layer write functions (canonical implementations behind the SDK).
# Read functions stay scoped to agsignal.queries by design — see module
# docstring for the rationale.
from agsignal.signaling import (
    acknowledge,
    dismiss,
    send_signal,
    simulate_signal,
)

# Direct re-exports from notification.* (no agsignal-side shim yet).
# Move imports up into the shim block as new agsignal/<module>.py files land.
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
    "ShadowEvaluationAggregate",
    "ShadowEvaluationResult",
    "ShadowStatus",
    "SignalClient",
    "SignalContextProvider",
    "SignalIntent",
    "SignalPolicy",
    "ValidationError",
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

"""
Unified Notification Service (UNS) - Core Package

A control-plane notification and acknowledgment service that:
- MUST NOT block execution loops
- MUST NOT participate in order routing or trade timing

This package provides the core notification infrastructure including:
- Models and data contracts
- Delivery adapters (Slack, Email, WebSocket, PagerDuty)
- Policy registry and routing rules
- Deduplication and rate limiting
- Acknowledgment handling
- SDK for notification sending
- Audit logging and persistence
"""

__version__ = "0.1.0"

from .acknowledgment import (
    AcknowledgmentEngine,
    AckState,
    AckStorageProtocol,
    EscalationHandler,
    InMemoryAckStorage,
    LoggingEscalationHandler,
)
from .audit import (
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
from .interfaces import (
    AcknowledgmentCallback,
    CompositeAcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
    NotificationContextProvider,
)
from .models import (
    AckEvent,
    AckStatus,
    AutonomyContext,
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    Notification,
    NotificationIntent,
    NotificationResult,
    Priority,
    get_default_ack_timeout_minutes,
    get_default_delivery_mode,
    get_default_priority,
    get_default_require_ack,
)
from .policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
    get_default_ack_timeout,
    get_default_channels,
    get_default_registry,
    get_policy_registry,
    resolve_channels,
    resolve_delivery_mode,
    resolve_require_ack,
    set_default_registry,
)
from .policy_config import (
    PolicyConfigEnvelope,
    PolicyEvaluationRecord,
    apply_policy_delta,
    canonical_config_json,
    compute_config_hash,
)
from .policy_learning import (
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
from .sdk import (
    NotificationSDK,
    ValidationError,
    configure_sdk,
    create_sdk,
    get_sdk,
)

__all__ = [
    # Enums
    "NotificationIntent",
    "DeliveryMode",
    "AutonomyMode",
    "AckStatus",
    "Channel",
    "Priority",
    "DeliveryStatus",
    # Models
    "AutonomyContext",
    "Notification",
    "NotificationResult",
    "AckEvent",
    # Interfaces (Protocols)
    "NotificationContextProvider",
    "AcknowledgmentCallback",
    "AckStorageProtocol",
    "EscalationHandler",
    # Default Implementations
    "DefaultContextProvider",
    "NoOpAcknowledgmentCallback",
    "LoggingAcknowledgmentCallback",
    "CompositeAcknowledgmentCallback",
    # Acknowledgment Engine
    "AcknowledgmentEngine",
    "AckState",
    "InMemoryAckStorage",
    "LoggingEscalationHandler",
    # Helper functions from models
    "get_default_delivery_mode",
    "get_default_priority",
    "get_default_ack_timeout_minutes",
    "get_default_require_ack",
    # Policies
    "ModeOverride",
    "NotificationPolicy",
    "PolicyRegistry",
    "get_policy_registry",
    "configure_policy_registry",
    "get_default_registry",
    "set_default_registry",
    "get_default_channels",
    "get_default_ack_timeout",
    "resolve_channels",
    "resolve_require_ack",
    "resolve_delivery_mode",
    # Policy learning
    "DeltaRejectionReason",
    "DeltaState",
    "FieldBound",
    "GuardStage",
    "GuardResult",
    "PolicyDelta",
    "PolicyDeltaTransition",
    "ShadowEvaluationAggregate",
    "ShadowEvaluationResult",
    "ShadowStatus",
    "PolicyConfigEnvelope",
    "PolicyEvaluationRecord",
    "apply_policy_delta",
    "canonical_config_json",
    "compute_config_hash",
    # SDK
    "NotificationSDK",
    "ValidationError",
    "create_sdk",
    "get_sdk",
    "configure_sdk",
    # Audit
    "AckAuditRecord",
    "AuditPersistenceError",
    "AuditRecord",
    "AuditStore",
    "FileAuditStore",
    "InMemoryAuditStore",
    "PersistentAuditLogger",
    "PersistentAcknowledgmentAuditCallback",
    "configure_audit_logger",
    "create_ack_audit_record",
    "create_audit_record",
    "get_audit_logger",
]

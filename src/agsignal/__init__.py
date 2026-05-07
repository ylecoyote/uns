"""AGSignal public API aliases.

The implementation currently lives in the historical ``notification`` package.
These aliases provide AGSignal-branded imports without breaking existing users.
"""

from agsignal.interfaces import (
    AcknowledgmentCallback,
    DefaultContextProvider,
    LoggingAcknowledgmentCallback,
    NoOpAcknowledgmentCallback,
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
    Priority,
    SignalIntent,
)
from agsignal.policies import (
    ModeOverride,
    PolicyRegistry,
    SignalPolicy,
    configure_policy_registry,
    get_policy_registry,
)
from agsignal.sdk import (
    SignalClient,
    configure_signal_client,
    create_signal_client,
    get_signal_client,
)

__all__ = [
    "AcknowledgmentCallback",
    "AckEvent",
    "AckStatus",
    "AutonomyContext",
    "AutonomyMode",
    "Channel",
    "DefaultContextProvider",
    "DeliveryMode",
    "DeliveryStatus",
    "GovernanceSignal",
    "LoggingAcknowledgmentCallback",
    "ModeOverride",
    "NoOpAcknowledgmentCallback",
    "PolicyRegistry",
    "Priority",
    "SignalContextProvider",
    "SignalClient",
    "SignalIntent",
    "SignalPolicy",
    "configure_signal_client",
    "configure_policy_registry",
    "create_signal_client",
    "get_policy_registry",
    "get_signal_client",
]

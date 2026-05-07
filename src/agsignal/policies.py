"""AGSignal-branded policy aliases."""

from notification.policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    PolicyStatus,
    configure_policy_registry,
    get_default_ack_timeout,
    get_default_channels,
    get_policy_registry,
    resolve_channels,
    resolve_delivery_mode,
    resolve_require_ack,
)

SignalPolicy = NotificationPolicy

__all__ = [
    "ModeOverride",
    "NotificationPolicy",
    "PolicyRegistry",
    "PolicyStatus",
    "SignalPolicy",
    "configure_policy_registry",
    "get_default_ack_timeout",
    "get_default_channels",
    "get_policy_registry",
    "resolve_channels",
    "resolve_delivery_mode",
    "resolve_require_ack",
]

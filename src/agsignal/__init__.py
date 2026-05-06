"""AGSignal public API aliases.

The implementation currently lives in the historical ``notification`` package.
These aliases provide AGSignal-branded imports without breaking existing users.
"""

from agsignal.models import GovernanceSignal, SignalIntent
from agsignal.sdk import (
    SignalClient,
    configure_signal_client,
    create_signal_client,
    get_signal_client,
)

__all__ = [
    "GovernanceSignal",
    "SignalClient",
    "SignalIntent",
    "configure_signal_client",
    "create_signal_client",
    "get_signal_client",
]

"""Integrations interfaces and implementations for UNS.

This module provides protocols for external system integration,
allowing UNS to remain ATP-agnostic through dependency injection interfaces.

Contains integration points for external systems and contexts.
This package enables UNS core to remain ATP-agnostic through
dependency injection interfaces.
"""

from notification.integrations.app_boundary import (
    AppEvidenceContext,
    AppSignalAdapter,
    AppSignalContextProvider,
    AppSignalRequest,
    DefaultAppSignalContextProvider,
)
from notification.integrations.mip_adapter import (
    MIPExecutionAlert,
    MIPExecutionSummary,
    MIPSignalAdapter,
)

__all__ = [
    "AppEvidenceContext",
    "AppSignalAdapter",
    "AppSignalContextProvider",
    "AppSignalRequest",
    "DefaultAppSignalContextProvider",
    "MIPExecutionAlert",
    "MIPExecutionSummary",
    "MIPSignalAdapter",
]

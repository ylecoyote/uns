"""Canonical async client sharing the transport application service."""

from __future__ import annotations

from uns.responses import (
    SendNotificationRequest,
    SendNotificationResponse,
    SimulateNotificationResponse,
)
from uns.runtime import Runtime
from uns.signaling import simulate_signal


class Client:
    def __init__(self, runtime: Runtime, *, principal: str) -> None:
        self.runtime = runtime
        self.principal = principal

    async def send(self, request: SendNotificationRequest) -> SendNotificationResponse:
        return await self.runtime.send(request, principal=self.principal)

    async def simulate(self, request: SendNotificationRequest) -> SimulateNotificationResponse:
        return await simulate_signal(
            request=request, policy_runtime=self.runtime.policy_runtime, principal=self.principal
        )

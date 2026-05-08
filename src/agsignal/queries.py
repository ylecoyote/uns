"""AGSignal read-side service layer.

Stateless async query functions that read state from the configured stores
and return typed Pydantic responses. No FastAPI imports — these functions
can be called from any caller (HTTP route handlers, MCP tools, future CLI).
Routes become thin adapters that parse `Request`, delegate here, and return
the response.

Each function in this module is the canonical implementation of its
operation. `mcp_server.routes_ui` and `agsignal_mcp.tools` both call into
these — there is no other source of truth.
"""

from __future__ import annotations

from datetime import datetime

# NOTE: response models (`InvariantSummaryResponse`) and the supporting
# `EnforcementType` enum currently live in `mcp_server.routes_ui` alongside
# the legacy route handlers. Phase 5 of the v0.2 refactor relocates them to
# a dedicated module (likely `mcp_server.read_models` or a new
# `agsignal.responses` module). Until then we import from their current home.
from mcp_server.routes_ui import (  # legacy location; Phase 5 relocates
    EnforcementType,
    InvariantSummaryResponse,
    list_invariants,
)


async def get_invariants_summary() -> InvariantSummaryResponse:
    """Return summary statistics for system invariants.

    Canonical implementation: HTTP routes and MCP tools both delegate here.
    """
    # Body extracted verbatim from mcp_server.routes_ui.get_invariants_summary
    # (minus the @router.get decorator and the log_endpoint_call observability
    # call, which is a route-handler concern).
    #
    # Note: this currently calls back into `mcp_server.routes_ui.list_invariants`.
    # Task 2 of Phase 2 migrates `list_invariants` into this module, at which
    # point this call site naturally becomes an in-module call.
    result = await list_invariants(limit=100)

    by_severity: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_enforcement: dict[str, int] = {"guard": 0, "isolation": 0, "test": 0, "exception": 0}
    by_status: dict[str, int] = {"active": 0, "inactive": 0}
    exceptions_count = 0

    for item in result.items:
        by_severity[item.severity.value] = by_severity.get(item.severity.value, 0) + 1
        by_enforcement[item.enforcement.type.value] = (
            by_enforcement.get(item.enforcement.type.value, 0) + 1
        )
        by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
        if item.enforcement.type == EnforcementType.EXCEPTION:
            exceptions_count += 1

    return InvariantSummaryResponse(
        total_count=len(result.items),
        by_severity=by_severity,
        by_enforcement_type=by_enforcement,
        by_status=by_status,
        exceptions_requiring_review=exceptions_count,
        last_updated=datetime.now().isoformat(),
    )

"""Unit tests for the agsignal.queries service layer."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_get_invariants_summary_returns_invariant_response_shape() -> None:
    """The query function returns the same response shape as the legacy route handler."""
    from agsignal.queries import get_invariants_summary

    result = await get_invariants_summary()

    # Mirror the assertions of the existing route smoke test for parity.
    # See tests/mcp_server/test_routes_ui_smoke_critical.py::test_smoke_invariants_summary_endpoint
    # and tests/ui_contract/test_ui_contracts.py::TestInvariantsSummaryContract.
    assert hasattr(result, "total_count")
    assert hasattr(result, "by_status")
    assert hasattr(result, "by_severity")
    assert hasattr(result, "by_enforcement_type")
    assert hasattr(result, "exceptions_requiring_review")
    assert hasattr(result, "last_updated")
    assert isinstance(result.total_count, int)
    assert isinstance(result.by_severity, dict)
    assert isinstance(result.by_enforcement_type, dict)
    assert isinstance(result.by_status, dict)
    # by_severity should include all severity levels
    for severity in ("HIGH", "MEDIUM", "LOW"):
        assert severity in result.by_severity
    # by_enforcement_type should include all enforcement types
    for etype in ("guard", "isolation", "test", "exception"):
        assert etype in result.by_enforcement_type
    # by_status should include all status values
    for status_value in ("active", "inactive"):
        assert status_value in result.by_status

    # Aggregation logic check: each invariant has exactly one severity, one
    # enforcement type, and one status, so the sum across each dict equals
    # total_count. Catches branch-skip / off-by-one regressions in the
    # aggregation loop that a pure shape check would miss.
    assert sum(result.by_severity.values()) == result.total_count
    assert sum(result.by_enforcement_type.values()) == result.total_count
    assert sum(result.by_status.values()) == result.total_count

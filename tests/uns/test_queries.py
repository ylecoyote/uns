"""Unit tests for the uns.queries service layer."""

from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_get_invariants_summary_returns_invariant_response_shape() -> None:
    """The query function returns the same response shape as the legacy route handler."""
    from uns.queries import get_invariants_summary

    result = await get_invariants_summary()

    # Mirror the assertions of the existing route smoke test for parity.
    # See tests/uns/api/test_routes_ui_smoke_critical.py::test_smoke_invariants_summary_endpoint
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


@pytest.mark.asyncio
async def test_list_deliveries_returns_paginated_response_shape() -> None:
    """The list_deliveries query returns a paginated response with items."""
    from uns.queries import list_deliveries

    result = await list_deliveries(limit=25)

    # Shape: response is a DeliveryTimelineListResponse with items + pagination
    assert hasattr(result, "items")
    assert hasattr(result, "pagination")
    assert isinstance(result.items, list)
    assert hasattr(result.pagination, "next_cursor")
    assert hasattr(result.pagination, "has_more")
    # items count should never exceed limit
    assert len(result.items) <= 25


@pytest.mark.asyncio
async def test_get_delivery_timeline_raises_not_found_for_unknown_id() -> None:
    """get_delivery_timeline raises typed NotFoundError for missing notifications.

    Phase 3 Task 2: the service layer no longer raises ``HTTPException``;
    it raises :class:`uns.errors.NotFoundError` and the route adapter
    translates that to HTTP 404.
    """
    from uns.errors import NotFoundError
    from uns.queries import get_delivery_timeline

    missing_id = uuid4()
    with pytest.raises(NotFoundError) as exc_info:
        await get_delivery_timeline(notification_id=missing_id)
    assert exc_info.value.resource == "delivery_timeline"
    assert exc_info.value.identifier == str(missing_id)


@pytest.mark.asyncio
async def test_get_effective_policy_returns_resolution_response_shape() -> None:
    """get_effective_policy returns an EffectivePolicyResponse with resolution data."""
    from notification.models import AutonomyMode, NotificationIntent
    from uns.queries import get_effective_policy

    result = await get_effective_policy(
        notification_type="test.invariant",
        intent=NotificationIntent.OPERATIONAL,
        autonomy_mode=AutonomyMode.LIVE,
        irreversible=False,
    )

    # Shape assertions
    assert hasattr(result, "notification_type")
    assert hasattr(result, "effective")
    assert hasattr(result, "resolution")
    assert hasattr(result, "resolution_context")
    # Required behavioral invariant: resolution dict has all 5 keys
    expected_keys = {
        "delivery_mode",
        "channels",
        "require_ack",
        "ack_timeout_minutes",
        "dedup_window_seconds",
    }
    assert set(result.resolution.keys()) == expected_keys
    # Each resolution chain must have at least one step
    for steps in result.resolution.values():
        assert len(steps) >= 1
    assert result.notification_type == "test.invariant"


@pytest.mark.asyncio
async def test_list_invariants_returns_paginated_response_shape() -> None:
    """list_invariants returns paginated response with items respecting limit."""
    from uns.queries import list_invariants

    result = await list_invariants(limit=10)

    # Shape: items + pagination
    assert hasattr(result, "items")
    assert hasattr(result, "pagination")
    assert isinstance(result.items, list)
    # Behavioral invariant: items count never exceeds limit
    assert len(result.items) <= 10
    # Each item should have the documented invariant fields
    for item in result.items:
        assert hasattr(item, "id")
        assert hasattr(item, "statement")
        assert hasattr(item, "severity")
        assert hasattr(item, "status")
        assert hasattr(item, "enforcement")


@pytest.mark.asyncio
async def test_list_audit_events_returns_paginated_response_shape() -> None:
    """list_audit_events returns paginated response respecting limit."""
    from uns.queries import list_audit_events

    result = await list_audit_events(limit=25)

    # Shape: items + pagination
    assert hasattr(result, "items")
    assert hasattr(result, "pagination")
    assert isinstance(result.items, list)
    assert hasattr(result.pagination, "next_cursor")
    assert hasattr(result.pagination, "has_more")
    # Behavioral invariant: count consistent with limit
    assert len(result.items) <= 25


@pytest.mark.asyncio
async def test_get_notification_status_for_unknown_returns_not_found() -> None:
    """get_notification_status returns found=False for unknown notification IDs."""
    from uns.queries import get_notification_status

    missing_id = uuid4()
    result = await get_notification_status(notification_id=missing_id)

    # Shape assertions: required fields populated
    assert hasattr(result, "notification_id")
    assert hasattr(result, "found")
    assert hasattr(result, "ack_status")
    assert result.notification_id == missing_id
    # Behavioral invariant: an unknown notification surfaces found=False
    assert result.found is False
    assert result.ack_status is None


@pytest.mark.asyncio
async def test_get_ack_status_for_unknown_returns_null_status() -> None:
    """get_ack_status returns null ack_status for unknown notifications."""
    from uns.queries import get_ack_status

    missing_id = uuid4()
    result = await get_ack_status(notification_id=missing_id)

    # Shape assertions: required fields populated
    assert hasattr(result, "notification_id")
    assert hasattr(result, "ack_status")
    assert result.notification_id == missing_id
    # Behavioral invariant: untracked notification has null ack_status
    assert result.ack_status is None

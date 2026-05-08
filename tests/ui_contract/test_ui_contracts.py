"""Contract drift tests for /ui endpoints.

These tests validate the shape of /ui endpoint responses to detect
breaking changes before they affect the UI. Tests are independent
of the UI codebase and use only backend models/schemas.

Requirements from uns-ui-phase-1_2-guardrails-ci-contracts.yaml:
- Validate response shapes for all /ui endpoints
- Include degraded-state test for invariants_source_unavailable
- Tests must NOT rely on UI codebase
- Tests use backend models/schemas only
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agsignal.app import create_app
from agsignal.responses import (
    AuditEvent,
    AuditEventType,
    AutonomyContextResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    EnforcementType,
    ErrorDetail,
    EvidenceLink,
    InvariantEnforcement,
    InvariantEntry,
    InvariantSeverity,
    InvariantStatus,
    PaginationInfo,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)
from agsignal.responses import (
    UIErrorResponse as ErrorResponse,
)
from mcp_server.read_models import (
    InMemoryReadModelAdapter,
    configure_read_model_adapter,
)
from notification.audit import InMemoryAuditStore
from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create a test client with fresh read model adapter."""
    fresh_store = InMemoryAuditStore()
    fresh_adapter = InMemoryReadModelAdapter(audit_store=fresh_store)
    configure_read_model_adapter(fresh_adapter)

    app = create_app()
    return TestClient(app)


@pytest.fixture
def populated_client() -> TestClient:
    """Create a test client with some sample data."""
    from notification.audit import AuditRecord

    fresh_store = InMemoryAuditStore()
    fresh_adapter = InMemoryReadModelAdapter(audit_store=fresh_store)

    # Add some test delivery data via the audit store
    notification_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Add a delivery audit record with all required fields
    audit_record = AuditRecord(
        audit_id=uuid.uuid4(),
        notification_id=notification_id,
        notification_type="test.notification",
        status=DeliveryStatus.DELIVERED,
        channels_attempted=(Channel.SLACK,),
        channels_succeeded=(Channel.SLACK,),
        channels_failed=(),
        error_message=None,
        intent=NotificationIntent.OPERATIONAL.value,
        delivery_mode=DeliveryMode.BEST_EFFORT.value,
        autonomy_mode=AutonomyMode.LIVE.value,
        agent_id=agent_id,
        plan_id=None,
        decision_snapshot_id=None,
        execution_snapshot_id=None,
        skip_snapshot_id=None,
        title="Test Notification",
        source="contract_tests",
        correlation_id=None,
        metadata={},
        audit_metadata={},
        notification_created_at=now,
        delivered_at=now,
        audit_created_at=now,
    )
    fresh_store.save_delivery_audit(audit_record)

    configure_read_model_adapter(fresh_adapter)
    app = create_app()
    return TestClient(app)


# =============================================================================
# Contract Field Validators
# =============================================================================


def validate_pagination_info(data: dict[str, Any]) -> None:
    """Validate PaginationInfo contract fields."""
    assert "next_cursor" in data, "PaginationInfo missing 'next_cursor'"
    assert "has_more" in data, "PaginationInfo missing 'has_more'"
    assert "total_count" in data, "PaginationInfo missing 'total_count'"

    # Type checks
    assert data["next_cursor"] is None or isinstance(data["next_cursor"], str), (
        "next_cursor must be string or null"
    )
    assert isinstance(data["has_more"], bool), "has_more must be boolean"
    assert data["total_count"] is None or isinstance(data["total_count"], int), (
        "total_count must be int or null"
    )


def validate_delivery_timeline_summary(data: dict[str, Any]) -> None:
    """Validate DeliveryTimelineSummary contract fields."""
    required_fields = [
        "notification_id",
        "notification_type",
        "intent",
        "delivery_mode",
        "status",
        "created_at",
        "channels_attempted",
        "channels_succeeded",
        "autonomy_mode",
        "agent_id",
    ]
    for field in required_fields:
        assert field in data, f"DeliveryTimelineSummary missing '{field}'"

    # Optional fields
    assert "delivered_at" in data, "DeliveryTimelineSummary missing 'delivered_at'"

    # Enum value checks
    assert data["intent"] in [e.value for e in NotificationIntent], (
        f"Invalid intent: {data['intent']}"
    )
    assert data["delivery_mode"] in [e.value for e in DeliveryMode], (
        f"Invalid delivery_mode: {data['delivery_mode']}"
    )
    assert data["status"] in [e.value for e in DeliveryStatus], f"Invalid status: {data['status']}"
    assert data["autonomy_mode"] in [e.value for e in AutonomyMode], (
        f"Invalid autonomy_mode: {data['autonomy_mode']}"
    )

    # Array type checks
    assert isinstance(data["channels_attempted"], list), "channels_attempted must be a list"
    assert isinstance(data["channels_succeeded"], list), "channels_succeeded must be a list"


def validate_delivery_timeline_response(data: dict[str, Any]) -> None:
    """Validate DeliveryTimelineResponse contract fields."""
    required_fields = [
        "notification_id",
        "notification_type",
        "intent",
        "delivery_mode",
        "status",
        "created_at",
        "attempts",
        "channels_attempted",
        "channels_succeeded",
        "channels_failed",
        "autonomy_context",
    ]
    for field in required_fields:
        assert field in data, f"DeliveryTimelineResponse missing '{field}'"

    # Optional fields
    assert "delivered_at" in data, "DeliveryTimelineResponse missing 'delivered_at'"

    # Validate autonomy_context
    validate_autonomy_context(data["autonomy_context"])

    # Validate attempts array
    assert isinstance(data["attempts"], list), "attempts must be a list"
    for attempt in data["attempts"]:
        validate_delivery_attempt(attempt)


def validate_autonomy_context(data: dict[str, Any]) -> None:
    """Validate AutonomyContextResponse contract fields."""
    required_fields = ["autonomy_mode", "agent_id"]
    for field in required_fields:
        assert field in data, f"AutonomyContextResponse missing '{field}'"

    optional_fields = [
        "plan_id",
        "decision_snapshot_id",
        "execution_snapshot_id",
        "skip_snapshot_id",
    ]
    for field in optional_fields:
        assert field in data, f"AutonomyContextResponse missing optional '{field}'"


def validate_delivery_attempt(data: dict[str, Any]) -> None:
    """Validate DeliveryAttempt contract fields."""
    required_fields = [
        "attempt_id",
        "channel",
        "status",
        "started_at",
        "completed_at",
        "duration_ms",
    ]
    for field in required_fields:
        assert field in data, f"DeliveryAttempt missing '{field}'"

    optional_fields = ["error_message", "error_code", "metadata"]
    for field in optional_fields:
        assert field in data, f"DeliveryAttempt missing optional '{field}'"


def validate_effective_policy_response(data: dict[str, Any]) -> None:
    """Validate EffectivePolicyResponse contract fields."""
    required_fields = [
        "notification_type",
        "effective",
        "resolution",
        "resolution_context",
    ]
    for field in required_fields:
        assert field in data, f"EffectivePolicyResponse missing '{field}'"

    # Validate effective policy values
    validate_effective_policy_values(data["effective"])

    # Validate resolution context
    validate_resolution_context(data["resolution_context"])

    # Validate resolution trace
    assert isinstance(data["resolution"], dict), "resolution must be a dict"
    expected_resolution_fields = [
        "delivery_mode",
        "channels",
        "require_ack",
        "ack_timeout_minutes",
        "dedup_window_seconds",
    ]
    for field in expected_resolution_fields:
        assert field in data["resolution"], f"resolution missing '{field}'"
        assert isinstance(data["resolution"][field], list), f"resolution[{field}] must be a list"


def validate_effective_policy_values(data: dict[str, Any]) -> None:
    """Validate EffectivePolicyValues contract fields."""
    required_fields = [
        "delivery_mode",
        "channels",
        "require_ack",
        "dedup_window_seconds",
    ]
    for field in required_fields:
        assert field in data, f"EffectivePolicyValues missing '{field}'"

    # Optional but expected
    assert "ack_timeout_minutes" in data, "EffectivePolicyValues missing 'ack_timeout_minutes'"

    # Type checks
    assert isinstance(data["channels"], list), "channels must be a list"
    assert isinstance(data["require_ack"], bool), "require_ack must be boolean"
    assert isinstance(data["dedup_window_seconds"], int), "dedup_window_seconds must be int"


def validate_resolution_context(data: dict[str, Any]) -> None:
    """Validate ResolutionContext contract fields."""
    required_fields = [
        "intent",
        "autonomy_mode",
        "irreversible",
        "policy_found",
    ]
    for field in required_fields:
        assert field in data, f"ResolutionContext missing '{field}'"

    # Optional
    assert "policy_notification_type" in data, (
        "ResolutionContext missing 'policy_notification_type'"
    )

    # Type checks
    assert isinstance(data["irreversible"], bool), "irreversible must be boolean"
    assert isinstance(data["policy_found"], bool), "policy_found must be boolean"


def validate_invariant_entry(data: dict[str, Any]) -> None:
    """Validate InvariantEntry contract fields."""
    required_fields = [
        "id",
        "statement",
        "severity",
        "status",
        "enforcement",
        "evidence",
        "owner",
        "last_reviewed",
    ]
    for field in required_fields:
        assert field in data, f"InvariantEntry missing '{field}'"

    # Optional
    assert "mitigation" in data, "InvariantEntry missing 'mitigation'"

    # Validate enforcement
    assert "type" in data["enforcement"], "enforcement missing 'type'"
    assert "description" in data["enforcement"], "enforcement missing 'description'"

    # Validate evidence array
    assert isinstance(data["evidence"], list), "evidence must be a list"
    for evidence in data["evidence"]:
        assert "path" in evidence, "EvidenceLink missing 'path'"
        assert "note" in evidence, "EvidenceLink missing 'note'"


def validate_invariant_summary_response(data: dict[str, Any]) -> None:
    """Validate InvariantSummaryResponse contract fields."""
    required_fields = [
        "total_count",
        "by_severity",
        "by_enforcement_type",
        "by_status",
        "exceptions_requiring_review",
        "last_updated",
    ]
    for field in required_fields:
        assert field in data, f"InvariantSummaryResponse missing '{field}'"

    # Type checks
    assert isinstance(data["total_count"], int), "total_count must be int"
    assert isinstance(data["by_severity"], dict), "by_severity must be dict"
    assert isinstance(data["by_enforcement_type"], dict), "by_enforcement_type must be dict"
    assert isinstance(data["by_status"], dict), "by_status must be dict"
    assert isinstance(data["exceptions_requiring_review"], int), (
        "exceptions_requiring_review must be int"
    )
    assert isinstance(data["last_updated"], str), "last_updated must be string"


def validate_audit_event(data: dict[str, Any]) -> None:
    """Validate AuditEvent contract fields."""
    required_fields = [
        "audit_id",
        "event_type",
        "event_time",
        "notification_id",
        "notification_type",
        "autonomy_context",
        "payload",
    ]
    for field in required_fields:
        assert field in data, f"AuditEvent missing '{field}'"

    # Optional
    assert "correlation_id" in data, "AuditEvent missing 'correlation_id'"

    # Validate autonomy_context
    validate_autonomy_context(data["autonomy_context"])

    # Type checks
    assert isinstance(data["payload"], dict), "payload must be a dict"


# =============================================================================
# Contract Tests: GET /ui/deliveries
# =============================================================================


class TestDeliveriesListContract:
    """Contract tests for GET /ui/deliveries -> DeliveryTimelineListResponse."""

    def test_response_has_items_and_pagination(self, client: TestClient) -> None:
        """Verify response contains items array and pagination object."""
        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data, "Response missing 'items'"
        assert "pagination" in data, "Response missing 'pagination'"

        assert isinstance(data["items"], list), "items must be a list"
        validate_pagination_info(data["pagination"])

    def test_empty_items_has_correct_pagination(self, client: TestClient) -> None:
        """Verify empty response has correct pagination defaults."""
        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == [], "items should be empty list"
        assert data["pagination"]["has_more"] is False, "has_more should be False for empty"
        assert data["pagination"]["total_count"] == 0, "total_count should be 0 for empty"

    def test_items_have_required_fields(self, populated_client: TestClient) -> None:
        """Verify each item in response has required fields."""
        response = populated_client.get("/ui/deliveries")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            validate_delivery_timeline_summary(item)

    def test_filter_params_accepted(self, client: TestClient) -> None:
        """Verify all documented filter parameters are accepted."""
        # Test all filter parameters are accepted without error
        response = client.get(
            "/ui/deliveries",
            params={
                "cursor": "test-cursor",
                "limit": 10,
                "status": "DELIVERED",
                "intent": "SAFETY",
                "delivery_mode": "GUARANTEED",
                "autonomy_mode": "LIVE",
                "notification_type": "test.type",
                "channel": "SLACK",
            },
        )
        assert response.status_code == 200

    def test_invalid_enum_returns_422(self, client: TestClient) -> None:
        """Verify invalid enum values return validation error."""
        response = client.get("/ui/deliveries", params={"status": "INVALID_STATUS"})
        assert response.status_code == 422


# =============================================================================
# Contract Tests: GET /ui/deliveries/{id}
# =============================================================================


class TestDeliveryDetailContract:
    """Contract tests for GET /ui/deliveries/{id} -> DeliveryTimelineResponse."""

    def test_not_found_returns_404_with_error_structure(self, client: TestClient) -> None:
        """Verify 404 response has correct error structure."""
        fake_id = uuid.uuid4()
        response = client.get(f"/ui/deliveries/{fake_id}")

        assert response.status_code == 404
        data = response.json()

        # FastAPI returns error in "detail" for HTTPException
        assert "detail" in data
        detail = data["detail"]
        assert "error" in detail, "Error response missing 'error'"
        assert "code" in detail["error"], "Error missing 'code'"
        assert "message" in detail["error"], "Error missing 'message'"
        assert detail["error"]["code"] == "not_found"

    def test_invalid_uuid_returns_422(self, client: TestClient) -> None:
        """Verify invalid UUID returns validation error."""
        response = client.get("/ui/deliveries/not-a-uuid")
        assert response.status_code == 422

    def test_found_delivery_has_required_fields(self, populated_client: TestClient) -> None:
        """Verify found delivery has all required fields."""
        # First get a delivery ID from the list
        list_response = populated_client.get("/ui/deliveries")
        assert list_response.status_code == 200
        items = list_response.json()["items"]

        if items:  # Only test if we have data
            notification_id = items[0]["notification_id"]
            response = populated_client.get(f"/ui/deliveries/{notification_id}")
            assert response.status_code == 200

            data = response.json()
            validate_delivery_timeline_response(data)


# =============================================================================
# Contract Tests: GET /ui/policies/effective
# =============================================================================


class TestEffectivePolicyContract:
    """Contract tests for GET /ui/policies/effective -> EffectivePolicyResponse."""

    def test_response_has_required_fields(self, client: TestClient) -> None:
        """Verify response contains all required fields."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200

        data = response.json()
        validate_effective_policy_response(data)

    def test_resolution_trace_has_all_fields(self, client: TestClient) -> None:
        """Verify resolution trace contains all policy fields."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "GOVERNANCE",
                "autonomy_mode": "SHADOW",
            },
        )
        assert response.status_code == 200

        data = response.json()
        resolution = data["resolution"]

        # All fields must be present in resolution trace
        expected_fields = [
            "delivery_mode",
            "channels",
            "require_ack",
            "ack_timeout_minutes",
            "dedup_window_seconds",
        ]
        for field in expected_fields:
            assert field in resolution, f"Resolution trace missing '{field}'"
            # Each field should have resolution steps
            steps = resolution[field]
            assert isinstance(steps, list), f"Resolution[{field}] must be a list"
            assert len(steps) > 0, f"Resolution[{field}] must have at least one step"

            # Validate each step
            for step in steps:
                assert "source" in step, "Resolution step missing 'source'"
                assert "value" in step, "Resolution step missing 'value'"
                assert "applied" in step, "Resolution step missing 'applied'"

    def test_missing_required_params_returns_422(self, client: TestClient) -> None:
        """Verify missing required params return validation error."""
        # Missing notification_type
        response = client.get(
            "/ui/policies/effective",
            params={"intent": "SAFETY", "autonomy_mode": "LIVE"},
        )
        assert response.status_code == 422

        # Missing intent
        response = client.get(
            "/ui/policies/effective",
            params={"notification_type": "test", "autonomy_mode": "LIVE"},
        )
        assert response.status_code == 422

        # Missing autonomy_mode
        response = client.get(
            "/ui/policies/effective",
            params={"notification_type": "test", "intent": "SAFETY"},
        )
        assert response.status_code == 422

    def test_irreversible_param_accepted(self, client: TestClient) -> None:
        """Verify irreversible parameter is accepted."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.notification",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
                "irreversible": True,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["resolution_context"]["irreversible"] is True


# =============================================================================
# Contract Tests: GET /ui/invariants
# =============================================================================


class TestInvariantsListContract:
    """Contract tests for GET /ui/invariants -> InvariantListResponse."""

    def test_response_has_items_and_pagination(self, client: TestClient) -> None:
        """Verify response contains items array and pagination object."""
        response = client.get("/ui/invariants")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data, "Response missing 'items'"
        assert "pagination" in data, "Response missing 'pagination'"

        assert isinstance(data["items"], list), "items must be a list"
        validate_pagination_info(data["pagination"])

    def test_items_have_required_fields(self, client: TestClient) -> None:
        """Verify each invariant has required fields."""
        response = client.get("/ui/invariants")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            validate_invariant_entry(item)

    def test_filter_params_accepted(self, client: TestClient) -> None:
        """Verify all documented filter parameters are accepted."""
        response = client.get(
            "/ui/invariants",
            params={
                "cursor": "test-cursor",
                "limit": 10,
                "severity": "HIGH",
                "enforcement_type": "guard",
                "status": "active",
                "search": "test",
            },
        )
        assert response.status_code == 200


# =============================================================================
# Contract Tests: GET /ui/invariants/summary
# =============================================================================


class TestInvariantsSummaryContract:
    """Contract tests for GET /ui/invariants/summary -> InvariantSummaryResponse."""

    def test_response_has_required_fields(self, client: TestClient) -> None:
        """Verify response contains all required fields."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200

        data = response.json()
        validate_invariant_summary_response(data)

    def test_by_severity_has_all_levels(self, client: TestClient) -> None:
        """Verify by_severity contains all severity levels."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200

        data = response.json()
        expected_severities = ["HIGH", "MEDIUM", "LOW"]
        for severity in expected_severities:
            assert severity in data["by_severity"], f"by_severity missing '{severity}'"

    def test_by_enforcement_type_has_all_types(self, client: TestClient) -> None:
        """Verify by_enforcement_type contains all enforcement types."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200

        data = response.json()
        expected_types = ["guard", "isolation", "test", "exception"]
        for etype in expected_types:
            assert etype in data["by_enforcement_type"], f"by_enforcement_type missing '{etype}'"

    def test_by_status_has_all_statuses(self, client: TestClient) -> None:
        """Verify by_status contains all status values."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200

        data = response.json()
        expected_statuses = ["active", "inactive"]
        for status in expected_statuses:
            assert status in data["by_status"], f"by_status missing '{status}'"


# =============================================================================
# Contract Tests: GET /ui/audit
# =============================================================================


class TestAuditEventsContract:
    """Contract tests for GET /ui/audit -> AuditEventListResponse."""

    def test_response_has_items_and_pagination(self, client: TestClient) -> None:
        """Verify response contains items array and pagination object."""
        response = client.get("/ui/audit")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data, "Response missing 'items'"
        assert "pagination" in data, "Response missing 'pagination'"

        assert isinstance(data["items"], list), "items must be a list"
        validate_pagination_info(data["pagination"])

    def test_empty_items_has_correct_pagination(self, client: TestClient) -> None:
        """Verify empty response has correct pagination defaults."""
        response = client.get("/ui/audit")
        assert response.status_code == 200

        data = response.json()
        # Note: total_count might not be present for audit events
        assert data["pagination"]["has_more"] is False, "has_more should be False for empty"

    def test_items_have_required_fields(self, populated_client: TestClient) -> None:
        """Verify each audit event has required fields."""
        response = populated_client.get("/ui/audit")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            validate_audit_event(item)

    def test_filter_params_accepted(self, client: TestClient) -> None:
        """Verify all documented filter parameters are accepted."""
        response = client.get(
            "/ui/audit",
            params={
                "cursor": "test-cursor",
                "limit": 10,
                "event_type": "notification.created",
                "autonomy_mode": "LIVE",
                "correlation_id": "test-correlation",
            },
        )
        assert response.status_code == 200


# =============================================================================
# Degraded State Tests
# =============================================================================


class TestDegradedState:
    """Tests for degraded-state behavior when data sources are unavailable."""

    def test_invariants_source_unavailable_graceful_degradation(self, client: TestClient) -> None:
        """Test that invariants endpoint handles source unavailable gracefully.

        When the invariants YAML file is not found or unreadable, the endpoint
        should return an empty list with correct pagination rather than failing.
        This tests the degraded:true scenario.
        """
        from pathlib import Path

        original_exists = Path.exists

        # Create a mock that returns False only for invariants.yml
        def mock_exists(self: Path) -> bool:
            if "invariants.yml" in str(self):
                return False
            return original_exists(self)

        with patch.object(Path, "exists", mock_exists):
            response = client.get("/ui/invariants")
            assert response.status_code == 200

            data = response.json()

            # Should return empty list, not error
            assert "items" in data
            assert data["items"] == []

            # Pagination should indicate no more data
            assert data["pagination"]["has_more"] is False
            assert data["pagination"]["total_count"] == 0

    def test_invariants_yaml_parse_error_graceful_degradation(self, client: TestClient) -> None:
        """Test that invariants endpoint handles YAML parse errors gracefully."""
        import yaml

        # Mock yaml.safe_load to raise an exception
        with patch.object(yaml, "safe_load", side_effect=Exception("YAML parse error")):
            response = client.get("/ui/invariants")
            assert response.status_code == 200

            data = response.json()

            # Should return empty list on error
            assert data["items"] == []
            assert data["pagination"]["has_more"] is False

    def test_invariants_summary_graceful_degradation(self, client: TestClient) -> None:
        """Test that invariants summary handles source unavailable gracefully."""
        from pathlib import Path

        original_exists = Path.exists

        # Create a mock that returns False only for invariants.yml
        def mock_exists(self: Path) -> bool:
            if "invariants.yml" in str(self):
                return False
            return original_exists(self)

        with patch.object(Path, "exists", mock_exists):
            response = client.get("/ui/invariants/summary")
            assert response.status_code == 200

            data = response.json()

            # Should return zero counts, not error
            assert data["total_count"] == 0
            assert data["exceptions_requiring_review"] == 0


# =============================================================================
# Pydantic Model Consistency Tests
# =============================================================================


class TestPydanticModelConsistency:
    """Tests that verify Pydantic models match expected contract shapes."""

    def test_pagination_info_model_fields(self) -> None:
        """Verify PaginationInfo model has expected fields."""
        info = PaginationInfo(next_cursor=None, has_more=False, total_count=0)
        data = info.model_dump()

        assert "next_cursor" in data
        assert "has_more" in data
        assert "total_count" in data

    def test_delivery_timeline_summary_model_fields(self) -> None:
        """Verify DeliveryTimelineSummary model has expected fields."""
        summary = DeliveryTimelineSummary(
            notification_id=uuid.uuid4(),
            notification_type="test",
            intent=NotificationIntent.OPERATIONAL,
            delivery_mode=DeliveryMode.BEST_EFFORT,
            status=DeliveryStatus.PENDING,
            created_at=datetime.now(UTC),
            channels_attempted=[],
            channels_succeeded=[],
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid.uuid4(),
        )
        data = summary.model_dump()

        validate_delivery_timeline_summary(data)

    def test_effective_policy_response_model_fields(self) -> None:
        """Verify EffectivePolicyResponse model has expected fields."""
        response = EffectivePolicyResponse(
            notification_type="test",
            effective=EffectivePolicyValues(
                delivery_mode=DeliveryMode.GUARANTEED,
                channels=[Channel.SLACK],
                require_ack=True,
                ack_timeout_minutes=15,
                dedup_window_seconds=300,
            ),
            resolution={
                "delivery_mode": [
                    ResolutionStep(
                        source=ResolutionSource.SDK_DEFAULT,
                        value="GUARANTEED",
                        applied=True,
                    )
                ],
                "channels": [],
                "require_ack": [],
                "ack_timeout_minutes": [],
                "dedup_window_seconds": [],
            },
            resolution_context=ResolutionContext(
                intent=NotificationIntent.SAFETY,
                autonomy_mode=AutonomyMode.LIVE,
                irreversible=False,
                policy_found=False,
            ),
        )
        data = response.model_dump()

        validate_effective_policy_response(data)

    def test_invariant_entry_model_fields(self) -> None:
        """Verify InvariantEntry model has expected fields."""
        entry = InvariantEntry(
            id="INV-TEST-001",
            statement="Test invariant",
            severity=InvariantSeverity.HIGH,
            status=InvariantStatus.ACTIVE,
            enforcement=InvariantEnforcement(
                type=EnforcementType.GUARD,
                description="Test enforcement",
            ),
            evidence=[
                EvidenceLink(path="test/file.py", note="Test evidence"),
            ],
            owner="test-team",
            last_reviewed="2024-01-01",
        )
        data = entry.model_dump()

        validate_invariant_entry(data)

    def test_audit_event_model_fields(self) -> None:
        """Verify AuditEvent model has expected fields."""
        event = AuditEvent(
            audit_id=uuid.uuid4(),
            event_type=AuditEventType.NOTIFICATION_CREATED,
            event_time=datetime.now(UTC),
            notification_id=uuid.uuid4(),
            notification_type="test",
            autonomy_context=AutonomyContextResponse(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id=uuid.uuid4(),
            ),
            payload={"test": "data"},
        )
        data = event.model_dump()

        validate_audit_event(data)


# =============================================================================
# Error Response Contract Tests
# =============================================================================


class TestErrorResponseContract:
    """Tests for error response contract structure."""

    def test_error_response_model_fields(self) -> None:
        """Verify ErrorResponse model has expected fields."""
        error = ErrorResponse(
            error=ErrorDetail(
                code="test_error",
                message="Test error message",
                details={"key": "value"},
            ),
            request_id="test-request-id",
        )
        data = error.model_dump()

        assert "error" in data
        assert "request_id" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "details" in data["error"]

    def test_404_error_format(self, client: TestClient) -> None:
        """Verify 404 errors follow standard format."""
        response = client.get(f"/ui/deliveries/{uuid.uuid4()}")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "not_found"

"""Tests for UI API client types."""

from datetime import UTC, datetime
from uuid import uuid4

from notification.models import (
    AutonomyMode,
    Channel,
    DeliveryMode,
    DeliveryStatus,
    NotificationIntent,
)
from ui_client.types import (
    AuditEvent,
    AuditEventListResponse,
    AuditEventType,
    AutonomyContextResponse,
    DeliveryAttempt,
    DeliveryTimelineListResponse,
    DeliveryTimelineResponse,
    DeliveryTimelineSummary,
    EffectivePolicyResponse,
    EffectivePolicyValues,
    EnforcementType,
    ErrorDetail,
    ErrorResponse,
    EvidenceLink,
    InvariantEnforcement,
    InvariantEntry,
    InvariantSeverity,
    InvariantStatus,
    InvariantSummaryResponse,
    PaginationInfo,
    ResolutionContext,
    ResolutionSource,
    ResolutionStep,
)


class TestPaginationInfo:
    """Tests for PaginationInfo model."""

    def test_empty_pagination(self):
        """Test pagination with no more pages."""
        pagination = PaginationInfo(next_cursor=None, has_more=False, total_count=0)
        assert pagination.next_cursor is None
        assert pagination.has_more is False
        assert pagination.total_count == 0

    def test_has_more_pagination(self):
        """Test pagination with more pages available."""
        pagination = PaginationInfo(next_cursor="abc123", has_more=True, total_count=100)
        assert pagination.next_cursor == "abc123"
        assert pagination.has_more is True
        assert pagination.total_count == 100

    def test_optional_total_count(self):
        """Test pagination without total_count."""
        pagination = PaginationInfo(next_cursor="xyz", has_more=True)
        assert pagination.total_count is None


class TestErrorTypes:
    """Tests for error response types."""

    def test_error_detail(self):
        """Test ErrorDetail model."""
        detail = ErrorDetail(
            code="not_found",
            message="Resource not found",
            details={"resource_id": "123"},
        )
        assert detail.code == "not_found"
        assert detail.message == "Resource not found"
        assert detail.details == {"resource_id": "123"}

    def test_error_response(self):
        """Test ErrorResponse model."""
        error = ErrorResponse(
            error=ErrorDetail(code="invalid_parameter", message="Invalid value"),
            request_id="req-123",
        )
        assert error.error.code == "invalid_parameter"
        assert error.request_id == "req-123"


class TestDeliveryTypes:
    """Tests for delivery timeline types."""

    def test_delivery_attempt(self):
        """Test DeliveryAttempt model."""
        now = datetime.now(UTC)
        attempt = DeliveryAttempt(
            attempt_id=uuid4(),
            channel=Channel.SLACK,
            status="SUCCESS",
            started_at=now,
            completed_at=now,
            duration_ms=150,
            error_message=None,
            error_code=None,
            metadata={"thread_id": "T123"},
        )
        assert attempt.channel == Channel.SLACK
        assert attempt.status == "SUCCESS"
        assert attempt.duration_ms == 150

    def test_autonomy_context_response(self):
        """Test AutonomyContextResponse model."""
        context = AutonomyContextResponse(
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=uuid4(),
            plan_id=uuid4(),
            decision_snapshot_id=None,
        )
        assert context.autonomy_mode == AutonomyMode.LIVE
        assert context.plan_id is not None
        assert context.decision_snapshot_id is None

    def test_delivery_timeline_summary(self):
        """Test DeliveryTimelineSummary model."""
        now = datetime.now(UTC)
        agent_id = uuid4()
        notification_id = uuid4()

        summary = DeliveryTimelineSummary(
            notification_id=notification_id,
            notification_type="trading.order_placed",
            intent=NotificationIntent.OPERATIONAL,
            delivery_mode=DeliveryMode.BEST_EFFORT,
            status=DeliveryStatus.DELIVERED,
            created_at=now,
            delivered_at=now,
            channels_attempted=[Channel.SLACK, Channel.WEBSOCKET],
            channels_succeeded=[Channel.SLACK],
            autonomy_mode=AutonomyMode.LIVE,
            agent_id=agent_id,
        )

        assert summary.notification_id == notification_id
        assert summary.intent == NotificationIntent.OPERATIONAL
        assert len(summary.channels_attempted) == 2
        assert Channel.SLACK in summary.channels_succeeded

    def test_delivery_timeline_response(self):
        """Test DeliveryTimelineResponse model."""
        now = datetime.now(UTC)
        agent_id = uuid4()
        notification_id = uuid4()

        response = DeliveryTimelineResponse(
            notification_id=notification_id,
            notification_type="trading.order_placed",
            intent=NotificationIntent.SAFETY,
            delivery_mode=DeliveryMode.GUARANTEED,
            status=DeliveryStatus.DELIVERED,
            created_at=now,
            delivered_at=now,
            attempts=[
                DeliveryAttempt(
                    attempt_id=uuid4(),
                    channel=Channel.SLACK,
                    status="SUCCESS",
                    started_at=now,
                    completed_at=now,
                    duration_ms=100,
                )
            ],
            channels_attempted=[Channel.SLACK],
            channels_succeeded=[Channel.SLACK],
            channels_failed=[],
            autonomy_context=AutonomyContextResponse(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id=agent_id,
            ),
        )

        assert response.intent == NotificationIntent.SAFETY
        assert response.delivery_mode == DeliveryMode.GUARANTEED
        assert len(response.attempts) == 1
        assert response.autonomy_context.agent_id == agent_id

    def test_delivery_timeline_list_response(self):
        """Test DeliveryTimelineListResponse model."""
        response = DeliveryTimelineListResponse(
            items=[],
            pagination=PaginationInfo(next_cursor=None, has_more=False),
        )
        assert response.items == []
        assert response.pagination.has_more is False


class TestPolicyTypes:
    """Tests for policy resolution types."""

    def test_resolution_source_enum(self):
        """Test ResolutionSource enum values."""
        assert ResolutionSource.EXPLICIT_OVERRIDE == "explicit_override"
        assert ResolutionSource.MODE_OVERRIDE == "mode_override"
        assert ResolutionSource.POLICY_BASE == "policy_base"
        assert ResolutionSource.SDK_DEFAULT == "sdk_default"

    def test_resolution_step(self):
        """Test ResolutionStep model."""
        step = ResolutionStep(
            source=ResolutionSource.POLICY_BASE,
            value=["SLACK", "EMAIL"],
            applied=True,
            reason=None,
        )
        assert step.source == ResolutionSource.POLICY_BASE
        assert step.applied is True

        step_not_applied = ResolutionStep(
            source=ResolutionSource.MODE_OVERRIDE,
            value=None,
            applied=False,
            reason="Not configured",
        )
        assert step_not_applied.applied is False
        assert step_not_applied.reason == "Not configured"

    def test_effective_policy_values(self):
        """Test EffectivePolicyValues model."""
        values = EffectivePolicyValues(
            delivery_mode=DeliveryMode.GUARANTEED,
            channels=[Channel.SLACK, Channel.PAGERDUTY],
            require_ack=True,
            ack_timeout_minutes=15,
            dedup_window_seconds=300,
        )
        assert values.delivery_mode == DeliveryMode.GUARANTEED
        assert Channel.PAGERDUTY in values.channels
        assert values.require_ack is True

    def test_effective_policy_response(self):
        """Test EffectivePolicyResponse model."""
        response = EffectivePolicyResponse(
            notification_type="trading.risk_breach",
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
                ]
            },
            resolution_context=ResolutionContext(
                intent=NotificationIntent.SAFETY,
                autonomy_mode=AutonomyMode.LIVE,
                irreversible=False,
                policy_found=True,
                policy_notification_type="trading.risk_breach",
            ),
        )

        assert response.notification_type == "trading.risk_breach"
        assert response.effective.require_ack is True
        assert response.resolution_context.policy_found is True


class TestInvariantTypes:
    """Tests for invariant types."""

    def test_enforcement_type_enum(self):
        """Test EnforcementType enum values."""
        assert EnforcementType.GUARD == "guard"
        assert EnforcementType.ISOLATION == "isolation"
        assert EnforcementType.TEST == "test"
        assert EnforcementType.EXCEPTION == "exception"

    def test_invariant_severity_enum(self):
        """Test InvariantSeverity enum values."""
        assert InvariantSeverity.HIGH == "HIGH"
        assert InvariantSeverity.MEDIUM == "MEDIUM"
        assert InvariantSeverity.LOW == "LOW"

    def test_evidence_link(self):
        """Test EvidenceLink model."""
        link = EvidenceLink(
            path="src/notification/sdk.py",
            note="Validates autonomy_context is present",
            line_ref="L160-L165",
        )
        assert link.path == "src/notification/sdk.py"
        assert link.line_ref == "L160-L165"

    def test_invariant_entry(self):
        """Test InvariantEntry model."""
        entry = InvariantEntry(
            id="INV-ACK-001",
            statement="SAFETY notifications in LIVE mode require acknowledgment",
            severity=InvariantSeverity.HIGH,
            status=InvariantStatus.ACTIVE,
            enforcement=InvariantEnforcement(
                type=EnforcementType.GUARD,
                description="Validated in SDK send method",
            ),
            evidence=[
                EvidenceLink(
                    path="src/notification/sdk.py",
                    note="Enforces require_ack default",
                )
            ],
            owner="platform-team",
            last_reviewed="2024-01-15",
        )

        assert entry.id == "INV-ACK-001"
        assert entry.severity == InvariantSeverity.HIGH
        assert entry.enforcement.type == EnforcementType.GUARD
        assert len(entry.evidence) == 1

    def test_invariant_summary_response(self):
        """Test InvariantSummaryResponse model."""
        summary = InvariantSummaryResponse(
            total_count=15,
            by_severity={"HIGH": 5, "MEDIUM": 8, "LOW": 2},
            by_enforcement_type={"guard": 7, "test": 6, "isolation": 2},
            by_status={"active": 14, "inactive": 1},
            exceptions_requiring_review=0,
            last_updated="2024-01-20T10:30:00Z",
        )

        assert summary.total_count == 15
        assert summary.by_severity["HIGH"] == 5
        assert summary.exceptions_requiring_review == 0


class TestAuditTypes:
    """Tests for audit event types."""

    def test_audit_event_type_enum(self):
        """Test AuditEventType enum values."""
        assert AuditEventType.NOTIFICATION_CREATED == "notification.created"
        assert AuditEventType.DELIVERY_SUCCEEDED == "delivery.succeeded"
        assert AuditEventType.ACK_RECEIVED == "ack.received"

    def test_audit_event(self):
        """Test AuditEvent model."""
        now = datetime.now(UTC)
        agent_id = uuid4()
        notification_id = uuid4()

        event = AuditEvent(
            audit_id=uuid4(),
            event_type=AuditEventType.DELIVERY_SUCCEEDED,
            event_time=now,
            notification_id=notification_id,
            notification_type="trading.order_placed",
            autonomy_context=AutonomyContextResponse(
                autonomy_mode=AutonomyMode.LIVE,
                agent_id=agent_id,
            ),
            payload={"channels_succeeded": ["SLACK"]},
            correlation_id="corr-123",
        )

        assert event.event_type == AuditEventType.DELIVERY_SUCCEEDED
        assert event.correlation_id == "corr-123"
        assert event.autonomy_context.autonomy_mode == AutonomyMode.LIVE

    def test_audit_event_list_response(self):
        """Test AuditEventListResponse model."""
        response = AuditEventListResponse(
            items=[],
            pagination=PaginationInfo(next_cursor="next", has_more=True, total_count=50),
        )
        assert response.items == []
        assert response.pagination.has_more is True
        assert response.pagination.total_count == 50

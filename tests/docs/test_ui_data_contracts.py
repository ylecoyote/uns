"""Tests for ui-data-contracts.md documentation.

Tests verify that the data contracts document:
1. Has correct structure and completeness
2. Documents all required endpoints
3. Contains consistent type definitions
4. Aligns with existing models and patterns
"""

from pathlib import Path

import pytest

UI_DATA_CONTRACTS_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "ui" / "ui-data-contracts.md"
)


@pytest.fixture
def data_contracts_doc() -> str:
    """Load the UI data contracts documentation."""
    assert UI_DATA_CONTRACTS_PATH.exists(), (
        f"ui-data-contracts.md not found at {UI_DATA_CONTRACTS_PATH}"
    )
    return UI_DATA_CONTRACTS_PATH.read_text()


class TestDocumentExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify ui-data-contracts.md exists."""
        assert UI_DATA_CONTRACTS_PATH.exists()

    def test_file_not_empty(self, data_contracts_doc: str) -> None:
        """Verify file is not empty."""
        assert len(data_contracts_doc) > 0

    def test_is_markdown(self, data_contracts_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in data_contracts_doc


class TestDocumentStructure:
    """Test the structure of the data contracts documentation."""

    def test_has_title(self, data_contracts_doc: str) -> None:
        """Verify document has correct title."""
        assert data_contracts_doc.startswith("# UNS Console Data Contracts")

    def test_has_design_principles(self, data_contracts_doc: str) -> None:
        """Verify document has design principles section."""
        assert "## Design Principles" in data_contracts_doc

    def test_has_common_types_section(self, data_contracts_doc: str) -> None:
        """Verify document has common types section."""
        assert "## Common Types" in data_contracts_doc

    def test_has_delivery_timeline_section(self, data_contracts_doc: str) -> None:
        """Verify document has delivery timeline section."""
        assert "## 1. Delivery Timeline + Attempts" in data_contracts_doc

    def test_has_escalations_section(self, data_contracts_doc: str) -> None:
        """Verify document has escalations section."""
        assert "## 2. Escalations + Failures" in data_contracts_doc

    def test_has_policy_resolution_section(self, data_contracts_doc: str) -> None:
        """Verify document has policy resolution trace section."""
        assert "## 3. Effective Policy Resolution Trace" in data_contracts_doc

    def test_has_invariant_registry_section(self, data_contracts_doc: str) -> None:
        """Verify document has invariant registry section."""
        assert "## 4. Invariant Registry Rendering" in data_contracts_doc

    def test_has_audit_event_section(self, data_contracts_doc: str) -> None:
        """Verify document has audit event stream section."""
        assert "## 5. Audit Event Stream" in data_contracts_doc


class TestCommonTypes:
    """Test that common types are properly documented."""

    def test_has_pagination_params(self, data_contracts_doc: str) -> None:
        """Verify PaginationParams interface is documented."""
        assert "PaginationParams" in data_contracts_doc
        assert "cursor" in data_contracts_doc
        assert "limit" in data_contracts_doc

    def test_has_paginated_response(self, data_contracts_doc: str) -> None:
        """Verify PaginatedResponse interface is documented."""
        assert "PaginatedResponse" in data_contracts_doc
        assert "next_cursor" in data_contracts_doc
        assert "has_more" in data_contracts_doc

    def test_has_time_range_filter(self, data_contracts_doc: str) -> None:
        """Verify TimeRangeFilter interface is documented."""
        assert "TimeRangeFilter" in data_contracts_doc
        assert "start_time" in data_contracts_doc
        assert "end_time" in data_contracts_doc

    def test_has_error_response(self, data_contracts_doc: str) -> None:
        """Verify ErrorResponse interface is documented."""
        assert "ErrorResponse" in data_contracts_doc
        assert "error" in data_contracts_doc
        assert "request_id" in data_contracts_doc

    def test_has_standard_error_codes(self, data_contracts_doc: str) -> None:
        """Verify standard error codes are documented."""
        assert "not_found" in data_contracts_doc
        assert "invalid_parameter" in data_contracts_doc
        assert "invalid_cursor" in data_contracts_doc
        assert "rate_limited" in data_contracts_doc
        assert "internal_error" in data_contracts_doc


class TestDeliveryTimelineContract:
    """Test delivery timeline data contract completeness."""

    def _get_delivery_timeline_section(self, doc: str) -> str:
        """Extract the delivery timeline section."""
        start = doc.find("## 1. Delivery Timeline")
        end = doc.find("## 2. Escalations")
        return doc[start:end]

    def test_has_endpoint_definition(self, data_contracts_doc: str) -> None:
        """Verify delivery timeline endpoint is documented."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "GET /ui/deliveries/{notification_id}" in section

    def test_has_response_shape(self, data_contracts_doc: str) -> None:
        """Verify DeliveryTimelineResponse interface is documented."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "DeliveryTimelineResponse" in section

    def test_includes_notification_fields(self, data_contracts_doc: str) -> None:
        """Verify response includes notification fields."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "notification_id" in section
        assert "notification_type" in section
        assert "intent" in section
        assert "delivery_mode" in section

    def test_includes_delivery_attempt(self, data_contracts_doc: str) -> None:
        """Verify DeliveryAttempt interface is documented."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "DeliveryAttempt" in section
        assert "attempt_id" in section
        assert "channel" in section
        assert "status" in section

    def test_includes_autonomy_context(self, data_contracts_doc: str) -> None:
        """Verify autonomy_context is included in response."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "autonomy_context" in section
        assert "autonomy_mode" in section
        assert "agent_id" in section

    def test_has_list_endpoint(self, data_contracts_doc: str) -> None:
        """Verify list delivery timelines endpoint is documented."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "GET /ui/deliveries" in section

    def test_has_channel_type(self, data_contracts_doc: str) -> None:
        """Verify Channel type aligns with existing models."""
        section = self._get_delivery_timeline_section(data_contracts_doc)
        assert "SLACK" in section
        assert "EMAIL" in section
        assert "WEBSOCKET" in section
        assert "PAGERDUTY" in section


class TestEscalationsContract:
    """Test escalations data contract completeness."""

    def _get_escalations_section(self, doc: str) -> str:
        """Extract the escalations section."""
        start = doc.find("## 2. Escalations")
        end = doc.find("## 3. Effective Policy")
        return doc[start:end]

    def test_has_endpoint_definition(self, data_contracts_doc: str) -> None:
        """Verify escalations endpoint is documented."""
        section = self._get_escalations_section(data_contracts_doc)
        assert "Planned: GET /ui/escalations" in section

    def test_has_escalation_event_shape(self, data_contracts_doc: str) -> None:
        """Verify EscalationEvent interface is documented."""
        section = self._get_escalations_section(data_contracts_doc)
        assert "EscalationEvent" in section

    def test_includes_escalation_types(self, data_contracts_doc: str) -> None:
        """Verify escalation types are documented."""
        section = self._get_escalations_section(data_contracts_doc)
        assert "delivery_failure" in section
        assert "ack_timeout" in section

    def test_includes_channel_errors(self, data_contracts_doc: str) -> None:
        """Verify ChannelError interface is documented."""
        section = self._get_escalations_section(data_contracts_doc)
        assert "ChannelError" in section
        assert "error_message" in section

    def test_delivery_failure_details(self, data_contracts_doc: str) -> None:
        """Verify DeliveryFailureDetails is documented."""
        section = self._get_escalations_section(data_contracts_doc)
        assert "DeliveryFailureDetails" in section
        assert "GUARANTEED" in section

    def test_ack_timeout_details(self, data_contracts_doc: str) -> None:
        """Verify AckTimeoutDetails is documented."""
        section = self._get_escalations_section(data_contracts_doc)
        assert "AckTimeoutDetails" in section
        assert "timeout_minutes" in section


class TestPolicyResolutionContract:
    """Test policy resolution trace data contract completeness."""

    def _get_policy_section(self, doc: str) -> str:
        """Extract the policy resolution section."""
        start = doc.find("## 3. Effective Policy")
        end = doc.find("## 4. Invariant Registry")
        return doc[start:end]

    def test_has_endpoint_definition(self, data_contracts_doc: str) -> None:
        """Verify policy trace endpoint is documented."""
        section = self._get_policy_section(data_contracts_doc)
        assert "GET /ui/policies/effective" in section

    def test_has_resolution_trace_response(self, data_contracts_doc: str) -> None:
        """Verify PolicyResolutionTraceResponse interface is documented."""
        section = self._get_policy_section(data_contracts_doc)
        assert "PolicyResolutionTraceResponse" in section

    def test_includes_effective_values(self, data_contracts_doc: str) -> None:
        """Verify effective values are documented."""
        section = self._get_policy_section(data_contracts_doc)
        assert "effective" in section
        assert "delivery_mode" in section
        assert "channels" in section
        assert "require_ack" in section

    def test_includes_resolution_steps(self, data_contracts_doc: str) -> None:
        """Verify ResolutionStep interface is documented."""
        section = self._get_policy_section(data_contracts_doc)
        assert "ResolutionStep" in section
        assert "source" in section
        assert "applied" in section

    def test_documents_resolution_order(self, data_contracts_doc: str) -> None:
        """Verify resolution priority order is documented."""
        section = self._get_policy_section(data_contracts_doc)
        assert "explicit_override" in section
        assert "mode_override" in section
        assert "policy_base" in section
        assert "sdk_default" in section

    def test_has_simulate_endpoint(self, data_contracts_doc: str) -> None:
        """Verify simulation endpoint is documented."""
        section = self._get_policy_section(data_contracts_doc)
        assert "Planned: POST /ui/policies/simulate" in section


class TestInvariantRegistryContract:
    """Test invariant registry data contract completeness."""

    def _get_invariant_section(self, doc: str) -> str:
        """Extract the invariant registry section."""
        start = doc.find("## 4. Invariant Registry")
        end = doc.find("## 5. Audit Event")
        return doc[start:end]

    def test_has_endpoint_definition(self, data_contracts_doc: str) -> None:
        """Verify invariants endpoint is documented."""
        section = self._get_invariant_section(data_contracts_doc)
        assert "GET /ui/invariants" in section

    def test_has_invariant_entry_shape(self, data_contracts_doc: str) -> None:
        """Verify InvariantEntry interface is documented."""
        section = self._get_invariant_section(data_contracts_doc)
        assert "InvariantEntry" in section

    def test_includes_severity_levels(self, data_contracts_doc: str) -> None:
        """Verify severity levels are documented."""
        section = self._get_invariant_section(data_contracts_doc)
        assert "HIGH" in section
        assert "MEDIUM" in section
        assert "LOW" in section

    def test_includes_enforcement_types(self, data_contracts_doc: str) -> None:
        """Verify enforcement types are documented."""
        section = self._get_invariant_section(data_contracts_doc)
        assert "guard" in section
        assert "isolation" in section
        assert "test" in section
        assert "exception" in section

    def test_includes_evidence_link(self, data_contracts_doc: str) -> None:
        """Verify EvidenceLink interface is documented."""
        section = self._get_invariant_section(data_contracts_doc)
        assert "EvidenceLink" in section
        assert "path" in section
        assert "note" in section

    def test_has_summary_endpoint(self, data_contracts_doc: str) -> None:
        """Verify summary statistics endpoint is documented."""
        section = self._get_invariant_section(data_contracts_doc)
        assert "GET /ui/invariants/summary" in section


class TestAuditEventStreamContract:
    """Test audit event stream data contract completeness."""

    def _get_audit_section(self, doc: str) -> str:
        """Extract the audit event stream section."""
        start = doc.find("## 5. Audit Event Stream")
        return doc[start:]

    def test_has_endpoint_definition(self, data_contracts_doc: str) -> None:
        """Verify audit events endpoint is documented."""
        section = self._get_audit_section(data_contracts_doc)
        assert "GET /ui/audit" in section

    def test_has_audit_event_shape(self, data_contracts_doc: str) -> None:
        """Verify AuditEvent interface is documented."""
        section = self._get_audit_section(data_contracts_doc)
        assert "AuditEvent" in section
        assert "audit_id" in section
        assert "event_type" in section
        assert "event_time" in section

    def test_includes_event_types(self, data_contracts_doc: str) -> None:
        """Verify all event types are documented."""
        section = self._get_audit_section(data_contracts_doc)
        assert "notification.created" in section
        assert "delivery.started" in section
        assert "delivery.succeeded" in section
        assert "delivery.failed" in section
        assert "ack.received" in section
        assert "ack.timed_out" in section
        assert "escalation.triggered" in section

    def test_includes_payload_types(self, data_contracts_doc: str) -> None:
        """Verify payload types are documented."""
        section = self._get_audit_section(data_contracts_doc)
        assert "AuditEventPayload" in section
        assert "NotificationCreatedPayload" in section
        assert "DeliveryOutcomePayload" in section
        assert "AckStatusChangePayload" in section

    def test_has_notification_events_endpoint(self, data_contracts_doc: str) -> None:
        """Verify endpoint for notification-specific events is documented."""
        section = self._get_audit_section(data_contracts_doc)
        assert "GET /ui/audit?notification_id={notification_id}" in section

    def test_has_statistics_endpoint(self, data_contracts_doc: str) -> None:
        """Verify audit statistics endpoint is documented."""
        section = self._get_audit_section(data_contracts_doc)
        assert "Planned: GET /ui/audit/statistics" in section


class TestModelAlignment:
    """Test that data contracts align with existing models."""

    def test_intent_values_match_models(self, data_contracts_doc: str) -> None:
        """Verify intent values match NotificationIntent enum."""
        assert "SAFETY" in data_contracts_doc
        assert "GOVERNANCE" in data_contracts_doc
        assert "OPERATIONAL" in data_contracts_doc
        assert "INFORMATIONAL" in data_contracts_doc

    def test_delivery_mode_values_match_models(self, data_contracts_doc: str) -> None:
        """Verify delivery mode values match DeliveryMode enum."""
        assert "GUARANTEED" in data_contracts_doc
        assert "BEST_EFFORT" in data_contracts_doc

    def test_autonomy_mode_values_match_models(self, data_contracts_doc: str) -> None:
        """Verify autonomy mode values match AutonomyMode enum."""
        assert "PREVIEW" in data_contracts_doc
        assert "SHADOW" in data_contracts_doc
        assert "LIVE" in data_contracts_doc

    def test_delivery_status_values_match_models(self, data_contracts_doc: str) -> None:
        """Verify delivery status values match DeliveryStatus enum."""
        assert "PENDING" in data_contracts_doc
        assert "DELIVERED" in data_contracts_doc
        assert "SUCCESS" in data_contracts_doc
        assert "FAILED" in data_contracts_doc
        assert "DEDUPLICATED" in data_contracts_doc
        assert "RATE_LIMITED" in data_contracts_doc

    def test_ack_status_values_match_models(self, data_contracts_doc: str) -> None:
        """Verify ack status values in audit events."""
        section = data_contracts_doc
        # Check for ack-related status changes
        assert "ack.pending" in section
        assert "ack.received" in section
        assert "ack.dismissed" in section
        assert "ack.timed_out" in section


class TestPaginationConsistency:
    """Test that pagination is consistently documented."""

    def test_cursor_based_pagination_documented(self, data_contracts_doc: str) -> None:
        """Verify cursor-based pagination is documented."""
        assert "cursor-based pagination" in data_contracts_doc.lower()

    def test_limit_parameter_documented(self, data_contracts_doc: str) -> None:
        """Verify limit parameter with defaults is documented."""
        assert "default: 25" in data_contracts_doc
        assert "max: 100" in data_contracts_doc

    def test_cursor_semantics_documented(self, data_contracts_doc: str) -> None:
        """Verify cursor semantics section exists."""
        assert "## Cursor Semantics" in data_contracts_doc
        assert "opaque" in data_contracts_doc.lower()
        assert "Invalid cursors currently restart pagination" in data_contracts_doc


class TestErrorHandling:
    """Test that error handling is consistently documented."""

    def test_http_status_codes_documented(self, data_contracts_doc: str) -> None:
        """Verify HTTP status codes are documented."""
        assert "## HTTP Status Code Summary" in data_contracts_doc
        assert "200" in data_contracts_doc
        assert "400" in data_contracts_doc
        assert "404" in data_contracts_doc
        assert "429" in data_contracts_doc
        assert "500" in data_contracts_doc

    def test_rate_limiting_documented(self, data_contracts_doc: str) -> None:
        """Verify rate limiting is documented."""
        assert "## Rate Limiting" in data_contracts_doc
        assert "do not currently add HTTP rate-limit headers" in data_contracts_doc


class TestRelatedDocumentation:
    """Test that related documentation is referenced."""

    def test_references_ui_scope(self, data_contracts_doc: str) -> None:
        """Verify reference to ui-scope.md."""
        assert "ui-scope.md" in data_contracts_doc

    def test_references_delivery_semantics(self, data_contracts_doc: str) -> None:
        """Verify reference to delivery-semantics.md."""
        assert "delivery-semantics.md" in data_contracts_doc

    def test_references_policy_lifecycle(self, data_contracts_doc: str) -> None:
        """Verify reference to policy-lifecycle.md."""
        assert "policy-lifecycle.md" in data_contracts_doc

    def test_references_invariants(self, data_contracts_doc: str) -> None:
        """Verify reference to invariants.md."""
        assert "invariants.md" in data_contracts_doc


class TestTypeDefinitions:
    """Test that type definitions use TypeScript syntax consistently."""

    def test_uses_interface_keyword(self, data_contracts_doc: str) -> None:
        """Verify TypeScript interface keyword is used."""
        assert "interface " in data_contracts_doc

    def test_uses_type_keyword(self, data_contracts_doc: str) -> None:
        """Verify TypeScript type keyword is used for unions."""
        assert "type " in data_contracts_doc

    def test_uses_typescript_code_blocks(self, data_contracts_doc: str) -> None:
        """Verify TypeScript code blocks are properly formatted."""
        assert "```typescript" in data_contracts_doc

    def test_no_python_type_hints_in_contracts(self, data_contracts_doc: str) -> None:
        """Verify contracts use TypeScript, not Python type hints."""
        # Look for Python-specific type hint patterns that shouldn't be in contracts
        # This is a basic check; we're looking for TypeScript style
        assert "Optional[" not in data_contracts_doc
        assert "List[" not in data_contracts_doc
        assert "Dict[" not in data_contracts_doc

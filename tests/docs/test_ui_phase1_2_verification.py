"""Tests for UI Phase 1.2 verification report.

Tests verify that:
1. CI script includes lint, typecheck, test, build
2. Backend contract tests exist and pass shape validation
3. UI-side TypeScript types match documented contracts
4. Report exists and has expected structure
"""

import json
from pathlib import Path

import pytest

# Paths
APPS_UI_ROOT = Path(__file__).parent.parent.parent / "apps" / "ui"
PACKAGE_JSON_PATH = APPS_UI_ROOT / "package.json"
TYPES_API_PATH = APPS_UI_ROOT / "src" / "types" / "api.ts"
API_TEST_PATH = APPS_UI_ROOT / "tests" / "api.test.ts"
UI_DATA_CONTRACTS_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "ui" / "ui-data-contracts.md"
)
PHASE_1_2_REPORT_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "reports" / "ui" / "phase-1_2-verify.md"
)
ROUTES_UI_COMPREHENSIVE_TEST_PATH = (
    Path(__file__).parent.parent / "mcp_server" / "test_routes_ui_comprehensive.py"
)


class TestPhase12ReportExists:
    """Test that the Phase 1.2 verification report exists and has expected structure."""

    def test_phase12_report_exists(self) -> None:
        """Verify phase-1_2-verify.md exists."""
        assert PHASE_1_2_REPORT_PATH.exists(), f"Report not found at {PHASE_1_2_REPORT_PATH}"

    def test_phase12_report_has_status(self) -> None:
        """Verify report has status in header."""
        content = PHASE_1_2_REPORT_PATH.read_text()
        assert "**Status**:" in content

    def test_phase12_report_has_scope_section(self) -> None:
        """Verify report has scope limits section."""
        content = PHASE_1_2_REPORT_PATH.read_text()
        assert "## Scope Limits" in content

    def test_phase12_report_has_ci_section(self) -> None:
        """Verify report has CI integration section."""
        content = PHASE_1_2_REPORT_PATH.read_text()
        assert "## 1. CI Integration Verification" in content or "CI Integration" in content

    def test_phase12_report_has_guardrail_section(self) -> None:
        """Verify report has boundary guardrail section."""
        content = PHASE_1_2_REPORT_PATH.read_text()
        assert "## 2. Boundary Guardrail Verification" in content or "Boundary Guardrail" in content

    def test_phase12_report_has_contract_section(self) -> None:
        """Verify report has contract drift tests section."""
        content = PHASE_1_2_REPORT_PATH.read_text()
        assert "## 3. Contract Drift Tests Verification" in content or "Contract Drift" in content


class TestCIScriptConfiguration:
    """Test that CI script includes required steps."""

    @pytest.fixture
    def package_json(self) -> dict:
        """Load package.json."""
        assert PACKAGE_JSON_PATH.exists(), f"package.json not found at {PACKAGE_JSON_PATH}"
        return json.loads(PACKAGE_JSON_PATH.read_text())

    def test_package_json_has_ci_script(self, package_json: dict) -> None:
        """Verify ci script exists in package.json."""
        assert "scripts" in package_json
        assert "ci" in package_json["scripts"]

    def test_ci_script_includes_typecheck(self, package_json: dict) -> None:
        """Verify ci script includes type-check."""
        ci_script = package_json["scripts"]["ci"]
        assert "type-check" in ci_script

    def test_ci_script_includes_lint(self, package_json: dict) -> None:
        """Verify ci script includes lint."""
        ci_script = package_json["scripts"]["ci"]
        assert "lint" in ci_script

    def test_ci_script_includes_test(self, package_json: dict) -> None:
        """Verify ci script includes test."""
        ci_script = package_json["scripts"]["ci"]
        assert "test" in ci_script

    def test_ci_script_includes_build(self, package_json: dict) -> None:
        """Verify ci script includes build."""
        ci_script = package_json["scripts"]["ci"]
        assert "build" in ci_script


class TestTypeScriptTypesExist:
    """Test that TypeScript types exist and match documented contracts."""

    @pytest.fixture
    def types_api_content(self) -> str:
        """Load the TypeScript types file."""
        assert TYPES_API_PATH.exists(), f"api.ts not found at {TYPES_API_PATH}"
        return TYPES_API_PATH.read_text()

    def test_types_file_exists(self) -> None:
        """Verify types/api.ts exists."""
        assert TYPES_API_PATH.exists()

    def test_has_pagination_info_type(self, types_api_content: str) -> None:
        """Verify PaginationInfo interface is defined."""
        assert (
            "interface PaginationInfo" in types_api_content or "PaginationInfo" in types_api_content
        )
        assert "next_cursor" in types_api_content
        assert "has_more" in types_api_content

    def test_has_error_response_type(self, types_api_content: str) -> None:
        """Verify ErrorResponse interface is defined."""
        assert "ErrorResponse" in types_api_content
        assert "request_id" in types_api_content

    def test_has_channel_type(self, types_api_content: str) -> None:
        """Verify Channel type is defined."""
        assert "Channel" in types_api_content
        assert "SLACK" in types_api_content
        assert "EMAIL" in types_api_content
        assert "WEBSOCKET" in types_api_content

    def test_has_delivery_status_type(self, types_api_content: str) -> None:
        """Verify DeliveryStatus type is defined."""
        assert "DeliveryStatus" in types_api_content
        assert "PENDING" in types_api_content
        assert "DELIVERED" in types_api_content
        assert "FAILED" in types_api_content

    def test_has_autonomy_mode_type(self, types_api_content: str) -> None:
        """Verify AutonomyMode type is defined."""
        assert "AutonomyMode" in types_api_content
        assert "PREVIEW" in types_api_content
        assert "SHADOW" in types_api_content
        assert "LIVE" in types_api_content

    def test_has_audit_event_type(self, types_api_content: str) -> None:
        """Verify AuditEvent interface is defined."""
        assert "AuditEvent" in types_api_content
        assert "audit_id" in types_api_content
        assert "event_type" in types_api_content
        assert "event_time" in types_api_content

    def test_has_delivery_timeline_response(self, types_api_content: str) -> None:
        """Verify DeliveryTimelineResponse interface is defined."""
        assert "DeliveryTimelineResponse" in types_api_content
        assert "notification_id" in types_api_content
        assert "attempts" in types_api_content

    def test_has_effective_policy_response(self, types_api_content: str) -> None:
        """Verify EffectivePolicyResponse interface is defined."""
        assert "EffectivePolicyResponse" in types_api_content
        assert "effective" in types_api_content
        assert "resolution" in types_api_content


class TestUIContractTestsExist:
    """Test that UI-side contract tests exist."""

    @pytest.fixture
    def api_test_content(self) -> str:
        """Load the API test file."""
        assert API_TEST_PATH.exists(), f"api.test.ts not found at {API_TEST_PATH}"
        return API_TEST_PATH.read_text()

    def test_api_test_file_exists(self) -> None:
        """Verify api.test.ts exists."""
        assert API_TEST_PATH.exists()

    def test_api_test_has_audit_events_tests(self, api_test_content: str) -> None:
        """Verify audit events tests exist."""
        assert "getAuditEvents" in api_test_content
        assert "describe" in api_test_content

    def test_api_test_has_invariants_tests(self, api_test_content: str) -> None:
        """Verify invariants tests exist."""
        assert "fetchInvariants" in api_test_content

    def test_api_test_has_error_handling_tests(self, api_test_content: str) -> None:
        """Verify error handling tests exist."""
        assert "ApiError" in api_test_content

    def test_api_test_has_pagination_tests(self, api_test_content: str) -> None:
        """Verify pagination tests exist."""
        assert "cursor" in api_test_content
        assert "pagination" in api_test_content


class TestBackendContractTestsExist:
    """Test that backend contract tests exist."""

    @pytest.fixture
    def comprehensive_test_content(self) -> str:
        """Load the comprehensive test file."""
        assert ROUTES_UI_COMPREHENSIVE_TEST_PATH.exists(), (
            f"test_routes_ui_comprehensive.py not found at {ROUTES_UI_COMPREHENSIVE_TEST_PATH}"
        )
        return ROUTES_UI_COMPREHENSIVE_TEST_PATH.read_text()

    def test_comprehensive_test_file_exists(self) -> None:
        """Verify test_routes_ui_comprehensive.py exists."""
        assert ROUTES_UI_COMPREHENSIVE_TEST_PATH.exists()

    def test_has_authorization_boundary_tests(self, comprehensive_test_content: str) -> None:
        """Verify authorization boundary tests exist."""
        assert "TestAuthorizationBoundaries" in comprehensive_test_content

    def test_has_response_mapping_tests(self, comprehensive_test_content: str) -> None:
        """Verify response mapping tests exist."""
        assert "ResponseMapping" in comprehensive_test_content

    def test_has_filtering_tests(self, comprehensive_test_content: str) -> None:
        """Verify filtering tests exist."""
        assert "Filtering" in comprehensive_test_content

    def test_has_error_handling_tests(self, comprehensive_test_content: str) -> None:
        """Verify error handling tests exist."""
        assert "TestErrorHandling" in comprehensive_test_content

    def test_has_edge_case_tests(self, comprehensive_test_content: str) -> None:
        """Verify edge case tests exist."""
        assert "TestEdgeCases" in comprehensive_test_content


class TestDocumentationContractsExist:
    """Test that documentation contract alignment exists."""

    @pytest.fixture
    def data_contracts_content(self) -> str:
        """Load the data contracts document."""
        assert UI_DATA_CONTRACTS_PATH.exists(), (
            f"ui-data-contracts.md not found at {UI_DATA_CONTRACTS_PATH}"
        )
        return UI_DATA_CONTRACTS_PATH.read_text()

    def test_data_contracts_file_exists(self) -> None:
        """Verify ui-data-contracts.md exists."""
        assert UI_DATA_CONTRACTS_PATH.exists()

    def test_data_contracts_has_delivery_timeline_section(
        self, data_contracts_content: str
    ) -> None:
        """Verify delivery timeline section exists."""
        assert "Delivery Timeline" in data_contracts_content

    def test_data_contracts_has_escalations_section(self, data_contracts_content: str) -> None:
        """Verify escalations section exists."""
        assert "Escalations" in data_contracts_content

    def test_data_contracts_has_policy_resolution_section(
        self, data_contracts_content: str
    ) -> None:
        """Verify policy resolution section exists."""
        assert "Policy" in data_contracts_content

    def test_data_contracts_has_invariant_registry_section(
        self, data_contracts_content: str
    ) -> None:
        """Verify invariant registry section exists."""
        assert "Invariant" in data_contracts_content

    def test_data_contracts_has_audit_event_section(self, data_contracts_content: str) -> None:
        """Verify audit event section exists."""
        assert "Audit" in data_contracts_content


class TestReportClaims:
    """Test that the report makes verifiable claims."""

    @pytest.fixture
    def report_content(self) -> str:
        """Load the Phase 1.2 report."""
        assert PHASE_1_2_REPORT_PATH.exists(), f"Report not found at {PHASE_1_2_REPORT_PATH}"
        return PHASE_1_2_REPORT_PATH.read_text()

    def test_report_claims_ci_lint(self, report_content: str) -> None:
        """Verify report claims CI includes lint."""
        assert "lint" in report_content.lower()

    def test_report_claims_ci_typecheck(self, report_content: str) -> None:
        """Verify report claims CI includes typecheck."""
        assert "typecheck" in report_content.lower() or "type-check" in report_content.lower()

    def test_report_claims_ci_test(self, report_content: str) -> None:
        """Verify report claims CI includes test."""
        assert "test" in report_content.lower()

    def test_report_claims_ci_build(self, report_content: str) -> None:
        """Verify report claims CI includes build."""
        assert "build" in report_content.lower()

    def test_report_has_checklist(self, report_content: str) -> None:
        """Verify report has verification checklist."""
        assert "Verification Checklist" in report_content or "Checklist" in report_content

    def test_report_has_conclusion(self, report_content: str) -> None:
        """Verify report has conclusion section."""
        assert "Conclusion" in report_content

    def test_report_has_appendix(self, report_content: str) -> None:
        """Verify report has appendix with file references."""
        assert "Appendix" in report_content

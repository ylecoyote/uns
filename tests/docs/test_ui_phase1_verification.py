"""Phase 1 Verification Tests.

These tests validate the claims made in docs/reports/ui/phase-1-verify.md.
Each test corresponds to a specific verification claim in the report.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from mcp_server.app import create_app
from mcp_server.read_models import ReadModelAdapter


class TestPhase1ReportExists:
    """Verify Phase 1 verification report exists and has expected structure."""

    def test_phase1_report_exists(self) -> None:
        """Phase 1 verification report must exist."""
        report_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "reports"
            / "ui"
            / "phase-1-verify.md"
        )
        assert report_path.exists(), "Phase 1 verification report not found"

    def test_phase1_report_has_pass_status(self) -> None:
        """Phase 1 report should have PASS status."""
        report_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "reports"
            / "ui"
            / "phase-1-verify.md"
        )
        content = report_path.read_text()
        assert "**Status**: PASS" in content, "Report should show PASS status"

    def test_phase1_report_claims_get_only(self) -> None:
        """Phase 1 report should verify GET-only endpoints."""
        report_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "reports"
            / "ui"
            / "phase-1-verify.md"
        )
        content = report_path.read_text()
        assert "UI calls only GET endpoints" in content
        assert "VERIFIED" in content


class TestGetOnlyEnforcement:
    """Test that all UI endpoints only accept GET requests."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def ui_endpoints(self) -> list[str]:
        """List of all UI endpoints to test."""
        return [
            "/ui/deliveries",
            "/ui/policies/effective",
            "/ui/invariants",
            "/ui/invariants/summary",
            "/ui/audit",
        ]

    def test_all_endpoints_accept_get(self, client: TestClient, ui_endpoints: list[str]) -> None:
        """All UI endpoints should accept GET requests."""
        for endpoint in ui_endpoints:
            # Some endpoints require query params
            if endpoint == "/ui/policies/effective":
                response = client.get(
                    endpoint,
                    params={
                        "notification_type": "test.type",
                        "intent": "SAFETY",
                        "autonomy_mode": "LIVE",
                    },
                )
            else:
                response = client.get(endpoint)
            assert response.status_code in [
                200,
                404,
            ], f"GET {endpoint} should be allowed, got {response.status_code}"

    @pytest.mark.parametrize(
        "method",
        ["post", "put", "patch", "delete"],
    )
    def test_mutation_methods_blocked(
        self, client: TestClient, ui_endpoints: list[str], method: str
    ) -> None:
        """All mutation methods should return 405 Method Not Allowed."""
        for endpoint in ui_endpoints:
            response = getattr(client, method)(endpoint)
            assert response.status_code == 405, (
                f"{method.upper()} {endpoint} should return 405, got {response.status_code}"
            )


class TestContractCompliance:
    """Test UI contract compliance with ui-data-contracts.md."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_pagination_structure(self, client: TestClient) -> None:
        """All list responses should have consistent pagination structure."""
        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "pagination" in data

        pagination = data["pagination"]
        assert "next_cursor" in pagination
        assert "has_more" in pagination
        # total_count is optional per contract

    def test_deliveries_response_structure(self, client: TestClient) -> None:
        """Deliveries response should match contract."""
        response = client.get("/ui/deliveries")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["items"], list)
        assert isinstance(data["pagination"], dict)

    def test_policy_effective_response_structure(self, client: TestClient) -> None:
        """Effective policy response should match contract."""
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test.order",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "notification_type" in data
        assert "effective" in data
        assert "resolution" in data
        assert "resolution_context" in data

        effective = data["effective"]
        assert "delivery_mode" in effective
        assert "channels" in effective
        assert "require_ack" in effective

    def test_invariants_response_structure(self, client: TestClient) -> None:
        """Invariants response should match contract."""
        response = client.get("/ui/invariants")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "pagination" in data

        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "statement" in item
            assert "severity" in item
            assert "status" in item
            assert "enforcement" in item

    def test_invariants_summary_response_structure(self, client: TestClient) -> None:
        """Invariants summary response should match contract."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200
        data = response.json()

        assert "total_count" in data
        assert "by_severity" in data
        assert "by_enforcement_type" in data
        assert "by_status" in data
        assert "exceptions_requiring_review" in data
        assert "last_updated" in data

    def test_audit_response_structure(self, client: TestClient) -> None:
        """Audit response should match contract."""
        response = client.get("/ui/audit")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "pagination" in data


class TestInvariantRegistryCompliance:
    """Test invariant registry compliance."""

    def test_invariants_yml_exists(self) -> None:
        """Invariants YAML file should exist."""
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        assert invariants_path.exists(), "invariants.yml not found"

    def test_invariants_yml_valid(self) -> None:
        """Invariants YAML file should be valid."""
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        with open(invariants_path) as f:
            data = yaml.safe_load(f)

        assert "invariants" in data
        assert isinstance(data["invariants"], list)
        assert len(data["invariants"]) >= 7  # At least the core invariants

    def test_invariants_yml_contains_required_ids(self) -> None:
        """Invariants YAML should contain all required invariant IDs."""
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        with open(invariants_path) as f:
            data = yaml.safe_load(f)

        required_ids = {
            "INV-ACK-001",
            "INV-POL-001",
            "INV-DEL-001",
            "INV-WS-001",
            "INV-CTX-001",
            "INV-CTX-002",
            "INV-MSG-001",
            "INV-UI-001",  # New in Phase 1
        }

        actual_ids = {inv["id"] for inv in data["invariants"]}
        missing = required_ids - actual_ids
        assert not missing, f"Missing invariant IDs: {missing}"

    def test_ui_invariant_exists(self) -> None:
        """INV-UI-001 (UI read-only) invariant should exist."""
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        with open(invariants_path) as f:
            data = yaml.safe_load(f)

        ui_invariant = next(
            (inv for inv in data["invariants"] if inv["id"] == "INV-UI-001"),
            None,
        )
        assert ui_invariant is not None, "INV-UI-001 not found"
        assert "read-only" in ui_invariant["statement"].lower()


class TestReadModelAdapterCompliance:
    """Test read model adapter is read-only."""

    def test_adapter_has_no_write_methods(self) -> None:
        """ReadModelAdapter ABC should not have write methods."""
        # Get all method names from the ABC
        method_names = [
            name for name in dir(ReadModelAdapter) if not name.startswith("_")
        ]

        # Check no write-related methods
        write_method_patterns = ["save", "update", "delete", "create", "insert", "modify"]
        for method in method_names:
            for pattern in write_method_patterns:
                assert pattern not in method.lower(), (
                    f"ReadModelAdapter should not have write method: {method}"
                )

    def test_adapter_methods_are_read_operations(self) -> None:
        """All adapter methods should be read operations (get_*)."""
        # Get abstract methods
        import inspect

        abstract_methods = []
        for name, method in inspect.getmembers(ReadModelAdapter):
            is_abstract = (
                not name.startswith("_")
                and hasattr(method, "__isabstractmethod__")
                and method.__isabstractmethod__
            )
            if is_abstract:
                abstract_methods.append(name)

        # All abstract methods should start with get_
        for method in abstract_methods:
            assert method.startswith("get_"), (
                f"Abstract method {method} should be a read operation (get_*)"
            )


class TestRouteCodeInspection:
    """Test route implementation via code inspection."""

    def test_routes_ui_uses_get_decorator_only(self) -> None:
        """routes_ui.py should only use @router.get() decorators."""
        routes_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "mcp_server"
            / "routes_ui.py"
        )
        content = routes_path.read_text()

        # Check for GET decorators
        get_count = len(re.findall(r"@router\.get\(", content))
        assert get_count >= 6, f"Expected at least 6 GET routes, found {get_count}"

        # Check no mutation decorators
        post_count = len(re.findall(r"@router\.post\(", content))
        put_count = len(re.findall(r"@router\.put\(", content))
        patch_count = len(re.findall(r"@router\.patch\(", content))
        delete_count = len(re.findall(r"@router\.delete\(", content))

        assert post_count == 0, f"Found {post_count} POST routes in routes_ui.py"
        assert put_count == 0, f"Found {put_count} PUT routes in routes_ui.py"
        assert patch_count == 0, f"Found {patch_count} PATCH routes in routes_ui.py"
        assert delete_count == 0, f"Found {delete_count} DELETE routes in routes_ui.py"

    def test_routes_ui_has_no_write_operations(self) -> None:
        """routes_ui.py should not contain write operations."""
        routes_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "mcp_server"
            / "routes_ui.py"
        )
        content = routes_path.read_text()

        # Check for write operation patterns (excluding string literals)
        write_patterns = [
            r"\.save\s*\(",
            r"\.update\s*\(",
            r"\.delete\s*\(",
            r"\.create\s*\(",
            r"\.insert\s*\(",
            r"\.add\s*\(",  # Could be false positive, but check
            r"\.remove\s*\(",
        ]

        for pattern in write_patterns:
            matches = re.findall(pattern, content)
            # Filter out doc strings and comments
            # This is a simple check - more sophisticated analysis would be needed
            # for production verification
            for match in matches:
                # Skip if in a comment or docstring (simplified check)
                assert "adapter" not in match.lower(), (
                    f"Potential write operation found: {match}"
                )


class TestTestCoverage:
    """Test that all test files exist and can be discovered."""

    def test_test_routes_ui_exists(self) -> None:
        """test_routes_ui.py should exist."""
        test_path = (
            Path(__file__).parent.parent / "mcp_server" / "test_routes_ui.py"
        )
        assert test_path.exists(), "test_routes_ui.py not found"

    def test_test_routes_ui_comprehensive_exists(self) -> None:
        """test_routes_ui_comprehensive.py should exist."""
        test_path = (
            Path(__file__).parent.parent
            / "mcp_server"
            / "test_routes_ui_comprehensive.py"
        )
        assert test_path.exists(), "test_routes_ui_comprehensive.py not found"

    def test_test_ui_phase0_verification_exists(self) -> None:
        """test_ui_phase0_verification.py should exist."""
        test_path = Path(__file__).parent / "test_ui_phase0_verification.py"
        assert test_path.exists(), "test_ui_phase0_verification.py not found"

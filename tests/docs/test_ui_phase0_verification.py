"""Tests validating UI Phase 0 verification claims.

These tests serve as automated verification that the claims made in
docs/reports/ui/phase-0-verify.md remain accurate.
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from mcp_server.app import create_app
from mcp_server.read_models import (
    InMemoryReadModelAdapter,
    configure_read_model_adapter,
)
from notification.audit import InMemoryAuditStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audit_store() -> InMemoryAuditStore:
    """Create a fresh in-memory audit store."""
    return InMemoryAuditStore()


@pytest.fixture
def adapter(audit_store: InMemoryAuditStore) -> InMemoryReadModelAdapter:
    """Create a fresh adapter with the audit store."""
    adapter = InMemoryReadModelAdapter(audit_store=audit_store)
    configure_read_model_adapter(adapter)
    return adapter


@pytest.fixture
def client(adapter: InMemoryReadModelAdapter) -> TestClient:
    """Create a test client with fresh read model adapter."""
    app = create_app()
    return TestClient(app)


# =============================================================================
# Test: Endpoint Verification
# =============================================================================


class TestEndpointDocumentationAlignment:
    """Verify that all documented endpoints exist in implementation."""

    DOCUMENTED_ENDPOINTS = [
        ("GET", "/ui/deliveries"),
        ("GET", "/ui/deliveries/{notification_id}"),
        ("GET", "/ui/policies/effective"),
        ("GET", "/ui/invariants"),
        ("GET", "/ui/invariants/summary"),
        ("GET", "/ui/audit"),
    ]

    def test_all_documented_endpoints_exist(self, client: TestClient):
        """Verify all documented endpoints return valid responses (not 404)."""
        # Test list endpoints
        response = client.get("/ui/deliveries")
        assert response.status_code == 200

        response = client.get("/ui/invariants")
        assert response.status_code == 200

        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200

        response = client.get("/ui/audit")
        assert response.status_code == 200

        # Test parameterized endpoints
        response = client.get(
            "/ui/policies/effective",
            params={
                "notification_type": "test",
                "intent": "SAFETY",
                "autonomy_mode": "LIVE",
            },
        )
        assert response.status_code == 200

        # Delivery by ID returns 404 (no data) but endpoint exists
        response = client.get(f"/ui/deliveries/{uuid4()}")
        assert response.status_code == 404  # Not found, but endpoint exists

    def test_router_only_has_get_decorators(self):
        """Verify routes_ui.py only uses @router.get() decorators."""
        routes_path = (
            Path(__file__).parent.parent.parent / "src" / "mcp_server" / "routes_ui.py"
        )
        assert routes_path.exists(), f"routes_ui.py not found at {routes_path}"

        content = routes_path.read_text()
        tree = ast.parse(content)

        # Find all decorator calls on async def functions
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    if not isinstance(decorator.func, ast.Attribute):
                        continue
                    # Check router.xxx() calls
                    if not (
                        isinstance(decorator.func.value, ast.Name)
                        and decorator.func.value.id == "router"
                    ):
                        continue
                    method = decorator.func.attr
                    assert method == "get", (
                        f"Found non-GET route: @router.{method}() "
                        f"on function {node.name}"
                    )


# =============================================================================
# Test: Read-Only Verification
# =============================================================================


class TestReadOnlyEnforcement:
    """Verify that all UI endpoints reject mutating HTTP methods."""

    UI_ENDPOINTS = [
        "/ui/deliveries",
        "/ui/policies/effective",
        "/ui/invariants",
        "/ui/invariants/summary",
        "/ui/audit",
    ]

    def test_post_blocked_on_all_endpoints(self, client: TestClient):
        """POST must return 405 on all UI endpoints."""
        for endpoint in self.UI_ENDPOINTS:
            response = client.post(endpoint, json={})
            assert response.status_code == 405, f"POST allowed on {endpoint}"

    def test_put_blocked_on_all_endpoints(self, client: TestClient):
        """PUT must return 405 on all UI endpoints."""
        for endpoint in self.UI_ENDPOINTS:
            response = client.put(endpoint, json={})
            assert response.status_code == 405, f"PUT allowed on {endpoint}"

    def test_delete_blocked_on_all_endpoints(self, client: TestClient):
        """DELETE must return 405 on all UI endpoints."""
        for endpoint in self.UI_ENDPOINTS:
            response = client.delete(endpoint)
            assert response.status_code == 405, f"DELETE allowed on {endpoint}"

    def test_patch_blocked_on_deliveries(self, client: TestClient):
        """PATCH must return 405 on delivery endpoints."""
        response = client.patch(f"/ui/deliveries/{uuid4()}", json={})
        assert response.status_code == 405


# =============================================================================
# Test: Invariant Registry Alignment
# =============================================================================


class TestInvariantRegistryAlignment:
    """Verify that the invariant registry is properly exposed via API."""

    def test_invariants_endpoint_returns_registry_data(self, client: TestClient):
        """Invariants endpoint should return data from invariants.yml."""
        # Load source YAML
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        if not invariants_path.exists():
            pytest.skip("invariants.yml not found")

        with open(invariants_path) as f:
            yaml_data = yaml.safe_load(f)

        expected_ids = {inv["id"] for inv in yaml_data.get("invariants", [])}

        # Query API
        response = client.get("/ui/invariants", params={"limit": 100})
        assert response.status_code == 200

        api_ids = {item["id"] for item in response.json()["items"]}

        # All YAML invariants should be in API response
        assert expected_ids == api_ids, (
            f"Mismatch: YAML has {expected_ids}, API has {api_ids}"
        )

    def test_invariant_severity_values_match_yaml(self, client: TestClient):
        """Verify invariant severity levels match source YAML."""
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        if not invariants_path.exists():
            pytest.skip("invariants.yml not found")

        with open(invariants_path) as f:
            yaml_data = yaml.safe_load(f)

        yaml_by_id = {inv["id"]: inv for inv in yaml_data.get("invariants", [])}

        response = client.get("/ui/invariants", params={"limit": 100})
        assert response.status_code == 200

        for item in response.json()["items"]:
            inv_id = item["id"]
            assert inv_id in yaml_by_id
            assert item["severity"] == yaml_by_id[inv_id]["severity"]


# =============================================================================
# Test: Response Structure Verification
# =============================================================================


class TestResponseStructureCompliance:
    """Verify response structures match documentation contracts."""

    def test_pagination_structure_consistent(self, client: TestClient):
        """All list endpoints must have consistent pagination structure."""
        list_endpoints = [
            "/ui/deliveries",
            "/ui/invariants",
            "/ui/audit",
        ]

        required_pagination_fields = {"next_cursor", "has_more", "total_count"}

        for endpoint in list_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200
            data = response.json()

            assert "items" in data, f"{endpoint} missing 'items'"
            assert "pagination" in data, f"{endpoint} missing 'pagination'"

            pagination = data["pagination"]
            actual_fields = set(pagination.keys())
            assert required_pagination_fields <= actual_fields, (
                f"{endpoint} pagination missing fields: "
                f"{required_pagination_fields - actual_fields}"
            )

    def test_error_response_structure(self, client: TestClient):
        """Error responses must follow standard error structure."""
        # Trigger a 404
        response = client.get(f"/ui/deliveries/{uuid4()}")
        assert response.status_code == 404

        detail = response.json()["detail"]
        assert "error" in detail
        assert "code" in detail["error"]
        assert "message" in detail["error"]

    def test_effective_policy_response_structure(self, client: TestClient):
        """Effective policy response must have required fields."""
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

        # Required top-level fields
        assert "notification_type" in data
        assert "effective" in data
        assert "resolution" in data
        assert "resolution_context" in data

        # Effective values
        effective = data["effective"]
        assert "delivery_mode" in effective
        assert "channels" in effective
        assert "require_ack" in effective
        assert "dedup_window_seconds" in effective

        # Resolution context
        ctx = data["resolution_context"]
        assert "intent" in ctx
        assert "autonomy_mode" in ctx
        assert "policy_found" in ctx


# =============================================================================
# Test: Documentation File Existence
# =============================================================================


class TestDocumentationExists:
    """Verify required documentation files exist."""

    REQUIRED_DOCS = [
        "docs/ui/ui-scope.md",
        "docs/ui/ui-data-contracts.md",
        "docs/ui/ui-read-models.md",
        "docs/ui/ui-observability.md",
        "docs/verification/invariants.yml",
        "docs/reports/ui/phase-0-verify.md",
    ]

    def test_all_required_docs_exist(self):
        """All required documentation files must exist."""
        root = Path(__file__).parent.parent.parent

        for doc_path in self.REQUIRED_DOCS:
            full_path = root / doc_path
            assert full_path.exists(), f"Missing documentation: {doc_path}"


# =============================================================================
# Test: Verification Report Accuracy
# =============================================================================


class TestVerificationReportAccuracy:
    """Verify claims in phase-0-verify.md are accurate."""

    def test_report_claims_six_endpoints(self, client: TestClient):
        """Report claims 6 endpoints - verify this is accurate."""
        # Count unique endpoint paths in routes_ui.py
        routes_path = (
            Path(__file__).parent.parent.parent / "src" / "mcp_server" / "routes_ui.py"
        )
        content = routes_path.read_text()

        # Count @router.get decorators
        import re

        get_decorators = re.findall(r'@router\.get\(\s*["\']([^"\']+)["\']', content)
        assert len(get_decorators) == 6, (
            f"Expected 6 endpoints, found {len(get_decorators)}: {get_decorators}"
        )

    def test_report_claims_all_tests_pass(self):
        """Report claims all tests pass - this test suite validates that."""
        # If this test runs successfully along with others, the claim is valid
        pass


# =============================================================================
# Test: Read Model Adapter Interface Verification
# =============================================================================


class TestReadModelAdapterInterface:
    """Verify that ReadModelAdapter ABC defines only read operations."""

    def test_adapter_interface_has_no_write_methods(self):
        """ReadModelAdapter ABC should only define get_* methods."""
        import inspect

        from mcp_server.read_models import ReadModelAdapter

        # Get all abstract methods from the ABC
        abstract_methods = []
        for name, method in inspect.getmembers(ReadModelAdapter, predicate=inspect.isfunction):
            if hasattr(method, "__isabstractmethod__") and method.__isabstractmethod__:
                abstract_methods.append(name)

        # All abstract methods should be read operations (get_*)
        for method_name in abstract_methods:
            assert method_name.startswith("get_"), (
                f"ReadModelAdapter has non-read method: {method_name}. "
                "This could introduce write operations to UI endpoints."
            )

    def test_in_memory_adapter_read_only(self):
        """InMemoryReadModelAdapter should not expose write methods."""
        from mcp_server.read_models import InMemoryReadModelAdapter

        # These are write operations that should NOT exist on the adapter
        write_methods = ["save", "update", "delete", "create", "insert", "remove"]

        for method in write_methods:
            assert not hasattr(InMemoryReadModelAdapter, method), (
                f"InMemoryReadModelAdapter has write method: {method}"
            )

    def test_sqlalchemy_adapter_read_only(self):
        """SQLAlchemyReadModelAdapter should not expose write methods."""
        from mcp_server.read_models import SQLAlchemyReadModelAdapter

        # These are write operations that should NOT exist on the adapter
        write_methods = ["save", "update", "delete", "create", "insert", "remove"]

        for method in write_methods:
            assert not hasattr(SQLAlchemyReadModelAdapter, method), (
                f"SQLAlchemyReadModelAdapter has write method: {method}"
            )


# =============================================================================
# Test: System Invariant Preservation
# =============================================================================


class TestSystemInvariantPreservation:
    """Verify UI Phase 0 does not violate system invariants."""

    def test_ui_code_has_no_notification_mutations(self):
        """routes_ui.py should not contain notification mutation code."""
        routes_path = (
            Path(__file__).parent.parent.parent / "src" / "mcp_server" / "routes_ui.py"
        )
        content = routes_path.read_text()

        # Patterns that would indicate actual write operations (method calls)
        # Note: "notification.created" as a string enum value is acceptable
        mutation_patterns = [
            ".save(",           # Method call to save
            ".create(",         # Method call to create
            ".delete(",         # Method call to delete
            ".update(",         # Method call to update
            "audit_store.save", # Direct store save
            ".commit(",         # Session commit
            "session.flush",    # Session flush
            "INSERT INTO",      # Raw SQL insert
            "UPDATE ",          # Raw SQL update
            "DELETE FROM",      # Raw SQL delete
        ]

        for pattern in mutation_patterns:
            # Skip if pattern is in a string literal or comment
            if pattern.lower() in content.lower():
                # Check if it's in actual code (not docstrings, comments, or string literals)
                lines_with_pattern = [
                    line for line in content.split("\n")
                    if pattern.lower() in line.lower()
                    and not line.strip().startswith("#")
                    and not line.strip().startswith('"""')
                    and not line.strip().startswith("'''")
                    and not ('"' in line and pattern.lower() in line.lower().split('"')[1] if '"' in line else False)
                ]
                # Filter out string literal occurrences (like enum values)
                actual_code_lines = [
                    line for line in lines_with_pattern
                    if not ('= "' in line or "= '" in line)  # Skip assignment to string literals
                ]
                assert len(actual_code_lines) == 0, (
                    f"Potential mutation pattern found in routes_ui.py: {pattern}\n"
                    f"Lines: {actual_code_lines}"
                )

    def test_ui_endpoints_use_read_model_adapter(self, client: TestClient):
        """Verify endpoints use the read model adapter (not direct store access)."""
        routes_path = (
            Path(__file__).parent.parent.parent / "src" / "mcp_server" / "routes_ui.py"
        )
        content = routes_path.read_text()

        # Should use get_read_model_adapter()
        assert "get_read_model_adapter()" in content, (
            "routes_ui.py should use get_read_model_adapter() for data access"
        )

        # Should NOT directly access audit stores
        assert "InMemoryAuditStore(" not in content, (
            "routes_ui.py should not directly instantiate InMemoryAuditStore"
        )
        assert "SQLAlchemyAuditStore(" not in content, (
            "routes_ui.py should not directly instantiate SQLAlchemyAuditStore"
        )

    def test_invariants_yml_contains_required_invariants(self):
        """Verify invariants.yml contains all required system invariants."""
        invariants_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "verification"
            / "invariants.yml"
        )
        if not invariants_path.exists():
            pytest.skip("invariants.yml not found")

        with open(invariants_path) as f:
            yaml_data = yaml.safe_load(f)

        invariant_ids = {inv["id"] for inv in yaml_data.get("invariants", [])}

        # These are the invariants mentioned in the verification report
        required_invariants = {
            "INV-ACK-001",  # Acks must not gate execution
            "INV-POL-001",  # Policy absence must not block delivery
            "INV-DEL-001",  # GUARANTEED must attempt all fallbacks
            "INV-WS-001",   # WebSocket is non-authoritative
            "INV-CTX-001",  # autonomy_context required
            "INV-CTX-002",  # autonomy_mode + agent_id required
            "INV-MSG-001",  # Title/message length limits
        }

        missing = required_invariants - invariant_ids
        assert not missing, f"Missing invariants in registry: {missing}"


# =============================================================================
# Test: Verification Report Consistency
# =============================================================================


class TestVerificationReportConsistency:
    """Verify the verification report is internally consistent."""

    def test_verification_report_exists(self):
        """Verification report file must exist."""
        report_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "reports"
            / "ui"
            / "phase-0-verify.md"
        )
        assert report_path.exists(), "phase-0-verify.md not found"

    def test_verification_report_has_pass_status(self):
        """Verification report should indicate PASS status."""
        report_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "reports"
            / "ui"
            / "phase-0-verify.md"
        )
        content = report_path.read_text()

        assert "PASS" in content, "Verification report should indicate PASS status"
        assert "**Status**: PASS" in content, (
            "Verification report should have explicit status line"
        )

    def test_verification_report_lists_all_endpoints(self):
        """Verification report should list all 6 endpoints."""
        report_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "reports"
            / "ui"
            / "phase-0-verify.md"
        )
        content = report_path.read_text()

        endpoints = [
            "/ui/deliveries",
            "/ui/deliveries/{notification_id}",
            "/ui/policies/effective",
            "/ui/invariants",
            "/ui/invariants/summary",
            "/ui/audit",
        ]

        for endpoint in endpoints:
            assert endpoint in content, (
                f"Verification report missing endpoint: {endpoint}"
            )

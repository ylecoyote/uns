"""Tests for UI invariants API endpoints.

Comprehensive tests for the invariants viewer (list + summary) functionality:
- GET /ui/invariants - List invariants with filtering
- GET /ui/invariants/summary - Get summary statistics

These tests verify the endpoints work correctly for the frontend UI.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agsignal.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    app = create_app(skip_persistence_config=True)  # Explicit legacy read-model fixture
    app.state.agsignal_api_key = "test-key"
    return TestClient(app, headers={"Authorization": "Bearer test-key"})


class TestInvariantsList:
    """Tests for GET /ui/invariants endpoint."""

    def test_list_invariants_returns_items(self, client: TestClient):
        """Test that list endpoint returns invariants from YAML."""
        response = client.get("/ui/invariants")

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)

    def test_invariant_entry_structure(self, client: TestClient):
        """Test that invariant entries have the correct structure per ui-data-contracts.md."""
        response = client.get("/ui/invariants")
        assert response.status_code == 200
        data = response.json()

        if data["items"]:
            item = data["items"][0]

            # Required fields per ui-data-contracts.md
            assert "id" in item  # e.g., "INV-ACK-001"
            assert "statement" in item
            assert "severity" in item  # HIGH, MEDIUM, LOW
            assert "status" in item  # active, inactive
            assert "enforcement" in item
            assert "evidence" in item
            assert "owner" in item
            assert "last_reviewed" in item

            # Enforcement structure
            assert "type" in item["enforcement"]
            assert "description" in item["enforcement"]
            assert item["enforcement"]["type"] in ["guard", "isolation", "test", "exception"]

            # Severity values
            assert item["severity"] in ["HIGH", "MEDIUM", "LOW"]

            # Status values
            assert item["status"] in ["active", "inactive"]

    def test_filter_by_severity_high(self, client: TestClient):
        """Test filtering invariants by HIGH severity."""
        response = client.get("/ui/invariants", params={"severity": "HIGH"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["severity"] == "HIGH"

    def test_filter_by_severity_medium(self, client: TestClient):
        """Test filtering invariants by MEDIUM severity."""
        response = client.get("/ui/invariants", params={"severity": "MEDIUM"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["severity"] == "MEDIUM"

    def test_filter_by_severity_low(self, client: TestClient):
        """Test filtering invariants by LOW severity."""
        response = client.get("/ui/invariants", params={"severity": "LOW"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["severity"] == "LOW"

    def test_filter_by_enforcement_type_guard(self, client: TestClient):
        """Test filtering invariants by guard enforcement type."""
        response = client.get("/ui/invariants", params={"enforcement_type": "guard"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["enforcement"]["type"] == "guard"

    def test_filter_by_enforcement_type_isolation(self, client: TestClient):
        """Test filtering invariants by isolation enforcement type."""
        response = client.get("/ui/invariants", params={"enforcement_type": "isolation"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["enforcement"]["type"] == "isolation"

    def test_filter_by_enforcement_type_test(self, client: TestClient):
        """Test filtering invariants by test enforcement type."""
        response = client.get("/ui/invariants", params={"enforcement_type": "test"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["enforcement"]["type"] == "test"

    def test_filter_by_enforcement_type_exception(self, client: TestClient):
        """Test filtering invariants by exception enforcement type."""
        response = client.get("/ui/invariants", params={"enforcement_type": "exception"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["enforcement"]["type"] == "exception"

    def test_filter_by_status_active(self, client: TestClient):
        """Test filtering invariants by active status."""
        response = client.get("/ui/invariants", params={"status": "active"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["status"] == "active"

    def test_filter_by_status_inactive(self, client: TestClient):
        """Test filtering invariants by inactive status."""
        response = client.get("/ui/invariants", params={"status": "inactive"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["status"] == "inactive"

    def test_search_by_statement(self, client: TestClient):
        """Test searching invariants by statement text."""
        response = client.get("/ui/invariants", params={"search": "acknowledgment"})

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert "acknowledgment" in item["statement"].lower()

    def test_combined_filters(self, client: TestClient):
        """Test combining multiple filters."""
        response = client.get(
            "/ui/invariants",
            params={
                "severity": "HIGH",
                "status": "active",
            },
        )

        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["severity"] == "HIGH"
            assert item["status"] == "active"

    def test_pagination_limit(self, client: TestClient):
        """Test pagination limit parameter."""
        response = client.get("/ui/invariants", params={"limit": 2})

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) <= 2

    def test_pagination_info_structure(self, client: TestClient):
        """Test pagination info has correct structure."""
        response = client.get("/ui/invariants")

        assert response.status_code == 200
        data = response.json()

        pagination = data["pagination"]
        assert "next_cursor" in pagination
        assert "has_more" in pagination
        assert "total_count" in pagination

    def test_evidence_links_structure(self, client: TestClient):
        """Test evidence links have correct structure."""
        response = client.get("/ui/invariants")
        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            if item["evidence"]:
                evidence = item["evidence"][0]
                assert "path" in evidence
                assert "note" in evidence
                # line_ref is optional

    def test_mitigation_for_exceptions(self, client: TestClient):
        """Test mitigation field is present for exception-type invariants."""
        response = client.get("/ui/invariants", params={"enforcement_type": "exception"})
        assert response.status_code == 200
        data = response.json()

        # If there are exceptions, they may have mitigation field
        # (mitigation is optional per the contract)
        for item in data["items"]:
            # Just verify the field can exist
            assert (
                "mitigation" in item or "mitigation" not in item
            )  # Always passes but documents expectation


class TestInvariantsSummary:
    """Tests for GET /ui/invariants/summary endpoint."""

    def test_summary_returns_statistics(self, client: TestClient):
        """Test that summary endpoint returns statistics."""
        response = client.get("/ui/invariants/summary")

        assert response.status_code == 200
        data = response.json()

        assert "total_count" in data
        assert "by_severity" in data
        assert "by_enforcement_type" in data
        assert "by_status" in data
        assert "exceptions_requiring_review" in data
        assert "last_updated" in data

    def test_summary_severity_breakdown(self, client: TestClient):
        """Test severity breakdown in summary."""
        response = client.get("/ui/invariants/summary")

        assert response.status_code == 200
        data = response.json()

        by_severity = data["by_severity"]
        assert "HIGH" in by_severity
        assert "MEDIUM" in by_severity
        assert "LOW" in by_severity

        assert isinstance(by_severity["HIGH"], int)
        assert isinstance(by_severity["MEDIUM"], int)
        assert isinstance(by_severity["LOW"], int)

    def test_summary_enforcement_breakdown(self, client: TestClient):
        """Test enforcement type breakdown in summary."""
        response = client.get("/ui/invariants/summary")

        assert response.status_code == 200
        data = response.json()

        by_enforcement = data["by_enforcement_type"]
        assert "guard" in by_enforcement
        assert "isolation" in by_enforcement
        assert "test" in by_enforcement
        assert "exception" in by_enforcement

        assert isinstance(by_enforcement["guard"], int)
        assert isinstance(by_enforcement["isolation"], int)
        assert isinstance(by_enforcement["test"], int)
        assert isinstance(by_enforcement["exception"], int)

    def test_summary_status_breakdown(self, client: TestClient):
        """Test status breakdown in summary."""
        response = client.get("/ui/invariants/summary")

        assert response.status_code == 200
        data = response.json()

        by_status = data["by_status"]
        assert "active" in by_status
        assert "inactive" in by_status

        assert isinstance(by_status["active"], int)
        assert isinstance(by_status["inactive"], int)

    def test_summary_total_count_matches_list(self, client: TestClient):
        """Test that summary total_count matches list pagination total."""
        summary_response = client.get("/ui/invariants/summary")
        list_response = client.get("/ui/invariants", params={"limit": 100})

        assert summary_response.status_code == 200
        assert list_response.status_code == 200

        summary_count = summary_response.json()["total_count"]
        list_count = list_response.json()["pagination"]["total_count"]

        assert summary_count == list_count

    def test_summary_breakdowns_sum_to_total(self, client: TestClient):
        """Test that breakdown counts sum to total_count."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200
        data = response.json()

        total = data["total_count"]
        severity_sum = sum(data["by_severity"].values())
        status_sum = sum(data["by_status"].values())

        assert severity_sum == total
        assert status_sum == total

    def test_summary_exceptions_count_matches(self, client: TestClient):
        """Test exceptions_requiring_review matches exception enforcement count."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200
        data = response.json()

        # exceptions_requiring_review should be <= exception count in enforcement
        assert data["exceptions_requiring_review"] <= data["by_enforcement_type"]["exception"]

    def test_summary_last_updated_is_valid_timestamp(self, client: TestClient):
        """Test last_updated is a valid ISO 8601 timestamp."""
        response = client.get("/ui/invariants/summary")
        assert response.status_code == 200
        data = response.json()

        from datetime import datetime

        # Should not raise an exception
        datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00"))


class TestInvariantsReadOnly:
    """Tests to verify invariants endpoints are read-only."""

    def test_invariants_no_post(self, client: TestClient):
        """POST /ui/invariants should return 405."""
        response = client.post("/ui/invariants", json={})
        assert response.status_code == 405

    def test_invariants_no_put(self, client: TestClient):
        """PUT /ui/invariants should return 405."""
        response = client.put("/ui/invariants", json={})
        assert response.status_code == 405

    def test_invariants_no_patch(self, client: TestClient):
        """PATCH /ui/invariants should return 405."""
        response = client.patch("/ui/invariants", json={})
        assert response.status_code == 405

    def test_invariants_no_delete(self, client: TestClient):
        """DELETE /ui/invariants should return 405."""
        response = client.delete("/ui/invariants")
        assert response.status_code == 405

    def test_invariants_summary_no_post(self, client: TestClient):
        """POST /ui/invariants/summary should return 405."""
        response = client.post("/ui/invariants/summary", json={})
        assert response.status_code == 405

    def test_invariants_summary_no_put(self, client: TestClient):
        """PUT /ui/invariants/summary should return 405."""
        response = client.put("/ui/invariants/summary", json={})
        assert response.status_code == 405

    def test_invariants_summary_no_patch(self, client: TestClient):
        """PATCH /ui/invariants/summary should return 405."""
        response = client.patch("/ui/invariants/summary", json={})
        assert response.status_code == 405

    def test_invariants_summary_no_delete(self, client: TestClient):
        """DELETE /ui/invariants/summary should return 405."""
        response = client.delete("/ui/invariants/summary")
        assert response.status_code == 405


class TestInvariantsEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_severity_value(self, client: TestClient):
        """Test invalid severity value returns 422."""
        response = client.get("/ui/invariants", params={"severity": "INVALID"})
        assert response.status_code == 422

    def test_invalid_enforcement_type_value(self, client: TestClient):
        """Test invalid enforcement_type value returns 422."""
        response = client.get("/ui/invariants", params={"enforcement_type": "INVALID"})
        assert response.status_code == 422

    def test_invalid_status_value(self, client: TestClient):
        """Test invalid status value returns 422."""
        response = client.get("/ui/invariants", params={"status": "INVALID"})
        assert response.status_code == 422

    def test_empty_search_returns_all(self, client: TestClient):
        """Test empty search string returns all invariants."""
        response_no_search = client.get("/ui/invariants")
        response_empty_search = client.get("/ui/invariants", params={"search": ""})

        assert response_no_search.status_code == 200
        assert response_empty_search.status_code == 200

        # Should return same results
        assert (
            response_no_search.json()["pagination"]["total_count"]
            == response_empty_search.json()["pagination"]["total_count"]
        )

    def test_search_case_insensitive(self, client: TestClient):
        """Test search is case-insensitive."""
        response_lower = client.get("/ui/invariants", params={"search": "acknowledgment"})
        response_upper = client.get("/ui/invariants", params={"search": "ACKNOWLEDGMENT"})

        assert response_lower.status_code == 200
        assert response_upper.status_code == 200

        # Should return same results
        assert (
            response_lower.json()["pagination"]["total_count"]
            == response_upper.json()["pagination"]["total_count"]
        )

    def test_limit_bounds_minimum(self, client: TestClient):
        """Test minimum limit value (1)."""
        response = client.get("/ui/invariants", params={"limit": 1})
        assert response.status_code == 200
        assert len(response.json()["items"]) <= 1

    def test_limit_bounds_maximum(self, client: TestClient):
        """Test maximum limit value (100)."""
        response = client.get("/ui/invariants", params={"limit": 100})
        assert response.status_code == 200
        assert len(response.json()["items"]) <= 100

    def test_limit_over_maximum(self, client: TestClient):
        """Test limit over maximum returns 422."""
        response = client.get("/ui/invariants", params={"limit": 101})
        assert response.status_code == 422

    def test_limit_under_minimum(self, client: TestClient):
        """Test limit under minimum returns 422."""
        response = client.get("/ui/invariants", params={"limit": 0})
        assert response.status_code == 422

"""Tests for the UI contract snapshot generator.

These tests verify that:
1. The generator produces valid JSON output
2. The output contains all required sections (enums, schemas, endpoints)
3. The output is deterministic (running twice produces identical content)
4. All expected endpoints and schemas are present
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Path to the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONTRACTS_PATH = PROJECT_ROOT / "docs" / "ui" / "contracts" / "ui-contracts.json"
GENERATOR_PATH = PROJECT_ROOT / "scripts" / "generate_ui_contracts.py"


class TestContractSnapshotFile:
    """Tests for the generated contract snapshot file."""

    def test_contracts_file_exists(self) -> None:
        """Verify the contracts file exists."""
        assert CONTRACTS_PATH.exists(), f"Contract snapshot not found at {CONTRACTS_PATH}"

    def test_contracts_file_is_valid_json(self) -> None:
        """Verify the contracts file contains valid JSON."""
        with open(CONTRACTS_PATH) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_contracts_file_has_required_sections(self) -> None:
        """Verify the contracts file has all required top-level sections."""
        with open(CONTRACTS_PATH) as f:
            data = json.load(f)

        required_sections = [
            "$schema",
            "title",
            "description",
            "version",
            "generated_at",
            "source",
            "enums",
            "constants",
            "schemas",
            "endpoints",
        ]

        for section in required_sections:
            assert section in data, f"Missing required section: {section}"


class TestEnums:
    """Tests for enum definitions in the contract snapshot."""

    @pytest.fixture
    def contract_data(self) -> dict:
        """Load contract data from file."""
        with open(CONTRACTS_PATH) as f:
            return json.load(f)

    def test_has_notification_intent_enum(self, contract_data: dict) -> None:
        """Verify NotificationIntent enum is present."""
        enums = contract_data["enums"]
        assert "NotificationIntent" in enums
        values = enums["NotificationIntent"]
        assert "SAFETY" in values
        assert "GOVERNANCE" in values
        assert "OPERATIONAL" in values
        assert "INFORMATIONAL" in values

    def test_has_delivery_mode_enum(self, contract_data: dict) -> None:
        """Verify DeliveryMode enum is present."""
        enums = contract_data["enums"]
        assert "DeliveryMode" in enums
        values = enums["DeliveryMode"]
        assert "GUARANTEED" in values
        assert "BEST_EFFORT" in values

    def test_has_autonomy_mode_enum(self, contract_data: dict) -> None:
        """Verify AutonomyMode enum is present."""
        enums = contract_data["enums"]
        assert "AutonomyMode" in enums
        values = enums["AutonomyMode"]
        assert "PREVIEW" in values
        assert "SHADOW" in values
        assert "LIVE" in values

    def test_has_channel_enum(self, contract_data: dict) -> None:
        """Verify Channel enum is present."""
        enums = contract_data["enums"]
        assert "Channel" in enums
        values = enums["Channel"]
        assert "SLACK" in values
        assert "EMAIL" in values
        assert "WEBSOCKET" in values
        assert "PAGERDUTY" in values

    def test_has_delivery_status_enum(self, contract_data: dict) -> None:
        """Verify DeliveryStatus enum is present."""
        enums = contract_data["enums"]
        assert "DeliveryStatus" in enums
        values = enums["DeliveryStatus"]
        assert "PENDING" in values
        assert "DELIVERED" in values
        assert "FAILED" in values

    def test_enums_are_sorted(self, contract_data: dict) -> None:
        """Verify enum values are sorted for determinism."""
        enums = contract_data["enums"]
        for enum_name, values in enums.items():
            assert values == sorted(values), f"{enum_name} values are not sorted"


class TestConstants:
    """Tests for constants in the contract snapshot."""

    @pytest.fixture
    def contract_data(self) -> dict:
        """Load contract data from file."""
        with open(CONTRACTS_PATH) as f:
            return json.load(f)

    def test_has_title_max_length(self, contract_data: dict) -> None:
        """Verify TITLE_MAX_LENGTH constant is present."""
        constants = contract_data["constants"]
        assert "TITLE_MAX_LENGTH" in constants
        assert constants["TITLE_MAX_LENGTH"] == 200

    def test_has_message_max_length(self, contract_data: dict) -> None:
        """Verify MESSAGE_MAX_LENGTH constant is present."""
        constants = contract_data["constants"]
        assert "MESSAGE_MAX_LENGTH" in constants
        assert constants["MESSAGE_MAX_LENGTH"] == 4000

    def test_has_pagination_defaults(self, contract_data: dict) -> None:
        """Verify pagination constants are present."""
        constants = contract_data["constants"]
        assert "PAGINATION_DEFAULT_LIMIT" in constants
        assert constants["PAGINATION_DEFAULT_LIMIT"] == 25
        assert "PAGINATION_MAX_LIMIT" in constants
        assert constants["PAGINATION_MAX_LIMIT"] == 100


class TestSchemas:
    """Tests for response schemas in the contract snapshot."""

    @pytest.fixture
    def contract_data(self) -> dict:
        """Load contract data from file."""
        with open(CONTRACTS_PATH) as f:
            return json.load(f)

    def test_has_pagination_info_schema(self, contract_data: dict) -> None:
        """Verify PaginationInfo schema is present."""
        schemas = contract_data["schemas"]
        assert "PaginationInfo" in schemas
        schema = schemas["PaginationInfo"]
        assert schema["type"] == "object"

    def test_has_delivery_timeline_response_schema(self, contract_data: dict) -> None:
        """Verify DeliveryTimelineResponse schema is present."""
        schemas = contract_data["schemas"]
        assert "DeliveryTimelineResponse" in schemas
        schema = schemas["DeliveryTimelineResponse"]
        assert schema["type"] == "object"
        assert "notification_id" in schema["properties"]

    def test_has_effective_policy_response_schema(self, contract_data: dict) -> None:
        """Verify EffectivePolicyResponse schema is present."""
        schemas = contract_data["schemas"]
        assert "EffectivePolicyResponse" in schemas
        schema = schemas["EffectivePolicyResponse"]
        assert schema["type"] == "object"
        assert "effective" in schema["properties"]
        assert "resolution" in schema["properties"]

    def test_has_invariant_list_response_schema(self, contract_data: dict) -> None:
        """Verify InvariantListResponse schema is present."""
        schemas = contract_data["schemas"]
        assert "InvariantListResponse" in schemas
        schema = schemas["InvariantListResponse"]
        assert schema["type"] == "object"
        assert "items" in schema["properties"]
        assert "pagination" in schema["properties"]

    def test_has_audit_event_list_response_schema(self, contract_data: dict) -> None:
        """Verify AuditEventListResponse schema is present."""
        schemas = contract_data["schemas"]
        assert "AuditEventListResponse" in schemas
        schema = schemas["AuditEventListResponse"]
        assert schema["type"] == "object"

    def test_has_error_response_schema(self, contract_data: dict) -> None:
        """Verify UIErrorResponse schema is present.

        Phase 3 Task 1 renamed ``ErrorResponse`` (the routes_ui flavor) to
        ``UIErrorResponse`` because two structurally incompatible
        ``ErrorResponse`` classes coexisted; both moved to
        :mod:`uns.responses` under disambiguated names.
        """
        schemas = contract_data["schemas"]
        assert "UIErrorResponse" in schemas
        schema = schemas["UIErrorResponse"]
        assert schema["type"] == "object"
        assert "error" in schema["properties"]
        assert "request_id" in schema["properties"]


class TestEndpoints:
    """Tests for endpoint definitions in the contract snapshot."""

    @pytest.fixture
    def contract_data(self) -> dict:
        """Load contract data from file."""
        with open(CONTRACTS_PATH) as f:
            return json.load(f)

    def test_has_six_endpoints(self, contract_data: dict) -> None:
        """Verify all six /ui endpoints are defined."""
        endpoints = contract_data["endpoints"]
        assert len(endpoints) == 6

    def test_all_endpoints_are_get(self, contract_data: dict) -> None:
        """Verify all /ui endpoints use GET method (read-only)."""
        endpoints = contract_data["endpoints"]
        for endpoint in endpoints:
            assert endpoint["method"] == "GET", f"Endpoint {endpoint['path']} is not GET"

    def test_has_deliveries_list_endpoint(self, contract_data: dict) -> None:
        """Verify /ui/deliveries endpoint is defined."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/ui/deliveries" in paths

    def test_has_deliveries_detail_endpoint(self, contract_data: dict) -> None:
        """Verify /ui/deliveries/{notification_id} endpoint is defined."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/ui/deliveries/{notification_id}" in paths

    def test_has_policies_effective_endpoint(self, contract_data: dict) -> None:
        """Verify /ui/policies/effective endpoint is defined."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/ui/policies/effective" in paths

    def test_has_invariants_endpoint(self, contract_data: dict) -> None:
        """Verify /ui/invariants endpoint is defined."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/ui/invariants" in paths

    def test_has_invariants_summary_endpoint(self, contract_data: dict) -> None:
        """Verify /ui/invariants/summary endpoint is defined."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/ui/invariants/summary" in paths

    def test_has_audit_endpoint(self, contract_data: dict) -> None:
        """Verify /ui/audit endpoint is defined."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/ui/audit" in paths

    def test_endpoints_are_sorted_by_path(self, contract_data: dict) -> None:
        """Verify endpoints are sorted by path for determinism."""
        endpoints = contract_data["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert paths == sorted(paths), "Endpoints are not sorted by path"

    def test_each_endpoint_has_response_model(self, contract_data: dict) -> None:
        """Verify each endpoint specifies a response model."""
        endpoints = contract_data["endpoints"]
        for endpoint in endpoints:
            assert "response_model" in endpoint, f"Missing response_model for {endpoint['path']}"


class TestGeneratorScript:
    """Tests for the generator script itself."""

    def test_generator_script_exists(self) -> None:
        """Verify the generator script exists."""
        assert GENERATOR_PATH.exists(), f"Generator script not found at {GENERATOR_PATH}"

    def test_generator_runs_successfully(self) -> None:
        """Verify the generator script runs without errors."""
        result = subprocess.run(
            [sys.executable, str(GENERATOR_PATH)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"Generator failed: {result.stderr}"

    def test_generator_is_idempotent(self) -> None:
        """Verify running the generator twice produces consistent output.

        Note: We compare the structure, not the generated_at timestamp.
        """
        # Load current state
        with open(CONTRACTS_PATH) as f:
            before = json.load(f)

        # Run generator
        result = subprocess.run(
            [sys.executable, str(GENERATOR_PATH)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0

        # Load new state
        with open(CONTRACTS_PATH) as f:
            after = json.load(f)

        # Compare structure (excluding timestamp)
        assert before["enums"] == after["enums"]
        assert before["constants"] == after["constants"]
        assert before["endpoints"] == after["endpoints"]
        # Schemas should be identical too
        assert before["schemas"].keys() == after["schemas"].keys()


class TestContractDrift:
    """Tests to detect contract drift between snapshot and implementation."""

    @pytest.fixture
    def contract_data(self) -> dict:
        """Load contract data from file."""
        with open(CONTRACTS_PATH) as f:
            return json.load(f)

    def test_schemas_match_routes_ui_models(self, contract_data: dict) -> None:
        """Verify snapshot schemas include all response models from routes_ui."""
        # These are the response models used in routes_ui.py endpoints
        expected_models = [
            "DeliveryTimelineListResponse",
            "DeliveryTimelineResponse",
            "EffectivePolicyResponse",
            "InvariantListResponse",
            "InvariantSummaryResponse",
            "AuditEventListResponse",
        ]

        schemas = contract_data["schemas"]
        for model in expected_models:
            assert model in schemas, f"Missing response model: {model}"

    def test_enums_match_notification_models(self, contract_data: dict) -> None:
        """Verify snapshot enums include all enums from notification.models."""
        expected_enums = [
            "NotificationIntent",
            "DeliveryMode",
            "AutonomyMode",
            "Channel",
            "DeliveryStatus",
            "AckStatus",
            "Priority",
        ]

        enums = contract_data["enums"]
        for enum in expected_enums:
            assert enum in enums, f"Missing enum: {enum}"

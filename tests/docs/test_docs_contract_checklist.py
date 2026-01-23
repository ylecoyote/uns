"""Tests for docs-contract-checklist.md documentation.

Tests verify that the checklist:
1. Covers all required topics
2. References correct document locations
3. Contains accurate invariants
"""

from pathlib import Path

import pytest

CHECKLIST_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "reports" / "docs-contract-checklist.md"
)


@pytest.fixture
def checklist_doc() -> str:
    """Load the docs contract checklist."""
    assert CHECKLIST_PATH.exists(), f"docs-contract-checklist.md not found at {CHECKLIST_PATH}"
    return CHECKLIST_PATH.read_text()


class TestChecklistExists:
    """Test that the checklist document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify docs-contract-checklist.md exists."""
        assert CHECKLIST_PATH.exists()

    def test_file_not_empty(self, checklist_doc: str) -> None:
        """Verify file is not empty."""
        assert len(checklist_doc) > 0

    def test_is_markdown(self, checklist_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in checklist_doc


class TestChecklistStructure:
    """Test the structure of the checklist."""

    def test_has_title(self, checklist_doc: str) -> None:
        """Verify document has correct title."""
        assert checklist_doc.startswith("# Documentation Contract Checklist")

    def test_has_purpose_section(self, checklist_doc: str) -> None:
        """Verify document has purpose statement."""
        assert "**Purpose:**" in checklist_doc

    def test_has_usage_section(self, checklist_doc: str) -> None:
        """Verify document has usage guidance."""
        assert "**Usage:**" in checklist_doc


class TestRequiredSections:
    """Test that checklist covers all required topics."""

    def test_has_intent_routing_section(self, checklist_doc: str) -> None:
        """Verify checklist covers intent routing."""
        assert "## 1. Intent Routing Described" in checklist_doc

    def test_has_delivery_semantics_section(self, checklist_doc: str) -> None:
        """Verify checklist covers delivery semantics."""
        assert "## 2. Delivery Semantics Described" in checklist_doc

    def test_has_ack_rules_section(self, checklist_doc: str) -> None:
        """Verify checklist covers acknowledgment rules and boundaries."""
        assert "## 3. Acknowledgment Rules and Boundaries Stated" in checklist_doc

    def test_has_policy_lifecycle_section(self, checklist_doc: str) -> None:
        """Verify checklist covers policy lifecycle."""
        assert "## 4. Policy Lifecycle Described" in checklist_doc

    def test_has_observability_section(self, checklist_doc: str) -> None:
        """Verify checklist covers observability and degradation."""
        assert "## 5. Observability and Degradation Documented" in checklist_doc


class TestIntentRoutingChecks:
    """Test that intent routing section contains required checks."""

    def test_references_delivery_semantics_doc(self, checklist_doc: str) -> None:
        """Verify section references delivery-semantics.md."""
        # Find the intent routing section
        section_start = checklist_doc.find("## 1. Intent Routing")
        section_end = checklist_doc.find("## 2.")
        section = checklist_doc[section_start:section_end]

        assert "delivery-semantics.md" in section

    def test_references_intent_delivery_mode_mapping(self, checklist_doc: str) -> None:
        """Verify section references Intent × Delivery Mode Mapping."""
        section_start = checklist_doc.find("## 1. Intent Routing")
        section_end = checklist_doc.find("## 2.")
        section = checklist_doc[section_start:section_end]

        assert "Intent × Delivery Mode Mapping" in section

    def test_documents_key_invariant(self, checklist_doc: str) -> None:
        """Verify section documents the key invariant."""
        section_start = checklist_doc.find("## 1. Intent Routing")
        section_end = checklist_doc.find("## 2.")
        section = checklist_doc[section_start:section_end]

        assert "SAFETY" in section
        assert "GOVERNANCE" in section
        assert "GUARANTEED" in section


class TestDeliverySemanticsChecks:
    """Test that delivery semantics section contains required checks."""

    def test_references_guaranteed_section(self, checklist_doc: str) -> None:
        """Verify section references GUARANTEED delivery semantics."""
        section_start = checklist_doc.find("## 2. Delivery Semantics")
        section_end = checklist_doc.find("## 3.")
        section = checklist_doc[section_start:section_end]

        assert "GUARANTEED Delivery Semantics" in section

    def test_references_best_effort_section(self, checklist_doc: str) -> None:
        """Verify section references BEST_EFFORT delivery semantics."""
        section_start = checklist_doc.find("## 2. Delivery Semantics")
        section_end = checklist_doc.find("## 3.")
        section = checklist_doc[section_start:section_end]

        assert "BEST_EFFORT Delivery Semantics" in section

    def test_documents_fallback_order(self, checklist_doc: str) -> None:
        """Verify section documents fallback order."""
        section_start = checklist_doc.find("## 2. Delivery Semantics")
        section_end = checklist_doc.find("## 3.")
        section = checklist_doc[section_start:section_end]

        assert "Slack" in section
        assert "Email" in section
        assert "PagerDuty" in section
        assert "fallback" in section.lower()

    def test_documents_delivery_error(self, checklist_doc: str) -> None:
        """Verify section documents DeliveryError behavior."""
        section_start = checklist_doc.find("## 2. Delivery Semantics")
        section_end = checklist_doc.find("## 3.")
        section = checklist_doc[section_start:section_end]

        assert "DeliveryError" in section


class TestAckRulesChecks:
    """Test that acknowledgment rules section contains required checks."""

    def test_references_ack_requirements(self, checklist_doc: str) -> None:
        """Verify section references Acknowledgment Requirements."""
        section_start = checklist_doc.find("## 3. Acknowledgment Rules")
        section_end = checklist_doc.find("## 4.")
        section = checklist_doc[section_start:section_end]

        assert "Acknowledgment Requirements" in section

    def test_references_architecture_warning(self, checklist_doc: str) -> None:
        """Verify section references ARCHITECTURE.md warning box."""
        section_start = checklist_doc.find("## 3. Acknowledgment Rules")
        section_end = checklist_doc.find("## 4.")
        section = checklist_doc[section_start:section_end]

        assert "ARCHITECTURE.md" in section
        assert "CRITICAL" in section or "warning" in section.lower()

    def test_documents_scope_restriction(self, checklist_doc: str) -> None:
        """Verify section documents that acks only gate autonomy transitions."""
        section_start = checklist_doc.find("## 3. Acknowledgment Rules")
        section_end = checklist_doc.find("## 4.")
        section = checklist_doc[section_start:section_end]

        assert "autonomy" in section.lower()
        assert "execution" in section.lower() or "order" in section.lower()

    def test_documents_anti_patterns(self, checklist_doc: str) -> None:
        """Verify section documents anti-patterns to check for."""
        section_start = checklist_doc.find("## 3. Acknowledgment Rules")
        section_end = checklist_doc.find("## 4.")
        section = checklist_doc[section_start:section_end]

        assert "Anti-Pattern" in section or "anti-pattern" in section


class TestPolicyLifecycleChecks:
    """Test that policy lifecycle section contains required checks."""

    def test_references_policy_lifecycle_doc(self, checklist_doc: str) -> None:
        """Verify section references policy-lifecycle.md."""
        section_start = checklist_doc.find("## 4. Policy Lifecycle")
        section_end = checklist_doc.find("## 5.")
        section = checklist_doc[section_start:section_end]

        assert "policy-lifecycle.md" in section

    def test_documents_resolution_priority(self, checklist_doc: str) -> None:
        """Verify section documents resolution priority."""
        section_start = checklist_doc.find("## 4. Policy Lifecycle")
        section_end = checklist_doc.find("## 5.")
        section = checklist_doc[section_start:section_end]

        assert "Resolution Priority" in section or "priority" in section.lower()
        assert "Explicit" in section or "override" in section.lower()
        assert "SDK default" in section or "default" in section.lower()

    def test_documents_fallback_behavior(self, checklist_doc: str) -> None:
        """Verify section documents fallback behavior."""
        section_start = checklist_doc.find("## 4. Policy Lifecycle")
        section_end = checklist_doc.find("## 5.")
        section = checklist_doc[section_start:section_end]

        assert "fallback" in section.lower() or "Unavailability" in section

    def test_documents_key_invariant(self, checklist_doc: str) -> None:
        """Verify section documents that notifications are never blocked."""
        section_start = checklist_doc.find("## 4. Policy Lifecycle")
        section_end = checklist_doc.find("## 5.")
        section = checklist_doc[section_start:section_end]

        assert "never blocked" in section.lower() or "always apply" in section.lower()


class TestObservabilityChecks:
    """Test that observability section contains required checks."""

    def test_references_observability_doc(self, checklist_doc: str) -> None:
        """Verify section references observability.md."""
        section_start = checklist_doc.find("## 5. Observability")
        section_end = checklist_doc.find("## Quick Reference") if "## Quick Reference" in checklist_doc else len(checklist_doc)
        section = checklist_doc[section_start:section_end]

        assert "observability.md" in section

    def test_documents_health_states(self, checklist_doc: str) -> None:
        """Verify section documents health states."""
        section_start = checklist_doc.find("## 5. Observability")
        section_end = checklist_doc.find("## Quick Reference") if "## Quick Reference" in checklist_doc else len(checklist_doc)
        section = checklist_doc[section_start:section_end]

        assert "HEALTHY" in section
        assert "DEGRADED" in section
        assert "UNHEALTHY" in section

    def test_documents_dlq_visibility(self, checklist_doc: str) -> None:
        """Verify section documents DLQ visibility."""
        section_start = checklist_doc.find("## 5. Observability")
        section_end = checklist_doc.find("## Quick Reference") if "## Quick Reference" in checklist_doc else len(checklist_doc)
        section = checklist_doc[section_start:section_end]

        assert "DLQ" in section

    def test_documents_metrics(self, checklist_doc: str) -> None:
        """Verify section documents key metrics."""
        section_start = checklist_doc.find("## 5. Observability")
        section_end = checklist_doc.find("## Quick Reference") if "## Quick Reference" in checklist_doc else len(checklist_doc)
        section = checklist_doc[section_start:section_end]

        assert "Metric" in section or "metric" in section

    def test_documents_degradation(self, checklist_doc: str) -> None:
        """Verify section documents degradation behavior."""
        section_start = checklist_doc.find("## 5. Observability")
        section_end = checklist_doc.find("## Quick Reference") if "## Quick Reference" in checklist_doc else len(checklist_doc)
        section = checklist_doc[section_start:section_end]

        assert "Degradation" in section or "degradation" in section


class TestFileReferences:
    """Test that checklist references correct file locations."""

    def test_references_delivery_semantics(self, checklist_doc: str) -> None:
        """Verify checklist references delivery-semantics.md."""
        assert "delivery-semantics.md" in checklist_doc

    def test_references_architecture(self, checklist_doc: str) -> None:
        """Verify checklist references ARCHITECTURE.md."""
        assert "ARCHITECTURE.md" in checklist_doc

    def test_references_policy_lifecycle(self, checklist_doc: str) -> None:
        """Verify checklist references policy-lifecycle.md."""
        assert "policy-lifecycle.md" in checklist_doc

    def test_references_observability(self, checklist_doc: str) -> None:
        """Verify checklist references observability.md."""
        assert "observability.md" in checklist_doc


class TestReferencedFilesExist:
    """Test that all referenced documentation files exist."""

    @pytest.fixture
    def docs_dir(self) -> Path:
        """Return the docs directory path."""
        return Path(__file__).parent.parent.parent / "docs"

    def test_delivery_semantics_exists(self, docs_dir: Path) -> None:
        """Verify delivery-semantics.md exists."""
        path = docs_dir / "sections" / "delivery-semantics.md"
        assert path.exists(), f"Referenced file not found: {path}"

    def test_architecture_exists(self, docs_dir: Path) -> None:
        """Verify ARCHITECTURE.md exists."""
        path = docs_dir / "ARCHITECTURE.md"
        assert path.exists(), f"Referenced file not found: {path}"

    def test_policy_lifecycle_exists(self, docs_dir: Path) -> None:
        """Verify policy-lifecycle.md exists."""
        path = docs_dir / "sections" / "policy-lifecycle.md"
        assert path.exists(), f"Referenced file not found: {path}"

    def test_observability_exists(self, docs_dir: Path) -> None:
        """Verify observability.md exists."""
        path = docs_dir / "sections" / "observability.md"
        assert path.exists(), f"Referenced file not found: {path}"

    def test_api_exists(self, docs_dir: Path) -> None:
        """Verify API.md exists."""
        path = docs_dir / "API.md"
        assert path.exists(), f"Referenced file not found: {path}"


class TestChecklistHasCheckboxes:
    """Test that checklist contains checkbox items for review."""

    def test_has_checkboxes(self, checklist_doc: str) -> None:
        """Verify checklist contains checkbox markers."""
        assert "☐" in checklist_doc or "[ ]" in checklist_doc

    def test_has_multiple_checkboxes(self, checklist_doc: str) -> None:
        """Verify checklist has multiple items to check."""
        checkbox_count = checklist_doc.count("☐") + checklist_doc.count("[ ]")
        assert checkbox_count >= 15, f"Expected at least 15 checkbox items, found {checkbox_count}"


class TestValidationTestCoverage:
    """Test that checklist documents test coverage."""

    def test_documents_test_files(self, checklist_doc: str) -> None:
        """Verify checklist references test files."""
        assert "tests/docs/" in checklist_doc

    def test_documents_pytest_command(self, checklist_doc: str) -> None:
        """Verify checklist includes pytest command."""
        assert "pytest" in checklist_doc

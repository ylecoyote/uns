"""Tests for doc-update-plan.md structure and completeness."""

import re
from pathlib import Path

import pytest

# Path to the documentation update plan
DOC_UPDATE_PLAN_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "reports" / "doc-update-plan.md"
)
GAP_ANALYSIS_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "reports" / "doc-alignment-summary.md"
)


@pytest.fixture
def doc_update_plan() -> str:
    """Load the documentation update plan."""
    assert DOC_UPDATE_PLAN_PATH.exists(), f"doc-update-plan.md not found at {DOC_UPDATE_PLAN_PATH}"
    return DOC_UPDATE_PLAN_PATH.read_text()


@pytest.fixture
def gap_analysis() -> str:
    """Load the gap analysis report."""
    assert GAP_ANALYSIS_PATH.exists(), f"doc-alignment-summary.md not found at {GAP_ANALYSIS_PATH}"
    return GAP_ANALYSIS_PATH.read_text()


class TestDocUpdatePlanExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify doc-update-plan.md exists."""
        assert DOC_UPDATE_PLAN_PATH.exists()

    def test_file_not_empty(self, doc_update_plan: str) -> None:
        """Verify doc-update-plan.md is not empty."""
        assert len(doc_update_plan) > 0

    def test_is_markdown(self, doc_update_plan: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in doc_update_plan


class TestDocUpdatePlanStructure:
    """Test the structure of the documentation update plan."""

    def test_has_title(self, doc_update_plan: str) -> None:
        """Verify document has a title."""
        assert doc_update_plan.startswith("# Documentation Update Plan")

    def test_has_overview_section(self, doc_update_plan: str) -> None:
        """Verify document has overview section."""
        assert "## Overview" in doc_update_plan

    def test_has_phase_sections(self, doc_update_plan: str) -> None:
        """Verify document has phased implementation sections."""
        assert "## Phase 1" in doc_update_plan
        assert "## Phase 2" in doc_update_plan
        assert "## Phase 3" in doc_update_plan

    def test_has_summary_section(self, doc_update_plan: str) -> None:
        """Verify document has summary section."""
        assert "## Summary" in doc_update_plan

    def test_has_files_to_change_table(self, doc_update_plan: str) -> None:
        """Verify document lists files to change."""
        assert "### Files to Change" in doc_update_plan
        assert "README.md" in doc_update_plan
        assert "docs/ARCHITECTURE.md" in doc_update_plan
        assert "docs/API.md" in doc_update_plan


class TestDocUpdatePlanContent:
    """Test the content completeness of the documentation update plan."""

    def test_references_gap_analysis(self, doc_update_plan: str) -> None:
        """Verify plan references the gap analysis source."""
        assert "doc-alignment-summary.md" in doc_update_plan

    def test_includes_gap_references(self, doc_update_plan: str) -> None:
        """Verify plan includes gap references for traceability."""
        # Should reference specific gaps from the analysis
        assert "Gap Reference:" in doc_update_plan

    def test_includes_change_types(self, doc_update_plan: str) -> None:
        """Verify plan specifies change types (Addition/Edit)."""
        assert "Addition" in doc_update_plan
        assert "Edit" in doc_update_plan

    def test_includes_expected_outputs(self, doc_update_plan: str) -> None:
        """Verify plan includes expected outputs."""
        assert "Expected Output:" in doc_update_plan

    def test_includes_new_content_examples(self, doc_update_plan: str) -> None:
        """Verify plan includes example content for additions."""
        assert "**New Content:**" in doc_update_plan or "New Content:" in doc_update_plan


class TestCriticalGapsCovered:
    """Test that all critical gaps from the analysis are covered in the plan."""

    def test_execution_constraints_covered(self, doc_update_plan: str) -> None:
        """Verify execution constraints gap (Omission 2.1) is addressed."""
        assert "Execution Constraint" in doc_update_plan
        assert "MUST NOT block" in doc_update_plan or "Non-Blocking" in doc_update_plan

    def test_ack_async_clarification_covered(self, doc_update_plan: str) -> None:
        """Verify acknowledgment async clarification (Ambiguity 3.1) is addressed."""
        assert "asynchronous" in doc_update_plan.lower()
        assert "does not block" in doc_update_plan.lower()

    def test_governance_ack_fix_covered(self, doc_update_plan: str) -> None:
        """Verify GOVERNANCE ack fix (Contradiction 1.3) is addressed."""
        assert "GOVERNANCE" in doc_update_plan
        # Should mention ack behavior correction
        assert "Not required" in doc_update_plan or "not required" in doc_update_plan

    def test_dlq_visibility_covered(self, doc_update_plan: str) -> None:
        """Verify DLQ/degradation visibility (Omission 2.2) is addressed."""
        assert "DLQ" in doc_update_plan or "Dead Letter" in doc_update_plan
        assert "degradation" in doc_update_plan.lower() or "Degradation" in doc_update_plan


class TestGapCoverage:
    """Test that the plan covers gaps from the analysis."""

    def test_contradiction_count_matches(self, doc_update_plan: str, gap_analysis: str) -> None:
        """Verify plan addresses contradictions from analysis."""
        # Analysis has 3 contradictions
        assert "Contradiction 1.1" in doc_update_plan or "SHADOW Mode" in doc_update_plan
        assert "Contradiction 1.2" in doc_update_plan or "async" in doc_update_plan.lower()
        assert "Contradiction 1.3" in doc_update_plan or "GOVERNANCE" in doc_update_plan

    def test_covers_shadow_mode_fix(self, doc_update_plan: str) -> None:
        """Verify SHADOW mode documentation fix is included."""
        assert "SHADOW" in doc_update_plan
        # Should mention LIVE defaults fallback
        assert "LIVE defaults" in doc_update_plan or "fallback" in doc_update_plan.lower()

    def test_covers_policy_registry_fix(self, doc_update_plan: str) -> None:
        """Verify PolicyRegistry async get() fix is included."""
        assert "PolicyRegistry" in doc_update_plan
        # Should mention removing or fixing async get()
        assert "async" in doc_update_plan.lower()


class TestNewFilesPlanned:
    """Test that new documentation files are planned where needed."""

    def test_deployment_doc_planned(self, doc_update_plan: str) -> None:
        """Verify DEPLOYMENT.md is planned."""
        assert "DEPLOYMENT.md" in doc_update_plan
        assert "NEW" in doc_update_plan or "New File" in doc_update_plan.lower()

    def test_observability_doc_planned(self, doc_update_plan: str) -> None:
        """Verify OBSERVABILITY.md is planned."""
        assert "OBSERVABILITY.md" in doc_update_plan
        assert "metrics" in doc_update_plan.lower()


class TestPriorityOrdering:
    """Test that changes are properly prioritized."""

    def test_critical_items_in_phase_1(self, doc_update_plan: str) -> None:
        """Verify critical items are in Phase 1."""
        # Find Phase 1 section
        phase_1_match = re.search(r"## Phase 1.*?## Phase 2", doc_update_plan, re.DOTALL)
        assert phase_1_match is not None
        phase_1_content = phase_1_match.group(0)

        # Critical items should be in Phase 1
        assert "Critical" in phase_1_content or "High Priority" in phase_1_content

    def test_phases_in_order(self, doc_update_plan: str) -> None:
        """Verify phases appear in numerical order."""
        phase_1_pos = doc_update_plan.find("## Phase 1")
        phase_2_pos = doc_update_plan.find("## Phase 2")
        phase_3_pos = doc_update_plan.find("## Phase 3")

        assert phase_1_pos < phase_2_pos < phase_3_pos


class TestChangeSpecificity:
    """Test that changes are specific enough to implement."""

    def test_includes_line_numbers_or_sections(self, doc_update_plan: str) -> None:
        """Verify plan includes specific locations for changes."""
        # Should reference line numbers or section names
        assert "line" in doc_update_plan.lower() or "section" in doc_update_plan.lower()

    def test_includes_before_after_examples(self, doc_update_plan: str) -> None:
        """Verify plan shows what content should change."""
        # Should have current/changed or similar indicators
        has_change_indicators = any(
            indicator in doc_update_plan
            for indicator in [
                "Current:",
                "Changed To:",
                "**Current:**",
                "**Changed To:**",
                "New Content:",
                "**New Content:**",
            ]
        )
        assert has_change_indicators

    def test_markdown_code_blocks_present(self, doc_update_plan: str) -> None:
        """Verify plan includes markdown code blocks for content examples."""
        assert "```" in doc_update_plan


class TestSummaryCompleteness:
    """Test that the summary section is complete."""

    def test_summary_has_file_list(self, doc_update_plan: str) -> None:
        """Verify summary lists all files to change."""
        summary_match = re.search(r"## Summary.*", doc_update_plan, re.DOTALL)
        assert summary_match is not None
        summary = summary_match.group(0)

        assert "README.md" in summary
        assert "ARCHITECTURE.md" in summary
        assert "API.md" in summary

    def test_summary_has_change_counts(self, doc_update_plan: str) -> None:
        """Verify summary includes change counts."""
        summary_match = re.search(r"## Summary.*", doc_update_plan, re.DOTALL)
        assert summary_match is not None
        summary = summary_match.group(0)

        # Should have counts of changes
        assert "Count" in summary or re.search(r"\d+", summary) is not None

    def test_summary_has_expected_outcomes(self, doc_update_plan: str) -> None:
        """Verify summary describes expected outcomes."""
        assert "Expected Outcome" in doc_update_plan or "After implementing" in doc_update_plan

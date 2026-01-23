"""Tests for acknowledgment scope documentation.

Validates that documentation clearly states:
1. Acknowledgments may ONLY gate autonomy state transitions
2. Acknowledgments MUST NEVER block execution loops, order routing, or risk unwind
3. Anti-pattern warnings are present and clear
"""

from pathlib import Path

import pytest

# Paths to documentation files
README_PATH = Path(__file__).parent.parent.parent / "README.md"
ARCHITECTURE_PATH = Path(__file__).parent.parent.parent / "docs" / "ARCHITECTURE.md"


@pytest.fixture
def readme_content() -> str:
    """Load README.md content."""
    assert README_PATH.exists(), f"README.md not found at {README_PATH}"
    return README_PATH.read_text()


@pytest.fixture
def architecture_content() -> str:
    """Load ARCHITECTURE.md content."""
    assert ARCHITECTURE_PATH.exists(), f"ARCHITECTURE.md not found at {ARCHITECTURE_PATH}"
    return ARCHITECTURE_PATH.read_text()


class TestReadmeAcknowledgmentScope:
    """Test that README.md contains proper acknowledgment scope warnings."""

    def test_has_critical_warning_header(self, readme_content: str) -> None:
        """Verify README has a CRITICAL warning about acknowledgment scope."""
        assert "CRITICAL" in readme_content
        assert "Acknowledgment" in readme_content

    def test_states_autonomy_transitions_only(self, readme_content: str) -> None:
        """Verify README states acknowledgments are for autonomy state transitions only."""
        lower_content = readme_content.lower()
        assert "autonomy" in lower_content
        assert "transition" in lower_content or "state" in lower_content

    def test_lists_what_acks_may_gate(self, readme_content: str) -> None:
        """Verify README lists what acknowledgments MAY gate."""
        assert "MAY gate" in readme_content or "Acknowledgments MAY gate" in readme_content
        # Should mention autonomy mode transitions
        assert "mode transition" in readme_content.lower()

    def test_lists_what_acks_must_never_gate(self, readme_content: str) -> None:
        """Verify README lists what acknowledgments MUST NEVER gate."""
        assert "MUST NEVER" in readme_content or "NEVER gate" in readme_content
        # Must mention critical execution paths
        lower_content = readme_content.lower()
        assert "order" in lower_content or "execution" in lower_content
        assert "risk" in lower_content

    def test_mentions_order_execution(self, readme_content: str) -> None:
        """Verify README explicitly prohibits gating order execution."""
        lower_content = readme_content.lower()
        assert "order execution" in lower_content or "order routing" in lower_content

    def test_mentions_risk_unwind(self, readme_content: str) -> None:
        """Verify README explicitly prohibits gating risk unwind."""
        lower_content = readme_content.lower()
        assert "risk unwind" in lower_content

    def test_has_anti_pattern_warning(self, readme_content: str) -> None:
        """Verify README has anti-pattern warning."""
        assert "Anti-Pattern" in readme_content or "anti-pattern" in readme_content.lower()

    def test_mentions_design_flaw(self, readme_content: str) -> None:
        """Verify README warns about design flaw if misused."""
        lower_content = readme_content.lower()
        assert "design flaw" in lower_content or "architectural flaw" in lower_content


class TestArchitectureAcknowledgmentScope:
    """Test that ARCHITECTURE.md contains detailed acknowledgment scope warnings."""

    def test_has_critical_warning_header(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE has a CRITICAL warning about acknowledgment scope."""
        assert "CRITICAL" in architecture_content
        assert "Acknowledgment Scope" in architecture_content

    def test_has_may_gate_table(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE has a table showing what acks MAY gate."""
        assert (
            "MAY Gate" in architecture_content or "Acknowledgments MAY Gate" in architecture_content
        )

    def test_has_must_never_gate_table(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE has a table showing what acks MUST NEVER gate."""
        assert "MUST NEVER Gate" in architecture_content or "NEVER Gate" in architecture_content

    def test_lists_autonomy_transitions(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE lists autonomy mode transitions as allowed."""
        assert "PREVIEW" in architecture_content
        assert "SHADOW" in architecture_content
        assert "LIVE" in architecture_content
        # Should show transition arrow
        assert "→" in architecture_content or "->" in architecture_content

    def test_lists_order_execution_prohibition(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE explicitly prohibits gating order execution."""
        lower_content = architecture_content.lower()
        assert "order execution" in lower_content or "order routing" in lower_content

    def test_lists_risk_unwind_prohibition(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE explicitly prohibits gating risk unwind."""
        lower_content = architecture_content.lower()
        assert "risk unwind" in lower_content

    def test_lists_emergency_procedures_prohibition(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE explicitly prohibits gating emergency procedures."""
        lower_content = architecture_content.lower()
        assert "emergency" in lower_content

    def test_has_anti_pattern_examples(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE has anti-pattern code examples."""
        assert "Anti-Pattern" in architecture_content
        # Should have code blocks showing wrong patterns
        assert "WRONG" in architecture_content or "DO NOT" in architecture_content

    def test_has_correct_pattern_examples(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE has correct pattern code examples."""
        assert "CORRECT" in architecture_content or "Correct Pattern" in architecture_content

    def test_anti_pattern_shows_blocking_code(self, architecture_content: str) -> None:
        """Verify anti-pattern examples show blocking on ack status."""
        # Should show code that blocks on acknowledgment status
        assert "wait_for_ack" in architecture_content or "get_ack_status" in architecture_content

    def test_correct_pattern_shows_fire_and_forget(self, architecture_content: str) -> None:
        """Verify correct pattern shows fire-and-forget approach."""
        lower_content = architecture_content.lower()
        # Should mention fire-and-forget or immediate execution
        assert (
            "fire-and-forget" in lower_content
            or "execute immediately" in lower_content
            or "don't wait" in lower_content
        )

    def test_has_architectural_flaw_warning(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE warns about fundamental architectural flaw."""
        lower_content = architecture_content.lower()
        assert "architectural flaw" in lower_content or "design flaw" in lower_content


class TestConsistencyBetweenDocs:
    """Test consistency between README and ARCHITECTURE documentation."""

    def test_both_mention_critical_warning(
        self, readme_content: str, architecture_content: str
    ) -> None:
        """Verify both documents have critical warning."""
        assert "CRITICAL" in readme_content
        assert "CRITICAL" in architecture_content

    def test_both_prohibit_order_execution_gating(
        self, readme_content: str, architecture_content: str
    ) -> None:
        """Verify both documents prohibit gating order execution."""
        readme_lower = readme_content.lower()
        arch_lower = architecture_content.lower()

        assert "order" in readme_lower
        assert "order" in arch_lower

    def test_both_prohibit_risk_unwind_gating(
        self, readme_content: str, architecture_content: str
    ) -> None:
        """Verify both documents prohibit gating risk unwind."""
        readme_lower = readme_content.lower()
        arch_lower = architecture_content.lower()

        assert "risk unwind" in readme_lower
        assert "risk unwind" in arch_lower

    def test_both_allow_autonomy_transitions(
        self, readme_content: str, architecture_content: str
    ) -> None:
        """Verify both documents allow gating autonomy transitions."""
        readme_lower = readme_content.lower()
        arch_lower = architecture_content.lower()

        assert "autonomy" in readme_lower
        assert "autonomy" in arch_lower

    def test_both_have_anti_pattern_warnings(
        self, readme_content: str, architecture_content: str
    ) -> None:
        """Verify both documents have anti-pattern warnings."""
        readme_lower = readme_content.lower()
        arch_lower = architecture_content.lower()

        assert "anti-pattern" in readme_lower
        assert "anti-pattern" in arch_lower


class TestNoExecutionGatingExamples:
    """Test that examples do not show execution gating patterns."""

    def test_readme_examples_dont_gate_execution(self, readme_content: str) -> None:
        """Verify README examples don't show blocking on ack for execution."""
        # The basic usage examples should not show waiting for ack before execution
        # They should show fire-and-forget pattern
        lines = readme_content.split("\n")

        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                # Code examples should not show patterns like:
                # - wait_for_ack(...) followed by execute()
                # - if ack_status == PENDING: block
                assert "wait_for_ack" not in line or "# WRONG" in line or "NEVER" in line.upper()

    def test_architecture_labels_wrong_patterns(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE labels wrong patterns explicitly."""
        # Anti-pattern examples should be clearly marked as WRONG
        assert "# WRONG" in architecture_content or "❌ WRONG" in architecture_content
        assert "# CORRECT" in architecture_content or "✅ CORRECT" in architecture_content

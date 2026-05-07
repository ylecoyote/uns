"""Tests for ui-scope.md documentation.

Tests cover:
- Document structure and completeness
- Required scope constraints are documented
- Invariant integrity statement is present
"""

from pathlib import Path

import pytest

UI_SCOPE_PATH = Path(__file__).parent.parent.parent / "docs" / "ui" / "ui-scope.md"


@pytest.fixture
def ui_scope_doc() -> str:
    """Load the UI scope documentation."""
    assert UI_SCOPE_PATH.exists(), f"ui-scope.md not found at {UI_SCOPE_PATH}"
    return UI_SCOPE_PATH.read_text()


class TestUIScopeDocExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify ui-scope.md exists."""
        assert UI_SCOPE_PATH.exists()

    def test_file_not_empty(self, ui_scope_doc: str) -> None:
        """Verify file is not empty."""
        assert len(ui_scope_doc) > 0

    def test_is_markdown(self, ui_scope_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in ui_scope_doc


class TestUIScopeDocStructure:
    """Test the structure of the UI scope documentation."""

    def test_has_title(self, ui_scope_doc: str) -> None:
        """Verify document has correct title."""
        assert "# AGSignal Console Scope" in ui_scope_doc

    def test_has_design_philosophy_section(self, ui_scope_doc: str) -> None:
        """Verify document has design philosophy section."""
        assert "## Design Philosophy" in ui_scope_doc

    def test_has_v1_constraints_section(self, ui_scope_doc: str) -> None:
        """Verify document has v1 constraints section."""
        assert "## v1 Constraints" in ui_scope_doc

    def test_has_invariant_integrity_section(self, ui_scope_doc: str) -> None:
        """Verify document has invariant integrity section."""
        assert "## Invariant Integrity" in ui_scope_doc


class TestUIScopeRequiredContent:
    """Test that required scope constraints are documented."""

    def test_read_first_flight_instruments(self, ui_scope_doc: str) -> None:
        """Verify 'read-first flight instruments' philosophy is documented."""
        doc_lower = ui_scope_doc.lower()
        assert "read-first" in doc_lower or "read first" in doc_lower
        assert "flight instruments" in doc_lower

    def test_not_control_cockpit(self, ui_scope_doc: str) -> None:
        """Verify 'not a control cockpit' is documented."""
        doc_lower = ui_scope_doc.lower()
        assert "not" in doc_lower and "control cockpit" in doc_lower

    def test_no_notification_authoring_v1(self, ui_scope_doc: str) -> None:
        """Verify no notification authoring in v1 is documented."""
        doc_lower = ui_scope_doc.lower()
        assert "notification authoring" in doc_lower
        assert "not included" in doc_lower or "no" in doc_lower

    def test_no_policy_editing_v1(self, ui_scope_doc: str) -> None:
        """Verify no policy editing in v1 is documented."""
        doc_lower = ui_scope_doc.lower()
        assert "policy editing" in doc_lower
        assert "not included" in doc_lower or "no" in doc_lower

    def test_ui_must_not_bypass_invariants(self, ui_scope_doc: str) -> None:
        """Verify UI must not bypass invariants is documented."""
        doc_lower = ui_scope_doc.lower()
        assert "ui" in doc_lower
        assert "must not bypass" in doc_lower or "not bypass" in doc_lower
        assert "invariant" in doc_lower

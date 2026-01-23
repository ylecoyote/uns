"""Tests for terminology consistency across documentation.

This module verifies that terminology is used consistently, particularly:
- "delivery service" refers to the DeliveryService component
- "delivery pipeline" refers to the sequence of processing steps

Per standardization task in uns-doc-nits.yaml.
"""

import re
from pathlib import Path

import pytest

# Paths to documentation files
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
ROOT_README = Path(__file__).parent.parent.parent / "README.md"
ARCHITECTURE_MD = DOCS_DIR / "ARCHITECTURE.md"
INTEGRATION_MODES_MD = DOCS_DIR / "sections" / "integration-modes.md"
DELIVERY_SEMANTICS_MD = DOCS_DIR / "sections" / "delivery-semantics.md"


@pytest.fixture
def architecture_content() -> str:
    """Load ARCHITECTURE.md content."""
    return ARCHITECTURE_MD.read_text()


@pytest.fixture
def readme_content() -> str:
    """Load README.md content."""
    return ROOT_README.read_text()


@pytest.fixture
def integration_modes_content() -> str:
    """Load integration-modes.md content."""
    return INTEGRATION_MODES_MD.read_text()


class TestDeliveryTerminologyStandardization:
    """Tests for delivery service vs delivery pipeline terminology."""

    def test_architecture_defines_terminology_distinction(
        self, architecture_content: str
    ) -> None:
        """ARCHITECTURE.md should clarify the terminology distinction."""
        # The terminology note should be present
        assert "Terminology Note" in architecture_content
        assert "delivery service" in architecture_content.lower()
        assert "delivery pipeline" in architecture_content.lower()

    def test_delivery_service_refers_to_component(
        self, architecture_content: str
    ) -> None:
        """Verify 'delivery service' is associated with the component."""
        # Check the section heading exists
        assert "### Delivery Service" in architecture_content
        # Check it references the module
        assert "notification.service" in architecture_content

    def test_delivery_pipeline_refers_to_steps(
        self, architecture_content: str
    ) -> None:
        """Verify 'delivery pipeline' describes the processing steps."""
        # The pipeline should be described with sequential steps
        assert "orchestrates the delivery pipeline" in architecture_content

    def test_readme_connects_service_to_pipeline(self, readme_content: str) -> None:
        """README should connect DeliveryService to the pipeline steps."""
        # Check that the Delivery Pipeline section mentions DeliveryService
        assert "### Delivery Pipeline" in readme_content
        assert "DeliveryService" in readme_content

    def test_integration_modes_component_table_correct(
        self, integration_modes_content: str
    ) -> None:
        """integration-modes.md should describe DeliveryService correctly."""
        # Should NOT conflate terms in the component table
        # The pattern "Delivery orchestration pipeline" is incorrect
        assert "Delivery orchestration pipeline" not in integration_modes_content
        # Should use correct terminology
        assert "Delivery service (orchestrates the delivery pipeline)" in integration_modes_content

    def test_integration_modes_file_tree_correct(
        self, integration_modes_content: str
    ) -> None:
        """integration-modes.md file tree should have correct comment."""
        # The file tree comment for service.py should mention both terms correctly
        # Should NOT just say "# Delivery pipeline"
        lines = integration_modes_content.split("\n")
        service_line = next(
            (line for line in lines if "service.py" in line and "#" in line), None
        )
        assert service_line is not None
        assert "Delivery service" in service_line or "delivery service" in service_line


class TestTerminologyConsistencyPatterns:
    """Test for patterns that might indicate incorrect terminology usage."""

    @pytest.mark.parametrize(
        "doc_path",
        [
            ROOT_README,
            ARCHITECTURE_MD,
            INTEGRATION_MODES_MD,
            DELIVERY_SEMANTICS_MD,
        ],
    )
    def test_no_conflated_terminology(self, doc_path: Path) -> None:
        """Verify documents don't conflate the two terms incorrectly.

        Incorrect patterns:
        - "delivery pipeline service"
        - "delivery service pipeline" (without 'orchestrates' context)
        """
        if not doc_path.exists():
            pytest.skip(f"{doc_path} does not exist")

        content = doc_path.read_text().lower()

        # These patterns would indicate conflated terminology
        bad_patterns = [
            "delivery pipeline service",  # Conflates terms
        ]

        for pattern in bad_patterns:
            assert pattern not in content, (
                f"Found potentially conflated terminology '{pattern}' in {doc_path.name}"
            )

    @pytest.mark.parametrize(
        "doc_path",
        [
            ROOT_README,
            ARCHITECTURE_MD,
            INTEGRATION_MODES_MD,
        ],
    )
    def test_delivery_service_capitalization_consistency(
        self, doc_path: Path
    ) -> None:
        """When referring to the class, DeliveryService should be capitalized."""
        if not doc_path.exists():
            pytest.skip(f"{doc_path} does not exist")

        content = doc_path.read_text()

        # If there are backtick-quoted references, they should be capitalized
        incorrect_class_refs = re.findall(r"`delivery\s*service`", content, re.IGNORECASE)
        incorrect_class_refs = [
            ref for ref in incorrect_class_refs if ref != "`DeliveryService`"
        ]

        # Allow lowercase when not in backticks (prose usage)
        assert len(incorrect_class_refs) == 0, (
            f"Found incorrectly capitalized class references in {doc_path.name}: {incorrect_class_refs}"
        )


class TestTerminologyDefinitions:
    """Test that terminology definitions are present where needed."""

    def test_architecture_has_terminology_note(self, architecture_content: str) -> None:
        """ARCHITECTURE.md should have a terminology note in Delivery Service section."""
        # Find the Delivery Service section
        service_section_start = architecture_content.find("### Delivery Service")
        assert service_section_start != -1, "Delivery Service section not found"

        # Get content after the section header (next 500 chars should contain the note)
        section_content = architecture_content[
            service_section_start : service_section_start + 500
        ]
        assert "Terminology Note" in section_content, (
            "Terminology note should appear near the Delivery Service section"
        )

    def test_terminology_note_content(self, architecture_content: str) -> None:
        """The terminology note should explain both terms."""
        # Find the terminology note section
        note_start = architecture_content.find("Terminology Note")
        assert note_start != -1

        note_content = architecture_content[note_start : note_start + 500]

        # Should mention delivery service as component
        assert "component" in note_content.lower() or "DeliveryService" in note_content

        # Should mention delivery pipeline as steps/sequence
        assert "step" in note_content.lower() or "sequence" in note_content.lower()

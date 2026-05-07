"""Tests for documentation cross-references and consistency."""

import re
from pathlib import Path

import pytest

# Paths to documentation files
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
ROOT_README = Path(__file__).parent.parent.parent / "README.md"
ARCHITECTURE_MD = DOCS_DIR / "ARCHITECTURE.md"
API_MD = DOCS_DIR / "API.md"
DOCS_README = DOCS_DIR / "README.md"
SECTIONS_DIR = DOCS_DIR / "sections"
DECISIONS_DIR = DOCS_DIR / "decisions"
UNS_README = DOCS_DIR / "uns" / "README.md"


@pytest.fixture
def root_readme() -> str:
    """Load root README.md."""
    assert ROOT_README.exists(), f"README.md not found at {ROOT_README}"
    return ROOT_README.read_text()


@pytest.fixture
def architecture_md() -> str:
    """Load ARCHITECTURE.md."""
    assert ARCHITECTURE_MD.exists(), f"ARCHITECTURE.md not found at {ARCHITECTURE_MD}"
    return ARCHITECTURE_MD.read_text()


@pytest.fixture
def api_md() -> str:
    """Load API.md."""
    assert API_MD.exists(), f"API.md not found at {API_MD}"
    return API_MD.read_text()


@pytest.fixture
def docs_readme() -> str:
    """Load docs/README.md."""
    assert DOCS_README.exists(), f"docs/README.md not found at {DOCS_README}"
    return DOCS_README.read_text()


@pytest.fixture
def uns_readme() -> str:
    """Load docs/uns/README.md."""
    assert UNS_README.exists(), f"docs/uns/README.md not found at {UNS_README}"
    return UNS_README.read_text()


class TestDocsReadmeExists:
    """Test that docs/README.md exists with proper structure."""

    def test_file_exists(self) -> None:
        """Verify docs/README.md exists."""
        assert DOCS_README.exists()

    def test_has_navigation_section(self, docs_readme: str) -> None:
        """Verify docs/README.md has navigation."""
        assert "## Task Navigation" in docs_readme
        assert "Evaluate AGSignal" in docs_readme

    def test_has_document_map(self, docs_readme: str) -> None:
        """Verify docs/README.md has document map."""
        assert "## Document Map" in docs_readme
        assert "uns/" in docs_readme
        assert "Historical UNS extraction materials" in docs_readme

    def test_has_reading_guide(self, docs_readme: str) -> None:
        """Verify docs/README.md has reading guide."""
        assert "## Reading Guide" in docs_readme

    def test_has_cross_reference_index(self, docs_readme: str) -> None:
        """Verify docs/README.md has cross-reference index."""
        assert "## Cross-Reference Index" in docs_readme


class TestSectionFilesExist:
    """Test that all section files exist."""

    def test_delivery_semantics_exists(self) -> None:
        """Verify delivery-semantics.md exists."""
        assert (SECTIONS_DIR / "delivery-semantics.md").exists()

    def test_integration_modes_exists(self) -> None:
        """Verify integration-modes.md exists."""
        assert (SECTIONS_DIR / "integration-modes.md").exists()

    def test_observability_exists(self) -> None:
        """Verify observability.md exists."""
        assert (SECTIONS_DIR / "observability.md").exists()

    def test_policy_lifecycle_exists(self) -> None:
        """Verify policy-lifecycle.md exists."""
        assert (SECTIONS_DIR / "policy-lifecycle.md").exists()


class TestDocsReadmeLinksToSections:
    """Test that docs/README.md links to all sections."""

    def test_links_to_architecture(self, docs_readme: str) -> None:
        """Verify link to ARCHITECTURE.md."""
        assert "[ARCHITECTURE.md](ARCHITECTURE.md)" in docs_readme

    def test_links_to_api(self, docs_readme: str) -> None:
        """Verify link to API.md."""
        assert "[API.md](API.md)" in docs_readme

    def test_links_to_delivery_semantics(self, docs_readme: str) -> None:
        """Verify link to delivery-semantics.md."""
        assert "sections/delivery-semantics.md" in docs_readme

    def test_links_to_integration_modes(self, docs_readme: str) -> None:
        """Verify link to integration-modes.md."""
        assert "sections/integration-modes.md" in docs_readme

    def test_links_to_observability(self, docs_readme: str) -> None:
        """Verify link to observability.md."""
        assert "sections/observability.md" in docs_readme

    def test_links_to_policy_lifecycle(self, docs_readme: str) -> None:
        """Verify link to policy-lifecycle.md."""
        assert "sections/policy-lifecycle.md" in docs_readme


class TestArchitectureCrossReferences:
    """Test that ARCHITECTURE.md has cross-references to sections."""

    def test_has_related_documentation_header(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md has related documentation section."""
        assert "## Related Documentation" in architecture_md

    def test_links_to_delivery_semantics(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md links to delivery-semantics.md."""
        assert "sections/delivery-semantics.md" in architecture_md

    def test_links_to_integration_modes(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md links to integration-modes.md."""
        assert "sections/integration-modes.md" in architecture_md

    def test_links_to_policy_lifecycle(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md links to policy-lifecycle.md."""
        assert "sections/policy-lifecycle.md" in architecture_md

    def test_links_to_api_md(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md links to API.md."""
        assert "API.md" in architecture_md


class TestApiCrossReferences:
    """Test that API.md has cross-references to sections."""

    def test_has_related_documentation_header(self, api_md: str) -> None:
        """Verify API.md has related documentation section."""
        assert "## Related Documentation" in api_md

    def test_links_to_delivery_semantics(self, api_md: str) -> None:
        """Verify API.md links to delivery-semantics.md."""
        assert "sections/delivery-semantics.md" in api_md

    def test_links_to_integration_modes(self, api_md: str) -> None:
        """Verify API.md links to integration-modes.md."""
        assert "sections/integration-modes.md" in api_md

    def test_links_to_policy_lifecycle(self, api_md: str) -> None:
        """Verify API.md links to policy-lifecycle.md."""
        assert "sections/policy-lifecycle.md" in api_md

    def test_links_to_architecture_md(self, api_md: str) -> None:
        """Verify API.md links to ARCHITECTURE.md."""
        assert "ARCHITECTURE.md" in api_md


class TestSectionsCrossReferenceBack:
    """Test that section files link back to main documents."""

    def test_delivery_semantics_links_to_architecture(self) -> None:
        """Verify delivery-semantics.md links to ARCHITECTURE.md."""
        content = (SECTIONS_DIR / "delivery-semantics.md").read_text()
        assert "../ARCHITECTURE.md" in content

    def test_integration_modes_links_to_architecture(self) -> None:
        """Verify integration-modes.md links to ARCHITECTURE.md."""
        content = (SECTIONS_DIR / "integration-modes.md").read_text()
        assert "../ARCHITECTURE.md" in content

    def test_observability_links_to_architecture(self) -> None:
        """Verify observability.md links to ARCHITECTURE.md."""
        content = (SECTIONS_DIR / "observability.md").read_text()
        assert "../ARCHITECTURE.md" in content

    def test_policy_lifecycle_links_to_architecture(self) -> None:
        """Verify policy-lifecycle.md links to ARCHITECTURE.md."""
        content = (SECTIONS_DIR / "policy-lifecycle.md").read_text()
        assert "../ARCHITECTURE.md" in content


class TestRootReadmeLinks:
    """Test that root README links to documentation."""

    def test_links_to_docs_readme(self, root_readme: str) -> None:
        """Verify root README links to docs/README.md."""
        assert "docs/README.md" in root_readme or "[Full Documentation]" in root_readme


class TestGovernanceAckConsistency:
    """Test GOVERNANCE acknowledgment description consistency across docs."""

    def test_root_readme_governance_ack_correct(self, root_readme: str) -> None:
        """Verify root README correctly describes GOVERNANCE ack as not required by default."""
        # GOVERNANCE should NOT require ack by default
        # The table should indicate "Not required" with footnote about 30min if enabled
        assert "GOVERNANCE" in root_readme
        # Should have footnote or clarification about GOVERNANCE ack
        assert "Not required*" in root_readme or "not required" in root_readme.lower()

    def test_architecture_governance_ack_correct(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md correctly describes GOVERNANCE ack."""
        # GOVERNANCE require_ack should default to False
        assert "require_ack = False" in architecture_md or "else:\n    require_ack = False" in architecture_md

    def test_delivery_semantics_governance_ack_correct(self) -> None:
        """Verify delivery-semantics.md correctly describes GOVERNANCE ack."""
        content = (SECTIONS_DIR / "delivery-semantics.md").read_text()
        # Should show GOVERNANCE does NOT require ack by default
        # The table shows: GOVERNANCE | No | No | No (30 min timeout if enabled)
        assert "GOVERNANCE" in content
        # Should indicate No for default ack requirement
        assert "No (30 min timeout if enabled)" in content or "| No | No | No |" in content


class TestNoAsyncPolicyRegistryGet:
    """Test that API.md does not document non-existent async get() method."""

    def test_no_async_get_documentation(self, api_md: str) -> None:
        """Verify API.md does not document async get() method that doesn't exist."""
        # Should NOT have "async def get" for PolicyRegistry
        # Should only have get_sync
        registry_section = re.search(
            r"### PolicyRegistry.*?(?=###|\Z)", api_md, re.DOTALL
        )
        assert registry_section is not None
        registry_content = registry_section.group(0)

        # Should have get_sync
        assert "get_sync" in registry_content
        # Should NOT have "async def get" in the method signature
        assert "async def get(" not in registry_content


class TestTerminologyConsistency:
    """Test terminology is consistent across documents."""

    def test_agsignal_terminology(self, docs_readme: str) -> None:
        """Verify AGSignal is the public product term."""
        assert "AGSignal" in docs_readme
        assert "AGSignal Core" in docs_readme
        assert "UNS" in docs_readme
        assert "Historical extraction/runtime name" in docs_readme

    def test_delivery_mode_terminology(self, docs_readme: str) -> None:
        """Verify delivery mode terminology is consistent."""
        assert "GUARANTEED" in docs_readme
        assert "BEST_EFFORT" in docs_readme

    def test_autonomy_mode_terminology(self, docs_readme: str) -> None:
        """Verify autonomy mode terminology is consistent."""
        assert "PREVIEW" in docs_readme
        assert "SHADOW" in docs_readme
        assert "LIVE" in docs_readme

    def test_intent_terminology(self, docs_readme: str) -> None:
        """Verify intent terminology is consistent."""
        assert "SAFETY" in docs_readme
        assert "GOVERNANCE" in docs_readme
        assert "OPERATIONAL" in docs_readme
        assert "INFORMATIONAL" in docs_readme


class TestUnsTaxonomyDecision:
    """Test that the UNS taxonomy decision is captured as provenance."""

    def test_decision_record_exists(self) -> None:
        """Verify the MIP-242 taxonomy decision has a durable decision record."""
        assert (DECISIONS_DIR / "2026-05-06-uns-taxonomy.md").exists()

    def test_docs_readme_links_taxonomy_decision(self, docs_readme: str) -> None:
        """Verify the docs index links the taxonomy decision."""
        assert "UNS Taxonomy" in docs_readme
        assert "decisions/2026-05-06-uns-taxonomy.md" in docs_readme

    def test_uns_folder_is_provenance_not_public_entrypoint(
        self, uns_readme: str
    ) -> None:
        """Verify docs/uns is explicitly historical rather than public product docs."""
        assert "historical extraction material" in uns_readme
        assert "should not be treated as the public product entrypoint" in uns_readme
        assert "instead of moving it to `docs/ags/`" in uns_readme

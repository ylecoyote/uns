"""Tests for verify command documentation references.

Tests validate that all file references in the /verify command documentation
point to actual files in the project. This ensures the command documentation
remains valid as the project evolves.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestUIBoundaryDocReferencesExist:
    """Test that UI boundary documentation references exist."""

    def test_ui_scope_exists(self) -> None:
        """Verify docs/ui/ui-scope.md exists."""
        path = PROJECT_ROOT / "docs" / "ui" / "ui-scope.md"
        assert path.exists(), f"UI scope doc not found at {path}"

    def test_apps_ui_readme_exists(self) -> None:
        """Verify apps/ui/README.md exists."""
        path = PROJECT_ROOT / "apps" / "ui" / "README.md"
        assert path.exists(), f"Apps UI README not found at {path}"

    def test_invariants_yml_exists(self) -> None:
        """Verify docs/verification/invariants.yml exists."""
        path = PROJECT_ROOT / "docs" / "verification" / "invariants.yml"
        assert path.exists(), f"Invariants registry not found at {path}"


class TestContractDocReferencesExist:
    """Test that contract documentation references exist."""

    def test_ui_data_contracts_exists(self) -> None:
        """Verify docs/ui/ui-data-contracts.md exists."""
        path = PROJECT_ROOT / "docs" / "ui" / "ui-data-contracts.md"
        assert path.exists(), f"UI data contracts doc not found at {path}"

    def test_apps_ui_types_dir_exists(self) -> None:
        """Verify apps/ui/src/types/ directory exists."""
        path = PROJECT_ROOT / "apps" / "ui" / "src" / "types"
        assert path.exists(), f"UI types directory not found at {path}"
        assert path.is_dir()

    def test_apps_ui_api_dir_exists(self) -> None:
        """Verify apps/ui/src/api/ directory exists."""
        path = PROJECT_ROOT / "apps" / "ui" / "src" / "api"
        assert path.exists(), f"UI API directory not found at {path}"
        assert path.is_dir()


class TestInvariantRegistryContainsUIInvariants:
    """Test that the invariant registry contains UI-related invariants."""

    @pytest.fixture
    def invariants_content(self) -> str:
        """Load the invariants registry."""
        path = PROJECT_ROOT / "docs" / "verification" / "invariants.yml"
        assert path.exists()
        return path.read_text()

    def test_inv_ui_001_exists(self, invariants_content: str) -> None:
        """Verify INV-UI-001 is defined in the registry."""
        assert "INV-UI-001" in invariants_content

    def test_inv_ui_001_read_only_constraint(self, invariants_content: str) -> None:
        """Verify INV-UI-001 describes read-only UI constraint."""
        assert "read-only" in invariants_content.lower()
        assert "UI endpoints" in invariants_content or "ui endpoints" in invariants_content.lower()


class TestUIReadmeContainsDesignPrinciples:
    """Test that the UI README contains required design principles."""

    @pytest.fixture
    def readme_content(self) -> str:
        """Load the UI README."""
        path = PROJECT_ROOT / "apps" / "ui" / "README.md"
        assert path.exists()
        return path.read_text()

    def test_read_only_endpoints_documented(self, readme_content: str) -> None:
        """Verify read-only endpoints constraint is documented."""
        content_lower = readme_content.lower()
        assert "read-only" in content_lower or "read only" in content_lower
        assert "endpoint" in content_lower

    def test_no_direct_backend_imports_documented(self, readme_content: str) -> None:
        """Verify no direct backend imports constraint is documented."""
        content_lower = readme_content.lower()
        assert "no direct backend imports" in content_lower or "not import" in content_lower

    def test_invariant_integrity_documented(self, readme_content: str) -> None:
        """Verify invariant integrity constraint is documented."""
        content_lower = readme_content.lower()
        assert "invariant" in content_lower

    def test_inv_ui_001_reference(self, readme_content: str) -> None:
        """Verify INV-UI-001 is referenced."""
        assert "INV-UI-001" in readme_content

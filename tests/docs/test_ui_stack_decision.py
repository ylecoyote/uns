"""Tests for UI stack decision documentation.

Tests verify that apps/ui/README.md properly documents:
- Canonical UI stack: React + TypeScript + Vite
- UI is non-authoritative and read-first
- UI must only call HTTP endpoints under /ui/* (no direct imports from backend src/)
- Phase 1 posture: GET-only from UI; no mutation actions
- Degraded-state handling
- How to run dev server, tests
- Environment variables (VITE_UNS_API_BASE_URL)
- .env.example file exists
"""

from pathlib import Path

import pytest

UI_README_PATH = Path(__file__).parent.parent.parent / "apps" / "ui" / "README.md"
ENV_EXAMPLE_PATH = Path(__file__).parent.parent.parent / "apps" / "ui" / ".env.example"


@pytest.fixture
def ui_readme() -> str:
    """Load the UI README documentation."""
    assert UI_README_PATH.exists(), f"apps/ui/README.md not found at {UI_README_PATH}"
    return UI_README_PATH.read_text()


@pytest.fixture
def env_example() -> str:
    """Load the .env.example file."""
    assert ENV_EXAMPLE_PATH.exists(), f".env.example not found at {ENV_EXAMPLE_PATH}"
    return ENV_EXAMPLE_PATH.read_text()


class TestUIStackDecisionDocExists:
    """Test that required files exist."""

    def test_readme_exists(self) -> None:
        """Verify apps/ui/README.md exists."""
        assert UI_README_PATH.exists()

    def test_env_example_exists(self) -> None:
        """Verify apps/ui/.env.example exists."""
        assert ENV_EXAMPLE_PATH.exists()

    def test_readme_not_empty(self, ui_readme: str) -> None:
        """Verify README is not empty."""
        assert len(ui_readme) > 0

    def test_env_example_not_empty(self, env_example: str) -> None:
        """Verify .env.example is not empty."""
        assert len(env_example) > 0


class TestCanonicalUIStack:
    """Test that canonical UI stack is properly documented."""

    def test_documents_react(self, ui_readme: str) -> None:
        """Verify React is documented as part of the stack."""
        assert "React" in ui_readme

    def test_documents_typescript(self, ui_readme: str) -> None:
        """Verify TypeScript is documented as part of the stack."""
        assert "TypeScript" in ui_readme

    def test_documents_vite(self, ui_readme: str) -> None:
        """Verify Vite is documented as part of the stack."""
        assert "Vite" in ui_readme

    def test_canonical_stack_statement(self, ui_readme: str) -> None:
        """Verify canonical stack is explicitly stated."""
        assert "React + TypeScript + Vite" in ui_readme or "React, TypeScript, Vite" in ui_readme

    def test_spa_mentioned(self, ui_readme: str) -> None:
        """Verify SPA (Single Page Application) architecture is mentioned."""
        assert "SPA" in ui_readme

    def test_has_stack_section(self, ui_readme: str) -> None:
        """Verify README has a Stack section."""
        assert "## Stack" in ui_readme


class TestNonAuthoritativeUI:
    """Test that non-authoritative UI principle is documented."""

    def test_non_authoritative_mentioned(self, ui_readme: str) -> None:
        """Verify non-authoritative principle is mentioned."""
        readme_lower = ui_readme.lower()
        assert "non-authoritative" in readme_lower

    def test_read_first_mentioned(self, ui_readme: str) -> None:
        """Verify read-first principle is mentioned."""
        readme_lower = ui_readme.lower()
        assert "read-first" in readme_lower or "read-only" in readme_lower

    def test_flight_instruments_mentioned(self, ui_readme: str) -> None:
        """Verify 'flight instruments' metaphor is used."""
        readme_lower = ui_readme.lower()
        assert "flight instruments" in readme_lower

    def test_backend_authoritative(self, ui_readme: str) -> None:
        """Verify backend is stated as authoritative for business rules."""
        readme_lower = ui_readme.lower()
        assert "backend" in readme_lower
        assert "authoritative" in readme_lower or "business rules" in readme_lower


class TestUIEndpointBoundary:
    """Test that UI endpoint boundaries are documented."""

    def test_ui_only_calls_ui_endpoints(self, ui_readme: str) -> None:
        """Verify UI must only call /ui/* endpoints."""
        assert "/ui/" in ui_readme or "`/ui/*`" in ui_readme

    def test_no_direct_backend_imports(self, ui_readme: str) -> None:
        """Verify no direct backend imports constraint is documented."""
        readme_lower = ui_readme.lower()
        assert "no direct" in readme_lower or "does not import" in readme_lower

    def test_http_only_constraint(self, ui_readme: str) -> None:
        """Verify HTTP-only constraint is documented."""
        assert "HTTP" in ui_readme or "endpoints" in ui_readme


class TestPhase1Posture:
    """Test that Phase 1 GET-only posture is documented."""

    def test_get_only_documented(self, ui_readme: str) -> None:
        """Verify GET-only constraint is documented."""
        assert "GET-only" in ui_readme or "GET only" in ui_readme

    def test_no_mutations_in_phase1(self, ui_readme: str) -> None:
        """Verify no mutations in Phase 1 is documented."""
        readme_lower = ui_readme.lower()
        assert "mutation" in readme_lower or "post" in readme_lower or "put" in readme_lower

    def test_phase_1_posture_section(self, ui_readme: str) -> None:
        """Verify Phase 1 posture is documented."""
        assert "Phase 1" in ui_readme

    def test_read_only_dashboards_included(self, ui_readme: str) -> None:
        """Verify read-only dashboards are included."""
        readme_lower = ui_readme.lower()
        assert "read-only" in readme_lower
        assert "dashboard" in readme_lower


class TestDegradedStateHandling:
    """Test that degraded-state handling is documented."""

    def test_degraded_state_mentioned(self, ui_readme: str) -> None:
        """Verify degraded state handling is mentioned."""
        readme_lower = ui_readme.lower()
        assert "degraded" in readme_lower

    def test_degraded_banner_mentioned(self, ui_readme: str) -> None:
        """Verify degraded banner UI element is mentioned."""
        readme_lower = ui_readme.lower()
        assert "degraded" in readme_lower and "banner" in readme_lower


class TestDevServerInstructions:
    """Test that dev server instructions are documented."""

    def test_npm_run_dev(self, ui_readme: str) -> None:
        """Verify npm run dev command is documented."""
        assert "npm run dev" in ui_readme or "npm dev" in ui_readme

    def test_localhost_url(self, ui_readme: str) -> None:
        """Verify localhost URL is documented."""
        assert "localhost" in ui_readme

    def test_local_development_section(self, ui_readme: str) -> None:
        """Verify Local Development section exists."""
        assert "## Local Development" in ui_readme or "### Local Development" in ui_readme


class TestTestInstructions:
    """Test that test instructions are documented."""

    def test_npm_test_documented(self, ui_readme: str) -> None:
        """Verify npm test command is documented."""
        assert "npm test" in ui_readme or "npm run test" in ui_readme

    def test_vitest_mentioned(self, ui_readme: str) -> None:
        """Verify Vitest is mentioned as test framework."""
        assert "Vitest" in ui_readme or "vitest" in ui_readme

    def test_run_tests_section(self, ui_readme: str) -> None:
        """Verify Run Tests section exists."""
        assert "Run Tests" in ui_readme or "run tests" in ui_readme.lower()


class TestEnvironmentVariables:
    """Test that environment variables are documented."""

    def test_vite_api_base_url_in_readme(self, ui_readme: str) -> None:
        """Verify VITE_UNS_API_BASE_URL is documented in README."""
        assert "VITE_UNS_API_BASE_URL" in ui_readme

    def test_vite_api_base_url_in_env_example(self, env_example: str) -> None:
        """Verify VITE_UNS_API_BASE_URL is in .env.example."""
        assert "VITE_UNS_API_BASE_URL" in env_example

    def test_vite_prefix_explained(self, ui_readme: str) -> None:
        """Verify VITE_ prefix requirement is explained."""
        assert "VITE_" in ui_readme

    def test_env_example_has_default_value(self, env_example: str) -> None:
        """Verify .env.example has default value for API URL."""
        assert "localhost:8000" in env_example or "localhost" in env_example

    def test_environment_variables_section(self, ui_readme: str) -> None:
        """Verify Environment Variables section exists."""
        assert "## Environment Variables" in ui_readme or "Environment" in ui_readme


class TestEnvExampleContent:
    """Test .env.example file content."""

    def test_has_comments(self, env_example: str) -> None:
        """Verify .env.example has explanatory comments."""
        assert "#" in env_example

    def test_has_vite_prefix_note(self, env_example: str) -> None:
        """Verify .env.example notes VITE_ prefix requirement."""
        assert "VITE_" in env_example

    def test_default_api_url(self, env_example: str) -> None:
        """Verify default API URL is localhost:8000."""
        assert "localhost:8000" in env_example


class TestInvariantIntegrity:
    """Test that invariant integrity is documented."""

    def test_invariant_mentioned(self, ui_readme: str) -> None:
        """Verify invariant integrity is mentioned."""
        readme_lower = ui_readme.lower()
        assert "invariant" in readme_lower

    def test_inv_ui_001_reference(self, ui_readme: str) -> None:
        """Verify INV-UI-001 invariant is referenced."""
        assert "INV-UI-001" in ui_readme

    def test_invariants_yml_link(self, ui_readme: str) -> None:
        """Verify link to invariants.yml exists."""
        assert "invariants.yml" in ui_readme


class TestProjectStructure:
    """Test that project structure is documented."""

    def test_has_project_structure_section(self, ui_readme: str) -> None:
        """Verify Project Structure section exists."""
        assert "## Project Structure" in ui_readme

    def test_documents_main_tsx(self, ui_readme: str) -> None:
        """Verify main.tsx entry point is documented."""
        assert "main.tsx" in ui_readme

    def test_documents_app_tsx(self, ui_readme: str) -> None:
        """Verify App.tsx is documented."""
        assert "App.tsx" in ui_readme

    def test_documents_api_directory(self, ui_readme: str) -> None:
        """Verify src/api/ directory is documented."""
        assert "api/" in ui_readme or "api" in ui_readme

    def test_documents_pages_directory(self, ui_readme: str) -> None:
        """Verify src/pages/ directory is documented."""
        assert "pages/" in ui_readme or "pages" in ui_readme

    def test_documents_components_directory(self, ui_readme: str) -> None:
        """Verify src/components/ directory is documented."""
        assert "components/" in ui_readme or "components" in ui_readme


class TestAPIEndpointsConsumed:
    """Test that API endpoints consumed by UI are documented."""

    def test_has_api_endpoints_section(self, ui_readme: str) -> None:
        """Verify API Endpoints section exists."""
        assert "Endpoint" in ui_readme

    def test_documents_deliveries_endpoint(self, ui_readme: str) -> None:
        """Verify deliveries endpoint is documented."""
        assert "/deliveries" in ui_readme or "deliveries" in ui_readme.lower()

    def test_documents_invariants_endpoint(self, ui_readme: str) -> None:
        """Verify invariants endpoint is documented."""
        assert "/invariants" in ui_readme or "invariants" in ui_readme.lower()

    def test_documents_audit_endpoint(self, ui_readme: str) -> None:
        """Verify audit endpoint is documented."""
        assert "/audit" in ui_readme or "audit" in ui_readme.lower()

    def test_documents_policies_endpoint(self, ui_readme: str) -> None:
        """Verify policies endpoint is documented."""
        assert "/policies" in ui_readme or "policies" in ui_readme.lower()


class TestScriptsReference:
    """Test that npm scripts are documented."""

    def test_has_scripts_section(self, ui_readme: str) -> None:
        """Verify Scripts Reference section exists."""
        assert "Scripts" in ui_readme

    def test_documents_dev_script(self, ui_readme: str) -> None:
        """Verify dev script is documented."""
        assert "dev" in ui_readme

    def test_documents_build_script(self, ui_readme: str) -> None:
        """Verify build script is documented."""
        assert "build" in ui_readme

    def test_documents_lint_script(self, ui_readme: str) -> None:
        """Verify lint script is documented."""
        assert "lint" in ui_readme


class TestRelatedDocumentation:
    """Test that related documentation links are included."""

    def test_links_to_ui_scope(self, ui_readme: str) -> None:
        """Verify link to ui-scope.md exists."""
        assert "ui-scope.md" in ui_readme

    def test_links_to_ui_data_contracts(self, ui_readme: str) -> None:
        """Verify link to ui-data-contracts.md exists."""
        assert "ui-data-contracts.md" in ui_readme

    def test_has_related_documentation_section(self, ui_readme: str) -> None:
        """Verify Related Documentation section exists."""
        assert "## Related Documentation" in ui_readme or "Related" in ui_readme

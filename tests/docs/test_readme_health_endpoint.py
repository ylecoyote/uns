"""Tests for /health endpoint documentation in the root README.

Tests verify that the root README includes guidance on the /health endpoint
for developers running UNS as a service.
"""

from pathlib import Path

import pytest

# Path to the root README
ROOT_README_PATH = Path(__file__).parent.parent.parent / "README.md"


@pytest.fixture
def root_readme() -> str:
    """Load the root README content."""
    assert ROOT_README_PATH.exists(), f"README.md not found at {ROOT_README_PATH}"
    return ROOT_README_PATH.read_text()


class TestRootReadmeHealthEndpoint:
    """Test that root README documents the /health endpoint."""

    def test_readme_exists(self) -> None:
        """Verify README.md exists at project root."""
        assert ROOT_README_PATH.exists()

    def test_readme_mentions_health_endpoint(self, root_readme: str) -> None:
        """Verify /health endpoint is mentioned in README."""
        assert "/health" in root_readme

    def test_readme_has_running_the_service_section(self, root_readme: str) -> None:
        """Verify README has a section for running the service."""
        assert "## Running the Service" in root_readme

    def test_readme_has_health_check_section(self, root_readme: str) -> None:
        """Verify README has a Health Check section."""
        assert "### Health Check" in root_readme or "## Health Check" in root_readme

    def test_readme_shows_health_endpoint_response(self, root_readme: str) -> None:
        """Verify README shows the /health endpoint response format."""
        # Should show the response format
        assert '"status"' in root_readme
        assert '"healthy"' in root_readme

    def test_readme_shows_curl_example(self, root_readme: str) -> None:
        """Verify README includes a curl example for health check."""
        assert "curl" in root_readme
        assert "/health" in root_readme

    def test_readme_links_to_observability_docs(self, root_readme: str) -> None:
        """Verify README links to observability documentation for more details."""
        assert "observability" in root_readme.lower()

    def test_readme_mentions_uvicorn_command(self, root_readme: str) -> None:
        """Verify README shows how to start the server."""
        assert "uvicorn" in root_readme
        assert "mcp_server.app" in root_readme

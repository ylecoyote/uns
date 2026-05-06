"""Tests for integration-modes.md structure and content."""

import re
from pathlib import Path

import pytest

# Path to the integration modes documentation
INTEGRATION_MODES_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "sections" / "integration-modes.md"
)
ARCHITECTURE_PATH = Path(__file__).parent.parent.parent / "docs" / "ARCHITECTURE.md"


@pytest.fixture
def integration_modes_doc() -> str:
    """Load the integration modes documentation."""
    assert INTEGRATION_MODES_PATH.exists(), (
        f"integration-modes.md not found at {INTEGRATION_MODES_PATH}"
    )
    return INTEGRATION_MODES_PATH.read_text()


@pytest.fixture
def architecture_doc() -> str:
    """Load the architecture documentation."""
    assert ARCHITECTURE_PATH.exists(), f"ARCHITECTURE.md not found at {ARCHITECTURE_PATH}"
    return ARCHITECTURE_PATH.read_text()


class TestIntegrationModesExists:
    """Test that the document exists and has basic structure."""

    def test_file_exists(self) -> None:
        """Verify integration-modes.md exists."""
        assert INTEGRATION_MODES_PATH.exists()

    def test_file_not_empty(self, integration_modes_doc: str) -> None:
        """Verify integration-modes.md is not empty."""
        assert len(integration_modes_doc) > 0

    def test_is_markdown(self, integration_modes_doc: str) -> None:
        """Verify file contains markdown headings."""
        assert "# " in integration_modes_doc


class TestIntegrationModesStructure:
    """Test the structure of the integration modes documentation."""

    def test_has_title(self, integration_modes_doc: str) -> None:
        """Verify document has correct title."""
        assert integration_modes_doc.startswith("# Integration Modes")

    def test_has_overview_section(self, integration_modes_doc: str) -> None:
        """Verify document has overview section."""
        assert "## Overview" in integration_modes_doc

    def test_has_architecture_separation_section(self, integration_modes_doc: str) -> None:
        """Verify document has architecture separation section."""
        assert "## Architecture Separation" in integration_modes_doc

    def test_has_integration_modes_section(self, integration_modes_doc: str) -> None:
        """Verify document has integration modes section."""
        assert "## Integration Modes" in integration_modes_doc

    def test_has_summary_section(self, integration_modes_doc: str) -> None:
        """Verify document has summary section."""
        assert "## Summary" in integration_modes_doc


class TestATPAgnosticClaims:
    """Test that the document clearly states UNS is ATP-agnostic."""

    def test_states_atp_agnostic(self, integration_modes_doc: str) -> None:
        """Verify document explicitly states UNS is ATP-agnostic."""
        assert "ATP-agnostic" in integration_modes_doc

    def test_states_uns_does_not_require_atp(self, integration_modes_doc: str) -> None:
        """Verify document states UNS does NOT require ATP."""
        # Check for explicit statement that UNS doesn't require ATP
        assert (
            "NOT require ATP" in integration_modes_doc
            or "does not require ATP" in integration_modes_doc.lower()
        )

    def test_atp_is_optional(self, integration_modes_doc: str) -> None:
        """Verify document states ATP integration is optional."""
        assert "optional" in integration_modes_doc.lower()

    def test_standalone_mode_documented(self, integration_modes_doc: str) -> None:
        """Verify standalone mode is documented."""
        assert "Standalone" in integration_modes_doc or "standalone" in integration_modes_doc


class TestCoreSeparation:
    """Test that UNS core components are clearly separated from integrations."""

    def test_core_components_listed(self, integration_modes_doc: str) -> None:
        """Verify core UNS components are listed."""
        core_components = [
            "NotificationSDK",
            "PolicyRegistry",
            "DeliveryService",
            "DeduplicationEngine",
            "RateLimiter",
            "AcknowledgmentEngine",
        ]
        for component in core_components:
            assert component in integration_modes_doc, f"Core component {component} not documented"

    def test_integration_protocols_listed(self, integration_modes_doc: str) -> None:
        """Verify integration protocols are listed."""
        protocols = [
            "NotificationContextProvider",
            "AcknowledgmentCallback",
        ]
        for protocol in protocols:
            assert protocol in integration_modes_doc, f"Protocol {protocol} not documented"

    def test_default_implementations_listed(self, integration_modes_doc: str) -> None:
        """Verify default implementations are listed."""
        defaults = [
            "DefaultContextProvider",
            "NoOpAcknowledgmentCallback",
            "LoggingAcknowledgmentCallback",
        ]
        for default in defaults:
            assert default in integration_modes_doc, (
                f"Default implementation {default} not documented"
            )


class TestIntegrationModesContent:
    """Test that all integration modes are documented."""

    def test_standalone_mode_documented(self, integration_modes_doc: str) -> None:
        """Verify Mode 1: Standalone is documented."""
        assert "Mode 1" in integration_modes_doc or "Standalone" in integration_modes_doc

    def test_context_provider_mode_documented(self, integration_modes_doc: str) -> None:
        """Verify Mode 2: Context Provider Integration is documented."""
        assert "Mode 2" in integration_modes_doc or "Context Provider" in integration_modes_doc

    def test_full_integration_mode_documented(self, integration_modes_doc: str) -> None:
        """Verify Mode 3: Full External Integration is documented."""
        assert (
            "Mode 3" in integration_modes_doc
            or "Full External Integration" in integration_modes_doc
        )

    def test_includes_code_examples(self, integration_modes_doc: str) -> None:
        """Verify document includes code examples."""
        assert "```python" in integration_modes_doc

    def test_generic_app_boundary_documented(self, integration_modes_doc: str) -> None:
        """Verify generic app adapter boundary is documented without MIP coupling."""
        assert "AppSignalAdapter" in integration_modes_doc
        assert "AppEvidenceContext" in integration_modes_doc
        assert "notification.integrations" in integration_modes_doc
        assert "MIP-specific" in integration_modes_doc


class TestWebSocketClarification:
    """Test that WebSocket ownership is clarified."""

    def test_websocket_section_exists(self, integration_modes_doc: str) -> None:
        """Verify WebSocket section exists."""
        assert "WebSocket" in integration_modes_doc

    def test_websocket_connection_ownership_clarified(self, integration_modes_doc: str) -> None:
        """Verify WebSocket connection management ownership is clarified."""
        # Should state UNS does NOT manage WebSocket connections
        doc_lower = integration_modes_doc.lower()
        assert "websocket" in doc_lower
        # Check for ownership clarification
        assert "does not" in doc_lower or "NOT" in integration_modes_doc

    def test_websocket_manager_injection_documented(self, integration_modes_doc: str) -> None:
        """Verify WebSocket manager injection pattern is documented."""
        assert (
            "inject" in integration_modes_doc.lower()
            or "connection_manager" in integration_modes_doc
        )


class TestComponentOwnership:
    """Test that component ownership is clearly documented."""

    def test_ownership_section_exists(self, integration_modes_doc: str) -> None:
        """Verify component ownership section exists."""
        assert "Ownership" in integration_modes_doc or "ownership" in integration_modes_doc.lower()

    def test_agsignal_owned_components_listed(self, integration_modes_doc: str) -> None:
        """Verify AGSignal Core-owned components are listed."""
        assert (
            "AGSignal Core" in integration_modes_doc
            or "AGSignal Core owned" in integration_modes_doc
        )

    def test_external_owned_components_listed(self, integration_modes_doc: str) -> None:
        """Verify externally-owned components are listed."""
        assert "External" in integration_modes_doc or "integrator" in integration_modes_doc.lower()


class TestArchitectureReferences:
    """Test that ARCHITECTURE.md references integration modes."""

    def test_architecture_mentions_atp_agnostic(self, architecture_doc: str) -> None:
        """Verify ARCHITECTURE.md mentions ATP-agnostic design."""
        assert "ATP-agnostic" in architecture_doc

    def test_architecture_references_integration_modes(self, architecture_doc: str) -> None:
        """Verify ARCHITECTURE.md references integration-modes.md."""
        assert (
            "integration-modes" in architecture_doc.lower()
            or "Integration Modes" in architecture_doc
        )

    def test_architecture_mentions_optional_integration(self, architecture_doc: str) -> None:
        """Verify ARCHITECTURE.md mentions integration points are optional."""
        assert "optional" in architecture_doc.lower()


class TestDependencyInjection:
    """Test that dependency injection pattern is documented."""

    def test_dependency_injection_documented(self, integration_modes_doc: str) -> None:
        """Verify dependency injection pattern is documented."""
        assert (
            "dependency injection" in integration_modes_doc.lower()
            or "Dependency Injection" in integration_modes_doc
        )

    def test_protocol_based_design_explained(self, integration_modes_doc: str) -> None:
        """Verify protocol-based design is explained."""
        assert "protocol" in integration_modes_doc.lower()


class TestSummaryTable:
    """Test that the summary table is complete."""

    def test_has_summary_table(self, integration_modes_doc: str) -> None:
        """Verify document has a summary table."""
        # Look for markdown table syntax in summary section
        summary_match = re.search(r"## Summary.*", integration_modes_doc, re.DOTALL)
        assert summary_match is not None
        summary = summary_match.group(0)
        assert "|" in summary

    def test_summary_distinguishes_agsignal_and_external(
        self, integration_modes_doc: str
    ) -> None:
        """Verify summary table distinguishes AGSignal Core from external."""
        summary_match = re.search(r"## Summary.*", integration_modes_doc, re.DOTALL)
        assert summary_match is not None
        summary = summary_match.group(0)
        assert "AGSignal Core" in summary
        assert "External" in summary or "integrator" in summary.lower()


class TestRelatedDocumentation:
    """Test that related documentation is linked."""

    def test_links_to_architecture(self, integration_modes_doc: str) -> None:
        """Verify document links to ARCHITECTURE.md."""
        assert "ARCHITECTURE.md" in integration_modes_doc or "Architecture" in integration_modes_doc

    def test_links_to_api(self, integration_modes_doc: str) -> None:
        """Verify document links to API.md."""
        assert "API.md" in integration_modes_doc or "API Reference" in integration_modes_doc

    def test_links_to_policy_lifecycle(self, integration_modes_doc: str) -> None:
        """Verify document links to policy-lifecycle.md."""
        assert (
            "policy-lifecycle" in integration_modes_doc.lower()
            or "Policy Lifecycle" in integration_modes_doc
        )

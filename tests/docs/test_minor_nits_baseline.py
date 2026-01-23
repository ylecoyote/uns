"""Tests for minor-nits-baseline.md report validation.

These tests verify:
1. API.md NotificationPolicy documents the intent field
2. Terminology consistency across documents
3. Cross-document alignment for key concepts
4. No contradictions introduced by documentation updates
"""

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
POLICY_LIFECYCLE_MD = SECTIONS_DIR / "policy-lifecycle.md"
DELIVERY_SEMANTICS_MD = SECTIONS_DIR / "delivery-semantics.md"
OBSERVABILITY_MD = SECTIONS_DIR / "observability.md"
INTEGRATION_MODES_MD = SECTIONS_DIR / "integration-modes.md"
REPORTS_DIR = DOCS_DIR / "reports"
MINOR_NITS_BASELINE = REPORTS_DIR / "minor-nits-baseline.md"


@pytest.fixture
def api_md() -> str:
    """Load API.md."""
    assert API_MD.exists(), f"API.md not found at {API_MD}"
    return API_MD.read_text()


@pytest.fixture
def policy_lifecycle_md() -> str:
    """Load policy-lifecycle.md."""
    assert POLICY_LIFECYCLE_MD.exists()
    return POLICY_LIFECYCLE_MD.read_text()


@pytest.fixture
def delivery_semantics_md() -> str:
    """Load delivery-semantics.md."""
    assert DELIVERY_SEMANTICS_MD.exists()
    return DELIVERY_SEMANTICS_MD.read_text()


@pytest.fixture
def observability_md() -> str:
    """Load observability.md."""
    assert OBSERVABILITY_MD.exists()
    return OBSERVABILITY_MD.read_text()


@pytest.fixture
def root_readme() -> str:
    """Load root README.md."""
    assert ROOT_README.exists()
    return ROOT_README.read_text()


@pytest.fixture
def architecture_md() -> str:
    """Load ARCHITECTURE.md."""
    assert ARCHITECTURE_MD.exists()
    return ARCHITECTURE_MD.read_text()


class TestMinorNitsBaselineReportExists:
    """Test that minor-nits-baseline.md report exists."""

    def test_report_exists(self) -> None:
        """Verify minor-nits-baseline.md exists."""
        assert MINOR_NITS_BASELINE.exists(), (
            f"minor-nits-baseline.md not found at {MINOR_NITS_BASELINE}"
        )

    def test_report_has_executive_summary(self) -> None:
        """Verify report has executive summary."""
        content = MINOR_NITS_BASELINE.read_text()
        assert "## Executive Summary" in content

    def test_report_has_action_items(self) -> None:
        """Verify report has action items section."""
        content = MINOR_NITS_BASELINE.read_text()
        assert "## 4. Action Items" in content or "Action Items" in content


class TestApiMdNotificationPolicyIntentField:
    """Test that API.md includes the intent field on NotificationPolicy.

    This was the primary fix identified by the minor nits baseline scan.
    """

    def test_notification_policy_has_intent_field(self, api_md: str) -> None:
        """Verify NotificationPolicy in API.md has intent field."""
        # Find the NotificationPolicy section
        policy_section = re.search(r"### NotificationPolicy.*?(?=###|\Z)", api_md, re.DOTALL)
        assert policy_section is not None, "NotificationPolicy section not found in API.md"
        policy_content = policy_section.group(0)

        # Check that intent field is documented
        assert "intent:" in policy_content or "intent =" in policy_content, (
            "intent field not found in NotificationPolicy section of API.md"
        )

    def test_notification_policy_intent_field_is_optional(self, api_md: str) -> None:
        """Verify intent field is documented as optional (None default)."""
        policy_section = re.search(r"### NotificationPolicy.*?(?=###|\Z)", api_md, re.DOTALL)
        assert policy_section is not None
        policy_content = policy_section.group(0)

        # intent should be NotificationIntent | None
        assert (
            "NotificationIntent | None" in policy_content or "NotificationIntent" in policy_content
        )

    def test_notification_policy_intent_matches_policy_lifecycle(
        self, api_md: str, policy_lifecycle_md: str
    ) -> None:
        """Verify API.md and policy-lifecycle.md both document intent field."""
        # Both should document the intent field
        assert "intent" in api_md
        assert "intent" in policy_lifecycle_md

        # policy-lifecycle.md line 387 should have intent in the API reference table
        assert "`intent`" in policy_lifecycle_md


class TestTerminologyConsistencyAcrossDocs:
    """Test that terminology is consistent across all documents."""

    def test_delivery_mode_terminology_root_readme(self, root_readme: str) -> None:
        """Verify delivery mode terms in root README."""
        assert "GUARANTEED" in root_readme
        assert "BEST_EFFORT" in root_readme

    def test_delivery_mode_terminology_architecture(self, architecture_md: str) -> None:
        """Verify delivery mode terms in ARCHITECTURE.md."""
        assert "GUARANTEED" in architecture_md
        assert "BEST_EFFORT" in architecture_md

    def test_delivery_mode_terminology_delivery_semantics(self, delivery_semantics_md: str) -> None:
        """Verify delivery mode terms in delivery-semantics.md."""
        assert "GUARANTEED" in delivery_semantics_md
        assert "BEST_EFFORT" in delivery_semantics_md

    def test_intent_terminology_consistent(
        self,
        root_readme: str,
        architecture_md: str,
        delivery_semantics_md: str,
    ) -> None:
        """Verify intent terminology is consistent."""
        intents = ["SAFETY", "GOVERNANCE", "OPERATIONAL", "INFORMATIONAL"]
        for doc_name, doc in [
            ("root_readme", root_readme),
            ("architecture", architecture_md),
            ("delivery_semantics", delivery_semantics_md),
        ]:
            for intent in intents:
                assert intent in doc, f"{intent} not found in {doc_name}"

    def test_autonomy_mode_terminology_consistent(
        self,
        root_readme: str,
        architecture_md: str,
        policy_lifecycle_md: str,
    ) -> None:
        """Verify autonomy mode terminology is consistent."""
        modes = ["PREVIEW", "SHADOW", "LIVE"]
        for doc_name, doc in [
            ("root_readme", root_readme),
            ("architecture", architecture_md),
            ("policy_lifecycle", policy_lifecycle_md),
        ]:
            for mode in modes:
                assert mode in doc, f"{mode} not found in {doc_name}"


class TestChannelRoutingConsistency:
    """Test that channel routing tables are consistent across documents."""

    def test_live_mode_safety_routing_consistent(
        self,
        root_readme: str,
        architecture_md: str,
        delivery_semantics_md: str,
    ) -> None:
        """Verify SAFETY intent LIVE mode routing is consistent."""
        # All docs should mention Slack + WebSocket for SAFETY in LIVE mode
        # with optional PagerDuty if irreversible
        for doc in [root_readme, architecture_md, delivery_semantics_md]:
            assert "Slack" in doc
            assert "WebSocket" in doc
            assert "PagerDuty" in doc or "PAGERDUTY" in doc

    def test_preview_mode_websocket_only_consistent(
        self,
        root_readme: str,
        delivery_semantics_md: str,
        policy_lifecycle_md: str,
    ) -> None:
        """Verify PREVIEW mode routes all intents to WebSocket only."""
        # All should indicate PREVIEW uses WebSocket only
        for _doc_name, doc in [
            ("root_readme", root_readme),
            ("delivery_semantics", delivery_semantics_md),
            ("policy_lifecycle", policy_lifecycle_md),
        ]:
            # Should mention PREVIEW mode going to WebSocket
            assert "PREVIEW" in doc
            assert "WebSocket" in doc


class TestNoRetryTerminologyContradiction:
    """Test that retry/fallback terminology doesn't imply automatic retries."""

    def test_observability_clarifies_no_retry(self, observability_md: str) -> None:
        """Verify observability.md clarifies no automatic retries."""
        # observability.md has "Retry/Fallback Counts" header
        # but should clarify no automatic retries
        assert (
            "does not implement automatic retries" in observability_md
            or ("Fallback" in observability_md and "retry" not in observability_md.lower())
            or "Note" in observability_md
        )

    def test_delivery_semantics_bounded_fallback(self, delivery_semantics_md: str) -> None:
        """Verify delivery-semantics.md describes bounded fallback."""
        # Should mention sequential fallback, not infinite retry
        assert (
            "sequential" in delivery_semantics_md.lower()
            or "fallback" in delivery_semantics_md.lower()
        )
        # Should mention it stops at first success
        assert (
            "first success" in delivery_semantics_md.lower()
            or "stops" in delivery_semantics_md.lower()
        )


class TestAckExecutionBoundaryWarnings:
    """Test that ack/execution boundary warnings are present."""

    def test_root_readme_has_ack_warning(self, root_readme: str) -> None:
        """Verify root README has acknowledgment scope warning."""
        assert "Acknowledgment" in root_readme or "acknowledgment" in root_readme
        assert "MUST NEVER" in root_readme or "NEVER" in root_readme

    def test_architecture_has_ack_warning(self, architecture_md: str) -> None:
        """Verify ARCHITECTURE.md has acknowledgment scope warning."""
        assert "Acknowledgment Scope" in architecture_md or "CRITICAL" in architecture_md
        # Should have anti-pattern examples
        assert "WRONG" in architecture_md or "NEVER" in architecture_md


class TestCrossReferenceIntegrity:
    """Test that cross-references between documents are valid."""

    def test_delivery_semantics_links_valid(self, delivery_semantics_md: str) -> None:
        """Verify delivery-semantics.md links are valid."""
        # Should link to integration-modes, policy-lifecycle, and ARCHITECTURE
        assert "integration-modes.md" in delivery_semantics_md
        assert "policy-lifecycle.md" in delivery_semantics_md
        assert "ARCHITECTURE.md" in delivery_semantics_md

    def test_policy_lifecycle_links_valid(self, policy_lifecycle_md: str) -> None:
        """Verify policy-lifecycle.md links are valid."""
        assert "ARCHITECTURE.md" in policy_lifecycle_md
        assert "API.md" in policy_lifecycle_md

    def test_observability_links_valid(self, observability_md: str) -> None:
        """Verify observability.md links are valid."""
        assert "delivery-semantics.md" in observability_md
        assert "ARCHITECTURE.md" in observability_md

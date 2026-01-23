"""Tests validating the final documentation audit findings.

These tests verify:
1. No spec contradictions exist in documentation
2. No examples imply forbidden behavior (ack/execution boundary)
3. Guarantees are explicitly scoped (no infinite retry implications)
4. Policy ownership and fallback behavior are unambiguous
"""

from pathlib import Path

import pytest

# Documentation paths
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
README_PATH = Path(__file__).parent.parent.parent / "README.md"
ARCHITECTURE_PATH = DOCS_DIR / "ARCHITECTURE.md"
API_PATH = DOCS_DIR / "API.md"
DELIVERY_SEMANTICS_PATH = DOCS_DIR / "sections" / "delivery-semantics.md"
POLICY_LIFECYCLE_PATH = DOCS_DIR / "sections" / "policy-lifecycle.md"
INTEGRATION_MODES_PATH = DOCS_DIR / "sections" / "integration-modes.md"
OBSERVABILITY_PATH = DOCS_DIR / "sections" / "observability.md"
FINAL_AUDIT_PATH = DOCS_DIR / "reports" / "final-doc-audit.md"


@pytest.fixture
def readme_content() -> str:
    """Load README.md content."""
    return README_PATH.read_text()


@pytest.fixture
def architecture_content() -> str:
    """Load ARCHITECTURE.md content."""
    return ARCHITECTURE_PATH.read_text()


@pytest.fixture
def api_content() -> str:
    """Load API.md content."""
    return API_PATH.read_text()


@pytest.fixture
def delivery_semantics_content() -> str:
    """Load delivery-semantics.md content."""
    return DELIVERY_SEMANTICS_PATH.read_text()


@pytest.fixture
def policy_lifecycle_content() -> str:
    """Load policy-lifecycle.md content."""
    return POLICY_LIFECYCLE_PATH.read_text()


@pytest.fixture
def integration_modes_content() -> str:
    """Load integration-modes.md content."""
    return INTEGRATION_MODES_PATH.read_text()


@pytest.fixture
def observability_content() -> str:
    """Load observability.md content."""
    return OBSERVABILITY_PATH.read_text()


class TestFinalAuditReportExists:
    """Verify the final audit report was created."""

    def test_final_audit_report_exists(self) -> None:
        """Verify final-doc-audit.md exists."""
        assert FINAL_AUDIT_PATH.exists(), f"Final audit report not found at {FINAL_AUDIT_PATH}"

    def test_final_audit_report_not_empty(self) -> None:
        """Verify final audit report has content."""
        content = FINAL_AUDIT_PATH.read_text()
        assert len(content) > 1000, "Audit report appears incomplete"

    def test_final_audit_report_has_executive_summary(self) -> None:
        """Verify audit report has executive summary."""
        content = FINAL_AUDIT_PATH.read_text()
        assert "## Executive Summary" in content

    def test_final_audit_report_has_all_sections(self) -> None:
        """Verify audit report covers all required areas."""
        content = FINAL_AUDIT_PATH.read_text()
        assert "## 1. Specification Contradiction Audit" in content
        assert "## 2. Ack/Execution Boundary Compliance" in content
        assert "## 3. Guarantee Scoping Audit" in content
        assert "## 4. Policy Ownership & Fallback Clarity" in content


class TestNoSpecContradictions:
    """Verify previously identified spec contradictions have been resolved."""

    def test_governance_ack_behavior_clarified(self, readme_content: str) -> None:
        """Verify GOVERNANCE ack behavior is correctly documented."""
        # Should NOT say ack is required by default for GOVERNANCE
        # Should clarify timeout only applies if explicitly enabled
        assert "Not required" in readme_content  # GOVERNANCE default
        # Should have clarifying footnote about 30-min timeout
        assert (
            "explicitly enabled" in readme_content.lower() or "if enabled" in readme_content.lower()
        )

    def test_policy_registry_no_async_get(self, api_content: str) -> None:
        """Verify API.md documents get_sync() not async get()."""
        assert "get_sync" in api_content
        # Should not claim async get() method exists
        lines = api_content.split("\n")
        for line in lines:
            if "async def get(" in line:
                # This would be a contradiction - async get() doesn't exist
                pytest.fail("API.md incorrectly documents non-existent async get() method")

    def test_shadow_mode_routing_complete(self, delivery_semantics_content: str) -> None:
        """Verify SHADOW mode routing is complete for all intents."""
        # SHADOW mode should mention routing for SAFETY
        assert "SHADOW" in delivery_semantics_content
        assert "Slack, WebSocket" in delivery_semantics_content  # SAFETY/GOVERNANCE in SHADOW


class TestNoInfiniteRetryImplications:
    """Verify documentation doesn't imply infinite retry behavior."""

    def test_no_retry_in_delivery_semantics(self, delivery_semantics_content: str) -> None:
        """Verify delivery-semantics.md doesn't imply automatic retry."""
        # Should use "fallback" not "retry" for channel strategy
        lines = delivery_semantics_content.split("\n")
        for i, line in enumerate(lines):
            if "retry" in line.lower():
                # Check context - retry should only appear in clarifying notes
                context = "\n".join(lines[max(0, i - 2) : min(len(lines), i + 3)])
                # Should mention "does not implement" or similar
                assert (
                    "does not implement" in context.lower()
                    or "no automatic" in context.lower()
                    or "not retry" in context.lower()
                    or "Retry/Fallback" in context  # Header that clarifies below
                ), f"Found 'retry' without clarification at line {i + 1}"

    def test_bounded_fallback_chain(self, delivery_semantics_content: str) -> None:
        """Verify fallback chain is explicitly bounded."""
        # Should show specific fallback order with finite channels
        assert "Slack" in delivery_semantics_content
        assert "Email" in delivery_semantics_content
        assert "PagerDuty" in delivery_semantics_content
        assert "fallback" in delivery_semantics_content.lower()

    def test_guaranteed_failure_terminates(self, delivery_semantics_content: str) -> None:
        """Verify GUARANTEED mode terminates with error, not infinite loop."""
        # Should mention DeliveryError on all-channel failure
        assert "DeliveryError" in delivery_semantics_content
        assert "all" in delivery_semantics_content.lower()
        assert "fail" in delivery_semantics_content.lower()

    def test_observability_clarifies_no_retry(self, observability_content: str) -> None:
        """Verify observability.md clarifies no automatic retry."""
        # Should have note about no automatic retries
        lower_content = observability_content.lower()
        # Either no mention of retry, or explicit clarification
        if "retry" in lower_content:
            assert (
                "does not implement" in lower_content
                or "no automatic" in lower_content
                or "fallback" in lower_content  # Fallback, not retry
            )


class TestAckExecutionBoundaryCompliance:
    """Verify all examples comply with ack/execution boundary rules."""

    def test_architecture_has_critical_warning(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE has critical warning about ack scope."""
        assert "CRITICAL" in architecture_content
        assert "Acknowledgment Scope" in architecture_content

    def test_architecture_has_antipattern_examples(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE shows anti-pattern examples."""
        assert "❌ WRONG" in architecture_content or "# WRONG" in architecture_content
        assert "wait_for_ack" in architecture_content or "get_ack_status" in architecture_content

    def test_architecture_has_correct_pattern(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE shows correct pattern."""
        assert "✅ CORRECT" in architecture_content or "# CORRECT" in architecture_content
        # Should show fire-and-forget pattern
        lower_content = architecture_content.lower()
        assert (
            "execute immediately" in lower_content
            or "don't wait" in lower_content
            or "fire-and-forget" in lower_content
        )

    def test_readme_has_execution_prohibition(self, readme_content: str) -> None:
        """Verify README explicitly prohibits execution gating."""
        lower_content = readme_content.lower()
        assert "must never gate" in lower_content or "never gate" in lower_content
        assert "order execution" in lower_content or "order routing" in lower_content
        assert "risk unwind" in lower_content

    def test_no_blocking_patterns_in_basic_examples(self, readme_content: str) -> None:
        """Verify basic usage examples don't show blocking patterns."""
        # Extract code blocks and verify no blocking patterns
        in_code_block = False
        code_lines = []
        for line in readme_content.split("\n"):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                code_lines.append(line)

        code_content = "\n".join(code_lines)
        # These patterns should not appear except in anti-pattern warnings
        blocking_patterns = ["wait_for_ack", "block_until_ack", "while.*pending"]
        for pattern in blocking_patterns:
            if pattern in code_content.lower():
                # Check it's in an anti-pattern section
                assert (
                    "WRONG" in code_content
                    or "NEVER" in code_content
                    or "anti-pattern" in code_content.lower()
                ), f"Found blocking pattern '{pattern}' without anti-pattern warning"


class TestPolicyOwnershipClarity:
    """Verify policy resolution and fallback behavior is unambiguous."""

    def test_resolution_priority_documented(self, policy_lifecycle_content: str) -> None:
        """Verify policy resolution priority is documented."""
        assert (
            "Resolution Priority" in policy_lifecycle_content
            or "resolution priority" in policy_lifecycle_content.lower()
        )
        # Should list: Explicit override > Policy > SDK default
        assert "Explicit" in policy_lifecycle_content
        assert "Policy" in policy_lifecycle_content
        assert (
            "SDK default" in policy_lifecycle_content
            or "default" in policy_lifecycle_content.lower()
        )

    def test_fallback_when_registry_unavailable(self, policy_lifecycle_content: str) -> None:
        """Verify fallback behavior when registry unavailable is documented."""
        lower_content = policy_lifecycle_content.lower()
        assert "unavailable" in lower_content or "none" in lower_content
        # Should mention safe fallback to defaults
        assert "fallback" in lower_content or "default" in lower_content

    def test_sdk_defaults_documented(self, policy_lifecycle_content: str) -> None:
        """Verify SDK default values are documented."""
        # Should have table or list of defaults by intent
        assert "SAFETY" in policy_lifecycle_content
        assert "GOVERNANCE" in policy_lifecycle_content
        assert "GUARANTEED" in policy_lifecycle_content
        assert "BEST_EFFORT" in policy_lifecycle_content

    def test_no_notification_blocked_by_missing_policy(self, policy_lifecycle_content: str) -> None:
        """Verify docs state notifications are never blocked by missing policies."""
        lower_content = policy_lifecycle_content.lower()
        assert (
            "never blocked" in lower_content
            or "not blocked" in lower_content
            or "always deliverable" in lower_content
        )


class TestATPIndependence:
    """Verify documentation clearly states UNS is ATP-agnostic."""

    def test_integration_modes_states_independence(self, integration_modes_content: str) -> None:
        """Verify integration-modes.md states UNS doesn't require ATP."""
        lower_content = integration_modes_content.lower()
        assert "atp-agnostic" in lower_content or "atp agnostic" in lower_content
        assert "does not require atp" in lower_content or "require atp to function" in lower_content

    def test_architecture_notes_atp_independence(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE notes ATP independence."""
        lower_content = architecture_content.lower()
        assert "atp-agnostic" in lower_content or "atp agnostic" in lower_content


class TestCrossDocumentConsistency:
    """Verify consistency across all documentation files."""

    def test_delivery_mode_terminology_consistent(
        self,
        readme_content: str,
        architecture_content: str,
        delivery_semantics_content: str,
    ) -> None:
        """Verify GUARANTEED and BEST_EFFORT terminology is consistent."""
        docs = [readme_content, architecture_content, delivery_semantics_content]
        for doc in docs:
            assert "GUARANTEED" in doc
            assert "BEST_EFFORT" in doc
            # Should not use inconsistent terms
            assert "RELIABLE" not in doc  # Wrong term
            assert "AT_LEAST_ONCE" not in doc  # Wrong term

    def test_intent_terminology_consistent(
        self,
        readme_content: str,
        architecture_content: str,
        delivery_semantics_content: str,
    ) -> None:
        """Verify intent terminology is consistent across docs."""
        docs = [readme_content, architecture_content, delivery_semantics_content]
        for doc in docs:
            assert "SAFETY" in doc
            assert "GOVERNANCE" in doc
            assert "OPERATIONAL" in doc
            assert "INFORMATIONAL" in doc

    def test_autonomy_mode_terminology_consistent(
        self,
        readme_content: str,
        architecture_content: str,
        delivery_semantics_content: str,
    ) -> None:
        """Verify autonomy mode terminology is consistent."""
        docs = [readme_content, architecture_content, delivery_semantics_content]
        for doc in docs:
            assert "PREVIEW" in doc
            assert "SHADOW" in doc
            assert "LIVE" in doc


class TestDocumentationLinks:
    """Verify all cross-document links are valid."""

    def test_architecture_links_valid(self, architecture_content: str) -> None:
        """Verify ARCHITECTURE.md links to existing files."""
        links = [
            "sections/delivery-semantics.md",
            "sections/integration-modes.md",
            "sections/observability.md",
            "sections/policy-lifecycle.md",
            "API.md",
        ]
        for link in links:
            assert link in architecture_content, f"Missing link to {link}"
            target_path = DOCS_DIR / link
            assert target_path.exists(), f"Broken link: {link} does not exist"

    def test_api_links_valid(self, api_content: str) -> None:
        """Verify API.md links to existing files."""
        links = [
            "ARCHITECTURE.md",
            "sections/delivery-semantics.md",
            "sections/integration-modes.md",
            "sections/policy-lifecycle.md",
        ]
        for link in links:
            assert link in api_content, f"Missing link to {link}"

    def test_delivery_semantics_links_valid(self, delivery_semantics_content: str) -> None:
        """Verify delivery-semantics.md links to existing files."""
        # Should link to related docs
        assert "integration-modes.md" in delivery_semantics_content
        assert "policy-lifecycle.md" in delivery_semantics_content

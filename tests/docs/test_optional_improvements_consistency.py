"""Tests for optional improvement consistency.

This test suite validates that optional improvements documented in the UNS
documentation do not contradict core specifications from prd.md.

Optional improvements are features documented as:
- "Future" or "planned" features
- "Not implemented" status
- "Recommendations (Non-Blocking)" sections
- Policy states documented as concepts but with current limitations

Core specifications are:
- Delivery semantics (GUARANTEED vs BEST_EFFORT)
- Acknowledgment scope restrictions
- Intent to delivery mode mapping
- Channel routing by autonomy mode
- No automatic retry behavior
"""

from pathlib import Path

import pytest

# Documentation paths
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
PRD_PATH = Path(__file__).parent.parent.parent / "prd.md"
README_PATH = Path(__file__).parent.parent.parent / "README.md"
ARCHITECTURE_PATH = DOCS_DIR / "ARCHITECTURE.md"
API_PATH = DOCS_DIR / "API.md"
DELIVERY_SEMANTICS_PATH = DOCS_DIR / "sections" / "delivery-semantics.md"
POLICY_LIFECYCLE_PATH = DOCS_DIR / "sections" / "policy-lifecycle.md"
OBSERVABILITY_PATH = DOCS_DIR / "sections" / "observability.md"
INTEGRATION_MODES_PATH = DOCS_DIR / "sections" / "integration-modes.md"
FINAL_AUDIT_PATH = DOCS_DIR / "reports" / "final-doc-audit.md"


@pytest.fixture
def prd_content() -> str:
    """Load prd.md content."""
    return PRD_PATH.read_text()


@pytest.fixture
def policy_lifecycle_content() -> str:
    """Load policy-lifecycle.md content."""
    return POLICY_LIFECYCLE_PATH.read_text()


@pytest.fixture
def observability_content() -> str:
    """Load observability.md content."""
    return OBSERVABILITY_PATH.read_text()


@pytest.fixture
def delivery_semantics_content() -> str:
    """Load delivery-semantics.md content."""
    return DELIVERY_SEMANTICS_PATH.read_text()


@pytest.fixture
def final_audit_content() -> str:
    """Load final-doc-audit.md content."""
    return FINAL_AUDIT_PATH.read_text()


class TestOptionalImprovementIdentification:
    """Test that optional improvements are clearly marked as such."""

    def test_policy_versioning_marked_as_future(self, policy_lifecycle_content: str) -> None:
        """Policy versioning is marked as future/planned, not current."""
        # Should have section about versioning
        assert "Policy Versioning" in policy_lifecycle_content
        # Should indicate it's not fully implemented yet
        lower_content = policy_lifecycle_content.lower()
        assert (
            "future" in lower_content
            or "planned" in lower_content
            or "not implemented" in lower_content
            or "current implementation" in lower_content
        )

    def test_policy_states_limitation_documented(self, policy_lifecycle_content: str) -> None:
        """Policy states (DRAFT/PREVIEW/ACTIVE/RETIRED) limitation is documented."""
        # Should document the states
        assert "DRAFT" in policy_lifecycle_content
        assert "ACTIVE" in policy_lifecycle_content
        assert "RETIRED" in policy_lifecycle_content
        # Should note current limitation
        lower_content = policy_lifecycle_content.lower()
        assert (
            "current implementation" in lower_content
            or "currently" in lower_content
            or "all registered policies" in lower_content
        )

    def test_external_metrics_marked_not_implemented(self, observability_content: str) -> None:
        """External metrics export is marked as not implemented."""
        lower_content = observability_content.lower()
        # Should mention Prometheus or StatsD
        has_external_metrics = "prometheus" in lower_content or "statsd" in lower_content
        if has_external_metrics:
            # Should indicate not implemented
            assert (
                "not implemented" in lower_content
                or "future" in lower_content
                or "planned" in lower_content
            )


class TestNoRetryContradictions:
    """Verify no documentation implies automatic retry behavior."""

    def test_observability_clarifies_no_retry(self, observability_content: str) -> None:
        """Observability doc clarifies there is no automatic retry."""
        lower_content = observability_content.lower()
        if "retry" in lower_content:
            # Must clarify no automatic retry
            assert (
                "does not implement automatic retries" in lower_content
                or "no automatic retries" in lower_content
                or "fallback" in lower_content  # Fallback, not retry
            ), "Mention of 'retry' without clarification that UNS uses fallback, not retry"

    def test_delivery_semantics_uses_fallback_not_retry(
        self, delivery_semantics_content: str
    ) -> None:
        """Delivery semantics uses 'fallback' terminology, not 'retry'."""
        # Should use fallback terminology
        assert "fallback" in delivery_semantics_content.lower()
        # Should document sequential fallback for GUARANTEED
        assert "sequential" in delivery_semantics_content.lower()

    def test_prd_specifies_fallback_not_retry(self, prd_content: str) -> None:
        """PRD specifies fallback behavior, not retry behavior."""
        lower_content = prd_content.lower()
        # PRD should specify fallback for GUARANTEED
        assert "fallback" in lower_content or "escalat" in lower_content
        # Should not imply infinite retry
        if "retry" in lower_content:
            # Must be in context of not implementing retry
            lines = prd_content.split("\n")
            for i, line in enumerate(lines):
                if "retry" in line.lower():
                    # Context should clarify it's fallback, not retry
                    context = "\n".join(lines[max(0, i - 2) : min(len(lines), i + 3)])
                    assert not ("infinite" in context.lower() and "retry" in context.lower()), (
                        "PRD implies infinite retry"
                    )


class TestPolicyStateConsistency:
    """Verify policy state documentation doesn't contradict current behavior."""

    def test_all_policies_treated_as_active_documented(self, policy_lifecycle_content: str) -> None:
        """Current limitation that all policies are ACTIVE is documented."""
        # Look for documentation of current behavior
        lower_content = policy_lifecycle_content.lower()
        # Should mention current implementation treats all as active
        has_limitation_note = (
            "current implementation treats all registered policies as active" in lower_content
            or "treats all registered policies as active" in lower_content
            or "all registered policies as active" in lower_content
            # OR the states are described as concepts
            or "conceptual" in lower_content
            or "future enhancement" in lower_content
        )
        # The document should at minimum mention ACTIVE state
        assert "active" in lower_content
        # If states other than ACTIVE are documented, should note limitation
        if "draft" in lower_content and "retired" in lower_content:
            # Should have some note about current implementation
            assert has_limitation_note or "current" in lower_content

    def test_policy_lookup_always_returns_active(self, policy_lifecycle_content: str) -> None:
        """Policy lookup returns policies regardless of state (current behavior)."""
        # Current behavior: get_sync returns policy if registered
        lower_content = policy_lifecycle_content.lower()
        # Should document get_sync behavior
        assert "get_sync" in lower_content
        # Should not imply only ACTIVE policies are returned if that's not implemented
        # (This is consistent with current implementation)


class TestAckBoundaryNoContradictions:
    """Verify optional improvements don't contradict ack boundary rules."""

    def test_no_ack_gating_in_improvements(
        self, policy_lifecycle_content: str, observability_content: str
    ) -> None:
        """No optional improvement implies ack can gate execution."""
        for content, name in [
            (policy_lifecycle_content, "policy-lifecycle.md"),
            (observability_content, "observability.md"),
        ]:
            lower_content = content.lower()
            # Should never suggest ack gates execution
            assert "block order" not in lower_content, f"{name} suggests blocking orders"
            assert "wait for ack" not in lower_content or "never" in lower_content, (
                f"{name} suggests waiting for ack without proper warning"
            )


class TestDeliveryGuaranteeConsistency:
    """Verify optional improvements don't contradict delivery guarantees."""

    def test_guaranteed_always_raises_on_failure(
        self, delivery_semantics_content: str, prd_content: str
    ) -> None:
        """GUARANTEED mode always raises on failure - no optional exception."""
        # Delivery semantics should document GUARANTEED raises
        assert "DeliveryError" in delivery_semantics_content
        assert "GUARANTEED" in delivery_semantics_content
        lower_ds = delivery_semantics_content.lower()
        assert "raise" in lower_ds or "exception" in lower_ds

        # PRD should specify GUARANTEED raises
        lower_prd = prd_content.lower()
        assert "guaranteed" in lower_prd
        assert "raise" in lower_prd or "error" in lower_prd

    def test_best_effort_never_raises(
        self, delivery_semantics_content: str, prd_content: str
    ) -> None:
        """BEST_EFFORT mode never raises - no optional exception mode."""
        lower_ds = delivery_semantics_content.lower()
        lower_prd = prd_content.lower()

        # Both should document BEST_EFFORT doesn't raise
        assert "best_effort" in lower_ds or "best effort" in lower_ds
        assert "best_effort" in lower_prd or "best effort" in lower_prd

        # Should indicate BEST_EFFORT logs but doesn't raise
        assert "log" in lower_ds or "silent" in lower_ds or "does not raise" in lower_ds


class TestFutureRecommendationsNonBlocking:
    """Verify future recommendations are marked as non-blocking."""

    def test_final_audit_recommendations_non_blocking(self, final_audit_content: str) -> None:
        """Final audit recommendations are marked as non-blocking."""
        # Should have recommendations section
        assert "Recommendations" in final_audit_content
        # Should be marked as non-blocking
        lower_content = final_audit_content.lower()
        assert "non-blocking" in lower_content or "optional" in lower_content

    def test_no_critical_issues_in_final_audit(self, final_audit_content: str) -> None:
        """Final audit has no critical issues."""
        # Look for the issues table
        lower_content = final_audit_content.lower()
        # Should indicate PASS status
        assert "pass" in lower_content
        # Should not have critical issues marked as action required
        assert "no critical issues" in lower_content or "- | - | - | -" in final_audit_content


class TestObservabilityNoContradictions:
    """Verify observability improvements don't contradict core behavior."""

    def test_health_states_documented_consistently(self, observability_content: str) -> None:
        """Health states (HEALTHY, DEGRADED, UNHEALTHY) are consistent."""
        assert "HEALTHY" in observability_content
        assert "DEGRADED" in observability_content
        assert "UNHEALTHY" in observability_content

    def test_degraded_behavior_documented(self, observability_content: str) -> None:
        """DEGRADED state behavior is documented and consistent with delivery semantics."""
        lower_content = observability_content.lower()
        # DEGRADED should attempt delivery
        assert "degraded" in lower_content
        # Should describe what happens in degraded state
        assert "attempt" in lower_content or "delivery" in lower_content

    def test_dlq_only_for_guaranteed(self, observability_content: str) -> None:
        """DLQ/escalation is only for GUARANTEED mode."""
        lower_content = observability_content.lower()
        if "dlq" in lower_content or "escalation" in lower_content:
            # Should mention GUARANTEED
            assert "guaranteed" in lower_content


class TestCrossDocumentConsistency:
    """Verify optional improvements are consistent across all documents."""

    def test_delivery_mode_terminology_consistent(
        self,
        prd_content: str,
        delivery_semantics_content: str,
        policy_lifecycle_content: str,
    ) -> None:
        """GUARANTEED and BEST_EFFORT terminology consistent across docs."""
        for content in [prd_content, delivery_semantics_content, policy_lifecycle_content]:
            assert "GUARANTEED" in content
            assert "BEST_EFFORT" in content

    def test_channel_fallback_order_consistent(
        self,
        prd_content: str,
        delivery_semantics_content: str,
    ) -> None:
        """Fallback order (Slack → Email → PagerDuty) is consistent."""
        # Both should mention fallback channels
        for content in [prd_content, delivery_semantics_content]:
            assert "Slack" in content
            assert "Email" in content
            assert "PagerDuty" in content

    def test_intent_mapping_consistent(
        self,
        prd_content: str,
        delivery_semantics_content: str,
    ) -> None:
        """Intent to delivery mode mapping is consistent."""
        # Both should have same mapping
        for content in [prd_content, delivery_semantics_content]:
            assert "SAFETY" in content
            assert "GOVERNANCE" in content
            assert "OPERATIONAL" in content
            assert "INFORMATIONAL" in content


class TestVersioningImprovement:
    """Verify policy versioning improvement doesn't contradict immutability."""

    def test_policies_immutable(self, policy_lifecycle_content: str) -> None:
        """Policies are documented as immutable (frozen)."""
        lower_content = policy_lifecycle_content.lower()
        # Should mention immutability or frozen
        has_immutability = (
            "immutable" in lower_content
            or "frozen" in lower_content
            or "unregister" in lower_content  # Update via unregister/register
        )
        assert has_immutability

    def test_versioning_via_replace(self, policy_lifecycle_content: str) -> None:
        """Versioning is done via unregister + register, not mutation."""
        lower_content = policy_lifecycle_content.lower()
        # Should mention unregister as update mechanism
        assert "unregister" in lower_content
        assert "register" in lower_content


class TestExternalIntegrationImprovements:
    """Verify external integration improvements don't create dependencies."""

    def test_atp_independence_maintained(
        self, policy_lifecycle_content: str, observability_content: str
    ) -> None:
        """Optional improvements don't introduce ATP dependency."""
        for content in [policy_lifecycle_content, observability_content]:
            lower_content = content.lower()
            # Should not require ATP
            if "atp" in lower_content:
                # Should be in context of independence
                assert (
                    "agnostic" in lower_content
                    or "independent" in lower_content
                    or "does not require" in lower_content
                    or "optional" in lower_content
                )

    def test_external_metrics_optional(self, observability_content: str) -> None:
        """External metrics are optional, not required."""
        lower_content = observability_content.lower()
        # If Prometheus/StatsD mentioned, should be optional
        if "prometheus" in lower_content or "statsd" in lower_content:
            # Should not be marked as required
            assert "required" not in lower_content or "not required" in lower_content

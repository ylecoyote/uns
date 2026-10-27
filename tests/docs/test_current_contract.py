"""Current documentation contracts replace historical prose-layout snapshots."""

import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/PRODUCT.md",
    "docs/API.md",
    "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md",
    "docs/LOCAL_DEPLOYMENT.md",
    "docs/DEPLOYMENT_SMOKE.md",
    "docs/CONSOLIDATED_BASELINE.md",
    "docs/REMEDIATION_ITERATION2.md",
    "docs/SECURITY-MODEL.md",
    "docs/MIGRATION.md",
    "docs/TESTING.md",
    "docs/sections/delivery-semantics.md",
    "docs/sections/policy-lifecycle.md",
    "docs/sections/integration-modes.md",
    "docs/sections/observability.md",
    "docs/support/STATE-MACHINE-AND-SCHEMA.md",
    "docs/tsg/README.md",
    "docs/tsg/TSG-01-DLQ-AND-REPLAY.md",
    "docs/tsg/TSG-02-LEASES-AND-PROVIDER-EFFECTS.md",
    "docs/tsg/TSG-03-ACK-TIMEOUTS-AND-CALLBACKS.md",
    "docs/tsg/TSG-04-POLICY-LIFECYCLE-AND-OVERRIDES.md",
    "docs/tsg/TSG-05-MCP-AND-AGENT-RECOVERY.md",
    "docs/tsg/TSG-06-MAINTENANCE-AND-ARCHIVAL.md",
    "docs/user-guides/OPERATOR-CONSOLE-GUIDE.md",
    "docs/user-guides/PRODUCER-INTEGRATION-GUIDE.md",
    "docs/user-guides/AGENT-MCP-GUIDE.md",
]


def test_canonical_document_links_resolve():
    for name in DOCS:
        path = ROOT / name
        content = path.read_text()
        assert content.startswith("# ")
        for href in re.findall(r"\]\(([^)]+)\)", content):
            if "://" not in href and not href.startswith("#"):
                assert (path.parent / href.split("#")[0]).exists(), (name, href)


def test_supported_and_experimental_boundaries_are_explicit():
    content = (ROOT / "docs/PRODUCT.md").read_text()
    assert "experimental" in content
    assert "not approve the action" in content
    assert "notification obligation" in content


def test_documented_import_names_remain_usable():
    for name in ("uns", "uns", "notification", "uns_mcp", "db", "ui_client"):
        importlib.import_module(name)
    from notification.sdk import NotificationSDK
    from uns import Client, Runtime, SignalClient

    assert SignalClient is NotificationSDK
    assert Client and Runtime

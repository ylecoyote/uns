"""Current documentation contracts replace historical prose-layout snapshots."""

import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    "README.md",
    "docs/README.md",
    "docs/PRODUCT.md",
    "docs/API.md",
    "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md",
    "docs/SECURITY-MODEL.md",
    "docs/MIGRATION.md",
    "docs/TESTING.md",
    "docs/sections/delivery-semantics.md",
    "docs/sections/policy-lifecycle.md",
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
    for name in ("uns", "agsignal", "notification", "agsignal_mcp", "db", "ui_client"):
        importlib.import_module(name)
    from agsignal import SignalClient
    from notification.sdk import NotificationSDK
    from uns import Client, Runtime

    assert SignalClient is NotificationSDK
    assert Client and Runtime

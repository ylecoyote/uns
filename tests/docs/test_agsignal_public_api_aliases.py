"""Tests for AGSignal public API alias documentation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
API = ROOT / "docs" / "API.md"


def test_readme_documents_agsignal_public_aliases() -> None:
    content = README.read_text()

    assert "from agsignal.sdk import SignalClient" in content
    assert "from agsignal.models import GovernanceSignal, SignalIntent" in content
    assert "`notification.*` imports remain supported" in content


def test_api_documents_agsignal_public_aliases() -> None:
    content = API.read_text()

    assert "SignalClient" in content
    assert "GovernanceSignal" in content
    assert "SignalIntent" in content
    assert "agsignal.integrations" in content

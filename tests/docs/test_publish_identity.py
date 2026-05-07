"""Publish-facing identity and release hygiene tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_uses_agsignal_publish_identity() -> None:
    content = (ROOT / "pyproject.toml").read_text()

    assert 'name = "agsignal"' in content
    assert "AGSignal - Control-plane governance signaling infrastructure" in content
    assert "Unified Notification Service" not in content
    assert '{name = "AGSignal Maintainers"}' in content
    assert '"agsignal[adapters,dev]"' in content


def test_agsignal_integrations_exposes_generic_boundary_only() -> None:
    import agsignal.integrations as integrations
    from notification.integrations.mip_adapter import MIPSignalAdapter

    assert hasattr(integrations, "AppSignalAdapter")
    assert not hasattr(integrations, "MIPSignalAdapter")
    assert MIPSignalAdapter.__name__ == "MIPSignalAdapter"


def test_readme_labels_current_policy_directory_as_sample_config() -> None:
    content = (ROOT / "README.md").read_text()

    assert "examples/policies/mip-uns" in content
    assert "config/notification_policies" in content
    assert "sample" in content.lower()
    assert "not AGSignal Core defaults" in content


def test_no_bytecode_artifacts_are_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "*__pycache__*", "*.pyc"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert result.stdout == ""

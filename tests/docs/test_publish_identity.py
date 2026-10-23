"""Publish-facing identity and release hygiene tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_uses_agsignal_publish_identity() -> None:
    content = (ROOT / "pyproject.toml").read_text()

    assert 'name = "uns"' in content
    assert "UNS - Unified Notification Service" in content
    assert "Unified Notification Service" in content
    assert 'license = {text = "Apache-2.0"}' in content
    assert '{name = "AGSignal Maintainers"}' in content
    # A self-referencing meta-extra exists so operators can opt into the
    # full server stack with one install line.
    assert '"uns[server,redis,sql,mcp,adapters]"' in content
    assert '"uns[full,dev]"' in content
    assert 'Repository = "https://github.com/ylecoyote/uns"' in content
    assert 'Documentation = "https://ylecoyote.github.io/uns/"' in content


def test_license_file_uses_apache_2_0() -> None:
    license_text = (ROOT / "LICENSE").read_text()
    readme = (ROOT / "README.md").read_text()
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    security = (ROOT / "SECURITY.md").read_text()

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "License-Apache--2.0" in readme
    assert "Apache License 2.0 - see [LICENSE](LICENSE)" in readme
    assert "Apache License 2.0 - see [LICENSE](LICENSE)" in contributing
    assert "MIT License" not in contributing
    assert "Before making this repository public" not in security


def test_mkdocs_nav_files_resolve() -> None:
    import yaml

    mkdocs_path = ROOT / "mkdocs.yml"
    assert mkdocs_path.exists()
    # Read nav section paths using safe_load on lines excluding !!python/name tags
    raw = "\n".join(
        line for line in mkdocs_path.read_text().splitlines() if "!!python/name:" not in line
    )
    config = yaml.safe_load(raw)
    docs_dir = ROOT / config.get("docs_dir", "docs")

    def _collect_paths(node: object) -> list[str]:
        paths: list[str] = []
        if isinstance(node, str) and node.endswith(".md"):
            paths.append(node)
        elif isinstance(node, list):
            for item in node:
                paths.extend(_collect_paths(item))
        elif isinstance(node, dict):
            for value in node.values():
                paths.extend(_collect_paths(value))
        return paths

    nav_paths = _collect_paths(config["nav"])
    assert len(nav_paths) >= 20
    for rel_path in nav_paths:
        assert (docs_dir / rel_path).exists(), f"Missing mkdocs nav target: {rel_path}"


def test_agsignal_integrations_exposes_generic_boundary_only() -> None:
    from examples.integrations.mip.adapter import MIPSignalAdapter

    import agsignal.integrations as integrations

    assert hasattr(integrations, "AppSignalAdapter")
    assert not hasattr(integrations, "MIPSignalAdapter")
    assert MIPSignalAdapter.__name__ == "MIPSignalAdapter"


def test_readme_labels_current_policy_directory_as_sample_config() -> None:
    content = (ROOT / "README.md").read_text()

    assert "examples/policies/mip-uns" in content
    assert "config/notification_policies" in content
    assert "sample" in content.lower()
    assert "not mandatory runtime defaults" in content
    assert "Planned `notification_policy`" not in content
    assert "Planned `POST /api/v1/policies/reload`" not in content


def test_docs_index_routes_publish_readers_by_task() -> None:
    content = (ROOT / "docs" / "README.md").read_text()

    for task in (
        "Evaluate UNS",
        "Quickstart: send a signal",
        "Configure policies",
        "Integrate an app",
        "Operate and audit",
        "Extend UNS",
        "Verify implementation",
    ):
        assert task in content


def test_publish_ui_surface_uses_agsignal_console_name() -> None:
    paths = (
        ROOT / "apps" / "ui" / "README.md",
        ROOT / "apps" / "ui" / "index.html",
        ROOT / "apps" / "ui" / "src" / "App.tsx",
        ROOT / "docs" / "ui" / "ui-data-contracts.md",
        ROOT / "docs" / "ui" / "contracts" / "ui-contracts.json",
    )

    for path in paths:
        content = path.read_text()
        assert "UNS Console" in content
        assert "UNS Dashboard" not in content
        assert "UNS UI" not in content


def test_ui_package_manifest_uses_console_identity() -> None:
    package_json = (ROOT / "apps" / "ui" / "package.json").read_text()
    package_lock = (ROOT / "apps" / "ui" / "package-lock.json").read_text()

    assert '"name": "uns-console"' in package_json
    assert '"name": "uns-console"' in package_lock
    assert '"name": "uns-ui"' not in package_json
    assert '"name": "uns-ui"' not in package_lock


def test_console_contract_docs_use_ui_endpoint_prefix() -> None:
    content = (ROOT / "docs" / "ui" / "ui-data-contracts.md").read_text()

    assert "GET /ui/deliveries" in content
    assert "GET /ui/policies/effective" in content
    assert "GET /ui/invariants" in content
    assert "GET /ui/audit" in content
    assert "GET /api/v1/notifications/{notification_id}/delivery-timeline" not in content


def test_no_bytecode_artifacts_are_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "*__pycache__*", "*.pyc"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert result.stdout == ""

"""Security boundaries that workflow syntax validation cannot establish."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    # BaseLoader preserves GitHub's YAML 1.2 `on` key as a string.
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def test_external_actions_are_pinned_to_full_commit_hashes():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for ref in re.findall(r"uses:\s+([^\s]+)", path.read_text()):
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), (path.name, ref)


def test_release_writes_require_the_protected_environment():
    config = workflow("release.yml")
    assert config["on"]["push"]["tags"] == ["v*"]
    assert "release" not in config["on"]
    for name, job in config["jobs"].items():
        if any(value == "write" for value in job.get("permissions", {}).values()):
            assert job.get("environment") == "release", name
    assert config["jobs"]["build-python-dist"]["permissions"] == {
        "contents": "read",
        "checks": "read",
    }


def test_release_publishing_waits_for_assets_and_package_jobs():
    job = workflow("release.yml")["jobs"]["publish-release"]
    assert set(job["needs"]) == {"stage-release", "publish-ghcr", "publish-pypi"}
    assert "needs.stage-release.result == 'success'" in job["if"]
    assert "needs.publish-ghcr.result == 'success'" in job["if"]
    assert "needs.publish-pypi.result == 'success'" in job["if"]
    assert "needs.publish-pypi.result == 'skipped'" in job["if"]


def test_docs_pull_requests_have_no_publication_permissions():
    config = workflow("docs.yml")
    assert config["permissions"] == {"contents": "read"}
    assert config["jobs"]["deploy"]["permissions"]["pages"] == "write"
    assert config["jobs"]["deploy"]["if"] == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    )


def test_codeql_covers_both_stacks_and_workflow_code():
    config = workflow("codeql.yml")
    assert set(config["jobs"]["analyze"]["strategy"]["matrix"]["language"]) == {
        "actions",
        "javascript-typescript",
        "python",
    }
    assert "pull_request" in config["on"]
    assert "schedule" in config["on"]

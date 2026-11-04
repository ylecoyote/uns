"""Failure cases for the tag-only, immutable release pipeline."""

import hashlib
import subprocess
from pathlib import Path

import pytest
from scripts.ci import release


def checks():
    return [
        {
            "id": i,
            "name": name,
            "app": {"slug": "github-actions"},
            "status": "completed",
            "conclusion": "success",
        }
        for i, name in enumerate(release.REQUIRED_CHECKS, start=1)
    ]


@pytest.mark.parametrize(
    "ref_type,tag,version",
    [
        ("branch", "main", "0.6.0"),
        ("tag", "v0.6.1", "0.6.0"),
        ("tag", "0.6.0", "0.6.0"),
        ("tag", "v0.6.0/other", "0.6.0"),
    ],
)
def test_rejects_non_release_refs_and_version_mismatches(ref_type, tag, version):
    with pytest.raises(ValueError):
        release.validate_identity(ref_type, tag, version)


def test_accepts_matching_stable_version():
    release.validate_identity("tag", "v0.6.0", "0.6.0")


@pytest.mark.parametrize("mutation", ["missing", "forged", "pending", "failed", "stale"])
def test_requires_latest_successful_checks_from_github_actions(mutation):
    runs = checks()
    if mutation == "missing":
        runs.pop()
    elif mutation == "forged":
        runs[0]["app"] = {"slug": "another-app"}
    elif mutation == "pending":
        runs[0]["status"] = "in_progress"
    elif mutation == "failed":
        runs[0]["conclusion"] = "failure"
    else:
        runs.append({**runs[0], "id": 99, "conclusion": "failure"})
    with pytest.raises(ValueError):
        release.validate_checks(runs)


def test_accepts_current_successful_checks():
    release.validate_checks(list(reversed(checks())))


def test_commit_outside_main_is_rejected_before_check_lookup(monkeypatch):
    def run(command, **kwargs):
        if command[1] == "merge-base":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(release.subprocess, "run", run)
    monkeypatch.setattr(release, "api", lambda *_a, **_k: pytest.fail("must reject first"))
    with pytest.raises(subprocess.CalledProcessError):
        release.verify_commit("owner/uns", "a" * 40)


def distributions(tmp_path):
    files = [tmp_path / "uns-0.6.0-py3-none-any.whl", tmp_path / "uns-0.6.0.tar.gz"]
    for path in files:
        path.write_bytes(path.name.encode())
    return files


@pytest.mark.parametrize("mutation", ["missing", "extra", "empty", "symlink"])
def test_distributions_must_be_exact_nonempty_wheel_and_sdist(tmp_path, mutation):
    files = distributions(tmp_path)
    if mutation == "missing":
        files[0].unlink()
    elif mutation == "extra":
        (tmp_path / "uns-0.5.0.tar.gz").write_bytes(b"stale")
    elif mutation == "empty":
        files[0].write_bytes(b"")
    else:
        content = files[0].read_bytes()
        files[0].unlink()
        target = tmp_path.parent / "outside-wheel"
        target.write_bytes(content)
        files[0].symlink_to(target)
    with pytest.raises(ValueError):
        release.release_files(tmp_path, "v0.6.0")


def test_published_release_is_never_overwritten(tmp_path, monkeypatch):
    distributions(tmp_path)
    monkeypatch.setattr(release, "api", lambda *_a, **_k: {"id": 1, "draft": False})
    monkeypatch.setattr(release, "upload", lambda *_a, **_k: pytest.fail("must not upload"))
    with pytest.raises(ValueError, match="already published"):
        release.stage_release("owner/uns", "v0.6.0", "a" * 40, tmp_path)


def test_new_release_is_draft_before_assets_are_uploaded(tmp_path, monkeypatch):
    files = distributions(tmp_path)
    calls = []

    def api(path, method="GET", body=None, missing_ok=False):
        calls.append((method, body))
        return None if method == "GET" else {"id": 1, "draft": True}

    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(
        release, "upload", lambda _repo, _tag, paths: calls.append(("upload", paths))
    )
    release.stage_release("owner/uns", "v0.6.0", "a" * 40, tmp_path)
    assert calls[1][0] == "POST"
    assert calls[1][1]["draft"] is True
    assert set(calls[2][1]) == set(files)


def asset_rows(files: list[Path]):
    return [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "digest": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in files
    ]


@pytest.mark.parametrize("mutation", ["missing", "extra", "tampered", "no_digest", "size"])
def test_release_cannot_publish_wrong_or_incomplete_assets(tmp_path, monkeypatch, mutation):
    files = distributions(tmp_path)
    assets = asset_rows(files)
    if mutation == "missing":
        assets.pop()
    elif mutation == "extra":
        assets.append({"name": "unexpected.txt"})
    elif mutation == "tampered":
        assets[0]["digest"] = "sha256:" + "0" * 64
    elif mutation == "no_digest":
        assets[0].pop("digest")
    else:
        assets[0]["size"] += 1
    calls = []

    def api(path, method="GET", body=None, missing_ok=False):
        calls.append(method)
        return {"id": 1, "draft": True, "assets": assets}

    monkeypatch.setattr(release, "api", api)
    with pytest.raises(ValueError):
        release.publish_release("owner/uns", "v0.6.0", tmp_path)
    assert calls == ["GET"]


def test_release_publishes_only_after_exact_asset_digest_check(tmp_path, monkeypatch):
    files = distributions(tmp_path)
    calls = []

    def api(path, method="GET", body=None, missing_ok=False):
        calls.append((method, body))
        return {"id": 1, "draft": True, "assets": asset_rows(files)}

    monkeypatch.setattr(release, "api", api)
    release.publish_release("owner/uns", "v0.6.0", tmp_path)
    assert calls[-1] == ("PATCH", {"draft": False, "make_latest": "true"})

"""Validate tag-only releases, stage assets on a draft, then publish verified assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import tomllib

REQUIRED_CHECKS = ("CI", "Build MkDocs Site")


def validate_identity(ref_type: str, tag: str, version: str) -> None:
    if ref_type != "tag" or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Releases require a stable vMAJOR.MINOR.PATCH tag, never a branch")
    if tag != f"v{version}":
        raise ValueError("Release tag must exactly match the committed pyproject.toml version")


def validate_checks(runs: list[dict[str, Any]]) -> None:
    for name in REQUIRED_CHECKS:
        matching = [
            r
            for r in runs
            if r.get("name") == name and r.get("app", {}).get("slug") == "github-actions"
        ]
        latest = max(matching, key=lambda r: r["id"], default=None)
        if (
            latest is None
            or latest.get("status") != "completed"
            or latest.get("conclusion") != "success"
        ):
            raise ValueError(
                f"Latest GitHub Actions check {name!r} must have succeeded on the tagged commit"
            )


def api(
    path: str, method: str = "GET", body: dict[str, Any] | None = None, missing_ok: bool = False
) -> Any:
    command = ["gh", "api", "--method", method, path]
    if body is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else None
    if result.returncode:
        if missing_ok and isinstance(payload, dict) and str(payload.get("status")) == "404":
            return None
        raise RuntimeError(f"GitHub API {method} {path} failed: {result.stderr.strip()}")
    return payload


def release_files(directory: Path, tag: str) -> list[Path]:
    version = tag.removeprefix("v")
    expected = {f"uns-{version}-py3-none-any.whl", f"uns-{version}.tar.gz"}
    files = sorted(directory.iterdir())
    if {p.name for p in files} != expected or any(
        p.is_symlink() or not p.is_file() or p.stat().st_size == 0 for p in files
    ):
        raise ValueError(
            "Release artifacts must be exactly the nonempty UNS wheel and sdist for this tag"
        )
    return files


def upload(repository: str, tag: str, files: list[Path]) -> None:
    subprocess.run(
        [
            "gh",
            "release",
            "upload",
            tag,
            *(str(p) for p in files),
            "--repo",
            repository,
            "--clobber",
        ],
        check=True,
    )


def stage_release(repository: str, tag: str, sha: str, directory: Path) -> None:
    files = release_files(directory, tag)
    existing = api(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
    if existing is not None and not existing["draft"]:
        raise ValueError(
            "Release is already published; refusing to modify immutable release assets"
        )
    if existing is None:
        api(
            f"repos/{repository}/releases",
            "POST",
            {
                "tag_name": tag,
                "target_commitish": sha,
                "name": tag,
                "draft": True,
                "generate_release_notes": True,
            },
        )
    # Replacement is permitted only while this release is still a draft.
    upload(repository, tag, files)


def publish_release(repository: str, tag: str, directory: Path) -> None:
    files = release_files(directory, tag)
    release = api(f"repos/{repository}/releases/tags/{tag}")
    if not release["draft"]:
        raise ValueError("Release is already published; refusing to publish it again")
    assets = {a["name"]: a for a in release["assets"]}
    if set(assets) != {p.name for p in files}:
        raise ValueError("Draft release has missing or unexpected assets")
    for path in files:
        asset = assets[path.name]
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if asset.get("digest") != digest or asset.get("size") != path.stat().st_size:
            raise ValueError(
                f"Draft release asset {path.name} does not match the validated distribution"
            )
    api(
        f"repos/{repository}/releases/{release['id']}",
        "PATCH",
        {
            "draft": False,
            "make_latest": "true",
        },
    )


def verify_commit(repository: str, sha: str) -> None:
    subprocess.run(["git", "fetch", "--no-tags", "origin", "main"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", sha, "FETCH_HEAD"], check=True)
    runs = []
    page = 1
    while True:
        batch = api(f"repos/{repository}/commits/{sha}/check-runs?per_page=100&page={page}")[
            "check_runs"
        ]
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    validate_checks(runs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["verify", "stage", "publish"])
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    repository = os.environ["GITHUB_REPOSITORY"]
    tag = os.environ["GITHUB_REF_NAME"]
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    validate_identity(os.environ["GITHUB_REF_TYPE"], tag, version)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if args.operation == "verify":
        verify_commit(repository, sha)
    elif args.operation == "stage":
        stage_release(repository, tag, sha, args.dist)
    else:
        publish_release(repository, tag, args.dist)


if __name__ == "__main__":
    main()

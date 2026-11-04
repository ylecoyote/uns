"""Reproduce audit probes in a disposable local PostgreSQL 16 container.

Requires Docker and an already available postgres:16-alpine image. No real
provider calls are made. The temporary database and container are removed.
Passing probes demonstrate issue presence, not remediation.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-acceptance", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    name = f"uns-mpdd-{uuid4().hex[:12]}"
    image = "postgres:16-alpine"
    subprocess.run(["docker", "image", "inspect", image], check=True, stdout=subprocess.DEVNULL)
    created = False
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                name,
                "-e",
                "POSTGRES_USER=uns_audit",
                "-e",
                "POSTGRES_PASSWORD=audit-only-password",
                "-e",
                "POSTGRES_DB=uns_audit",
                "-p",
                "127.0.0.1::5432",
                image,
            ],
            check=True,
        )
        created = True
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "uns_audit"], capture_output=True
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        bindings = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True)
        port = bindings.strip().rsplit(":", 1)[1]
        url = f"postgresql+psycopg://uns_audit:audit-only-password@127.0.0.1:{port}/uns_audit"
        env = dict(os.environ, UNS_TEST_POSTGRES_URL=url, UNS_AUDIT_DATABASE_URL=url)
        targets = ["verification/mpdd-2026-11-03/test_audit_probes.py"]
        if args.include_acceptance:
            targets.insert(0, "tests/uns/test_postgres_and_load.py")
        result_code = 0
        for target in targets:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", target, "-q", "--tb=short"], cwd=root, env=env
            )
            result_code = max(result_code, result.returncode)
        return result_code
    finally:
        if created:
            subprocess.run(["docker", "stop", name], check=True)


if __name__ == "__main__":
    raise SystemExit(main())

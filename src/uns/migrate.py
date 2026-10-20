"""Idempotent additive schema bootstrap for new UNS runtime tables."""

from uns.config import value
from uns.runtime import Runtime


def main() -> None:
    url = value("DATABASE_URL")
    if not url:
        raise SystemExit("Set UNS_DATABASE_URL for the migration target")
    runtime = Runtime(url, create_tables=True)
    runtime.engine.dispose()
    print("UNS additive schema migration complete")


if __name__ == "__main__":
    main()

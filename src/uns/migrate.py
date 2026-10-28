"""Idempotent additive schema bootstrap for new UNS runtime tables."""

from uns.config import database_url
from uns.runtime import Runtime


def main() -> None:
    url = database_url()
    if not url:
        raise SystemExit("Set UNS_DATABASE_URL for the migration target")
    runtime = Runtime(url, create_tables=True)
    runtime.engine.dispose()
    print("UNS additive schema migration complete")


if __name__ == "__main__":
    main()

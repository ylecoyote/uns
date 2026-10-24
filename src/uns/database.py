"""Database URL classification shared by service startup and runtime diagnostics."""

from __future__ import annotations

from urllib.parse import unquote


def is_in_memory_database_url(url: str) -> bool:
    """Identify volatile SQLite storage without inspecting unrelated URL text.

    Missing SQLite file paths use memory regardless of the selected driver.
    SQLite ``file:`` URI options apply only when SQLAlchemy's ``uri`` flag is
    enabled; the same text in an ordinary filename is just part of that name.
    Invalid URLs remain errors rather than being classified as persistent.
    """
    normalized = url.strip()
    if not normalized:
        return True

    # Keep importing the public SDK independent of optional database packages.
    from sqlalchemy.engine import make_url

    parsed = make_url(normalized)
    if parsed.get_backend_name() != "sqlite":
        return False

    database = parsed.database or ""
    if not database or database == ":memory:":
        return True

    uri_flag = parsed.query.get("uri", "false")
    uri_enabled = isinstance(uri_flag, str) and uri_flag.strip().lower() in {
        "1", "true", "t", "yes", "y", "on",
    }
    if not uri_enabled or not database.startswith("file:"):
        return False

    uri_path = unquote(database.removeprefix("file:"))
    return not uri_path or uri_path == ":memory:" or parsed.query.get("mode") == "memory"

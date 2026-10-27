"""Persistence guarantees at actual service-construction boundaries."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from uns.database import is_in_memory_database_url


@pytest.mark.parametrize(
    ("url", "in_memory"),
    [
        ("", True),
        ("   ", True),
        ("sqlite://", True),
        ("sqlite:///", True),
        ("sqlite:///:memory:", True),
        ("sqlite+pysqlite://", True),
        ("sqlite+pysqlite:///:memory:", True),
        ("sqlite:///file::memory:?cache=shared&uri=true", True),
        ("sqlite:///file:%3Amemory%3A?uri=true", True),
        ("sqlite:///file:memdb1?mode=memory&cache=shared&uri=true", True),
        ("sqlite:///file:?uri=true", True),
        ("sqlite:///./uns.db", False),
        ("sqlite+pysqlite:////var/lib/uns/uns.db", False),
        ("sqlite:///normal-:memory:.db", False),
        ("sqlite:///mode=memory.db", False),
        ("sqlite:///:MEMORY:", False),
        ("sqlite:///file::memory:", False),
        ("sqlite:///file:memdb1?mode=memory", False),
        ("sqlite:///file:memdb1?mode=memory&uri=false", False),
        ("postgresql://example/uns?mode=memory", False),
    ],
)
def test_memory_url_classification_uses_database_semantics(url, in_memory):
    assert is_in_memory_database_url(url) is in_memory


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+pysqlite://",
        "sqlite:///",
        "sqlite:///file:memdb1?mode=memory&uri=true",
    ],
)
def test_mcp_write_guard_uses_same_memory_classification(monkeypatch, database_url):
    from uns_mcp.transports.stdio import runtime_config

    monkeypatch.setenv("UNS_DATABASE_URL", database_url)
    # HTTP's explicit demo opt-in must not relax the MCP write contract.
    monkeypatch.setenv("UNS_ALLOW_IN_MEMORY", "true")
    with pytest.raises(ValueError, match="Write-enabled MCP requires a persistent database"):
        runtime_config(enable_writes=True)


@pytest.fixture
def service_environment():
    # Fresh subprocesses must not inherit a real provider or database profile.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("UNS_") and key != "DATABASE_URL"
    }
    source_root = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, env.get("PYTHONPATH")]))
    return env


def service_process(tmp_path, env, script, *args):
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("module", ["uns.app", "uns.app"])
@pytest.mark.parametrize("database_url", [None, "", "sqlite+pysqlite://"])
def test_asgi_entrypoint_refuses_implicit_volatile_storage(
    tmp_path, service_environment, module, database_url
):
    if database_url is not None:
        service_environment["UNS_DATABASE_URL"] = database_url
    result = service_process(
        tmp_path,
        service_environment,
        "import importlib, sys; getattr(importlib.import_module(sys.argv[1]), 'app')",
        module,
    )
    assert result.returncode != 0
    assert "Refusing to start the UNS daemon with volatile in-memory storage" in result.stderr


@pytest.mark.parametrize("module", ["uns.app", "uns.app"])
def test_asgi_entrypoint_accepts_explicit_memory_opt_in(tmp_path, service_environment, module):
    service_environment["UNS_ALLOW_IN_MEMORY"] = "true"
    service_environment["UNS_DATABASE_URL"] = "sqlite+pysqlite://"
    result = service_process(
        tmp_path,
        service_environment,
        """
        import importlib
        import sys
        app = getattr(importlib.import_module(sys.argv[1]), "app")
        assert app.state.runtime.persistence_mode == "in_memory"
        app.state.runtime.engine.dispose()
        """,
        module,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("database_variable", ["UNS_DATABASE_URL", "UNS_DATABASE_URL", "DATABASE_URL"])
def test_asgi_entrypoint_preserves_persistent_database_aliases(
    tmp_path, service_environment, database_variable
):
    service_environment[database_variable] = f"sqlite:///{tmp_path / 'service.db'}"
    service_environment["UNS_CREATE_TABLES"] = "true"
    result = service_process(
        tmp_path,
        service_environment,
        """
        from uns.app import app
        assert app.state.runtime.persistence_mode == "persistent"
        app.state.runtime.engine.dispose()
        """,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "service.db").is_file()


def test_cli_refuses_missing_database_before_starting_uvicorn(tmp_path, service_environment):
    result = service_process(
        tmp_path,
        service_environment,
        """
        import uvicorn
        from uns.app import main
        def unexpected_server(*args, **kwargs):
            raise AssertionError("Uvicorn must not start without explicit persistence")
        uvicorn.run = unexpected_server
        main([])
        """,
    )
    assert result.returncode != 0
    assert "Refusing to start the UNS daemon with volatile in-memory storage" in result.stderr
    assert "Uvicorn must not start" not in result.stderr


def test_cli_memory_flag_reaches_guarded_asgi_factory(tmp_path, service_environment):
    service_environment["UNS_DATABASE_URL"] = ""
    result = service_process(
        tmp_path,
        service_environment,
        """
        import importlib
        import uvicorn
        from uns.app import main
        def inspect_server(target, **kwargs):
            module, attribute = target.split(":")
            app = getattr(importlib.import_module(module), attribute)
            assert app.state.runtime.persistence_mode == "in_memory"
            app.state.runtime.engine.dispose()
        uvicorn.run = inspect_server
        main(["--in-memory"])
        """,
    )
    assert result.returncode == 0, result.stderr


def test_explicit_embedded_memory_runtime_remains_supported(tmp_path, service_environment):
    result = service_process(
        tmp_path,
        service_environment,
        """
        from uns.app import create_app
        from uns.config import build_runtime
        runtime = build_runtime()
        app = create_app(runtime=runtime)
        assert app.state.runtime is runtime
        assert runtime.persistence_mode == "in_memory"
        runtime.engine.dispose()
        """,
    )
    assert result.returncode == 0, result.stderr

from __future__ import annotations

import signal

import pytest

from uns_mcp.transports.stdio import main


def test_stdio_main_is_importable() -> None:
    assert callable(main)


def test_write_profile_requires_explicit_persistent_config(monkeypatch):
    from uns_mcp.transports.stdio import runtime_config

    for name in ("UNS_DATABASE_URL", "UNS_DATABASE_URL", "DATABASE_URL", "UNS_API_PRINCIPAL", "UNS_API_PRINCIPAL", "UNS_MCP_DELIVERY_CONFIRMATION_TOKEN", "UNS_MCP_DELIVERY_CONFIRMATION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert runtime_config(enable_writes=False).read_only
    with pytest.raises(ValueError, match="DATABASE_URL"):
        runtime_config(enable_writes=True)
    for ephemeral in (
        "sqlite:///:memory:", "sqlite:///file::memory:?cache=shared&uri=true",
        "sqlite:///file:%3Amemory%3A?uri=true", "sqlite:///file:?uri=true",
        "sqlite:///file:memdb?mode=memory&cache=shared&uri=true",
    ):
        monkeypatch.setenv("UNS_DATABASE_URL", ephemeral)
        with pytest.raises(ValueError, match="persistent"):
            runtime_config(enable_writes=True)
    monkeypatch.setenv("UNS_DATABASE_URL", "sqlite:////tmp/uns-cli-test.db")
    with pytest.raises(ValueError, match="API_PRINCIPAL"):
        runtime_config(enable_writes=True)
    monkeypatch.setenv("UNS_API_PRINCIPAL", "operator")
    with pytest.raises(ValueError, match="CONFIRMATION_TOKEN"):
        runtime_config(enable_writes=True)
    monkeypatch.setenv("UNS_MCP_DELIVERY_CONFIRMATION_TOKEN", "test-confirmation")
    config = runtime_config(enable_writes=True)
    assert config.mode == "stdio-persistent"
    assert not config.read_only
    assert config.operator_principal == "operator"
    assert config.require_delivery_confirmation
    assert config.delivery_confirmation_token == "test-confirmation"


@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_real_write_enabled_stdio_exits_cleanly_on_signal(tmp_path, shutdown_signal):
    import json
    import os
    import select
    import subprocess
    import sys

    from mcp.types import LATEST_PROTOCOL_VERSION

    from uns.runtime import Runtime

    url = f"sqlite:///{tmp_path}/stdio.db"
    runtime = Runtime(url, create_tables=True)
    runtime.engine.dispose()
    env = {key: value for key, value in os.environ.items() if not key.startswith("UNS_")}
    env.update({
        "UNS_DATABASE_URL": url, "UNS_API_PRINCIPAL": "test-operator",
        "UNS_MCP_DELIVERY_CONFIRMATION_TOKEN": "test-confirmation",
        "PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1",
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uns_mcp.transports.stdio", "--enable-writes"],
        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "lifecycle-test", "version": "1"},
        }}) + "\n")
        process.stdin.flush()
        assert select.select([process.stdout], [], [], 10)[0], "MCP initialization timed out"
        response = json.loads(process.stdout.readline())
        assert response["id"] == 1 and "result" in response
        process.send_signal(shutdown_signal)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, (stdout, stderr)
        assert "Traceback" not in stderr
        assert "Task was destroyed" not in stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)

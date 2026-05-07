# AGSignal MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build AGSignal's first stdio MCP server with AGSignal-specific control-plane tools and a reusable factory boundary for future HTTP/SSE transport.

**Architecture:** Add a small `agsignal_mcp` package with a shared FastMCP factory, typed tool inputs, and a stdio entrypoint. Keep business behavior in `notification.*` by extracting reusable runtime helpers from existing HTTP route logic, then have both HTTP routes and MCP tools call those helpers.

**Tech Stack:** Python 3.10, Pydantic v2, FastAPI route models already in repo, official MCP Python SDK `FastMCP`, pytest.

---

## File Structure

- Create `src/agsignal_mcp/__init__.py`: package metadata and public factory export.
- Create `src/agsignal_mcp/runtime.py`: runtime mode/config object for MCP tools.
- Create `src/agsignal_mcp/tools.py`: typed MCP tool inputs and tool implementation functions.
- Create `src/agsignal_mcp/factory.py`: `create_mcp_server(runtime_config)` and tool registration.
- Create `src/agsignal_mcp/transports/__init__.py`: transport package marker.
- Create `src/agsignal_mcp/transports/stdio.py`: stdio entrypoint.
- Create `tests/agsignal_mcp/test_factory.py`: tool registry and package tests.
- Create `tests/agsignal_mcp/test_signal_tools.py`: simulate/send safety tests.
- Create `tests/agsignal_mcp/test_status_tools.py`: ACK/status/policy/DLQ/health tests.
- Create `tests/agsignal_mcp/test_stdio_entrypoint.py`: stdio module import/smoke tests.
- Modify `pyproject.toml`: add MCP optional extra/dev dependency and package include.
- Modify `src/notification/routes.py`: extract reusable send/simulate/status/ops helpers or delegate to them.
- Modify `src/mcp_server/routes_notification.py`: expose reusable ACK/DISMISS helpers or delegate to them.
- Modify `README.md` or publish docs only after code behavior exists.

## Task 1: Dependency And Package Skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/agsignal_mcp/__init__.py`
- Create: `src/agsignal_mcp/runtime.py`
- Create: `src/agsignal_mcp/transports/__init__.py`
- Test: `tests/agsignal_mcp/test_factory.py`

- [ ] **Step 1: Write the failing package/import test**

```python
from __future__ import annotations

from agsignal_mcp import MCPRuntimeConfig


def test_runtime_config_defaults_to_safe_local_stdio() -> None:
    config = MCPRuntimeConfig()

    assert config.mode == "stdio-local"
    assert config.read_only is False
    assert config.require_delivery_confirmation is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp/test_factory.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'agsignal_mcp'`.

- [ ] **Step 3: Add MCP dependency and package include**

In `pyproject.toml`, add:

```toml
dependencies = [
    "pydantic>=2.0.0",
    "PyYAML>=6.0.0",
    "redis>=5.0.0",
    "rq>=1.15.0",
    "fastapi>=0.100.0",
    "uvicorn>=0.22.0",
    "sqlalchemy>=2.0",
]

[project.optional-dependencies]
mcp = [
    "mcp[cli]>=1.0.0",
]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "fakeredis>=2.20.0",
    "httpx>=0.24.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "mcp[cli]>=1.0.0",
]
all = [
    "agsignal[adapters,dev,mcp]",
]

[tool.setuptools.packages.find]
where = ["src", "apps"]
include = ["agsignal*", "agsignal_mcp*", "notification*", "mcp_server*", "db*", "ui*"]
```

- [ ] **Step 4: Add package skeleton**

`src/agsignal_mcp/runtime.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RuntimeMode = Literal["stdio-local", "stdio-persistent", "read-only"]


@dataclass(frozen=True)
class MCPRuntimeConfig:
    mode: RuntimeMode = "stdio-local"
    read_only: bool = False
    require_delivery_confirmation: bool = True
```

`src/agsignal_mcp/__init__.py`:

```python
"""AGSignal Model Context Protocol integration."""

from agsignal_mcp.runtime import MCPRuntimeConfig

__all__ = ["MCPRuntimeConfig"]
```

`src/agsignal_mcp/transports/__init__.py`:

```python
"""AGSignal MCP transport entrypoints."""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp/test_factory.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/agsignal_mcp tests/agsignal_mcp
git commit -m "feat: add AGSignal MCP package skeleton"
```

## Task 2: Shared Runtime Helpers

**Files:**
- Create: `src/notification/runtime.py`
- Modify: `src/notification/routes.py`
- Modify: `src/mcp_server/routes_notification.py`
- Test: `tests/notification/test_runtime.py`

- [ ] **Step 1: Write failing tests for shared behavior**

```python
from __future__ import annotations

from uuid import uuid4

from notification.acknowledgment import InMemoryAckStorage, configure_ack_engine
from notification.models import AutonomyMode, NotificationIntent
from notification.runtime import RuntimeState, simulate_signal


def _payload() -> dict[str, object]:
    return {
        "notification_type": "agent.risk_limit_breach",
        "intent": NotificationIntent.SAFETY,
        "title": "Risk limit breached",
        "message": "Agent entered a position outside configured limits.",
        "source": "agent-runtime",
        "autonomy_context": {
            "autonomy_mode": AutonomyMode.LIVE,
            "agent_id": uuid4(),
        },
    }


def test_simulate_signal_has_no_ack_side_effects() -> None:
    configure_ack_engine(storage=InMemoryAckStorage())
    state = RuntimeState()

    response = simulate_signal(state, _payload())

    assert response.simulated is True
    assert response.ack_status is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/notification/test_runtime.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'notification.runtime'`.

- [ ] **Step 3: Implement `RuntimeState` and initial simulate helper**

`src/notification/runtime.py` should define:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from notification.audit import AuditStore, InMemoryAuditStore
from notification.channel_health import ChannelHealthTracker
from notification.dlq import DLQService
from notification.routes import SendNotificationRequest, SimulateNotificationResponse
from notification.routes import simulate_notification as simulate_notification_route


class _InMemoryRedisList:
    def __init__(self) -> None:
        self.values: list[str] = []

    def lpush(self, key: str, value: str) -> int:
        self.values.insert(0, value)
        return len(self.values)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        stop = None if end == -1 else end + 1
        return self.values[start:stop]

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        next_values = []
        for item in self.values:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            next_values.append(item)
        self.values = next_values
        return removed

    def llen(self, key: str) -> int:
        return len(self.values)


@dataclass
class RuntimeState:
    audit_store: AuditStore = field(default_factory=InMemoryAuditStore)
    dlq_service: DLQService = field(
        default_factory=lambda: DLQService(redis_client=_InMemoryRedisList())
    )
    channel_health_tracker: ChannelHealthTracker = field(default_factory=ChannelHealthTracker)


async def simulate_signal_async(
    state: RuntimeState,
    payload: dict[str, Any],
) -> SimulateNotificationResponse:
    request = SendNotificationRequest.model_validate(payload)
    return await simulate_notification_route(request)

def simulate_signal(
    state: RuntimeState,
    payload: dict[str, Any],
) -> SimulateNotificationResponse:
    import asyncio

    return asyncio.run(simulate_signal_async(state, payload))
```

- [ ] **Step 4: Refactor HTTP route logic only after tests cover parity**

Move duplicated `_InMemoryRedisList` behavior out of `notification.main` only if
the extraction stays small. Preserve existing `notification.main.create_app()`
tests exactly.

- [ ] **Step 5: Run existing route tests**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/notification/test_standalone_http_app.py tests/mcp_server/test_routes_notification.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/notification/runtime.py src/notification/routes.py src/mcp_server/routes_notification.py tests/notification/test_runtime.py
git commit -m "refactor: share AGSignal runtime helpers"
```

## Task 3: MCP Tool Factory And Safe Send Preview

**Files:**
- Create: `src/agsignal_mcp/tools.py`
- Create: `src/agsignal_mcp/factory.py`
- Modify: `src/agsignal_mcp/__init__.py`
- Test: `tests/agsignal_mcp/test_factory.py`
- Test: `tests/agsignal_mcp/test_signal_tools.py`

- [ ] **Step 1: Write failing factory/tool tests**

```python
from __future__ import annotations

import pytest

from agsignal_mcp.factory import AGSIGNAL_MCP_TOOL_NAMES, create_mcp_server
from agsignal_mcp.runtime import MCPRuntimeConfig
from agsignal_mcp.tools import SendSignalInput, send_signal


def test_factory_declares_v1_tool_names() -> None:
    create_mcp_server(MCPRuntimeConfig())

    assert "simulate_signal" in AGSIGNAL_MCP_TOOL_NAMES
    assert "send_signal" in AGSIGNAL_MCP_TOOL_NAMES
    assert "reload_policies" not in AGSIGNAL_MCP_TOOL_NAMES
    assert "remove_dlq_entry" not in AGSIGNAL_MCP_TOOL_NAMES


def test_send_signal_requires_confirmation_for_delivery() -> None:
    payload = SendSignalInput(
        notification_type="agent.risk_limit_breach",
        intent="SAFETY",
        title="Risk limit breached",
        message="Agent entered a position outside configured limits.",
        source="agent-runtime",
        autonomy_context={
            "autonomy_mode": "LIVE",
            "agent_id": "00000000-0000-0000-0000-000000000001",
        },
        deliver=True,
    )

    with pytest.raises(ValueError, match="operator_intent"):
        send_signal(payload)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp/test_factory.py tests/agsignal_mcp/test_signal_tools.py -q`

Expected: FAIL with missing `agsignal_mcp.factory` and `agsignal_mcp.tools`.

- [ ] **Step 3: Implement tool models and registration**

`src/agsignal_mcp/tools.py` should define:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SendSignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_type: str
    intent: str
    title: str
    message: str
    source: str
    autonomy_context: dict[str, Any]
    irreversible: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    delivery_mode: str | None = None
    require_ack: bool | None = None
    priority: str | None = None
    dedup_key: str | None = None
    idempotency_key: str | None = None
    deliver: bool = False
    operator_intent: Literal["deliver"] | None = None


def send_signal(payload: SendSignalInput) -> dict[str, Any]:
    if payload.deliver and payload.operator_intent != "deliver":
        raise ValueError("send_signal deliver=true requires operator_intent='deliver'")
    return {
        "delivered": False,
        "message": "delivery preview only",
        "notification_type": payload.notification_type,
    }
```

`src/agsignal_mcp/factory.py` should define:

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agsignal_mcp.runtime import MCPRuntimeConfig
from agsignal_mcp.tools import SendSignalInput, send_signal


AGSIGNAL_MCP_TOOL_NAMES = (
    "simulate_signal",
    "send_signal",
)


def create_mcp_server(runtime_config: MCPRuntimeConfig | None = None) -> FastMCP:
    config = runtime_config or MCPRuntimeConfig()
    mcp = FastMCP("AGSignal")

    @mcp.tool()
    def send_signal_tool(payload: SendSignalInput) -> dict[str, object]:
        """Preview or send an AGSignal signal."""
        if config.read_only:
            raise ValueError("send_signal is disabled in read-only mode")
        return send_signal(payload)

    return mcp
```

- [ ] **Step 4: Replace preview stub with real simulate path**

Wire `send_signal(deliver=False)` to the same simulation helper from Task 2.
Preserve the test that `deliver=True` requires confirmation before any runtime
call is made.

- [ ] **Step 5: Run tests**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp/test_factory.py tests/agsignal_mcp/test_signal_tools.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agsignal_mcp tests/agsignal_mcp
git commit -m "feat: add AGSignal MCP signal tools"
```

## Task 4: Status, ACK, Policy, DLQ, And Health Tools

**Files:**
- Modify: `src/agsignal_mcp/tools.py`
- Modify: `src/agsignal_mcp/factory.py`
- Test: `tests/agsignal_mcp/test_status_tools.py`

- [ ] **Step 1: Write failing status/read tests**

```python
from __future__ import annotations

from agsignal_mcp.factory import AGSIGNAL_MCP_TOOL_NAMES


def test_v1_status_tool_names_are_declared() -> None:
    assert "ack_notification" in AGSIGNAL_MCP_TOOL_NAMES
    assert "dismiss_notification" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_ack_status" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_delivery_status" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_effective_policy" in AGSIGNAL_MCP_TOOL_NAMES
    assert "list_invariants" in AGSIGNAL_MCP_TOOL_NAMES
    assert "list_dlq" in AGSIGNAL_MCP_TOOL_NAMES
    assert "get_channel_health" in AGSIGNAL_MCP_TOOL_NAMES
    assert "ready" in AGSIGNAL_MCP_TOOL_NAMES
```

- [ ] **Step 2: Run test to verify failure**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp/test_status_tools.py -q`

Expected: FAIL because the tool names are not yet declared.

- [ ] **Step 3: Add read/status tool functions**

Add functions in `src/agsignal_mcp/tools.py` that call shared helpers or existing
read-model adapters:

```python
def ready(config: MCPRuntimeConfig) -> dict[str, object]:
    return {
        "status": "ready",
        "service": "agsignal-mcp",
        "mode": config.mode,
        "read_only": config.read_only,
    }
```

Follow the same pattern for `health`, `list_dlq`, `get_channel_health`,
`get_ack_status`, and read-only policy/invariant helpers. Keep each tool
returning JSON-serializable dicts or lists.

- [ ] **Step 4: Add ACK/DISMISS write guards**

`ack_notification` and `dismiss_notification` must reject writes when
`MCPRuntimeConfig.read_only` is true:

```python
if config.read_only:
    raise ValueError("ack_notification is disabled in read-only mode")
```

- [ ] **Step 5: Register the full v1 tool set**

Update `AGSIGNAL_MCP_TOOL_NAMES` and `create_mcp_server()` so the registered
tool list matches the design spec. Do not register `reload_policies` or
`remove_dlq_entry`.

- [ ] **Step 6: Run focused tests**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/agsignal_mcp tests/agsignal_mcp
git commit -m "feat: add AGSignal MCP status tools"
```

## Task 5: Stdio Entrypoint, Docs, And Verification

**Files:**
- Create: `src/agsignal_mcp/transports/stdio.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-06-agsignal-mcp-server-design.md`
- Test: `tests/agsignal_mcp/test_stdio_entrypoint.py`

- [ ] **Step 1: Write failing stdio import test**

```python
from __future__ import annotations

from agsignal_mcp.transports.stdio import main


def test_stdio_main_is_importable() -> None:
    assert callable(main)
```

- [ ] **Step 2: Run test to verify failure**

Run: `UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp/test_stdio_entrypoint.py -q`

Expected: FAIL with missing module.

- [ ] **Step 3: Add stdio entrypoint**

`src/agsignal_mcp/transports/stdio.py`:

```python
from __future__ import annotations

from agsignal_mcp.factory import create_mcp_server
from agsignal_mcp.runtime import MCPRuntimeConfig


def main() -> None:
    """Run the AGSignal MCP server over stdio."""
    mcp = create_mcp_server(MCPRuntimeConfig())
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Document local usage**

Add a concise README section:

````markdown
### MCP Server

AGSignal includes a local stdio MCP server for agent clients:

```bash
uv run python -m agsignal_mcp.transports.stdio
```

The v1 server is stdio-only. HTTP/SSE transport is a deferred option documented
in `docs/superpowers/specs/2026-05-06-agsignal-mcp-server-design.md`.
````

- [ ] **Step 5: Run full verification**

Run:

```bash
UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run pytest tests/agsignal_mcp tests/notification/test_standalone_http_app.py tests/mcp_server/test_routes_notification.py -q
UV_CACHE_DIR=/private/tmp/agsignal-uv-cache uv run ruff check src tests
```

Expected: all selected pytest tests pass and ruff reports no new issues.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/superpowers/specs/2026-05-06-agsignal-mcp-server-design.md src/agsignal_mcp tests/agsignal_mcp pyproject.toml
git commit -m "docs: document AGSignal MCP stdio usage"
```

## Self-Review

- Spec coverage: Option B stdio server, reusable factory, safe delivery default,
  read-mostly v1 tools, explicit delivery confirmation, and deferred Option C
  are covered.
- Placeholder scan: no forbidden placeholder patterns remain.
- Type consistency: `MCPRuntimeConfig`, `create_mcp_server`, `SendSignalInput`,
  `simulate_signal`, and `send_signal` names are used consistently.
- Risk: Task 2 intentionally asks for a runtime helper extraction before the MCP
  tool implementation. If the extraction grows beyond a small adapter, stop and
  split a separate refactor task before continuing.

## References

- Design spec: `docs/superpowers/specs/2026-05-06-agsignal-mcp-server-design.md`
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Official MCP SDK list: https://modelcontextprotocol.io/docs/sdk

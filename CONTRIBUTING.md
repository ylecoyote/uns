# Contributing to UNS

Thank you for your interest in contributing to the **Unified Notification Service (UNS)**.

## Development Setup

### Prerequisites

**Backend:**
- Python 3.11 or higher (Python 3.12 recommended)
- `uv` or `pip` package manager
- SQLite 3 (bundled with Python) and optional PostgreSQL 16 (`psycopg[binary]>=3.2.0` included in `.[dev]` / `.[full]`; set `UNS_TEST_POSTGRES_URL` to run live PostgreSQL acceptance tests; Redis is optional for multi-instance WebSocket fanout tests)

**UNS Console (`apps/ui`):**
- Node.js `^20.19.0 || ^22.12.0 || >=24.0.0`
- `npm` (use `npm ci` with the committed lockfile)

### Installation

```bash
# Clone the repository
git clone https://github.com/ylecoyote/uns.git
cd uns

# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install with all runtime and development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all Python + UI contract tests
pytest

# Run documentation contract tests
pytest tests/docs/

# Run with coverage
pytest tests --cov=src/uns --cov=src/notification --cov=src/db --cov=src/uns_mcp

# Run a specific test file
pytest tests/uns/test_remediation_runtime.py
```

### Code Quality & Security Checks

```bash
# Lint code
ruff check src tests scripts apps

# Format code
ruff format src tests

# Type check
mypy src

# Security static analysis
bandit -q -r src
```

### UNS Console Development (`apps/ui`)

The **UNS Console** is a read-only React 19 + TypeScript 5.9 + ESLint 9 flat config (`eslint.config.js`) + Vite 8 Single Page Application across the 6 console surfaces (`/deliveries`, `/policy`, `/operations`, `/invariants`, `/audit`, `/docs`) in `apps/ui/`.

```bash
cd apps/ui

# Install dependencies from lockfile
npm ci

# Start local development server (proxies /ui/* to localhost:8000)
npm run dev

# Run full UI CI pipeline (type-check, lint, vitest, and production build)
npm run ci
```

From the repository root, verify the strict UI read-only boundary (`INV-UI-001`):

```bash
python scripts/ci/check_ui_boundary.py --strict
```

## Project Structure

```text
src/
├── uns/                    # Canonical durable outbox runtime, HTTP/WebSocket service & CLI entrypoints
│   ├── runtime.py          # Transactional outbox, leased dispatch, dedup, ACK & callback worker
│   ├── client.py           # Principal-bound async Client (send, simulate)
│   ├── policy_runtime.py   # Revision-locked ACTIVE policy resolver & override guard
│   ├── config.py           # Environment composition (UNS_* environment variables)
│   ├── routes.py           # /api/v1/runtime/* inspection, DLQ, and replay routes
│   ├── maintenance.py      # Explicit retention & SHA-256 verified archive CLI (uns-maintain)
│   ├── migrate.py          # Idempotent additive schema bootstrap (uns-migrate)
│   ├── app.py              # Unified FastAPI factory (uns CLI entrypoint)
│   ├── signaling.py        # Shared transport signaling service
│   ├── queries.py          # Read-model queries for /ui/* and MCP
│   └── api/                # Auth, observability, /v1/notifications/*, and /ui/* routers
├── uns_mcp/           # Model Context Protocol (MCP) server (uns-mcp)
│   ├── factory.py          # FastMCP factory & lifespan recovery worker
│   ├── tools.py            # 16 MCP tool implementations
│   └── transports/stdio.py # Trusted-local stdio entrypoint
├── notification/           # Core models, policy engine, and channel adapters
│   ├── models.py           # Domain contracts (Notification, AutonomyContext, etc.)
│   ├── policies.py         # Policy schema, registry, and delta validation
│   ├── service.py          # Channel delivery pipeline orchestration
│   └── adapters/           # Slack, Email, PagerDuty, and WebSocket adapters
├── db/                     # SQLAlchemy audit and policy snapshot persistence
└── ui_client/              # Typed Python read-model client helpers

apps/
└── ui/                     # UNS Console (React + TypeScript + Vite SPA)

docs/
├── support/                # State machines, database schema, and event catalog
├── tsg/                    # Troubleshooting Guides (TSG-01 through TSG-06)
├── user-guides/            # Operator Console, Producer, and Agent/MCP guides
├── sections/               # Delivery semantics, policy lifecycle, integration, observability
└── ui/                     # UI scope and JSON data contracts
```

## Coding Standards

- Follow PEP 8 with Ruff enforcement (`line-length = 100`).
- Use strict type annotations (`mypy --strict` on `src/`).
- Preserve existing docstrings and comments unless intentionally updating behavior.
- Never allow untrusted producer payloads or metadata to override `ACTIVE` policy routing or caller principal attribution.

## Writing Tests

Prefer testing against the canonical durable `uns.Runtime` and `uns.Client` (or using explicit `delivery_handler` wiring when testing low-level `NotificationSDK`):

```python
import pytest
from uuid import uuid4

from uns.responses import AutonomyContextRequest, SendNotificationRequest
from notification.models import AutonomyMode, Channel, NotificationIntent
from uns import Client, Runtime


@pytest.mark.asyncio
async def test_durable_send_and_ack(tmp_path):
    runtime = Runtime(f"sqlite:///{tmp_path / 'test.db'}", create_tables=True)
    client = Client(runtime, principal="test-operator")

    request = SendNotificationRequest(
        notification_type="system.alert",
        intent=NotificationIntent.OPERATIONAL,
        title="Test Signal",
        message="Verifying durable outbox intake",
        source="test_suite",
        autonomy_context=AutonomyContextRequest(
            autonomy_mode=AutonomyMode.PREVIEW,
            agent_id=uuid4(),
        ),
    )

    preview = await client.simulate(request)
    assert Channel.WEBSOCKET in preview.resolved_channels
    runtime.engine.dispose()
```

## Invariants (`docs/verification/invariants.yml`)

If your pull request introduces or modifies any system invariant:
1. Update [`docs/verification/invariants.yml`](docs/verification/invariants.yml) with severity, enforcement type, and evidence links.
2. Ensure all contract and documentation tests (`pytest tests/docs/`) pass.

## Pull Request Process

1. Run `ruff check src tests scripts apps` and `pytest`.
2. If touching `apps/ui` or `/ui/*` contracts, run `python scripts/ci/check_ui_boundary.py --strict` and `npm --prefix apps/ui run ci`.
3. Follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).

## Getting Help

- Browse the documentation index in [`docs/README.md`](docs/README.md).
- Review the product contract in [`docs/PRODUCT.md`](docs/PRODUCT.md) and security model in [`docs/SECURITY-MODEL.md`](docs/SECURITY-MODEL.md).

## License

By contributing to UNS, you agree that your contributions will be licensed under the Apache License 2.0 - see [LICENSE](LICENSE).

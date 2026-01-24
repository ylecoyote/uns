# UNS UI Dashboard

Read-only "flight instruments" dashboard for the Unified Notification Service (UNS).

## Overview

The UNS UI is a **read-first dashboard** that provides visibility into the notification system's state and health. Per the v1 scope, the UI is strictly **read-only** and does not provide any write operations.

See [UI Scope v1](../../docs/ui/ui-scope.md) for design philosophy and constraints.

## ⚠️ Non-Authoritative Rules

**The UI is NOT authoritative for business logic.**

All business rules, validation logic, and safety constraints are enforced by the UNS backend. The UI layer is strictly a presentation concern and does not:

- Bypass system invariants
- Introduce alternative paths for policy enforcement
- Perform any write operations to system state
- Cache or persist authoritative data

The backend API responses are the source of truth for all displayed data.

## Pages

| Page | Route | Description |
|------|-------|-------------|
| **Deliveries** | `/deliveries` | View notification delivery timelines and channel attempts |
| **Policy** | `/policy` | Inspect effective policy resolution and traces |
| **Invariants** | `/invariants` | View system invariants and compliance status |
| **Audit** | `/audit` | Browse the audit event timeline |

## Local Development

### Prerequisites

- Python 3.10+
- UNS backend running (default: `http://localhost:8000`)

### Installation

From the repository root:

```bash
# Install dependencies (includes UI package)
pip install -e ".[dev]"
```

### Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `UNS_API_BASE_URL` | Base URL for the UNS backend API | `http://localhost:8000` |
| `UNS_UI_DEBUG` | Enable debug mode | `false` |
| `UNS_UI_REQUEST_TIMEOUT` | Request timeout in seconds | `30` |
| `UNS_API_VERSION` | API version prefix | `v1` |

### Running Locally

1. **Start the UNS backend** (in a separate terminal):
   ```bash
   uvicorn mcp_server.app:app --reload
   ```

2. **Configure the API URL** (if not using default):
   ```bash
   export UNS_API_BASE_URL="http://localhost:8000"
   ```

3. **Run the UI** (development mode):
   ```bash
   # From repository root
   python -m apps.ui
   ```

### Running Tests

```bash
# Run UI tests only
pytest apps/ui/tests -v

# Run with coverage
pytest apps/ui/tests -v --cov=apps.ui
```

## Project Structure

```
apps/ui/
├── __init__.py           # Package initialization
├── README.md             # This file
├── src/
│   ├── __init__.py
│   ├── config.py         # Configuration management
│   ├── auth.py           # Authentication placeholder
│   ├── router.py         # Route definitions
│   ├── api/              # API client modules
│   │   └── __init__.py
│   ├── pages/            # Page components
│   │   ├── __init__.py
│   │   ├── deliveries.py # Deliveries explorer
│   │   ├── policy.py     # Policy inspector
│   │   ├── invariants.py # Invariants viewer
│   │   └── audit.py      # Audit timeline
│   ├── components/       # Reusable UI components
│   │   └── __init__.py
│   ├── layouts/          # Layout components
│   │   ├── __init__.py
│   │   └── main_layout.py
│   ├── hooks/            # Custom hooks
│   │   └── __init__.py
│   └── utils/            # Utility functions
│       └── __init__.py
└── tests/
    └── __init__.py
```

## API Endpoints

The UI consumes read-only endpoints from the UNS backend:

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/delivery-timelines` | List delivery timelines with filtering |
| `GET /api/v1/notifications/{id}/delivery-timeline` | Single delivery timeline |
| `GET /api/v1/policy-trace` | Effective policy resolution trace |
| `GET /api/v1/invariants` | List system invariants |
| `GET /api/v1/invariants/summary` | Invariant summary statistics |
| `GET /api/v1/audit-events` | List audit events |

See [UI Data Contracts](../../docs/ui/ui-data-contracts.md) for full API documentation.

## Security Model

### v1 Read-Only Posture

- **No write operations**: All endpoints are GET requests only
- **No privileged actions**: UI cannot modify system state
- **Backend authoritative**: All access control enforced by UNS backend
- **Minimal auth**: Placeholder authentication for v1 (configurable)

### Request ID Propagation

All API requests include an `X-Request-ID` header for correlation and debugging. This enables tracing requests through the system for support and troubleshooting.

## Related Documentation

- [UI Scope v1](../../docs/ui/ui-scope.md) - Design philosophy and constraints
- [UI Data Contracts](../../docs/ui/ui-data-contracts.md) - API response shapes and pagination
- [UI Read Models](../../docs/ui/ui-read-models.md) - Backend adapter architecture
- [UI Observability](../../docs/ui/ui-observability.md) - Health monitoring and metrics

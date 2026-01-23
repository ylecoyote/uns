# UNS UI App

Read-only dashboard for the Unified Notification Service.

## Overview

This UI provides visibility into:
- **Deliveries**: View delivery timelines and attempts
- **Policy**: Inspect effective policy resolution and trace
- **Invariants**: Browse system invariants
- **Audit**: View audit event stream

**Important**: All endpoints are READ-ONLY. No mutating actions are permitted.

## Local Development

### Prerequisites
- Python 3.11+
- UNS backend running on `http://localhost:8000`

### Setup

```bash
# From repository root
pip install -e ".[dev]"

# Run the backend
python -m mcp_server.app

# Run UI tests
pytest apps/ui/tests/
```

### Environment Configuration

Set `UNS_API_BASE_URL` environment variable to point to your UNS backend:

```bash
export UNS_API_BASE_URL=http://localhost:8000
```

## Architecture

```
apps/ui/
├── src/
│   ├── api/          # Typed API client for /ui endpoints
│   ├── pages/        # Page components (Policy, Deliveries, etc.)
│   └── components/   # Reusable UI components
├── tests/            # UI-specific tests
└── README.md
```

## Non-Authoritative Rules

This UI is **non-authoritative** per UI Scope v1:
- All data is read-only
- No privileged actions (RBAC enforcement, policy mutation, etc.)
- UI displays data as provided by the backend
- Error states are shown with request IDs for support

## API Contracts

See `docs/ui/ui-data-contracts.md` for complete response shapes.

# UNS Dashboard UI

Read-only dashboard for the Unified Notification Service.

## Overview

This is a **read-only "flight instruments" dashboard** per [ui-scope.md](../../docs/ui/ui-scope.md). It provides visibility into the notification system's state and health without offering direct manipulation capabilities.

**v1 Constraints:**
- No notification authoring
- No policy editing
- Read-only dashboards only
- Metrics & health monitoring included

## Pages

### Deliveries Explorer
- **List view** (`/pages/deliveries/`): Paginated list of delivery timelines with filters
  - Filter by: status, intent, delivery_mode, autonomy_mode, channel, notification_type, agent_id, time range
  - Cursor-based pagination
- **Detail view** (`/pages/deliveries/{notification_id}`): Full delivery timeline
  - Notification summary
  - Autonomy context
  - Channel results
  - Delivery attempts with timing and errors

### Other Pages (Planned)
- Policy Inspector (`/pages/policies/`)
- Invariants Viewer (`/pages/invariants/`)
- Audit Timeline (`/pages/audit/`)

## Local Development

### Prerequisites
- Python 3.10+
- Dependencies from main project

### Run Standalone

```bash
# From project root
cd apps/ui
uvicorn app:app --reload --port 8001

# Or from project root
uvicorn apps.ui.app:app --reload --port 8001
```

Then visit http://localhost:8001/pages/deliveries/

### Run with Main Server

The UI can be mounted into the main UNS server:

```python
from apps.ui.app import create_ui_app

# In your main app setup
main_app.mount("/dashboard", create_ui_app())
```

## Architecture

This module provides a **JSON API backend** for the React frontend:

- **Backend (this module)**: FastAPI endpoints returning JSON responses
- **Frontend (React)**: TypeScript/React components in `src/*.tsx` that consume the JSON API

The backend does not serve HTML directly. All HTML rendering is handled by the React frontend.

## Project Structure

```
apps/ui/
├── __init__.py           # Package init
├── app.py                # FastAPI app factory (JSON API)
├── README.md             # This file
├── src/
│   ├── api/              # Typed API client
│   │   ├── __init__.py
│   │   ├── client.py     # UNSUIClient
│   │   └── types.py      # Response types
│   ├── pages/            # Page routers (JSON API endpoints)
│   │   ├── __init__.py
│   │   └── deliveries.py # Deliveries Explorer API
│   ├── components/       # React components
│   │   └── *.tsx
│   ├── hooks/            # React hooks
│   │   └── *.ts
│   ├── App.tsx           # Main React app
│   └── main.tsx          # React entry point
├── static/
│   └── css/
│       └── main.css      # Styles
└── tests/                # API tests
    └── __init__.py
```

## API Client Usage

The typed API client can be used programmatically:

```python
from apps.ui.src.api import UNSUIClient
from notification.models import DeliveryStatus

client = UNSUIClient(base_url="http://localhost:8000")

# List deliveries with filters
deliveries = client.list_deliveries(
    status=DeliveryStatus.DELIVERED,
    limit=10,
)

# Get single delivery timeline
timeline = client.get_delivery_timeline(notification_id)
```

## Non-Authoritative Rules

Per the project's invariant integrity principles:
- The UI layer is strictly a presentation concern
- All business rules and validation logic are enforced by the backend
- The UI does not introduce alternative paths that could circumvent policy enforcement

## Data Contracts

Response shapes match [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md):
- `DeliveryTimelineListResponse` - Paginated list with filtering
- `DeliveryTimelineResponse` - Full timeline with attempts
- `DeliveryTimelineSummary` - Summary for list items
- `DeliveryAttempt` - Single channel attempt

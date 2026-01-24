# UNS Dashboard UI

Read-only dashboard for the Unified Notification Service.

## Stack

**Canonical UI**: React + TypeScript + Vite (SPA)

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.x | UI framework |
| TypeScript | 5.x | Type safety |
| Vite | 5.x | Build tool and dev server |
| React Router | 6.x | Client-side routing |
| Vitest | 1.x | Unit testing |
| React Testing Library | 14.x | Component testing |

## Design Principles

### Non-Authoritative UI

The UI is a **read-first "flight instruments" dashboard** per [ui-scope.md](../../docs/ui/ui-scope.md). It provides visibility into the notification system's state and health without offering direct manipulation capabilities.

**Key constraints:**

1. **Read-only endpoints only** — UI must only call HTTP endpoints under `/ui/*`
2. **No direct backend imports** — UI does not import from `src/notification/` or any Python modules
3. **Non-authoritative** — All business rules and validation logic are enforced by the backend; the UI is strictly a presentation layer
4. **Degraded-state handling** — UI renders a degraded banner when backend returns `degraded: true`

### Phase 1 Posture

| Capability | v1 Status |
|------------|-----------|
| Notification authoring | **Not included** |
| Policy editing | **Not included** |
| Read-only dashboards | ✅ Included |
| Metrics & health monitoring | ✅ Included |
| Mutation actions (POST/PUT/DELETE) | **Not included** |

All UI endpoints are **GET-only**. No mutation actions are exposed in Phase 1.

### Invariant Integrity

**The UI must not bypass system invariants.**

All business rules, validation logic, and safety constraints enforced by the backend remain authoritative. The UI layer is strictly a presentation concern and does not introduce alternative paths that could circumvent policy enforcement or data integrity checks.

See [INV-UI-001](../../docs/verification/invariants.yml) for the formal invariant definition.

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `/deliveries` | Deliveries Explorer | Paginated list with filters |
| `/deliveries/:notification_id` | Delivery Detail | Full delivery timeline with attempts |
| `/policy` | Policy Inspector | Effective policy resolution viewer |
| `/invariants` | Invariants Viewer | System invariants with filters |
| `/audit` | Audit Timeline | Audit events with filters |

## Architecture

This module provides a **JSON API backend** for the React frontend:

- **Backend (this module)**: FastAPI endpoints returning JSON responses
- **Frontend (React)**: TypeScript/React components in `src/*.tsx` that consume the JSON API

The backend does not serve HTML directly. All HTML rendering is handled by the React frontend.

## Project Structure

```
apps/ui/
├── index.html              # HTML entry point (Vite)
├── package.json            # npm dependencies and scripts
├── vite.config.ts          # Vite configuration
├── tsconfig.json           # TypeScript configuration
├── .eslintrc.cjs           # ESLint configuration
├── .env.example            # Environment variable template
├── __init__.py             # Package init (Python backend)
├── app.py                  # FastAPI app factory (JSON API backend)
├── src/
│   ├── main.tsx            # React entry point
│   ├── App.tsx             # Layout + routing
│   ├── App.css             # Global styles
│   ├── api/                # Typed API client (TypeScript)
│   │   ├── client.ts       # UNSUIClient
│   │   ├── types.ts        # Response type definitions
│   │   ├── audit.ts        # Audit endpoints
│   │   └── invariants.ts   # Invariants endpoints
│   ├── pages/              # Page components (React) + API routers (Python)
│   │   ├── AuditTimeline.tsx
│   │   ├── InvariantsPage.tsx
│   │   ├── index.ts
│   │   ├── __init__.py
│   │   └── deliveries.py   # Deliveries Explorer JSON API
│   ├── components/         # Reusable UI components
│   │   ├── AuditEventCard.tsx
│   │   ├── AuditFilters.tsx
│   │   ├── InvariantsList.tsx
│   │   ├── InvariantsFilter.tsx
│   │   ├── InvariantsSummary.tsx
│   │   ├── Pagination.tsx
│   │   └── index.ts
│   ├── hooks/              # Custom React hooks
│   │   ├── useAuditEvents.ts
│   │   ├── useInvariants.ts
│   │   └── index.ts
│   ├── types/              # TypeScript type definitions
│   │   ├── api.ts
│   │   ├── common.ts
│   │   ├── invariants.ts
│   │   └── index.ts
│   └── test/               # Test utilities
│       ├── mocks.ts        # MSW mocks
│       └── setup.ts        # Vitest setup
├── static/
│   └── css/
│       └── main.css        # Styles
└── tests/                  # Component, integration, and API tests
    ├── *.test.tsx          # React component tests
    ├── *.test.ts           # API client tests
    └── __init__.py
```

## Local Development

### Prerequisites

- Node.js 18+ (LTS recommended)
- npm 9+

### Environment Setup

Copy the environment template:

```bash
cp .env.example .env
```

Configure the API base URL (defaults to local dev server):

```bash
# .env
VITE_UNS_API_BASE_URL=http://localhost:8000
```

### Install Dependencies

```bash
cd apps/ui
npm install
```

### Run Dev Server

```bash
npm run dev
```

Then visit http://localhost:5173

The Vite dev server proxies `/ui/*` requests to the backend at `http://localhost:8000` (configurable via `VITE_UNS_API_BASE_URL`).

### Run Tests

```bash
# Run tests in watch mode
npm test

# Run tests once (CI mode)
npm run test:run
```

### Run Linting

```bash
npm run lint
```

### Type Checking

```bash
npm run type-check
```

### Build for Production

```bash
npm run build
```

Output is placed in `dist/`.

### Preview Production Build

```bash
npm run preview
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_UNS_API_BASE_URL` | Base URL for UNS API endpoints | `http://localhost:8000` |

All environment variables must be prefixed with `VITE_` to be exposed to the browser.

## API Client Usage

The typed API client consumes only `/ui/*` endpoints:

```typescript
import { UNSUIClient } from './api/client';

const client = new UNSUIClient();

// List deliveries with filters
const deliveries = await client.listDeliveries({
  status: 'DELIVERED',
  limit: 10,
});

// Get single delivery timeline
const timeline = await client.getDeliveryTimeline(notificationId);

// Get invariants with filters
const invariants = await client.listInvariants({
  severity: 'HIGH',
});

// Get audit events
const events = await client.listAuditEvents({
  start_time: '2026-01-01T00:00:00Z',
  end_time: '2026-01-31T23:59:59Z',
});
```

### Degraded State Handling

The API client detects degraded responses and exposes them:

```typescript
const response = await client.listInvariants();

if (response.degraded) {
  // Show degraded banner in UI
  console.warn('Data may be incomplete:', response.degraded_reason);
}
```

## API Endpoints Consumed

All endpoints are **GET-only** per Phase 1 posture. The UI consumes only `/ui/*` endpoints:

| Endpoint | Description | Documentation |
|----------|-------------|---------------|
| `GET /ui/deliveries` | List delivery timelines | [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md) |
| `GET /ui/deliveries/{id}` | Single delivery timeline | [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md) |
| `GET /ui/policies/effective` | Effective policy resolution | [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md) |
| `GET /ui/invariants` | List system invariants | [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md) |
| `GET /ui/invariants/summary` | Invariants summary stats | [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md) |
| `GET /ui/audit` | List audit events | [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md) |

## Scripts Reference

| Script | Command | Description |
|--------|---------|-------------|
| `dev` | `npm run dev` | Start Vite dev server with HMR |
| `build` | `npm run build` | Type-check and build for production |
| `preview` | `npm run preview` | Preview production build |
| `test` | `npm test` | Run tests in watch mode |
| `test:run` | `npm run test:run` | Run tests once (CI mode) |
| `lint` | `npm run lint` | Run ESLint |
| `type-check` | `npm run type-check` | Run TypeScript type checking |

## Data Contracts

Response shapes match [ui-data-contracts.md](../../docs/ui/ui-data-contracts.md):

- `DeliveryTimelineListResponse` - Paginated list with filtering
- `DeliveryTimelineResponse` - Full timeline with attempts
- `DeliveryTimelineSummary` - Summary for list items
- `DeliveryAttempt` - Single channel attempt
- `InvariantsListResponse` - Paginated invariants list
- `InvariantsSummaryResponse` - Summary statistics
- `AuditEventsListResponse` - Paginated audit events

## Boundary Rules

The canonical `apps/ui/` directory enforces strict boundaries to prevent Flask/Python HTML-serving patterns from returning. This is enforced by a CI guardrail.

### Rules

| Rule | Description |
|------|-------------|
| **NO_PYTHON_IN_CANONICAL_UI** | No `.py` files allowed in `apps/ui/` except under `legacy_flask_reference/` |
| **NO_TEMPLATES_DIRECTORY** | No `templates/` directories (Flask-style HTML templating) |
| **NO_FLASK_APP_IN_UI** | No Flask imports or `render_template` patterns in app.py files |

### Allowed Exceptions

Python files are allowed **only** under `apps/ui/legacy_flask_reference/` for migration reference purposes. This folder is intended for:
- Temporary preservation of old Flask code during migration
- Reference for developers migrating functionality to the canonical React/TypeScript stack

### Where Backend Code Should Live

| Code Type | Location |
|-----------|----------|
| UI API Routes | `src/mcp_server/routes_ui.py` |
| Pydantic Models | `src/notification/models.py` or `src/mcp_server/read_models.py` |
| Backend Tests | `tests/ui_client/` or `tests/mcp_server/` |
| Read Model Adapters | `src/mcp_server/read_models.py` |

### Running the Guardrail

```bash
# Check for violations (warning mode)
python scripts/ci/check_ui_boundary.py

# Strict mode (fails CI on violations)
python scripts/ci/check_ui_boundary.py --strict

# Show migration guidance
python scripts/ci/check_ui_boundary.py --fix
```

### Current Status

The guardrail currently detects Python files in `apps/ui/` that need to be migrated. These files are legacy artifacts from the initial FastAPI-based UI implementation and should be moved to the appropriate backend locations.

See [scripts/ci/check_ui_boundary.py](../../scripts/ci/check_ui_boundary.py) for the full guardrail implementation.

## Related Documentation

- [UI Scope v1](../../docs/ui/ui-scope.md) - v1 constraints and design philosophy
- [UI Data Contracts](../../docs/ui/ui-data-contracts.md) - API response shapes and contracts
- [UI Observability](../../docs/ui/ui-observability.md) - Observability for UI layer
- [System Invariants](../../docs/verification/invariants.yml) - Formal invariant definitions
- [Phase 1 Verification](../../docs/reports/ui/phase-1-verify.md) - Bounded verification report

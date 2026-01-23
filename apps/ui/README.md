# UNS UI - Read-Only Dashboard

A read-only UI dashboard for the Unified Notification Service (UNS).

## Non-Authoritative Rules

This UI is **read-only** by design per [UI Scope v1](../../docs/ui/ui-scope.md):

- All endpoints are GET-only
- No mutating actions are permitted
- No privileged operations are exposed
- UI cannot modify policies, invariants, or delivery state

## Features

### Invariants Viewer

View system invariants for compliance and audit purposes:

- **Summary Panel**: Statistics from `/ui/invariants/summary`
  - Total count
  - Breakdown by severity (HIGH/MEDIUM/LOW)
  - Breakdown by enforcement type (guard/isolation/test/exception)
  - Breakdown by status (active/inactive)
  - Exceptions requiring review count

- **Filter Controls**:
  - Severity filter
  - Enforcement type filter
  - Status filter
  - Full-text search on statement

- **Paginated List**:
  - Cursor-based pagination
  - Evidence links
  - Mitigation details for exceptions

- **Degraded State Display**:
  - Visual warning when API indicates degraded state
  - Error details with request ID for debugging

## Local Development

### Prerequisites

- Node.js >= 18
- npm or yarn

### Installation

```bash
cd apps/ui
npm install
```

### Environment Configuration

Create a `.env.local` file:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### Running Locally

```bash
npm run dev
```

The UI will be available at `http://localhost:5173`.

### Building for Production

```bash
npm run build
```

## API Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /ui/invariants` | List invariants with filters |
| `GET /ui/invariants/summary` | Get summary statistics |

See [UI Data Contracts](../../docs/ui/ui-data-contracts.md) for full API documentation.

## Project Structure

```
apps/ui/
  src/
    api/           # API client
    components/    # Reusable UI components
    hooks/         # React hooks
    pages/         # Page components
    types/         # TypeScript types
```

## Testing

```bash
npm run test
```

## Linting

```bash
npm run lint
```

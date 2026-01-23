# UNS UI Dashboard

Read-only dashboard for the Unified Notification Service.

## Overview

This UI provides read-only visibility into the UNS notification delivery system:
- **Deliveries**: View delivery timelines and attempt history
- **Policy**: Inspect effective policy resolution
- **Invariants**: View system invariants and their enforcement status
- **Audit**: Browse the audit event stream with filtering

## Read-Only Posture

All UI interactions are read-only. No mutations are permitted through this interface.
See [UI Scope](../../docs/ui/ui-scope.md) for constraints.

## Development

### Prerequisites

- Node.js 18+
- npm 9+
- UNS backend running on `http://localhost:8000`

### Setup

```bash
cd apps/ui
npm install
npm run dev
```

The UI will be available at `http://localhost:5173`.

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run test` - Run tests in watch mode
- `npm run test:run` - Run tests once
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript type checking

### API Proxy

In development, requests to `/ui/*` are proxied to the backend at `http://localhost:8000`.

## Architecture

```
src/
  api/          # API client functions
  components/   # Reusable UI components
  hooks/        # Custom React hooks
  pages/        # Page components
  types/        # TypeScript type definitions
  test/         # Test utilities and setup
```

## Non-Authoritative

This README is non-authoritative. For canonical API contracts, see:
- [UI Data Contracts](../../docs/ui/ui-data-contracts.md) - Authoritative API shapes
- [UI Scope](../../docs/ui/ui-scope.md) - Read-only constraints

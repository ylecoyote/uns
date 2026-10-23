# UNS Console

Read-first, read-only dashboard for UNS. The backend is authoritative for all policy, delivery and response state; the UI is non-authoritative and has no mutation actions.

## Stack

Canonical UI: **React + TypeScript + Vite (SPA)**.

| Technology | Supported line | Purpose |
|---|---|---|
| React | 18.x | UI components |
| TypeScript | 5.x | Static types |
| Vite | 7.x | Development and production build |
| React Router | 7.x | Client-side navigation |
| Vitest | 4.x | Component and client tests |

Node must satisfy `^20.19.0 || ^22.12.0 || >=24.0.0`, as declared in package.json. Use the committed lockfile with `npm ci`.

## Design Principles

The console provides flight instruments for operators. It has no direct backend imports and consumes HTTP GET-only endpoints under `/ui/*`. Phase 1 posture remains read-only dashboards, effective-policy inspection and audit history. Authentication does not turn the UI into an approval or execution surface.

Backend invariants remain authoritative. See [INV-UI-001](../../docs/verification/invariants.yml) and [UI scope](../../docs/ui/ui-scope.md). Degraded responses produce a degraded banner; successful HTTP status is not proof of provider delivery or human comprehension.

## Operator access

The console starts at a sign-in form. An operator enters the configured service API key, which is validated with a protected read before pages mount. The key is held only in memory for that tab and sent in the Authorization header. It is not stored in localStorage/sessionStorage, placed in URLs, or embedded in build output. Reloading or signing out clears the key and unmounts sensitive pages.

A 401 expires the current session; a 403 is shown as an authorization failure without destroying an otherwise valid session. Cancellation and late responses cannot restore a discarded session. Requests reject redirects and bypass browser caches.

The current backend uses an operator API key, not separate read-only roles. A read-only UI does not make that credential read-only. Host the console only on a trusted origin over HTTPS for shared use. The React console currently has no WebSocket client.

## Pages

| Route | Page |
|---|---|
| `/deliveries` | Deliveries Explorer |
| `/deliveries/:notification_id` | Delivery, response deadline and policy evidence |
| `/policy` | Effective Policy Inspector |
| `/invariants` | Invariants Viewer |
| `/audit` | Audit Timeline |

## Architecture

The frontend contains React/TypeScript only. The JSON API lives in `src/agsignal/api/` at the repository root. Historical Python UI code is preserved in `legacy_flask_reference/`, is not served by the console, and is not part of its current test suite.

## Project Structure

```text
apps/ui/
  index.html
  package.json
  package-lock.json
  vite.config.ts
  vitest.config.ts
  src/
    main.tsx
    App.tsx
    api/          # typed GET clients and runtime contract decoders
    auth/         # tab-lifetime credential state
    components/   # sign-in and shared views
    pages/        # React pages
    hooks/
    types/
    test/
  tests/          # component and HTTP client tests
  legacy_flask_reference/  # historical, not an active backend
```

## Local Development

Run the backend separately using [deployment instructions](../../docs/DEPLOYMENT.md). From this directory:

```sh
npm ci
npm run dev
```

Visit http://localhost:5173. `vite.config.ts` proxies `/ui/*` to `http://localhost:8000` for local development. Change that development proxy target when needed. Production hosting must route `/ui/*` on the same origin to the UNS backend and serve the SPA for its frontend routes.

## Environment Variables

No environment file is required by the current client. Requests use same-origin `/ui` URLs. The historical `VITE_UNS_API_BASE_URL` setting is not read by the client. `.env.example` records this boundary; do not place credentials in any `VITE_` variable, because such values can be embedded in browser assets.

## Run Tests and Build Scripts

```sh
npm run test:run
npm run test:coverage
npm run type-check
npm run lint
npm run build
npm run ci
```

`npm test` runs watch mode. `npm run preview` previews `dist/`; it is not a production host. The CI command runs types, lint, tests and build. The independent Python boundary check is `python scripts/ci/check_ui_boundary.py --strict` from the repository root.

## API Client Usage

```typescript
import { getDeliveries, getDeliveryTimeline } from './src/api/deliveries';

const deliveries = await getDeliveries({ status: 'DELIVERED', limit: 10 });
const timeline = await getDeliveryTimeline(notificationId);
```

The client reads the current tab credential. Contract decoders validate the response shape; missing or malformed results must not be treated as successful delivery.

## API Endpoints Consumed

| Endpoint | Purpose |
|---|---|
| GET `/ui/deliveries` | Delivery summaries |
| GET `/ui/deliveries/{notification_id}` | Delivery and response detail |
| GET `/ui/audit` | Audit events and sign-in probe |
| GET `/ui/policies/effective` | Current effective policy |
| GET `/ui/invariants` | Invariant records |
| GET `/ui/invariants/summary` | Invariant summary |

## Related Documentation

See [Operator Console Guide](../../docs/user-guides/OPERATOR-CONSOLE-GUIDE.md), [UI scope](../../docs/ui/ui-scope.md), [UI contracts](../../docs/ui/ui-data-contracts.md), [security](../../docs/SECURITY-MODEL.md), and [verification](../../docs/TESTING.md) for current evidence and limits.

# UNS Console

Read-first, read-only dashboard for UNS. The backend is authoritative for all policy, delivery and response state; the UI is non-authoritative and has no mutation actions.

## Stack

Canonical UI: **React + TypeScript + Vite (SPA)**.

| Technology | Supported line | Purpose |
|---|---|---|
| React | 19.x | UI components |
| TypeScript | 5.8+ (5.9.x) | Static types |
| Vite | 8.x | Development and production build |
| React Router | 7.x | Client-side navigation |
| Vitest | 5.x | Component and client tests |
| ESLint | 9.x | Flat config linting (eslint.config.js) |

Node must satisfy `^20.19.0 || ^22.12.0 || >=24.0.0`, as declared in package.json. Use the committed lockfile with `npm ci`.

## Design Principles

The console provides flight instruments for operators. It has no direct backend imports and consumes HTTP GET-only endpoints under `/ui/*`. Phase 1 posture remains read-only dashboards, effective-policy inspection and audit history. While `/ui/*` endpoints are `GET-only` read models (`Phase 1` read-only baseline), `Phase 2` responder and operator workflows invoke capability-gated `/api/v1/*` endpoints (`POST /api/v1/notifications/{id}/ack`, `/dismiss`, `POST /api/v1/runtime/notifications/{id}/replay`, `DELETE /api/v1/dlq/{entry_id}`, `POST /api/v1/notifications/simulate`, `POST /api/v1/notifications`, `POST /api/v1/policies/reload`, `GET /readyz`, `GET /api/v1/channels/health`, `GET /api/v1/dlq`, `GET /api/v1/runtime/dead-letters`). In both postures, the backend is authoritative; the UI is non-authoritative and has no mutation actions without explicit server verification. Authentication does not turn the UI into an unverified approval or execution surface.

Backend invariants remain authoritative. See [INV-UI-001](../../docs/verification/invariants.yml) and [UI scope](../../docs/ui/ui-scope.md). Degraded responses produce a degraded banner; successful HTTP status is not proof of provider delivery or human comprehension.

## Operator access

The console starts at a sign-in form. An operator enters a configured service API key, which is validated before pages mount via `GET /ui/session` capability introspection (discovering granted roles: `OPERATOR`, `RESPONDER`, `PRODUCER`, `READ-ONLY`), falling back to `GET /ui/audit?limit=1`. The key is held only in memory for that tab and sent in the Authorization header. It is not stored in localStorage/sessionStorage, placed in URLs, or embedded in build output. Reloading or signing out clears the key and unmounts sensitive pages.

A 401 expires the current session; a 403 is shown as an authorization failure without destroying an otherwise valid session. Cancellation and late responses cannot restore a discarded session. Requests reject redirects and bypass browser caches.

The backend supports scoped role credentials (`UNS_API_KEY`, `UNS_RESPONDER_API_KEY`, `UNS_PRODUCER_API_KEY`, `UNS_OBSERVER_API_KEY`) alongside the Phase 1 read-first / GET-only inspection baseline. A read-only UI does not make an administrative credential read-only; scoped roles enforce principle-of-least-privilege at the backend API boundary. Host the console only on a trusted origin over HTTPS for shared use. The React console currently has no WebSocket client.

## Pages

| Route | Page |
|---|---|
| `/deliveries` | Deliveries Explorer |
| `/deliveries/:notification_id` | Delivery, response deadline and policy evidence |
| `/policy` | Effective Policy Inspector |
| `/operations` | Operations & Dead-Letter Recovery |
| `/invariants` | Invariants Viewer |
| `/audit` | Audit Timeline |
| `/docs` | In-Portal Documentation & Runbooks |

## Architecture

The frontend contains React/TypeScript only. The JSON API lives in `src/uns/api/` at the repository root. Historical Python UI code is preserved in `legacy_flask_reference/`, is not served by the console, and is not part of its current test suite.

## Project Structure

```text
apps/ui/
  index.html
  package.json
  package-lock.json
  eslint.config.js
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

### Read Model Endpoints (`/ui/*` — Phase 1 Read-Only Baseline)

`/ui/*` endpoints are `GET-only` read models representing the Phase 1 read-only baseline:

| Endpoint | Purpose |
|---|---|
| GET `/ui/session` | Capability introspection (`OPERATOR`, `RESPONDER`, `PRODUCER`, `READ-ONLY`) |
| GET `/ui/deliveries` | Delivery summaries |
| GET `/ui/deliveries/{notification_id}` | Delivery and response detail |
| GET `/ui/audit` | Audit events and sign-in probe |
| GET `/ui/policies/active` | Active policies catalog |
| GET `/ui/policies/effective` | Current effective policy |
| GET `/ui/policies/revisions` | Policy revision history and lineage |
| GET `/ui/invariants` | Invariant records |
| GET `/ui/invariants/summary` | Invariant summary |

### Responder & Operator Workflows (`/api/v1/*` & Telemetry — Phase 2 Capability-Gated)

Phase 2 responder and operator workflows invoke capability-gated `/api/v1/*` endpoints and operational telemetry:

| Endpoint | Purpose |
|---|---|
| POST `/api/v1/notifications/{id}/ack` | Acknowledge pending notification |
| POST `/api/v1/notifications/{id}/dismiss` | Dismiss notification |
| POST `/api/v1/runtime/notifications/{id}/replay` | Replay dead-letter notification |
| DELETE `/api/v1/dlq/{entry_id}` | Purge / resolve dead-letter queue entry |
| POST `/api/v1/notifications/simulate` | Policy evaluation dry-run simulation |
| POST `/api/v1/notifications` | Tagged test notification send |
| POST `/api/v1/policies/reload` | Hot-reload policies from disk |
| GET `/readyz` | System readiness telemetry with degraded tolerance |
| GET `/api/v1/channels/health` | Channel health inspection |
| GET `/api/v1/dlq` | Dead-letter queue inspection |
| GET `/api/v1/runtime/dead-letters` | Runtime dead-letter recovery eligibility |

## Related Documentation

See [Operator Console Guide](../../docs/user-guides/OPERATOR-CONSOLE-GUIDE.md), [UI scope](../../docs/ui/ui-scope.md), [UI contracts](../../docs/ui/ui-data-contracts.md), [security](../../docs/SECURITY-MODEL.md), and [verification](../../docs/TESTING.md) for current evidence and limits.

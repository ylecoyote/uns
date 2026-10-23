# Deploy UNS

The selected [persistent localhost recording deployment](LOCAL_DEPLOYMENT.md) is running. The [earlier deployment smoke report](DEPLOYMENT_SMOKE.md) preserves container, socket and browser evidence.

This guide covers local and single-node production deployment of the Unified Notification Service (`uns`), including environment configuration, process topology, reverse-proxy/TLS setup, `uns-mcp` lifecycle, migrations, backups, and explicit database retention (`uns-maintain`).

## Supported local profile

The reproducible profile is Python 3.12, a file-backed SQLite database and recording adapters. Supported Python metadata starts at 3.11. PostgreSQL locking and real-provider acceptance remain separate checks. In-memory SQLite is suitable for demos and is rejected by write-enabled MCP CLI startup.

Install `.[full]` in an isolated environment. The server extra includes Uvicorn standard protocol dependencies, including network WebSocket support. The Dockerfile installs its exact built UNS wheel; the Compose readiness probe authenticates with its configured operator key. For a local service:

```sh
export UNS_DATABASE_URL='sqlite:///./uns.db'
.venv/bin/uns-migrate
export UNS_API_KEY='replace-with-your-local-test-key'
export UNS_API_PRINCIPAL='local-operator'
.venv/bin/uns
```

Use actual deployment secret provisioning rather than committing environment files. Back up an existing database before migration. Only `/health` and `/healthz` are public liveness; readiness and metrics require the operator credential. Shared hosting needs HTTPS/WSS and a trusted origin. Do not expose a development server publicly.

---

## Complete Environment Variable Reference

UNS reads `UNS_*` environment variables first and falls back to `AGSIGNAL_*` aliases for backward compatibility (`src/uns/config.py` and `src/agsignal/api/auth.py`).

### Core Runtime & HTTP Server

| Variable | Legacy Alias | Default | Required | Description |
| :--- | :--- | :--- | :--- | :--- |
| `UNS_DATABASE_URL` | `AGSIGNAL_DATABASE_URL`, `DATABASE_URL` | `sqlite://` (in-memory) | **Yes** (Production / MCP Writes) | SQLAlchemy database URL (e.g., `sqlite:////var/lib/uns/uns.db`). Must be a persistent file path for write-enabled `uns-mcp` and `uns-maintain`. |
| `UNS_API_KEY` | `AGSIGNAL_API_KEY` | *(None)* | **Yes** | Shared secret required for HTTP writes, reads (by default), `/readyz`, `/metrics`, and WebSocket establishment. If unset, protected endpoints return `503 write_auth_not_configured`. |
| `UNS_API_PRINCIPAL` | `AGSIGNAL_API_PRINCIPAL` | `agsignal-api-key` | **Yes** (MCP Writes) | Audited actor/principal identity bound to `UNS_API_KEY` and `uns-mcp --enable-writes`. |
| `UNS_HOST` | `AGSIGNAL_HOST` | `127.0.0.1` | No | Bind address for the `uns` HTTP/WebSocket server (`--host` CLI override). |
| `UNS_PORT` | `AGSIGNAL_PORT` | `8000` | No | TCP port for the `uns` HTTP/WebSocket server (`--port` CLI override). |
| `UNS_POLICY_DIR` | `AGSIGNAL_POLICY_DIR` | *(None)* | No | Directory of YAML policy definitions loaded and persisted into the durable `notification_policies` store at startup. |
| `UNS_CREATE_TABLES` | `AGSIGNAL_CREATE_TABLES` | `false` (`true` for `sqlite://`) | No | When `true`, runs additive table bootstrap on startup (`uns-migrate` is recommended instead in production). |
| `UNS_ALLOWED_ORIGINS` | `AGSIGNAL_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | No | Comma-separated list of allowed CORS and WebSocket `Origin` headers for the UNS Console. |
| `UNS_ALLOW_UNAUTHENTICATED_READS` | `AGSIGNAL_ALLOW_UNAUTHENTICATED_READS` | `false` | No | Compatibility flag (`true`/`1`/`yes`) permitting unauthenticated HTTP `GET`/`HEAD` on read routes only. Never enables writes, `/readyz`, `/metrics`, or WebSockets. |
| `AGSIGNAL_ENABLE_DOCS` | *(None)* | `false` | No | Enables interactive `/docs`, `/redoc`, and `/openapi.json` endpoints when set to `true`. Keep `false` in production. |

### MCP Process (`uns-mcp`)

| Variable | Legacy Alias | Default | Required | Description |
| :--- | :--- | :--- | :--- | :--- |
| `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` | `AGSIGNAL_MCP_DELIVERY_CONFIRMATION_TOKEN` | *(None)* | **Yes** (`--enable-writes`) | Secret token required by `send_signal` (`operator_confirmation_token`) when `deliver=true` in write-enabled MCP mode. |

### Channel Providers

Configure only intended providers/recipients:

- `UNS_SLACK_BOT_TOKEN`, `UNS_SLACK_CHANNEL`.
- `UNS_PAGERDUTY_ROUTING_KEY`.
- `UNS_SMTP_HOST`, `UNS_SMTP_PORT`, `UNS_SMTP_USER`, `UNS_SMTP_PASSWORD`, `UNS_EMAIL_FROM`, `UNS_EMAIL_TO`.

| Variable | Legacy Alias | Default | Description |
| :--- | :--- | :--- | :--- |
| `UNS_SLACK_BOT_TOKEN` | `AGSIGNAL_SLACK_BOT_TOKEN` | *(None)* | Slack Bot OAuth token (`xoxb-...`). Registers `SlackAdapter` when set. |
| `UNS_SLACK_CHANNEL` | `AGSIGNAL_SLACK_CHANNEL` | `""` | Default target Slack channel ID or name (e.g., `#ops-alerts`). |
| `UNS_PAGERDUTY_ROUTING_KEY` | `AGSIGNAL_PAGERDUTY_ROUTING_KEY` | *(None)* | PagerDuty Events API v2 integration/routing key. Registers `PagerDutyAdapter` when set. |
| `UNS_SMTP_HOST` | `AGSIGNAL_SMTP_HOST` | *(None)* | SMTP server hostname. Registers `EmailAdapter` when set. |
| `UNS_SMTP_PORT` | `AGSIGNAL_SMTP_PORT` | `587` | SMTP server port (integer). |
| `UNS_SMTP_USER` | `AGSIGNAL_SMTP_USER` | `""` | SMTP authentication username. |
| `UNS_SMTP_PASSWORD` | `AGSIGNAL_SMTP_PASSWORD` | `""` | SMTP authentication password. |
| `UNS_EMAIL_FROM` | `AGSIGNAL_EMAIL_FROM` | `""` | Sender email address for `EmailAdapter`. |
| `UNS_EMAIL_TO` | `AGSIGNAL_EMAIL_TO` | `""` | Comma-separated list of default recipient email addresses. |

Compatible AGSIGNAL-prefixed aliases remain. Missing adapters produce explicit failures. Canonical producer metadata cannot redirect adapter recipients or lower severity.

Use `UNS_POLICY_DIR` for an explicit startup YAML snapshot, or the authenticated policy reload endpoint. Successful activation advances the persisted snapshot revision. Every runtime resolves against that durable authority during intake, including cold MCP processes. Already accepted work retains its previous resolved snapshot.

---

## Process Topology & Concurrency Architecture

```mermaid
flowchart LR
    Proxy["Reverse Proxy (TLS / HTTPS / WSS)"] --> UNS["uns (FastAPI + Runtime.worker)"]
    Agent["MCP Host"] -->|stdio| MCP["uns-mcp --enable-writes"]
    Cron["Systemd Timer / Cron"] --> Maintain["uns-maintain --apply"]

    UNS --> DB[("SQLite DB (uns.db)")]
    MCP --> DB
    Maintain --> DB

    UNS --> Providers["Slack / PagerDuty / SMTP / WebSocket"]
    MCP --> Providers
```

1. **Unified HTTP Service (`uns`):**
   - Runs `uvicorn uns.app:app`.
   - On startup, FastAPI's `lifespan` starts `runtime.worker()`, which runs three concurrent 1-second loops in an `asyncio.TaskGroup`:
     - `dispatch_loop`: claims `PENDING` leader notifications (`lease_seconds = 60.0`) and dispatches to configured adapters.
     - `timeout_loop`: marks expired `ack_status = "PENDING"` rows (`deadline <= now`) as `TIMED_OUT`.
     - `callback_loop`: delivers pending terminal callbacks (`ACKED`, `DISMISSED`, `TIMED_OUT`) with exponential backoff up to 3 attempts.
2. **MCP process lifecycle (`uns-mcp`):**
   - `uns-mcp` defaults to read-only trusted-local stdio. To enable writes, configure a persistent database and the host environment:
     - `UNS_DATABASE_URL` (or supported legacy database setting).
     - `UNS_API_PRINCIPAL` for attribution.
     - `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` for explicit tool delivery confirmation.
   - After `uns-migrate`, launch `uns-mcp --enable-writes`. There are no secret command-line arguments. Send tools still require `deliver=true`, `operator_intent=deliver` and the matching confirmation token. The write-enabled MCP lifespan hydrates policies, starts its own recovery/expiry/callback worker, and cancels/joins it on shutdown. SIGTERM and SIGINT cleanup are exercised locally.
   - Do not run the previous accept-only MCP pattern without recovery and assume pending work will complete. Multiple workers coordinate individual jobs through database claims, not an exclusive process-wide file lock.
3. **Storage & File System Permissions:**
   - Place the SQLite database file on a local POSIX filesystem (never NFS/SMB) owned by the `uns` service user with mode `0600` (directory mode `0700`).
   - All processes sharing the SQLite database (`uns`, `uns-mcp`, `uns-maintain`) must run on the same host with read/write access to both the database file and its parent directory (for SQLite journal/WAL files).

---

## Console

From `apps/ui`, use `npm ci` then `npm run dev`. Node must satisfy `^20.19.0 || ^22.12.0 || >=24.0.0`. The development proxy forwards same-origin `/ui/*` to localhost:8000. For production, serve the SPA and route `/ui/*` to the backend on the same trusted origin.

Operators enter the API key at runtime. It lives in tab memory only; logout or reload removes it. Do not put keys in VITE variables, browser storage or URLs. The credential is an operator credential even though the console only makes reads. See [console instructions](../apps/ui/README.md) and the [Operator Console Guide](user-guides/OPERATOR-CONSOLE-GUIDE.md).

### Building the Console for Production

```sh
cd apps/ui
npm ci
npm run build
# Static assets are emitted to apps/ui/dist/
```

---

## Reverse Proxy & TLS Configuration (Nginx Example)

In production, terminate HTTPS/WSS at a reverse proxy, serve the built `apps/ui/dist` static bundle on the same origin, and proxy API, `/ui/*` data routes, probes, and `/ws/agents/*` to `127.0.0.1:8000`:

```nginx
server {
    listen 443 ssl http2;
    server_name uns.internal.example.com;

    ssl_certificate     /etc/ssl/certs/uns.crt;
    ssl_certificate_key /etc/ssl/private/uns.key;

    root /var/www/uns-console/dist;
    index index.html;

    # Backend API, Console JSON read-models, and health/metrics probes
    location ~ ^/(api|v1|ui|health|healthz|ready|readyz|metrics)(/|$) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Authenticated Agent WebSocket stream
    location /ws/agents/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header Origin $http_origin;
        proxy_read_timeout 3600s;
    }

    # SPA client-side routing fallback for Console views (/deliveries, /policy, /invariants, /audit)
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Process Supervision & Health Probes

### Systemd Service (`uns.service`)

```ini
[Unit]
Description=UNS Unified Notification Service
After=network.target

[Service]
Type=simple
User=uns
Group=uns
WorkingDirectory=/opt/uns
EnvironmentFile=/etc/uns/uns.env
ExecStartPre=/opt/uns/.venv/bin/uns-migrate
ExecStart=/opt/uns/.venv/bin/uns --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### Liveness vs. Readiness Probe Configuration

- **Liveness Probe (`GET /healthz`):** Public, unauthenticated. Checks that the ASGI event loop is responsive.
  ```sh
  curl -fsS http://127.0.0.1:8000/healthz
  ```
- **Readiness Probe (`GET /readyz`):** Authenticated. Verifies SQLite connectivity (`SELECT 1`), policy store hydration, DLQ depth, and read-model/audit configuration.
  ```sh
  curl -fsS -H "Authorization: Bearer $UNS_API_KEY" http://127.0.0.1:8000/readyz
  ```

---

## Migration and recovery

`uns-migrate` performs additive runtime schema migration, new policy-table bootstrap and scheduling-index creation. Repeated and concurrent startup migrations are tested with SQLite. Existing cumulative attempt counts and audit records remain; replay adds a new cycle rather than erasing history. Iteration 2 adds indexed successor links and normalizes old unattempted callback due times from zero to event time. Migration reconstructs recorded promotion links, including missing successor targets, from retained events. Missing targets and cyclic lineage block replay until an operator resolves/reissues the obligation; they are not treated as proof of non-delivery. Old tied replay/promotion clocks cannot erase handoff evidence. The one-time backfill scans retained work and promotion events; budget upgrade time for large stores and stop old writers before upgrading. Earlier erased promotion evidence cannot be reconstructed.

Old ownerless dedup claims cannot suppress new work. Previously suppressed historical records and policy fields already lost by old persistence cannot be reconstructed reliably. Preserve original source policies and use explicit operator reissue/replay when evidence cannot establish delivery.

Rollback requires the previous code and an appropriate database backup. An older runtime cannot safely process new pending owner/follower generations. Do not run old and new binaries against one active database during rollback.

### Online SQLite Backup & Restore

Before running `uns-migrate`, upgrading binaries, or executing bulk retention:

```sh
# Safe online backup using SQLite's backup API
sqlite3 /var/lib/uns/uns.db ".backup '/var/backups/uns/uns-$(date -u +%Y%m%dT%H%M%SZ).db'"
```

### Secret Rotation

To rotate `UNS_API_KEY` or `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN`:
1. Update the secret in your secret manager / `/etc/uns/uns.env`.
2. Restart `uns` and any write-enabled `uns-mcp` processes (`systemctl restart uns`).
3. Update downstream HTTP producers and re-enter the API key in active UNS Console browser tabs.

---

## Explicit retention

There is no automatic purge. `uns-maintain` defaults to dry-run and requires an operator-selected UTC-aware cutoff and minimum idempotency horizon:

```sh
.venv/bin/uns-maintain --database-url "$UNS_DATABASE_URL" \
  --cutoff "$UNS_RETENTION_CUTOFF" \
  --idempotency-seconds "$UNS_IDEMPOTENCY_SECONDS" \
  --batch-size 100
```

No universal retention duration is prescribed. Expiring a notification row also expires its idempotency key, allowing a later request with that key to create a new notification. Choose the horizon accordingly.

Apply requires `--apply --operator <actor>`. Without `--archive`, existing event/audit history stays in the database and a retained receipt preserves removed operational state. This is operational-table pruning, not database-size compaction.

Optional `--archive /absolute/new-file.json` exports an entire eligible settled group, creates a new file exclusively with mode0600, fsyncs the file and parent directory, verifies its SHA256, then prunes the corresponding rows in the same SQLite writer transaction. A no-content database receipt records archive path/hash, ids, counts and operator. Existing files and symlinks are not overwritten. Export or commit failure preserves database state but may leave an archive/partial file; inspect it and choose a new path before retrying.

Pending delivery, unsettled ACK, open dead letters, callback work, live leases, recent activity and retained dedup/follower/successor references are protected. Policy history and retention receipts are not pruned. The command supports SQLite only and requires the current schema.

A batch limits candidate/deletion rows, not bytes, SQL work or elapsed time. Oversized groups remain. Use `--after-id` with the returned `next_after_id` to advance past examined groups; applying a preview reuses that preview's INPUT cursor, not its returned continuation. A null continuation ends that scan pass. Start a new pass to revisit oversized/newly eligible or earlier-inserted records. Apply always recomputes safety; a cursor is not a snapshot or authorization.

Pruning makes pages reusable; no VACUUM or file-size reduction is claimed. Operators remain responsible for archive retention, storage capacity, backups and restore testing. Run maintenance with a suitable live-service impact budget.

---

## Related Documentation

- [Local Deployment Runbook](LOCAL_DEPLOYMENT.md)
- [Deployment Smoke Report](DEPLOYMENT_SMOKE.md)
- [API Reference](API.md)
- [Security Model](SECURITY-MODEL.md)
- [Support State Machine & Schema](support/STATE-MACHINE-AND-SCHEMA.md)
- [Troubleshooting Guides (TSGs)](tsg/README.md)
- [Operator Console Guide](user-guides/OPERATOR-CONSOLE-GUIDE.md)

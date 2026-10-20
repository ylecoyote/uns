> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Deploying AGSignal

This guide is for **operators self-hosting AGSignal as the governance signaling
control plane** for an autonomous-agent system. It documents the production
deployment recipe, hardening checklist, environment-variable reference, and
common runbook tasks.

> **Non-goals.** This guide does not cover the threat model
> (see [`SECURITY-MODEL.md`](SECURITY-MODEL.md)), vulnerability reporting
> (see [`SECURITY.md`](../SECURITY.md)), end-to-end agent system architecture
> (see your host application's docs), or Postgres/Redis operations
> (see the upstream documentation for each).
>
> AGSignal is **single-tenant per process**. Run separate processes for
> separate tenants. Multi-tenancy in a single process is not supported in v0.1.x.

---

## Architecture at a glance

AGSignal ships one HTTP application and one MCP server:

| Surface | Module | Purpose |
|---|---|---|
| **AGSignal HTTP** | `agsignal.app:app` | Unified Core (write) + Console (read) HTTP API. |
| **AGSignal MCP** | `agsignal_mcp.transports.stdio:main` | MCP stdio server for embedding inside an agent host. |

A typical deployment runs the **single FastAPI app as one process** behind
a reverse proxy that terminates TLS, plus a Postgres for durable state and a
Redis for idempotency / dedup / DLQ / WebSocket fanout. The MCP server runs as
a subprocess of the agent host (Claude Desktop, Cline, internal MCP runner).

```
                                 ┌──────────────────────────┐
        Browsers / SDK clients   │  Reverse proxy (TLS)     │
        ─────────────────────► │  e.g. nginx / Caddy      │
                                 └──────────┬───────────────┘
                                            │
                                ┌───────────▼──────────────┐
                                │ AGSignal HTTP            │
                                │ agsignal.app:app         │
                                │ (Core write + Console    │
                                │  read in one process)    │
                                └───────────┬──────────────┘
                                            │
                              ┌─────────────▼────────┐
                              │  Postgres + Redis    │
                              └──────────────────────┘

                    ┌──────────────────┐
   Agent host       │ AGSignal MCP     │   stdio JSON-RPC
   (Claude Desktop, ◄┤ stdio server    │
   Cline, etc.)     │ subprocess       │
                    └──────────────────┘
```

---

## Quick start (local-only smoke test)

### Option A: pip install

```bash
pip install 'agsignal[full]'   # server + redis + sql + mcp + adapters

# Fresh local DB (SQLite for testing only).
export DATABASE_URL='sqlite:///./agsignal-dev.db'
export AGSIGNAL_CREATE_TABLES=true   # FIRST RUN ONLY (see below)

# Auth: set a single API key and the principal that writes will be attributed to.
export AGSIGNAL_API_KEY='dev-only-key'
export AGSIGNAL_API_PRINCIPAL='dev-operator'

# Bind to loopback (default) for local testing.
uvicorn agsignal.app:app
```

In another terminal:

```bash
curl -H 'Authorization: Bearer dev-only-key' http://127.0.0.1:8000/healthz
```

After the first successful start, **unset `AGSIGNAL_CREATE_TABLES`** and never
set it again outside of a controlled bootstrap.

### Option B: docker compose

The repo ships a `Dockerfile` and `docker-compose.yml` that spin up Postgres,
Redis, and the unified AGSignal HTTP service with sane local-dev defaults. All
services bind to `127.0.0.1` on the host.

```bash
docker compose up --build      # first run: builds image, creates schema
docker compose up              # subsequent runs
```

Access:

```bash
curl -H 'Authorization: Bearer dev-only-key-rotate-before-real-use' \
     http://127.0.0.1:8000/healthz
```

After the first successful start, edit `docker-compose.yml` and flip
`AGSIGNAL_CREATE_TABLES` from `"true"` to `"false"`.

The compose file is **for local development only**. Production uses the same
Dockerfile but runs through your platform's orchestrator (k8s, ECS, Nomad,
etc.) with its own secrets, reverse proxy, and TLS termination.

---

## Production deployment recipe

The minimum production-grade deployment is:

1. **Postgres** (v14+) for `notification_audit_records`, `ack_audit_records`,
   `notification_policies`, `policy_learning`, `websocket_replay`.
2. **Redis** (v7+) for idempotency, deduplication, DLQ, rate limiting, and
   optional WebSocket fanout.
3. **One process** of `agsignal.app:app` (unified Core write + Console read API).
4. **A reverse proxy** (nginx, Caddy, Traefik, ALB, etc.) terminating TLS and
   forwarding to the AGSignal process on a private interface.

AGSignal does **not** terminate TLS itself.

### Environment template

> Legacy `UNS_*` env vars are honored as compatibility aliases for the
> `AGSIGNAL_*` variants. Each fallback emits a one-time `DeprecationWarning`
> per process. The `UNS_*` aliases will be removed in v1.0.

Save as `.env` and load in your process supervisor:

```bash
# --- Persistence ---
DATABASE_URL='postgresql+psycopg2://agsignal:STRONG_PW@db.internal:5432/agsignal'
AGSIGNAL_REDIS_URL='redis://redis.internal:6379/0'

# --- Auth (REQUIRED — without AGSIGNAL_API_KEY all writes return 503) ---
AGSIGNAL_API_KEY='generate-a-32-byte-random-string'
AGSIGNAL_API_PRINCIPAL='ops-rotation@example.com'
# Optional. If "true", clients may set their own acked_by / dismissed_by.
# Default false locks audit identity to the verified principal.
AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE=false

# --- Network ---
AGSIGNAL_HOST=127.0.0.1                # default; only the reverse proxy talks to AGSignal
AGSIGNAL_ALLOWED_ORIGINS='https://console.example.com'  # closed-list CORS

# --- Schema (DEFAULT FALSE — do not enable except on bootstrap) ---
AGSIGNAL_CREATE_TABLES=false

# --- Docs (DEFAULT FALSE — leaks API surface to anonymous callers) ---
# Leave unset in production. Set to "true" only on locked-down dev hosts.
# AGSIGNAL_ENABLE_DOCS=false

# --- Policy directory ---
AGSIGNAL_POLICY_DIR='/etc/agsignal/policies'

# --- WebSocket fanout (optional; required for multi-process Console scaling) ---
AGSIGNAL_WEBSOCKET_REDIS_ENABLED=true
AGSIGNAL_WEBSOCKET_REDIS_CHANNEL='agsignal:websocket'

# --- Channel adapters (set only the ones you use) ---
AGSIGNAL_SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...'
AGSIGNAL_PAGERDUTY_ROUTING_KEY='...'
AGSIGNAL_SMTP_HOST='smtp.example.com'
AGSIGNAL_SMTP_PORT=587
AGSIGNAL_SMTP_USER='agsignal@example.com'
AGSIGNAL_SMTP_PASSWORD='...'

# --- TTLs (defaults shown; tune to your retention SLO) ---
AGSIGNAL_DEDUP_TTL_SECONDS=300
AGSIGNAL_IDEMPOTENCY_TTL_SECONDS=86400
AGSIGNAL_DLQ_KEY='agsignal:dlq'
```

### Reverse-proxy snippet (nginx)

```nginx
# /etc/nginx/sites-enabled/agsignal.conf
upstream agsignal { server 127.0.0.1:8000; }

server {
    listen 443 ssl http2;
    server_name api.agsignal.example.com;

    ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    # Unified AGSignal HTTP (Core write + Console read + WebSockets).
    location / { proxy_pass http://agsignal; }
    location /ws/ { proxy_pass http://agsignal; proxy_http_version 1.1;
                    proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }

    # Block /docs, /redoc, /openapi.json explicitly even if AGSIGNAL_ENABLE_DOCS
    # was accidentally set on the upstream.
    location ~ ^/(docs|redoc|openapi\.json)$ { return 404; }
}
```

Run the unified AGSignal app on `:8000`, bound to `127.0.0.1` (the default).

### Rate limiting

Both apps install a process-wide default limit of `1000/minute` per principal
(or remote IP for unauthenticated callers). The limit string accepts slowapi
syntax — e.g. `100/minute`, `10/second`, `5000/hour`, or multiple comma-
separated limits applied as a chain.

| Caller | Key |
|---|---|
| Authenticated (Bearer token, `X-AGSignal-API-Key`, or legacy `X-UNS-API-Key`) | The verified API key |
| Unauthenticated | Remote IP |

Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset` headers. When the limit is exceeded, the API returns
`HTTP 429 Too Many Requests` with a `Retry-After` integer header (seconds).

For multi-process or multi-host deployments, point the limiter at Redis so
counters are shared:

```
AGSIGNAL_RATE_LIMIT_STORAGE_URI=redis://redis.internal:6379/1
```

(Use a different Redis DB number than the AGSIGNAL_REDIS_URL idempotency /
dedup data, or share — the limit keys are namespaced.)

The default limit is intentionally generous — its job is to detect runaway
behavior, not enforce per-route SLAs. For finer-grained limits per route,
layer rules at your reverse proxy:

```nginx
# Per-route limits at the proxy: stricter on writes than reads.
limit_req_zone $http_authorization zone=agsignal_writes:10m rate=10r/s;
location /api/v1/notifications/ {
    limit_req zone=agsignal_writes burst=20 nodelay;
    proxy_pass http://agsignal;
}
```

To disable AGSignal's built-in rate limiter (e.g. when the reverse proxy is
the sole authority):

```
AGSIGNAL_RATE_LIMIT_DEFAULT=""
```

### Audit retention

AGSignal does not auto-rotate audit data in v0.1. Two retention concerns:

1. **`transition_history` per policy delta** — capped to the most recent
   `AGSIGNAL_TRANSITION_HISTORY_LIMIT` entries (default 100). This is
   defense-in-depth for future state-machine evolution; in v0.1's strict
   forward-only lifecycle the cap is rarely hit. Set the env var to `0`
   to disable.

2. **`notification_audit_records` and `ack_audit_records` tables** — these
   are append-only audit logs. AGSignal never deletes from them. The operator
   is responsible for retention policy:

   ```sql
   -- Example monthly archival cron. Adjust window to your retention SLO.
   INSERT INTO notification_audit_archive
       SELECT * FROM notification_audit_records
       WHERE created_at < NOW() - INTERVAL '90 days';
   DELETE FROM notification_audit_records
       WHERE created_at < NOW() - INTERVAL '90 days';
   ```

   Operators with compliance constraints (SOX, SOC 2, regulatory) should
   archive to write-once storage rather than delete. Tamper-evident archival
   is roadmap; track [`SECURITY-MODEL.md`](SECURITY-MODEL.md) for the audit-
   chain feature.

Monitor the row counts of both tables and the transition_history JSON length
distribution. Alert when growth deviates from steady-state baseline.

### Prometheus metrics

Both apps expose a `/metrics` endpoint in the standard Prometheus exposition
format. Metric families:

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `agsignal_http_requests_total` | counter | `method`, `path_template`, `status_code` | Every request. `path_template` is the FastAPI route template (e.g. `/api/v1/notifications/{notification_id}/ack`), not the raw URL — avoids cardinality explosion on path parameters. |
| `agsignal_http_request_duration_seconds` | histogram | `method`, `path_template` | Latency from receive to response. Default buckets cover sub-millisecond to 10-second ranges. |
| `agsignal_signals_received_total` | counter | `intent`, `autonomy_mode`, `transport` | Counts each accepted signal. `transport` is `http` or `mcp`. |
| `agsignal_deliveries_total` | counter | `channel`, `status` | One increment per channel attempt. `status` is `succeeded` or `failed`. |

`/metrics` is **unauthenticated by design** (Prometheus scrapers do not present
credentials). Restrict it at the reverse proxy to your internal scrape network:

```nginx
# Inside the upstream block, allow only the scrape network.
location = /metrics {
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://agsignal;
}
```

Sample Prometheus scrape config (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: agsignal
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["agsignal.internal:8000"]
```

More metric families (DLQ depth, ack latency, policy reload rate) ship in
0.1.x as the corresponding code paths are instrumented.

### Liveness and readiness probes

The unified app exposes Kubernetes-convention endpoints alongside legacy paths.

| Endpoint | Purpose | Returns |
|---|---|---|
| `/healthz` | Liveness probe — process is up. | 200 with `{status: "alive", service, version}` |
| `/readyz` | Readiness probe — dependencies wired. | 200 with status + dependency info; surfaces errors if persistence is not configured |
| `/health` | Legacy alias for `/healthz`. | Same payload. |
| `/ready` | Legacy alias for `/readyz`. | Same payload. |

All four are unauthenticated by design (probes from a load balancer cannot
present credentials). Place them on the **internal** listener and do not
expose them through the public reverse proxy:

```nginx
# Inside the internal upstream, allowing kubelet / load-balancer health checks
location ~ ^/(healthz|readyz)$ {
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://agsignal;
}
```

---

## Configuration reference

All environment variables. `UNS_*` aliases work for one release; prefer the
`AGSIGNAL_*` form. **Bold** are required in production.

| Variable | Default | Notes |
|---|---|---|
| **`AGSIGNAL_API_KEY`** | unset | Required. Without it, all write endpoints return 503. Use a 32+ byte random string. |
| `AGSIGNAL_API_PRINCIPAL` | `agsignal-api-key` | The audit subject attributed to API-key writes. |
| `AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE` | `false` | If true, callers may set `acked_by`/`dismissed_by` to a different value. Leave false for hardest audit guarantees. |
| `AGSIGNAL_ALLOWED_ORIGINS` | `http://localhost:5173, http://127.0.0.1:5173` | Comma-separated CORS allowlist. |
| `AGSIGNAL_HOST` | `127.0.0.1` | Bind address for the standalone `agsignal.app` server. Override only behind a reverse proxy. |
| `DATABASE_URL` | unset | SQLAlchemy URL. Without it, in-memory storage (no durability). Postgres recommended. |
| `AGSIGNAL_CREATE_TABLES` | `false` | If `true`, creates DB schema on startup. **Bootstrap only.** Unset after first run. |
| `AGSIGNAL_ENABLE_DOCS` | `false` | If `true`, exposes `/docs`, `/redoc`, `/openapi.json`. **Leave off in production.** |
| `AGSIGNAL_POLICY_DIR` | unset | Directory of YAML policy files loaded at startup (ACTIVE-only). |
| `AGSIGNAL_REDIS_URL` | `redis://localhost:6379/0` | Redis for idempotency, dedup, DLQ, rate limiting. |
| `AGSIGNAL_DEDUP_TTL_SECONDS` | `300` | How long a dedup key is held. |
| `AGSIGNAL_IDEMPOTENCY_TTL_SECONDS` | `86400` | How long an idempotency record is held. |
| `AGSIGNAL_DLQ_KEY` | `uns:dlq` | Redis key for the DLQ list. Migrating from UNS? Keep this for replay. |
| `AGSIGNAL_WEBSOCKET_REDIS_ENABLED` | `false` | Enable Redis-backed WS fanout. Required if running multiple Console processes. |
| `AGSIGNAL_WEBSOCKET_REDIS_CHANNEL` | `agsignal:websocket` | Channel prefix. |
| `AGSIGNAL_SLACK_WEBHOOK_URL` | unset | Slack channel adapter. |
| `AGSIGNAL_PAGERDUTY_ROUTING_KEY` | unset | PagerDuty Events v2 routing key. |
| `AGSIGNAL_SMTP_HOST` / `PORT` / `USER` / `PASSWORD` | unset / 587 / unset / unset | Email channel adapter. |
| `AGSIGNAL_RATE_LIMIT_DEFAULT` | `1000/minute` | Default API-level rate limit per principal/IP. Applies to all routes (probe traffic at ~10 req/min is well below this). Set to an empty string to disable. |
| `AGSIGNAL_RATE_LIMIT_STORAGE_URI` | `memory://` | Rate-limit accounting backend. Use `redis://...` in multi-process deployments so counters are shared. |
| `AGSIGNAL_TRANSITION_HISTORY_LIMIT` | `100` | Cap on the per-policy-delta `transition_history` JSON list. Defense-in-depth against future evolution that allows ping-pong cycles. Set to `0` to disable. |

---

## First-run database bootstrap

AGSignal does not ship a migration runner in v0.1. Schema management is
operator-driven. The bootstrap recipe:

1. Create the database and user; grant CREATE/USAGE on the public schema.
2. Set `DATABASE_URL`, `AGSIGNAL_CREATE_TABLES=true`, and the rest of the env.
3. Start `agsignal.app` once, watch the log for `Configuring SQLAlchemy
   persistence`. Confirm the expected tables exist.
4. **Stop the process. Unset `AGSIGNAL_CREATE_TABLES`.** Restart for steady-state.
5. Take a backup of the empty schema.

For subsequent schema changes, write a forward-only SQL migration manually
against the version you are upgrading from. (Alembic integration is a roadmap
item; track upstream releases.)

---

## Hardening checklist

Run through this before flipping the API to a public surface.

- [ ] `AGSIGNAL_API_KEY` is set; without it writes return 503.
- [ ] Process binds to `127.0.0.1` (or a private interface) — never `0.0.0.0`
      directly facing the internet.
- [ ] Reverse proxy terminates TLS with a current certificate.
- [ ] Reverse proxy adds `X-Forwarded-For` / `X-Forwarded-Proto` headers your
      log aggregator can correlate.
- [ ] `AGSIGNAL_ENABLE_DOCS` is **not** set (or `false`). Reverse proxy also
      blocks `/docs`, `/redoc`, `/openapi.json` as defense in depth.
- [ ] `AGSIGNAL_ALLOWED_ORIGINS` lists only the Console UI's production origin.
- [ ] `AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE` is `false` unless you have a specific
      reason to allow caller-asserted audit identity.
- [ ] Database user has only the privileges AGSignal needs (no superuser).
- [ ] Redis is on a private network and password-protected (`requirepass`).
- [ ] Process supervisor (systemd, k8s, etc.) restarts AGSignal automatically.
- [ ] Logs are shipped to a tamper-evident store. AGSignal does not redact
      query parameters; rely on log aggregator filters until that ships.
- [ ] DLQ depth is monitored. Alert at any sustained growth.
- [ ] Audit table size is monitored. AGSignal does not auto-rotate
      `transition_history`; build a rotation job before the first 100K rows.
- [ ] API key rotation is documented for your team. AGSignal accepts only one
      key per process; rotate via supervised restart.
- [ ] gitleaks is enforced in CI on every PR (already shipped via the repo's
      gitleaks config + pre-commit setup).

---

## MCP transport deployment

The MCP server (`agsignal_mcp.transports.stdio:main`) is invoked by the agent
host (Claude Desktop, Cline, internal runner) as a subprocess. It is not a
network service.

Install on the host:

```bash
pip install 'agsignal[mcp]'
```

Default runtime config: **`read_only=True`**, `require_delivery_confirmation=True`,
`operator_principal=None`, `delivery_confirmation_token=None`. In this state,
all write tools refuse and only read tools are exposed.

To enable writes, configure the runtime explicitly:

```python
from agsignal_mcp import MCPRuntimeConfig, create_mcp_server

config = MCPRuntimeConfig(
    read_only=False,
    require_delivery_confirmation=True,
    operator_principal="ops-rotation@example.com",
    delivery_confirmation_token="...32-byte-random-...",
)
server = create_mcp_server(config)
```

The `delivery_confirmation_token` must come from a different principal than
the LLM agent — it gates the two-key send-signal flow. Do not expose this
token to the LLM context.

---

## Operator runbook

### Reload policies without restart

```bash
curl -X POST -H 'Authorization: Bearer $AGSIGNAL_API_KEY' \
     https://api.example.com/api/v1/policies/reload
```

Reloads from `AGSIGNAL_POLICY_DIR`. Only `status: ACTIVE` policies are honored;
non-ACTIVE policies are filtered at load.

### Inspect the DLQ

```bash
curl -H 'Authorization: Bearer $AGSIGNAL_API_KEY' \
     https://api.example.com/api/v1/dlq
```

DLQ entries land here when GUARANTEED-priority deliveries fail after retries.
Expect depth = 0 in steady state.

### Replay from the DLQ

There is **no automatic replay path in v0.1**. Replay is a manual operator
action: read the DLQ entries, reconstruct the original notification, and POST
it back through `/api/v1/notifications`. Track this as a deliberate policy
choice — automated retry across the DLQ boundary risks duplicate side effects.

### Rotate the API key

1. Stage the new key alongside the old by deploying a second process with the
   new key (separate DNS/port).
2. Migrate clients to the new key.
3. Decommission the old process.

(Single-process key rotation is roadmap.)

### Confirm CORS, auth, and docs are gated

```bash
# CORS denial
curl -i -H 'Origin: https://attacker.example' \
     -H 'Access-Control-Request-Method: POST' \
     -X OPTIONS https://api.example.com/api/v1/notifications/some-id/ack
# expect 400 (CORS rejected)

# Auth required
curl -i -X POST https://api.example.com/api/v1/notifications/some-id/ack
# expect 401

# Docs gated
curl -i https://api.example.com/openapi.json
# expect 404
```

---

## What this guide does not cover

- **Threat model.** See [`SECURITY-MODEL.md`](SECURITY-MODEL.md). Vulnerability
  reporting policy is in [`SECURITY.md`](../SECURITY.md).
- **Backup and restore.** Operator's database choice; standard Postgres
  procedures apply. Take backups before any `AGSIGNAL_CREATE_TABLES=true` run.
- **Monitoring SaaS integration.** `/metrics` Prometheus endpoint is roadmap.
  Until then, scrape AGSignal's structured logs for the relevant counters.
- **Multi-tenant isolation.** Out of scope for v0.1.x. Run separate processes.
- **High availability.** AGSignal Core can run multiple instances behind the
  reverse proxy if Redis-backed WebSocket fanout is enabled and the database
  is shared. Consult your platform team for the rest.
- **Migration tooling.** No alembic in v0.1. Forward-only SQL migrations are
  the operator's responsibility for now.

For questions, open a GitHub issue. For security-sensitive matters, use
GitHub private vulnerability reporting per [`SECURITY.md`](../SECURITY.md);
do **not** open a public issue.

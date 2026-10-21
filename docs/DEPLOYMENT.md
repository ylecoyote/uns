# Deploy UNS

See the [deployment candidate smoke report](DEPLOYMENT_SMOKE.md) for the latest container, socket/browser checks, and remaining target selection.

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

## Console

From `apps/ui`, use `npm ci` then `npm run dev`. Node must satisfy `^20.19.0 || ^22.12.0 || >=24.0.0`. The development proxy forwards same-origin `/ui/*` to localhost:8000. For production, serve the SPA and route `/ui/*` to the backend on the same trusted origin.

Operators enter the API key at runtime. It lives in tab memory only; logout or reload removes it. Do not put keys in VITE variables, browser storage or URLs. The credential is an operator credential even though the console only makes reads. See [console instructions](../apps/ui/README.md).

## MCP process lifecycle

`uns-mcp` defaults to read-only trusted-local stdio. To enable writes, configure a persistent database and the host environment:

- `UNS_DATABASE_URL` (or supported legacy database setting).
- `UNS_API_PRINCIPAL` for attribution.
- `UNS_MCP_DELIVERY_CONFIRMATION_TOKEN` for explicit tool delivery confirmation.

After `uns-migrate`, launch `uns-mcp --enable-writes`. There are no secret command-line arguments. Send tools still require `deliver=true`, `operator_intent=deliver` and the matching confirmation token. The write-enabled MCP lifespan hydrates policies, starts its own recovery/expiry/callback worker, and cancels/joins it on shutdown. SIGTERM and SIGINT cleanup are exercised locally.

Do not run the previous accept-only MCP pattern without recovery and assume pending work will complete. Multiple workers coordinate individual jobs through database claims, not an exclusive process-wide file lock.

## Channels and policies

Configure only intended providers/recipients:

- `UNS_SLACK_BOT_TOKEN`, `UNS_SLACK_CHANNEL`.
- `UNS_PAGERDUTY_ROUTING_KEY`.
- `UNS_SMTP_HOST`, `UNS_SMTP_PORT`, `UNS_SMTP_USER`, `UNS_SMTP_PASSWORD`, `UNS_EMAIL_FROM`, `UNS_EMAIL_TO`.

Compatible AGSIGNAL-prefixed aliases remain. Missing adapters produce explicit failures. Canonical producer metadata cannot redirect adapter recipients or lower severity.

Use `UNS_POLICY_DIR` for an explicit startup YAML snapshot, or the authenticated policy reload endpoint. Successful activation advances the persisted snapshot revision. Every runtime resolves against that durable authority during intake, including cold MCP processes. Already accepted work retains its previous resolved snapshot.

## Migration and recovery

`uns-migrate` performs additive runtime schema migration, new policy-table bootstrap and scheduling-index creation. Repeated and concurrent startup migrations are tested with SQLite. Existing cumulative attempt counts and audit records remain; replay adds a new cycle rather than erasing history. Iteration 2 adds indexed successor links and normalizes old unattempted callback due times from zero to event time. Migration reconstructs recorded promotion links, including missing successor targets, from retained events. Missing targets and cyclic lineage block replay until an operator resolves/reissues the obligation; they are not treated as proof of non-delivery. Old tied replay/promotion clocks cannot erase handoff evidence. The one-time backfill scans retained work and promotion events; budget upgrade time for large stores and stop old writers before upgrading. Earlier erased promotion evidence cannot be reconstructed.

Old ownerless dedup claims cannot suppress new work. Previously suppressed historical records and policy fields already lost by old persistence cannot be reconstructed reliably. Preserve original source policies and use explicit operator reissue/replay when evidence cannot establish delivery.

Rollback requires the previous code and an appropriate database backup. An older runtime cannot safely process new pending owner/follower generations. Do not run old and new binaries against one active database during rollback.

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

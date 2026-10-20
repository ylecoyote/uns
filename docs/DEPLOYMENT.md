# Deploy UNS

## Local recording demo

Run the README quickstart. No external messages are sent. SQLite file storage proves local restart behavior; an in-memory `sqlite://` runtime is demo-only and loses state on exit.

## Durable service

Use an isolated environment and install `.[full]`. For a local file-backed service:

```sh
export UNS_DATABASE_URL='sqlite:///./uns.db'
.venv/bin/uns-migrate
export UNS_API_KEY='replace-with-your-local-test-key'
export UNS_API_PRINCIPAL='local-operator'
.venv/bin/uns
```

Bind behind an authenticated reverse proxy for shared access. HTTPS termination, secret provisioning, database backups and restore are deployment responsibilities. SQLite is the locally tested profile. A PostgreSQL URL requires its driver and separate database-specific acceptance; no new driver is bundled by this consolidation.

The HTTP lifespan processes dispatch recovery and timeouts every second. The default claim lease is 60 seconds, longer than the maximum four sequential 10-second adapter waits. Do not reduce the lease below the adapter time budget. Monitor errors and queue age, not only process liveness. MCP-only deployments run a recovery process against the same database.

## Channel configuration

UNS uses the existing adapters. Configure only the recipients and providers you intend to exercise:

- `UNS_SLACK_BOT_TOKEN`, `UNS_SLACK_CHANNEL`.
- `UNS_PAGERDUTY_ROUTING_KEY`.
- `UNS_SMTP_HOST`, `UNS_SMTP_PORT`, `UNS_SMTP_USER`, `UNS_SMTP_PASSWORD`, `UNS_EMAIL_FROM`, `UNS_EMAIL_TO` (comma-separated).

Legacy AGSIGNAL-prefixed equivalents remain accepted. The runtime does not treat the older Slack webhook setting as a bot-token adapter configuration. Missing adapters produce explicit delivery failure, not simulated success.

`UNS_POLICY_DIR` selects notification YAML. Historical `AGSIGNAL_POLICY_DIR` also works. The current code's compatibility modules retain older configuration names; see API and migration documentation for the canonical boundaries.

## Migrations and recovery

`uns-migrate` creates missing tables from the unified metadata, including additive UNS outbox/event/dedup and policy-evidence tables. It does not delete or transform prior audit/policy rows. Back up existing databases first. The legacy SQL files in `src/db/migrations` record predecessor schema history; the UNS command is the current additive bootstrap entry point.

Rollback restores the previous code and its database backup. Do not run an older runtime against pending UNS work and expect it to process that work. Existing audit data remains readable, while new UNS state requires the new runtime.

Notification/idempotency/event retention is operator controlled. No automatic purge is enabled. A safe retention task must retain unresolved work and acknowledgment deadlines, and document the idempotency horizon it removes.

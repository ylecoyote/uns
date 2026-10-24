# Persistent localhost recording deployment

The user selected localhost with recording adapters. The service is deployed at **http://127.0.0.1:18080** and remains available while Docker Desktop is running. This resolves the target/provider questions in the earlier rehearsal report.

## Sign in

Paste the contents of `$HOME/Library/Application Support/UNS/operator-api-key.txt` into the console's API key field. The file is mode 0600 inside a private configuration directory. The key stays in browser-tab memory; reload or sign-out clears it. Credential values are not in the repository, vault, receipts or URLs.

The visible banner says **Local recording mode**. Slack, email and PagerDuty channels write durable local receipts instead of contacting providers. WebSockets are available to authenticated local clients. DELIVERED in this profile means recording-sink acceptance, not an external message or human receipt. Notification details are in SQLite; lightweight channel receipts and response callbacks are in the same persistent data volume.

## Installed components

- Application image: `uns:8156cb6`, pinned by image ID `sha256:1cf4d7cf73aaafcd484dd1c42657dc3ea5bc602c792a7d8ff4908f02a00823e6`. Core code is `8156cb6b6b699e37f01ba8b729f6be3c4935e100`.
- Recording composition: `deploy/local/recording_runtime.py`, `local_app.py`, and `local_mcp.py`, deployed as a read-only release snapshot under `$HOME/Library/Application Support/UNS/releases/8156cb6`.
- Fixed reverse proxy: `deploy/local/nginx.conf` from `9fd53d8`, with the Nginx image pinned by digest in the installed Compose configuration.
- Configuration and immutable profile/console snapshot: `$HOME/Library/Application Support/UNS/`. Active release is recorded in `active-release.txt`; active deployment is `compose.json`.
- Database, local channel receipts and response receipts: Docker volume `uns-local-data`. Source-checkout changes do not mutate the running release.

Containers `uns-local` and `uns-local-ingress` use `unless-stopped` restart policies. They restart with Docker after an engine restart unless deliberately stopped. Docker Desktop startup on Mac login and OS-reboot behavior were not changed or separately tested.

The application stays exclusively on an internal Docker network, has no default route, and exposes no host port. The fixed ingress proxy publishes only `127.0.0.1:18080` and forwards only to UNS; it has no service credential or arbitrary forward/CONNECT behavior. This preserves application isolation while working around Docker Desktop's inability to publish the application port directly from the internal network. Both containers run as non-root with read-only root filesystems. Local administrators controlling Docker remain trusted.

## Operate

```sh
docker compose -f "$HOME/Library/Application Support/UNS/compose.json" ps
docker compose -f "$HOME/Library/Application Support/UNS/compose.json" logs --tail 100
docker compose -f "$HOME/Library/Application Support/UNS/compose.json" stop
docker compose -f "$HOME/Library/Application Support/UNS/compose.json" up -d --pull never
```

Stopping/recreating these containers retains the external data volume. For an application release replacement, back up the database, prepare a new immutable profile/console release, and recreate both services so the fixed proxy resolves the current backend. The running release is pinned; rebuilding a mutable tag alone does not update it.

Read-only local MCP can be started with `docker exec -i uns-local python /profile/local_mcp.py`. Explicit writes use `--enable-writes` and still require the MCP delivery-confirmation token kept in the private service environment. Do not place tokens in command-line arguments or URLs.

## Backup and verification

An initial consistent SQLite backup was created through SQLite's backup API and passed `PRAGMA quick_check`. It is under `$HOME/Library/Application Support/UNS/backups/`, mode 0600; its filename and SHA-256 are in the deployment receipt. This is an initial recovery copy, not an automatic backup/retention schedule. Restore into a stopped service with a compatible code/profile release and preserve the existing volume until the restored copy is verified.

**62 checks passed against this persistent deployment**, including protected/public endpoints, visible recording banners, simulation, recorded Slack/email/PagerDuty acceptance, idempotency/dedup/conflicts, actor-bound ACK/dismiss, UTC audit projection, actual proxied WebSockets, read-only and write-enabled MCP, cross-transport idempotency, a real one-minute timeout, durable local callbacks, persisted pending-work recovery and ACK survival after an application restart. The final demo notification was acknowledged after the run. The earlier isolated full rehearsal passed 99 checks against the same application image, including fault injection, retries and copied-data retention.

`deploy/local/smoke.py` is the executed persistent-profile verifier. It creates labeled demo notifications and policies and briefly restarts only its local UNS container. Run it only when that interruption is acceptable. The rehearsal's deliberately failing adapters/callbacks are not installed in this persistent profile.

See [deployment receipts](../verification/local-deployment/results.json), [earlier rehearsal](DEPLOYMENT_SMOKE.md), and [testing](TESTING.md). Real-provider delivery, public hosting/TLS, live PostgreSQL and representative load remain unverified and are outside the selected deployment scope.

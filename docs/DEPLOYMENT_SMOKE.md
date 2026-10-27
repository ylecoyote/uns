# Deployment candidate and local smoke

Tested code: `07ef52a87b45128b77715f64c8b0e5f8f91387a9`. Base: `ca43bea`. Image: `uns:07ef52a`, image ID `sha256:15544fa7893287e391331f46b069e4dba0c38a158594405b4bcd7f41a0bd8e0d`. Application code and dependency changes were built into the image; all 90 installed modules matched source.

The user subsequently accepted localhost plus recording adapters. See [the completed persistent deployment](LOCAL_DEPLOYMENT.md) for the current service and runbook. The receipt below preserves the earlier rehearsal scope.

## Deployment status at the rehearsal checkpoint

The request did not identify a target server or designated real recipients. Target/provider questions were presented and remained unanswered during this run. Therefore only an isolated localhost recording-profile rehearsal was performed. No production service, real database, external recipient, registry or remote host was modified. A lasting deployment still requires the target selection.

The rehearsal binds only `127.0.0.1:18080`, serves the existing production SPA assets, runs the installed image's HTTP and WebSocket implementation, and launches its MCP server over real stdio. A trusted smoke composition registers a local recording Slack adapter and intentionally fails selected synthetic sends/callbacks. This composition is test code, not a real-provider deployment mode. Its settings, database and credentials are outside the repository; credential values and database payloads are excluded from receipts.

## Findings repaired

- The Dockerfile installed `uns[full]` after the distribution had been renamed. It now installs the exact wheel produced by its builder, preventing accidental resolution of a different registry package.
- Compose readiness lacked authentication and did not assert the returned status. Its authenticated probe now passes against the running service.
- The clean server image had neither supported WebSocket protocol implementation. The server extra now uses `uvicorn[standard]`; real network upgrades, fanout and durable ACK pass.
- Browser inspection exposed placeholder PREVIEW/zero-agent ACK audit context and naive SQLite timestamps. The read adapters now recover available notification context, apply the corresponding ACK filters, and return explicit UTC timestamps. The invariant summary timestamp also carries UTC. Historical orphan ACKs retain compatibility placeholders and an explicit `context_unavailable` payload flag.

## Checked behavior

**99 live checks passed**: public liveness, protected readiness/metrics/read endpoints, wrong-key rejection, SPA route serving, no-effect simulation, policy and routing-override rejection, recorded GUARANTEED delivery, idempotency/conflict, semantic dedup, actor-bound ACK/dismiss/replay conflicts, worker retries and dead letters, explicit replay recovery, audit evidence, real WebSocket delivery/ACK/authentication, MCP registry/read/simulation/send/ACK, HTTP/MCP idempotency, policy activation observed by an already-running MCP process, retained acceptance policy, a real one-minute timeout, callback retry identity, and pending-work/ACK persistence across an actual service restart.

A separate retention check copied the synthetic SQLite database, verified a non-writing preview, archived and pruned 95 rows only on that copy, verified archive SHA-256, and confirmed the live notification count was unchanged. This does not choose or apply a production retention policy.

Browser checks in Brave observed sign-in, invalid-key denial, deliveries, audit context/local dates, activated policy inspection, invariants, logout and reload clearing the credential. Full Python verification passed **1,776 tests at 90.76% coverage**, including 11 new projection regressions. Ruff, mypy (91 files), Bandit and Compose validation passed. Framework/annotation warnings remain in logs. Frontend source/assets were unchanged; the previous 305-test console result is retained, with live browser checks added here.

## Reproduction and handoff

[Machine receipts](../verification/deployment/results.json) include source/image identities, raw outputs, the exact live smoke driver and recording profile. The original regression output establishes nine failing projection cases before repair; the additional summary-clock case also failed before repair.

`verification/deployment/live_smoke.py` is the exact executed rehearsal driver, using `/private/tmp/uns-live-smoke`, localhost port 18080 and the named test container. Run it only with that isolated recording profile and a fresh synthetic store. It intentionally restarts its own container, toggles recorder failure and activates a smoke policy. It must not be pointed at a production database or provider configuration. The retention helper refuses to overwrite an existing backup and uses a synthetic future cutoff only on the copy.

Build the candidate using `docker build --label org.opencontainers.image.revision=$(git rev-parse HEAD) -t uns:local-smoke .`. For the selected lasting target, provision destination-specific secrets, intended provider recipients, an appropriate database and the console's same-origin host. Back up existing data before migration. Real-provider delivery, human receipt, PostgreSQL, representative load and public TLS hosting remain separate acceptance steps.

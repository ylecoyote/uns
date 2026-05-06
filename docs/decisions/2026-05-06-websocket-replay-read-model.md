# WebSocket Replay Read Model

Date: 2026-05-06

Status: Accepted

Linear: MIP-243, MIP-245

## Context

AGSignal WebSocket clients can reconnect and send a `last_seen` cursor. The
original MIP donor docs described pending-notification replay, while the donor
implementation returned an explicit empty list because it did not have a
durable WebSocket payload read model.

The existing AGSignal audit rows are not sufficient replay payloads by
themselves. They preserve delivery outcome, title, source, and attribution, but
they do not retain the exact WebSocket notification body or reconnect cursor
shape. Reconstructing replay from audit rows would risk sending partial or
different payloads from live delivery.

## Decision

AGSignal records the exact WebSocket payload accepted by
`POST /api/v1/notifications` into a replay read model before live local delivery
and optional Redis fanout:

- Each replay payload includes `replay_cursor`.
- Live WebSocket and Redis fanout payloads also include the same
  `replay_cursor` so clients can persist the latest processed cursor.
- `subscribe` with a missing or invalid `last_seen` returns no history.
- `subscribe` with a valid prior cursor returns only newer payloads for that
  agent.
- The default standalone app uses `InMemoryWebSocketReplayStore` for local
  operation and tests.
- Durable deployments can inject `SQLAlchemyWebSocketReplayStore`, which
  persists payloads in `websocket_replay_records`.

Redis pub/sub remains live fanout only. It is not used as a replay log.

## Implementation Notes

- Replay records are scoped by `agent_id`.
- The persisted payload is the WebSocket payload, not a reconstructed audit
  projection.
- The cursor is timestamp-shaped and UTC-normalized.
- The SQLAlchemy store follows the existing audit/policy store pattern:
  caller-provided `sessionmaker`, explicit commit/rollback, and optional
  `Base.metadata.create_all()` factory.
- Redis subscriber tasks retry transient subscription failures with bounded
  backoff and remain cancellable when the last local connection disconnects.

## Verification

Unit and smoke coverage:

- `tests/notification/test_websocket_runtime.py` covers in-memory replay,
  WebSocket subscribe replay, Redis origin suppression, and Redis subscriber
  reconnect after transient subscription failure.
- `tests/notification/test_standalone_http_app.py` verifies the HTTP route
  records replay payloads.
- `tests/db/test_websocket_replay_store.py` verifies SQLAlchemy persistence and
  agent scoping with SQLite.
- `scripts/smoke_websocket_replay.py` verifies the reconnect replay flow.
- `scripts/smoke_websocket_redis_fanout.py` verifies real Redis live fanout
  across two in-process app instances.

## Consequences

- Reconnect replay has a dedicated read model rather than borrowing audit
  storage or Redis pub/sub.
- Single-process local operation still has no database requirement.
- Durable replay requires injecting the SQLAlchemy store during app creation.
- Clients must retain the latest `replay_cursor` they have processed to avoid
  duplicate replay on reconnect.

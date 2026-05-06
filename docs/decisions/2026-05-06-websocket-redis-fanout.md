# WebSocket Redis Fanout

Date: 2026-05-06

Status: Accepted

Linear: MIP-245

## Context

AGSignal needs live WebSocket delivery for connected agent clients and optional
cross-process fanout when more than one AGSignal process is serving WebSocket
connections. Redis is already used by the notification package for runtime
coordination, but Redis must not become a required dependency for local
single-process WebSocket delivery.

The original MIP implementation influenced this design:

- `src/notification/adapters/websocket.py` published notifications to
  per-agent Redis channels named from a WebSocket channel prefix plus
  `agent:{agent_id}`.
- `src/notification/websocket_handler.py` started a Redis subscription when an
  agent WebSocket client connected and stopped it when the last connection for
  that agent disconnected.
- Missed notification replay was documented in the WebSocket protocol, but the
  implementation explicitly returned an empty list because there was no durable
  notification persistence table.
- The MIP subscriber used synchronous Redis `pubsub.listen()` inside an asyncio
  task. That shape is not copied because it can block the event loop.

The AGSignal extraction had already added direct local WebSocket delivery and a
Redis publisher. That differs from MIP: MIP delivered through Redis, while
AGSignal now sends locally first and publishes for other processes.

## Decision

AGSignal WebSocket Redis fanout uses per-agent Redis channels and origin
suppression:

- Local delivery remains available without Redis.
- When Redis fanout is enabled, AGSignal publishes each WebSocket envelope to
  `{UNS_WEBSOCKET_REDIS_CHANNEL}:agent:{agent_id}`.
- Each AGSignal process has a generated `origin_id`.
- The publisher stamps outgoing Redis envelopes with its `origin_id`.
- The subscriber ignores envelopes whose `origin_id` matches the current
  process, preventing same-instance duplicate delivery.
- Subscribers are started per agent when a local WebSocket client connects and
  stopped when the last local connection for that agent disconnects.
- Redis subscription polling uses bounded `get_message(..., timeout=0.5)` calls
  through `asyncio.to_thread()` rather than a blocking `listen()` loop.
- Redis subscription tasks retry transient subscription failures with bounded
  backoff until the local agent subscription is cancelled.
- Durable missed replay remains out of scope for Redis pub/sub and is owned by
  a separate WebSocket replay read model.

## Alternatives Considered

### Copy MIP Exactly

This would publish to Redis and rely on per-agent subscription tasks for all
delivery. It matches the donor architecture but would make local WebSocket
delivery dependent on Redis whenever the WebSocket path is used. It would also
carry forward the blocking `pubsub.listen()` loop.

### App-Wide Fanout Channel

One global channel is simpler to configure, but every process would receive
every WebSocket notification and filter locally. That is unnecessary load and
does not match the donor implementation's per-agent routing.

### Direct Local Delivery Plus Per-Agent Redis Fanout

This is the accepted design. It preserves local operation, follows the useful
part of MIP's per-agent Redis channel model, and adds origin suppression to
avoid duplicate delivery caused by AGSignal's direct local send path.

## Consequences

- Redis remains an optional runtime adapter, not an AGSignal core domain
  dependency.
- Single-process deployments continue to deliver WebSocket notifications without
  Redis.
- Multi-process deployments can fan out live WebSocket events across instances.
- Redis pub/sub is still best-effort live delivery. It does not provide durable
  replay, ordering guarantees across reconnects, or historical recovery.
- Transient Redis subscription failures do not permanently drop an active
  local agent subscription task.
- Tests can validate message parsing, origin suppression, local forwarding, and
  app wiring without requiring a real Redis server.

See [WebSocket Replay Read Model](2026-05-06-websocket-replay-read-model.md)
for the reconnect replay decision.

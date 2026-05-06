# WebSocket Redis Fanout Smoke

This smoke verifies AGSignal's optional Redis-backed WebSocket fanout with a
real Redis server and two AGSignal app instances.

## What It Proves

The smoke starts two in-process AGSignal FastAPI apps with Redis fanout enabled:

1. A consumer app accepts a WebSocket connection for one agent.
2. A producer app accepts `POST /api/v1/notifications` for that same agent.
3. The producer publishes the WebSocket envelope to Redis.
4. The consumer subscriber receives the Redis message and forwards it to the
   connected WebSocket client.
5. The script asserts that the WebSocket event's `notification_id` matches the
   HTTP response from the producer app.

The smoke also checks that the two app instances have different generated
fanout origin IDs. Origin IDs are required because AGSignal sends locally first
and publishes Redis only for other processes.

## What It Does Not Prove

- It does not validate durable missed replay. Redis pub/sub is live fanout only.
  Use [WebSocket Replay Smoke](websocket-replay-smoke.md) for reconnect replay.
- It does not run separate OS processes. The two app instances are independent
  FastAPI app objects in one Python process, sharing only Redis.
- It does not run for hours. Transient Redis subscription reconnect behavior is
  covered by unit tests.

## Prerequisites

A Redis server must be reachable. The default URL is:

```bash
redis://localhost:6379/0
```

Check Redis:

```bash
redis-cli ping
```

Expected output:

```text
PONG
```

## Command

Run the smoke from the repository root:

```bash
python scripts/smoke_websocket_redis_fanout.py
```

Use a custom Redis URL if needed:

```bash
python scripts/smoke_websocket_redis_fanout.py --redis-url redis://localhost:6379/0
```

The script uses a unique Redis channel prefix by default. To make a run easier
to inspect manually, pass an explicit prefix:

```bash
python scripts/smoke_websocket_redis_fanout.py \
  --channel-prefix agsignal:smoke:websocket:manual
```

## Expected Output

```text
AGSignal WebSocket Redis fanout smoke passed
agent_id: ...
notification_id: ...
channel_prefix: ...
consumer_origin: ...
producer_origin: ...
websocket_event_type: notification
```

## Failure Interpretation

- Redis connection failure: Redis is unavailable or `--redis-url` is wrong.
- WebSocket timeout: the consumer subscriber did not receive or forward the
  producer's Redis message.
- Notification ID mismatch: the WebSocket event did not correspond to the
  producer's accepted notification.

## Related Decision

See [WebSocket Redis Fanout](../decisions/2026-05-06-websocket-redis-fanout.md)
for the implementation decision, donor MIP comparison, and rejected
alternatives.

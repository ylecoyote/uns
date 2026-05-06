# WebSocket Replay Smoke

This smoke verifies AGSignal's reconnect replay contract for standalone
WebSocket clients.

## What It Proves

The smoke starts one in-process AGSignal FastAPI app:

1. It posts `POST /api/v1/notifications` for an agent while no WebSocket client
   is connected.
2. The HTTP route records the exact WebSocket payload in the replay read model.
3. A WebSocket client connects for the same agent.
4. The client sends `{"type": "subscribe", "last_seen": "<cursor>"}` with an
   older cursor.
5. The script asserts that the subscribe response contains one missed
   notification with the accepted `notification_id` and a `replay_cursor`.

## What It Does Not Prove

- It does not require Redis. Redis pub/sub remains live fanout only.
- It uses the default process-local replay store. SQLAlchemy-backed replay is
  covered by SQLite tests.
- It does not validate browser UI rendering of replayed notifications.

## Command

Run the smoke from the repository root:

```bash
python scripts/smoke_websocket_replay.py
```

## Expected Output

```text
AGSignal WebSocket replay smoke passed
agent_id: ...
notification_id: ...
replay_available: True
replay_cursor: ...
```

## Failure Interpretation

- Missing replay payload: the HTTP route did not record the WebSocket read model
  payload before the client subscribed.
- Notification ID mismatch: the replayed event did not correspond to the
  accepted notification.
- Missing replay cursor: clients cannot advance their reconnect cursor safely.

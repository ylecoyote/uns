# App Adapter Proving Smoke

This smoke verifies AGSignal's generic host-application adapter boundary.

## What It Proves

The smoke uses AGSignal public imports:

- `agsignal.sdk.SignalClient`
- `agsignal.models.SignalIntent`
- `agsignal.integrations.AppSignalAdapter`
- `agsignal.integrations.AppEvidenceContext`

It runs one host-app style safety event through the generic app adapter boundary
and verifies:

1. The event emits an AGSignal signal through the SDK path.
2. App-owned evidence IDs are carried into `AutonomyContext`.
3. The same evidence IDs are copied into notification metadata under
   `app_evidence`.
4. Required acknowledgment state is registered as `PENDING`.
5. Delivery and acknowledgment audit records are written.

## What It Does Not Prove

- It does not implement a real host application, governor, circuit breaker, or
  execution engine.
- It does not import MIP or any MIP domain model.
- It does not send Slack, PagerDuty, email, or WebSocket messages.
- It does not prove browser UI rendering.

## Command

Run from the repository root:

```bash
python scripts/smoke_app_adapter_proving.py
```

## Expected Output

```text
AGSignal app adapter proving smoke passed
agent_id: ...
notification_id: ...
status: SUCCESS
ack_status: PENDING
delivery_audits: 1
ack_audits: 1
decision_snapshot_attached: True
app_evidence_attached: True
```

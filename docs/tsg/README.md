# UNS Troubleshooting Guides (TSGs) & Operational Runbooks

This directory contains symptom-driven Troubleshooting Guides (TSGs) for on-call operators and support engineers managing the Unified Notification Service (`uns`).

## Rapid Incident Triage Matrix

| Observed Symptom / Alert | Primary Diagnostic Endpoint / CLI | Go To Runbook |
| :--- | :--- | :--- |
| `/readyz` reports `dlq_depth > 0`, or critical `GUARANTEED` notifications show `status: "FAILED"` with `dead_letter: true` | `GET /api/v1/runtime/dead-letters`<br>`GET /api/v1/runtime/notifications/{id}` | [TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay](TSG-01-DLQ-AND-REPLAY.md) |
| `LEASE_LOST` events appear in `uns_events`, or downstream recipients report duplicate emails/Slack messages during provider slowdowns | `GET /api/v1/runtime/notifications/{id}` | [TSG-02: Expired Worker Leases & Uncertain Provider Effects](TSG-02-LEASES-AND-PROVIDER-EFFECTS.md) |
| Notifications transition to `ack_status: "TIMED_OUT"`, human ACKs fail with `409 Conflict`, or downstream ACK callbacks are delayed/failing | `GET /api/v1/notifications/{id}`<br>`GET /api/v1/runtime/notifications/{id}` | [TSG-03: Acknowledgment Timeouts, Escalations, & Callback Failures](TSG-03-ACK-TIMEOUTS-AND-CALLBACKS.md) |
| `POST /api/v1/policies/reload` returns `409` or `422`, or producer `POST /api/v1/notifications` fails with `422` override rejection | `POST /api/v1/policies/reload`<br>`GET /ui/policies/effective` | [TSG-04: Policy Lifecycle, Shadow Promotion, & Override Rejections](TSG-04-POLICY-LIFECYCLE-AND-OVERRIDES.md) |
| `uns-mcp` fails at startup, `send_signal` / `ack_notification` raises `ValueError`, or agent WebSocket connections fail with `1008` | `uns-mcp --enable-writes`<br>`/ws/agents/{agent_id}` | [TSG-05: MCP Process Lifecycle & Agent WebSocket Recovery](TSG-05-MCP-AND-AGENT-RECOVERY.md) |
| `uns-maintain` fails with `FileExistsError`, reports `oversized_notification_ids`, or SQLite file size does not shrink after pruning | `uns-maintain` | [TSG-06: Database Maintenance, Retention, & Archive Recovery](TSG-06-MAINTENANCE-AND-ARCHIVAL.md) |

---

## Standard On-Call Prerequisites

Before executing any diagnostic or remediation commands in these guides, ensure your shell has the operator environment configured:

```sh
export UNS_BASE_URL="http://127.0.0.1:8000"
export UNS_API_KEY="<your-operator-api-key>"
export UNS_DATABASE_URL="sqlite:////var/lib/uns/uns.db"
```

## Related Documentation

- [Support Reference: State Machines, Schema, & Event Catalog](../support/STATE-MACHINE-AND-SCHEMA.md)
- [Deployment Guide](../DEPLOYMENT.md)
- [API Reference](../API.md)
- [Observability](../sections/observability.md)

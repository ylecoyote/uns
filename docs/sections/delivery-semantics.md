# Delivery and response semantics

## Delivery

| State | Meaning |
|---|---|
| PENDING | Accepted recoverable work; delivery not established |
| DELIVERED | A qualifying selected channel succeeded |
| FAILED | Retry budget exhausted or BEST_EFFORT failed |
| DEDUPLICATED | A scoped repeated event was suppressed |
| RATE_LIMITED | A channel attempt could not obtain its rate-limit token; attempt evidence records this condition |

GUARANTEED requires at least one persistent channel. Selected persistent channels are attempted in Slack, Email, PagerDuty order, stopping at the first success. WebSocket success cannot satisfy the guarantee. A WebSocket-only configuration must explicitly choose BEST_EFFORT; incompatible configurations are rejected rather than downgraded.

BEST_EFFORT attempts configured persistent channels concurrently. WebSocket is handled separately. Each adapter call is bounded by a 10-second runtime deadline. GUARANTEED uses at most three completed attempts by default, with 1-second then 2-second backoff. Adapter-local retries, if configured, remain inside that deadline. Rate-limit denial is an attempt failure, never successful delivery.

Exhausted GUARANTEED failures remain in the SQL runtime dead-letter view and audit/event history. Operator replay preserves notification identity and records the requesting actor. Provider errors and lease recovery are inspectable independently of the console.

## Acknowledgment

PENDING transitions to ACKED, DISMISSED, or TIMED_OUT. Repeating the same terminal response returns the original actor/time without adding another terminal event; attempting a different terminal response is a conflict. Responses arriving after the deadline are rejected, even if the timeout worker has not yet run.

The deadline starts on the first qualifying successful delivery, not acceptance. Delivery failure does not imply human silence. Timeout processing resumes after restart and atomically records a timeout/escalation event. A response is not proof of comprehension or business-action authorization.

## Duplicate and recovery limits

Idempotency records are retained with notification state until an operator retention migration removes them; there is no silent automatic expiry. Dedup windows come from the resolved policy and default to 300 seconds. Dedup claims survive runtime restart. Independent runtime processes still have process-local channel token buckets unless the existing shared limiter is explicitly configured.

Exactly-once external delivery is not promised. A crash after provider acceptance but before local result commit may repeat a provider call after lease recovery. The same notification identity and attempt evidence remain available for reconciliation.

Optional terminal-event callbacks are injected into Runtime. Their attempts, lease, and last error are persisted separately from the terminal response. A failed callback cannot undo acknowledgment. The worker retries up to three times with bounded calls; consumers deduplicate using the durable event ID. Exhausted callbacks remain visible in the event record.

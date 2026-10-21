# Delivery and response semantics

## Delivery states

| State | Meaning |
|---|---|
| PENDING | Accepted recoverable work, or a follower linked to a pending owner |
| DELIVERED | A qualifying selected provider/channel succeeded |
| FAILED | The cycle exhausted or BEST_EFFORT failed |
| DEDUPLICATED | A matching delivered owner satisfied the duplicate obligation |
| RATE_LIMITED | An attempt could not obtain a channel token; this is not delivery success |

GUARANTEED requires a persistent channel. Selected persistent channels run in Slack, Email, PagerDuty order, stopping at the first success. WebSocket success cannot satisfy that contract. WebSocket-only configuration must explicitly use BEST_EFFORT. Legacy SUCCESS audit outcomes describe an actual successful attempt, not mere acceptance.

BEST_EFFORT attempts persistent channels concurrently; WebSocket is separate. The runtime adapter deadline is 10 seconds and its default lease is 60 seconds. Provider-local retries remain within the adapter deadline. Default GUARANTEED cycles have three attempts with exponential backoff starting at one second.

## Deduplication and replay

Idempotency scope is principal, source and key, bound to request content. Same content retains identity; different content conflicts. Semantic deduplication is separate and also considers the effective delivery obligation.

A pending duplicate references a live owner/generation. It cannot become a terminal successful suppression while its owner has not delivered. Owner success atomically satisfies followers. Terminal owner failure elects one successor and re-links remaining followers; a new intake cannot be suppressed by a FAILED owner.

Manual replay preserves notification identity, cumulative attempts and event history. It increments delivery cycle and resets only that cycle's budget. Historical failed outcomes remain auditable. Exhausted failures stay in the durable dead-letter view until explicit resolution/replay.

Old ownerless dedup claims are never taken as evidence of delivery. Previously suppressed pre-upgrade rows remain historical because their lost association cannot be reliably reconstructed; operators may need to reissue those obligations.

## Leases and provider attempts

Claim transactions end before network I/O. Ownership and expiry are checked before each channel attempt and each built-in provider retry. Email executor work carries its guard context and checks before connection and sending. Custom adapters with internal retries must declare `guards_provider_attempts` and call `guard_provider_attempt` before each provider effect; otherwise only the outer adapter entry is guarded.

Fencing a database commit does not make provider I/O atomic. A crash after provider acceptance, an already-running effect, or a pause between the last guard and sending can still cause duplicate external effects. Attempt events preserve that uncertainty. Exactly-once external delivery is not promised.

## Response lifecycle

The response deadline starts at the first qualifying delivery, not acceptance. Delivery failure is not human silence. PENDING transitions atomically to ACKED, DISMISSED or TIMED_OUT with actor/time and audit. Repeated same-actor/same-state requests return the original result. A different actor, conflicting terminal state or late initial response conflicts without overwriting attribution.

Timeout expiry runs separately from dispatch and callback batches. Callback failures cannot rewrite terminal state. Callback attempts are persisted and bounded; recipients deduplicate by event ID. Callbacks must be cooperative asynchronous host code, not blocking synchronous work in the event loop.

## Retention and profile limits

No startup purge occurs. Idempotency remains effective while its record is retained. Explicit retention requires a cutoff and minimum idempotency horizon, protects unsettled work and linked obligations, and records archival/pruning decisions. See [deployment](../DEPLOYMENT.md).

Process-level token buckets are not a verified fleet-wide rate limiter. PostgreSQL operation, real-provider behavior and representative production load require separate acceptance. A provider success or actor response is not proof of human comprehension or business-action authorization.

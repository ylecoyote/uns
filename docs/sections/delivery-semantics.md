# Delivery and response semantics

## Delivery states

| State | Meaning |
|---|---|
| PENDING | Accepted recoverable work, or a follower linked to a pending owner |
| DELIVERED | A qualifying selected provider/channel succeeded |
| FAILED | The cycle exhausted or BEST_EFFORT failed |
| DEDUPLICATED | A matching delivered owner satisfied the duplicate obligation |
| RATE_LIMITED | An attempt could not obtain a channel token; this is not delivery success |

GUARANTEED requires a persistent channel and provides **bounded durable delivery**, not infinite retry or guaranteed human comprehension: each cycle performs up to three attempts with exponential backoff before recording a visible dead-letter (`FAILED`, `dead_letter=True`) for operator inspection or replay. Selected persistent channels run in Slack, Email, PagerDuty order, stopping at the first success. WebSocket success cannot satisfy that contract. WebSocket-only configuration must explicitly use BEST_EFFORT. Legacy SUCCESS audit outcomes describe an actual successful attempt, not mere acceptance.

### Delivery fallback vs. post-silence escalation

| Operational Question | Mechanism | Boundary |
|---|---|---|
| What if the first provider rejects or fails to accept the message? | **Delivery fallback** (`Slack → Email → PagerDuty`) | Runs within a dispatch attempt until the first selected persistent channel succeeds. |
| What if a provider accepts the message, but nobody acknowledges before `deadline`? | **Response timeout** (`TIMED_OUT`) + **durable host callback** | Once a persistent channel accepts the message, delivery fallback for that cycle is complete. Expiry transitions `ack_status` to `TIMED_OUT` and invokes the configured host callback. |
| Who gets paged next on human silence, and on what schedule? | **External incident escalation** (e.g. PagerDuty escalation policy) or **host callback handler** | Route urgent unacknowledged incidents directly to PagerDuty (or trigger a secondary notification from the timeout callback). |

BEST_EFFORT attempts persistent channels concurrently; WebSocket is separate. The runtime adapter deadline is 10 seconds and its default lease is 60 seconds. Provider-local retries share the adapter deadline. Blocking SMTP work uses remaining monotonic/socket budgets and cancellation checks before send admission; Python cannot terminate an already-running SMTP/DNS operation. Default GUARANTEED cycles have three attempts with exponential backoff starting at one second.

## Deduplication and replay

Idempotency scope is principal, source and key, bound to request content. Same content retains identity; different content conflicts. Semantic deduplication is separate and also considers the effective delivery obligation.

A pending duplicate references a live owner/generation. Pending ownership survives window expiry: expiry alone never admits a concurrent owner. It cannot become a terminal successful suppression while its owner has not delivered. Owner success atomically satisfies followers. Terminal owner failure elects one successor and re-links remaining followers; a new intake cannot be suppressed by a FAILED owner. Promotion preserves the existing suppression expiry rather than starting another window. Once an owner delivers after that expiry, a fresh arrival may become a new owner.

For overlapping owners retained from earlier versions, failure settlement consults the current claim in the same transaction. Its pending owner receives the old followers even after TTL expiry; its delivered owner satisfies those followers only inside the active window. Otherwise one successor is elected with a higher generation. The old owner cannot replace a live newer claim. Already-started legacy effects cannot be withdrawn.

Manual replay preserves notification identity, cumulative attempts and event history. It increments delivery cycle and resets only that cycle's budget. Historical failed outcomes remain auditable. Exhausted failures stay in the durable dead-letter view until explicit resolution/replay. Replay is recovery of an unsatisfied obligation, not a force-send operation. It conflicts if a successor is pending, delivered, or has unresolved lineage, or if another current owner is pending or delivered inside the suppression window. A successful replay atomically acquires ownership and starts a new cycle/window. Failed descendants transfer to that cycle, so replaying a former owner cannot later make those descendants replayable after satisfaction.

`dedup_successor_id` retains handoff evidence independently of the current claim/window. Status and acceptance responses expose `obligation_owner_id`, `effective_ack_status`, and `ack_inherited` so callers can inspect the canonical obligation's response state directly without parsing status messages. Dead-letter reads expose `replay_blocked_by` and `replay_block_reason`; they do not erase historical failure or automatically clear the dead-letter flag. An operator may explicitly resolve that failure. Deliberate new notification requests use new idempotency identities and remain subject to ordinary policy and dedup rules; no `force` bypass is provided.

Old ownerless dedup claims are never taken as evidence of delivery. Previously suppressed pre-upgrade rows remain historical because their lost association cannot be reliably reconstructed; operators may need to reissue those obligations.

## Leases and provider attempts

Claim transactions end before network I/O. Ownership and expiry are checked before each channel attempt and each built-in provider retry. Email executor work carries its guard context and checks before connection and sending. Custom adapters with internal retries must declare `guards_provider_attempts` and call `guard_provider_attempt` before each provider effect; otherwise only the outer adapter entry is guarded.

Fencing a database commit does not make provider I/O atomic. A crash after provider acceptance, an already-running effect, or a pause between the last guard and sending can still cause duplicate external effects. `CHANNEL_ATTEMPT_STARTED` records each provider send admission; lease-only checks do not create extra starts. `CHANNEL_ATTEMPT_RESULT` records each completed channel observation with its original lease/cycle, including observations before later lease loss. These append-only events do not authorize a stale worker to overwrite the notification outcome. One channel observation may summarize several provider retries.

An email timeout after send admission records `provider_outcome=UNKNOWN`; timeout before admission records `NOT_STARTED`. UNKNOWN is not evidence of provider rejection. Fallback or subsequent recovery may repeat an external effect; late SMTP completion does not rewrite the earlier observation. Socket deadlines cannot retract accepted bytes or forcibly stop DNS resolution. If persisting channel evidence fails, dispatch leaves its claim recoverable and does not mistake that storage error for a provider rejection or initiate another fallback in that invocation. Exactly-once external delivery is not promised.

## Response lifecycle

The response deadline starts at the first qualifying delivery, not acceptance. Delivery failure is not human silence. PENDING transitions atomically to ACKED, DISMISSED or TIMED_OUT with actor/time and audit. Repeated same-actor/same-state requests return the original result. A different actor, conflicting terminal state or late initial response conflicts without overwriting attribution.

Timeout expiry runs separately from dispatch and callback batches. Callback failures cannot rewrite terminal state. Callback attempts are persisted and bounded; recipients deduplicate by event ID. Callbacks must be cooperative asynchronous host code, not blocking synchronous work in the event loop. New callbacks are due at their event timestamp; retries use their retry timestamp. Batches order by due time, event time and ID, so fresh arrivals cannot systematically preempt overdue retries. Dispatch and expiry also use explicit due-time/ID ordering. This is scheduling fairness, not a throughput or latency guarantee. Runtime-created delivery and response audit timestamps use the same injected clock as runtime events.

## Retention and profile limits

No startup purge occurs. Idempotency remains effective while its record is retained. Explicit retention requires a cutoff and minimum idempotency horizon, protects unsettled work and linked obligations, and records archival/pruning decisions. See [deployment](../DEPLOYMENT.md).

Process-level token buckets are not a verified fleet-wide rate limiter. SQLite WAL and PostgreSQL 16 (`postgres:16-alpine`), sustained multi-worker concurrency/load tests, and hosted GitHub Actions CI are verified, whereas real external provider delivery, human comprehension, and multi-node production capacity remain separate operational boundaries. A provider success or actor response is not proof of human comprehension or business-action authorization.

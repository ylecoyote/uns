# UNS architecture

The canonical chain is producer -> policy resolution -> transactional acceptance/outbox -> leased dispatch -> adapter result -> durable acknowledgment state -> audit.

`uns.Runtime` stores the resolved notification and pending work in `uns_notifications`. The same transaction writes acceptance audit and an `uns_events` record. An accepted response therefore has recoverable work. `uns_dedup` applies scoped semantic suppression independently of request idempotency.

The dispatcher claims work with a conditional database update and lease token, performs bounded external calls through `notification.service.DeliveryService`, and commits the result only while it owns that token. Expired leases can be recovered. A crash after provider acceptance but before local commit can repeat an external effect. Attempt history labels recovery as potentially ambiguous.

Delivery and acknowledgment states are separate. The first successful delivery creates the response deadline. ACK, DISMISS, and timeout use conditional transitions so only one terminal state wins. State, response audit, and event commit together. A caller can poll durable events without making execution depend on a notification acknowledgment.

HTTP and the canonical Python client share the runtime. MCP factory tools use the same database configuration. The HTTP lifespan runs recovery and timeout processing once per second. A persistent MCP-only installation also runs an HTTP service or an explicit recovery worker against that database.

The console reads the existing SQL audit tables and augments detail views with runtime policy identity and acknowledgment state. Legacy unit/integration composition can inject in-memory services using `skip_persistence_config=True`; that fixture mode is not the durable deployment profile.

Notification policy lifecycle is distinct from action authorization. The latter's unfinished schema/operator code is retained for compatibility under `agsignal.governance`, outside the supported runtime API.

UNS is ATP-agnostic. Host integration is optional; see [Integration Modes](sections/integration-modes.md).

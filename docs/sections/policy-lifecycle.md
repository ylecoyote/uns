# Notification policy lifecycle

DRAFT is proposal state, PREVIEW is shadow-only, ACTIVE is eligible for runtime, and RETIRED is terminal history. The default PolicyRegistry rejects non-ACTIVE registration. Compatibility SQL loaders distinguish runtime and shadow roles.

## Durable authority

Canonical Runtime uses immutable database snapshots and a monotonic revision. `notification_policy_revision` records the current revision; `notification_policy_snapshots` retains serialized ACTIVE snapshots and hashes. `notification_policy_contents` preserves complete per-version content, including DRAFT/PREVIEW intent and priority fields, while `notification_policies` retains lifecycle/history compatibility. Row status remains authoritative.

A fresh process hydrates the persisted snapshot. Each intake checks and locks the revision inside its acceptance transaction. Activation and acceptance therefore have a defined commit order across processes without polling generic database changes or requiring pub/sub. Different runtime databases do not share mutable policy authority.

Reload validates the complete candidate, persists it transactionally and advances the revision. Failure leaves the prior snapshot active. Accepted work retains original settings. Effective-policy inspection and simulation use the same resolved mode overrides and configured intent as intake.

## Producer inputs and provenance

For ACTIVE policies, explicit producer values may agree with resolved policy but may not change its delivery mode, channel selection, acknowledgment requirement, timeout, priority or configured intent. This is an equality boundary, not a claim that every apparently stronger override is safe. There is no payload-granted administrator exception. Unconfigured notification types retain documented defaults; an explicit BEST_EFFORT preview remains usable when no ACTIVE policy forbids it.

Adapter-control metadata cannot bypass canonical authority. Recipient/channel and severity controls are rejected at producer intake/simulation. Trusted direct adapter integrations remain outside this producer boundary.

Each accepted notification records policy/config identity, evaluation identity, snapshot revision/hash, effective values/hash, principal and supplied override values. Defaults have a versioned identity. Policy hashes identify content rather than prove authenticity.

## Controlled policy changes

PolicyDelta tracks PROPOSED -> SHADOW -> APPROVED -> APPLIED, with REJECTED alternatives and attributed history. Use the persisted transition path; a data model alone is not an authorization boundary.

Shadow evidence binds to the baseline and exact candidate hashes, identifies its evaluator and declares sample/quality criteria. Required guard evidence must match the candidate. Configured bounds and step sizes are checked; blocking or missing guards prevent promotion. A changed candidate invalidates approval.

`apply_policy_delta` requires approval and matching baseline hash/version/current value. It creates a new DRAFT and leaves current active behavior unchanged. Activation is a separate operator action. Reusing an already RETIRED version is rejected; restoring historical behavior requires a new version identifier.

The system validates evidence binding and declared criteria, not an external evaluator's honesty or measurement methodology. It is not an autonomous optimizer or a business-action permission engine.

## Migration limits

Concurrent first-upgrade schema creation is idempotent. Current writes preserve complete policy serialization. Fields already discarded by older persistence versions cannot be reconstructed from missing data; operators must restore authoritative source content when necessary. SQLite process ordering is tested; live PostgreSQL acceptance remains separate.

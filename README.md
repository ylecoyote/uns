# UNS, Unified Notification Service

![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)

**Durable notifications with policy provenance and response history.**

When several autonomous applications or background jobs emit operational alerts, ordinary fire-and-forget webhooks leave operators guessing: *Which policy governed this alert? Did a provider accept it? Was it coalesced with an earlier incident? Did anyone actually respond before the deadline?*

UNS treats an important notification as a **recoverable obligation** backed by a transactional SQLite outbox (`uns.Runtime`). Policy resolution, acceptance, deduplication ownership, and audit provenance commit together at intake so accepted work retains the exact policy revision that governed it—even across process restarts, provider timeouts, or later policy updates.

| Lifecycle Event | What UNS Establishes |
| :--- | :--- |
| **Accepted (`PENDING`)** | The service has committed recoverable outbox work bound to an immutable policy revision hash. |
| **Delivered (`DELIVERED`)** | A qualifying persistent channel (`SLACK`, `EMAIL`, `PAGERDUTY`) returned a confirmed delivery result. |
| **Coalesced (`DEDUPLICATED`)** | The event was linked to an active canonical obligation (`obligation_owner_id`) and inherits its response tracking (`effective_ack_status`, `ack_inherited`). |
| **Responded (`ACKED` / `DISMISSED`)** | An authenticated principal recorded a terminal response before the deadline elapsed. |
| **Timed Out (`TIMED_OUT`)** | No response was recorded before the deadline; a durable terminal event is emitted for downstream escalation callbacks. |

## Core Capabilities & Boundaries

- **Policy Authority at Intake:** Producer payloads cannot weaken an `ACTIVE` notification policy's delivery mode, channels, acknowledgment requirement, or timeout. Proposed policy changes carry shadow evaluation evidence and explicit approval before activation.
- **Scoped Credential Authority:** Supports least-privilege API keys for independent callers (`UNS_PRODUCER_API_KEY`, `UNS_RESPONDER_API_KEY`, `UNS_OBSERVER_API_KEY`) alongside the full operator key (`UNS_API_KEY`).
- **Failure-Aware Deduplication:** Pending ownership survives window expiry, owner failure promotes a follower or hands off to a successor (`dedup_successor_id`), and status responses expose `obligation_owner_id` and `effective_ack_status` directly.
- **Delivery Fallback vs. Post-Silence Escalation:** `GUARANTEED` mode performs bounded durable retries across selected persistent channels (`Slack → Email → PagerDuty`), stopping at the first channel that accepts the message, or surfacing a visible dead-letter entry on exhaustion. If a channel accepts the message but no human responds before the deadline, UNS records `TIMED_OUT` and invokes the host callback—multi-step human on-call paging belongs to your incident responder (such as PagerDuty escalation policies) or host callback.
- **Explicit Scope Boundary:** UNS governs notification obligations and response evidence. It does not authorize or execute an agent's business actions; acknowledgment records a response, not comprehension or permission to act. The unfinished action-authorization models remain experimental.

## Local quickstart

From this repository, with Python 3.12:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python examples/uns_demo.py
.venv/bin/python examples/mip_producer_demo.py
```

The demos use a local recording adapter, accept and deliver signals, exercise dry-run simulation, deduplication coalescing, and operator acknowledgment, and verify audit history without sending external network traffic. Starting the persistent HTTP daemon (`uns`) requires an explicit `UNS_DATABASE_URL` (or `--in-memory` for ephemeral testing). See [deployment](docs/DEPLOYMENT.md) for the durable HTTP service, [operator console guide](docs/user-guides/OPERATOR-CONSOLE-GUIDE.md) for the 6-surface Responder & Operator Console (`/deliveries`, `/policy`, `/operations`, `/invariants`, `/audit`, `/docs`), and [API](docs/API.md) for the canonical Python and MCP interfaces.

Simulation has no side effects. Acceptance means recoverable pending work. Delivery requires a channel result. Human acknowledgment is a separate state.

## Documentation

- [Product boundary](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Delivery semantics](docs/sections/delivery-semantics.md)
- [Policy lifecycle](docs/sections/policy-lifecycle.md)
- [Deployment](docs/DEPLOYMENT.md) and [security](docs/SECURITY-MODEL.md)
- [Testing and acceptance](docs/TESTING.md)
- [Migration and provenance](docs/MIGRATION.md)

`examples/policies/mip-uns` and `config/notification_policies` contain sample policies, not mandatory runtime defaults. Existing `agsignal`, `notification`, and `agsignal_mcp` imports remain available. New integrations use `uns.Client` and `uns.Runtime` with the `full` extra. The legacy low-level `NotificationSDK` resolves policy and needs an explicit delivery handler; without one it returns PENDING and attempts no channels.

## Verification & Provenance

The canonical development branch is **main**, containing the consolidation and both remediation iterations. See the [consolidated baseline](docs/CONSOLIDATED_BASELINE.md) for merge provenance and fresh verification.

Adversarial remediation adds durable policy revision checks, explicit dedup ownership, replay cycles, per-provider lease guards, independent callback recovery, authenticated transport reads, and bounded archive/retention tooling. The [second remediation iteration](docs/REMEDIATION_ITERATION2.md) strengthens window/replay ownership, channel-result evidence, SMTP timeout semantics, callback fairness, read-only policy loading and direct MCP reads. See [verification](docs/TESTING.md) for checked behavior and remaining deployment limits.

The [deployment smoke report](docs/DEPLOYMENT_SMOKE.md) records the latest container and live HTTP/WebSocket/MCP/browser checks. It distinguishes the local recording-only rehearsal from a lasting deployment and real-provider acceptance. The selected [localhost recording service](docs/LOCAL_DEPLOYMENT.md) is deployed with persistent storage and a private API key. It is explicitly a recording profile, with no real Slack, email or PagerDuty messages.

Apache License 2.0 - see [LICENSE](LICENSE). Local validation is recorded in docs/TESTING.md; real-channel receipt is a separate opt-in smoke check.

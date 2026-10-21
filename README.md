# UNS, Unified Notification Service

The canonical development branch is **main**, containing the consolidation and both remediation iterations. See the [consolidated baseline](docs/CONSOLIDATED_BASELINE.md) for merge provenance and fresh verification.

![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)

UNS delivers policy-driven notifications and records delivery, acknowledgment, dismissal, and timeout evidence. Notification policies have version identity; proposed policy changes can carry shadow evidence and explicit approval before a new draft is activated.

Producer requests cannot weaken an ACTIVE notification policy. HTTP/MCP/WebSocket reads and writes use the configured trust boundary; the console asks for an operator credential at runtime.

UNS does not authorize or execute an agent's business actions. Acknowledgment records a response, not comprehension or permission to act. The unfinished action-authorization models remain experimental.

## Local quickstart

From this repository, with Python 3.12:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python examples/uns_demo.py
```

The demo uses a local recording adapter, accepts and delivers one signal, restarts the runtime, acknowledges it, and checks audit history. It sends nothing externally. See [deployment](docs/DEPLOYMENT.md) for the durable HTTP service and [API](docs/API.md) for the canonical Python and MCP interfaces.

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

Apache License 2.0 - see [LICENSE](LICENSE). Local validation is recorded in docs/TESTING.md; real-channel receipt is a separate opt-in smoke check.

Adversarial remediation adds durable policy revision checks, explicit dedup ownership, replay cycles, per-provider lease guards, independent callback recovery, authenticated transport reads, and bounded archive/retention tooling. The [second remediation iteration](docs/REMEDIATION_ITERATION2.md) strengthens window/replay ownership, channel-result evidence, SMTP timeout semantics, callback fairness, read-only policy loading and direct MCP reads. See [verification](docs/TESTING.md) for checked behavior and remaining deployment limits.

The [deployment smoke report](docs/DEPLOYMENT_SMOKE.md) records the latest container and live HTTP/WebSocket/MCP/browser checks. It distinguishes the local recording-only rehearsal from a lasting deployment and real-provider acceptance.

The selected [localhost recording service](docs/LOCAL_DEPLOYMENT.md) is deployed with persistent storage and a private API key. It is explicitly a recording profile, with no real Slack, email or PagerDuty messages.

# UNS security model

HTTP writes derive identity from the configured API key and principal. ACK/DISMISS payload identity is checked against that principal. The canonical Python client and embedded MCP configuration are trusted host boundaries, not mechanisms for authenticating arbitrary user-provided principals.

Runtime inspection contains event context and is authenticated. Existing console read endpoints and WebSocket surfaces retain their legacy access model; place the service behind an authenticated reverse proxy before sharing it. Do not expose a default local process publicly.

Database transactions protect local acceptance/state/audit consistency. Append-only event and audit behavior is enforced by application paths, not cryptographic proof or database administrator restrictions. Content hashes identify policy configuration; they are not signatures.

Policy YAML uses safe loading. The experimental action-policy operators are allowlisted and regular expressions are bounded, but that does not establish a shipped authorization engine. Policy activation is an operator action and the reload path must not be exposed to untrusted file-path input.

Avoid secrets and unnecessary personal data in notification metadata. Provider credentials belong in deployment configuration. Audit retention, backups, access control, encryption at rest, and restore procedures must be defined for the deployment.

See [delivery semantics](sections/delivery-semantics.md) for crash ambiguity and [deployment](DEPLOYMENT.md) for supported local validation. This repository makes no regulatory-compliance or human-comprehension guarantee.

The final local audit retains frontend dependency advisories, including development-tool critical advisories and two moderate production router advisories. See [verification](TESTING.md). Do not treat the local consolidation as a production-security signoff.

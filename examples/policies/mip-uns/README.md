# UNS MIP UNS Sample Policy Pack

This directory contains UNS sample policies derived from the Market Insights
Platform UNS implementation.

These policies are examples, not UNS Core defaults. They show how a host
application can model safety, governance, and operational signaling with
mode-aware routing, acknowledgments, escalation, and deduplication.

## Policies

| File | Notification type | Demonstrates |
|---|---|---|
| `safety_kill_switch.yaml` | `safety.kill_switch` | LIVE-mode guaranteed delivery, required acknowledgment, and MIP escalation metadata |
| `governance_approval_required.yaml` | `governance.approval_required` | Approval workflow routing and failure escalation |
| `execution_slippage.yaml` | `execution.slippage` | Best-effort operational signaling and a five-minute deduplication window |

## Usage

Load the sample pack with the standard UNS YAML loader. The loader still
lives under the historical `notification.*` runtime package for compatibility:

```python
from pathlib import Path

from notification.policies import PolicyRegistry
from notification.policy_loader import load_policies_from_directory

registry = PolicyRegistry()
load_policies_from_directory(Path("examples/policies/mip-uns"), registry=registry)
policy = registry.get("safety.kill_switch")
```

Applications should copy these files into their own policy directory and adapt
notification types, channels, acknowledgment requirements, and escalation rules
to their domain.

`examples/policies/mip-uns` is the canonical sample pack. The repository also
keeps `config/notification_policies` loadable for demos and compatibility, but
that directory is not an UNS Core default policy set.

## Boundary

The sample content keeps MIP's concrete notification names because that makes the
examples realistic. UNS Core does not require these notification types, does
not import MIP or ATP code, and does not own trading-specific evidence models.

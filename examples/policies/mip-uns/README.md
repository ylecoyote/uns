# MIP UNS Sample Policy Pack

This directory contains AGSignal sample policies derived from the Market Insights
Platform UNS implementation.

These policies are examples, not AGSignal Core defaults. They show how a host
application can model safety, governance, and operational signaling with
mode-aware routing, acknowledgments, escalation, and deduplication.

## Policies

| File | Notification type | Demonstrates |
|---|---|---|
| `safety_kill_switch.yaml` | `safety.kill_switch` | LIVE-mode guaranteed delivery, PagerDuty escalation, required acknowledgment |
| `governance_approval_required.yaml` | `governance.approval_required` | Approval workflow routing and failure escalation |
| `execution_slippage.yaml` | `execution.slippage` | Best-effort operational signaling and a five-minute deduplication window |

## Usage

Load the sample pack with the standard AGSignal YAML loader:

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

## Boundary

The sample content keeps MIP's concrete notification names because that makes the
examples realistic. AGSignal Core does not require these notification types, does
not import MIP or ATP code, and does not own trading-specific evidence models.


# MIP-250 Sample Policy Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing MIP-derived UNS notification policies as a clearly labeled AGSignal sample policy pack.

**Architecture:** Keep AGSignal runtime defaults unchanged and add a separate `examples/policies/mip-uns/` sample pack. Tests validate the sample pack through the existing YAML loader and policy routing methods, while docs explain sample-vs-default semantics.

**Tech Stack:** Python, pytest, YAML policy loader, Markdown docs.

---

## File Structure

- Create `examples/policies/mip-uns/safety_kill_switch.yaml`: sample copy of the current safety kill switch policy.
- Create `examples/policies/mip-uns/governance_approval_required.yaml`: sample copy of the current governance approval policy.
- Create `examples/policies/mip-uns/execution_slippage.yaml`: sample copy of the current execution slippage policy.
- Create `examples/policies/mip-uns/README.md`: sample policy pack documentation.
- Create `tests/examples/test_mip_uns_policy_samples.py`: loader and behavior tests for the sample pack.
- Modify `docs/README.md`: add the sample policy pack to navigation.
- Modify `docs/m5-publish-readiness-reference.md`: mark MIP-250 sample policy pack as the reference path.

### Task 1: Add Sample Pack Files

**Files:**
- Create: `examples/policies/mip-uns/safety_kill_switch.yaml`
- Create: `examples/policies/mip-uns/governance_approval_required.yaml`
- Create: `examples/policies/mip-uns/execution_slippage.yaml`
- Create: `examples/policies/mip-uns/README.md`

- [ ] **Step 1: Create the sample policy directory**

Run:

```bash
mkdir -p examples/policies/mip-uns
```

Expected: directory exists.

- [ ] **Step 2: Copy the existing policy YAMLs into the sample directory**

Run:

```bash
cp config/notification_policies/safety_kill_switch.yaml examples/policies/mip-uns/safety_kill_switch.yaml
cp config/notification_policies/governance_approval_required.yaml examples/policies/mip-uns/governance_approval_required.yaml
cp config/notification_policies/execution_slippage.yaml examples/policies/mip-uns/execution_slippage.yaml
```

Expected: three YAML files exist in `examples/policies/mip-uns/`.

- [ ] **Step 3: Add the sample pack README**

Create `examples/policies/mip-uns/README.md` with this content:

```markdown
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
```

- [ ] **Step 4: Verify sample files are present**

Run:

```bash
find examples/policies/mip-uns -maxdepth 1 -type f | sort
```

Expected output includes the README and three YAML files.

### Task 2: Add Tests For Sample Pack Behavior

**Files:**
- Create: `tests/examples/test_mip_uns_policy_samples.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/examples/test_mip_uns_policy_samples.py` with:

```python
from pathlib import Path

from notification.models import AutonomyMode, Channel, DeliveryMode
from notification.policies import PolicyRegistry
from notification.policy_loader import load_policies_from_directory


SAMPLE_DIR = Path("examples/policies/mip-uns")


def load_sample_registry() -> PolicyRegistry:
    registry = PolicyRegistry()
    loaded_count = load_policies_from_directory(SAMPLE_DIR, registry=registry)
    assert loaded_count == 3
    return registry


def test_mip_uns_sample_pack_loads_all_policies() -> None:
    registry = load_sample_registry()

    assert registry.get("safety.kill_switch") is not None
    assert registry.get("governance.approval_required") is not None
    assert registry.get("execution.slippage") is not None


def test_safety_kill_switch_demonstrates_live_guaranteed_ack_escalation() -> None:
    registry = load_sample_registry()
    policy = registry.get("safety.kill_switch")

    assert policy is not None
    assert policy.delivery_mode == DeliveryMode.GUARANTEED
    assert policy.get_delivery_mode_for_mode(AutonomyMode.PREVIEW) == DeliveryMode.BEST_EFFORT
    assert policy.get_delivery_mode_for_mode(AutonomyMode.LIVE) == DeliveryMode.GUARANTEED
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is True
    assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [Channel.SLACK, Channel.WEBSOCKET]


def test_execution_slippage_demonstrates_best_effort_dedup() -> None:
    registry = load_sample_registry()
    policy = registry.get("execution.slippage")

    assert policy is not None
    assert policy.delivery_mode == DeliveryMode.BEST_EFFORT
    assert policy.dedup_window_seconds == 300
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is False
    assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [Channel.SLACK]
```

- [ ] **Step 2: Run tests to verify they pass once files exist**

Run:

```bash
pytest tests/examples/test_mip_uns_policy_samples.py -q
```

Expected: `3 passed`.

### Task 3: Link Docs To Sample Pack

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/m5-publish-readiness-reference.md`

- [ ] **Step 1: Add sample pack link to docs index**

Add this section to `docs/README.md` after Testing Guides:

```markdown
### Examples

| Example | Description |
|---------|-------------|
| [MIP UNS Sample Policy Pack](../examples/policies/mip-uns/README.md) | Realistic MIP-derived sample policies for safety, governance, and operational signaling |
```

- [ ] **Step 2: Update M5 reference**

In `docs/m5-publish-readiness-reference.md`, update the MIP-250 row to mention:

```markdown
Creates `examples/policies/mip-uns/` as the canonical sample policy pack path.
```

- [ ] **Step 3: Run docs and sample tests**

Run:

```bash
pytest tests/examples/test_mip_uns_policy_samples.py tests/docs/test_doc_cross_references.py -q
```

Expected: all tests pass.

### Task 4: Final Verification And Commit

**Files:**
- All files changed in Tasks 1-3.

- [ ] **Step 1: Run focused verification**

Run:

```bash
pytest tests/examples/test_mip_uns_policy_samples.py tests/notification/test_policy_loader.py tests/docs/test_doc_cross_references.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint and diff checks**

Run:

```bash
ruff check tests/examples/test_mip_uns_policy_samples.py
git diff --check
```

Expected: both commands pass.

- [ ] **Step 3: Check worktree status**

Run:

```bash
git status --short --branch
```

Expected: only intended sample pack, docs, spec, plan, and test files are changed.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-06-mip-250-sample-policy-pack-design.md docs/superpowers/plans/2026-05-06-mip-250-sample-policy-pack.md examples/policies/mip-uns tests/examples/test_mip_uns_policy_samples.py docs/README.md docs/m5-publish-readiness-reference.md
git commit -m "Publish MIP UNS sample policy pack" -m "MIP-250 needs the MIP-derived policies to be explicit sample content rather than ambiguous runtime defaults. This adds a documented sample pack, tests that load it through the AGSignal policy loader, and docs links from the M5 reference." -m "Constraint: the runtime default config directory remains unchanged in this issue." -m "Rejected: move config/notification_policies now | that would change current standalone runtime behavior and belongs in a separate configuration-boundary change." -m "Confidence: high" -m "Scope-risk: low" -m "Tested: pytest tests/examples/test_mip_uns_policy_samples.py tests/notification/test_policy_loader.py tests/docs/test_doc_cross_references.py -q" -m "Tested: ruff check tests/examples/test_mip_uns_policy_samples.py" -m "Tested: git diff --check" -m "Not-tested: full repository test suite" -m "Related: MIP-250" -m "Co-authored-by: OmX <omx@oh-my-codex.dev>"
```

Expected: commit succeeds.


# Policy Engine Migration: MIP → AGSignal Core

**Date:** 2026-04-22
**Status:** Planning
**Source:** `~/trading-assistant/market-insights-platform/src/policy/`
**Target:** `src/policy/` (this repo)

---

> Historical note: this document was written during the UNS extraction phase.
> In current product terminology, UNS maps to AGSignal Core. Remaining UNS
> references below are provenance references to the source PRD and migration
> language, not the public product name.

---

## Overview

The policy engine was built as part of the Market Insights Platform (MIP) and is
fully operational there. This document captures what exists, what's worth porting,
what needs to change, and the recommended order of work.

---

## What Exists in MIP

### File inventory (~4,800 LOC)

| File | LOC | Purpose |
|---|---|---|
| `schemas.py` | 892 | Pydantic models, enums, config types, hash utilities |
| `loader.py` | 796 | Bridges PolicyConfig system to PolicyEvaluator; fallback to defaults |
| `repository.py` | 770 | CRUD, lifecycle transitions, audit logging (psycopg2) |
| `learning_schemas.py` | 678 | Phase 17.3 policy learning layer schemas |
| `async_repository.py` | 624 | Async variant of repository (migration in progress in MIP) |
| `shadow_repository.py` | 446 | Shadow evaluation storage |
| `delta_repository.py` | 365 | Policy delta proposal persistence |
| `async_loader.py` | 128 | Async loader variant |
| `__init__.py` | 99 | Public exports |

---

## Design Principles (Non-Negotiable — carry these forward)

From `schemas.py` — these are enforced in the implementation, not just documented:

1. Configs are immutable once activated
2. Every config is versioned
3. No config affects live trading without explicit rollout
4. Every evaluation records exact config hash used
5. UI edits != enforcement

From `learning_schemas.py`:

6. Deltas are immutable once APPLIED or REJECTED (terminal states)
7. Every delta tracks its full state transition history
8. Shadow evaluation must pass before approval
9. Guard checks are explicit and auditable
10. No silent policy changes — every mutation is observable

---

## What's Strong (Keep As-Is Architecture)

### Policy lifecycle state machine

```
DRAFT → PREVIEW → ACTIVE → RETIRED
```

Clean one-way transitions. DRAFT is editable, PREVIEW is shadow-only, ACTIVE is
enforced, RETIRED is archived. This maps directly to the historical UNS PRD's policy lifecycle
requirements.

### Policy learning layer (the crown jewel)

`learning_schemas.py` implements a full automated parameter tuning system with
human-in-the-loop approval. Key pieces:

**Delta state machine:**
```
PROPOSED → SHADOW → APPROVED → APPLIED
                 ↘ REJECTED (terminal)
```

**Observation types that trigger learning:**
- `NEAR_MISS_REGRET` — decision was correct but barely; threshold may be too loose
- `THRESHOLD_BOUNDARY` — decision landed exactly on a configured threshold
- `REGIME_MISMATCH` — current market regime doesn't match policy assumptions
- `SKIP_PATTERN` — repeated skips suggest a systematic policy gap

**Guard stages** (explicit checks at each transition):
- `PROPOSE` — bounds check, step size limit
- `PROMOTE_SHADOW` — rate limit, learning-paused check
- `APPROVE` — shadow must have passed
- `APPLY` — final immutability gate

**Rejection reasons are explicit and auditable:**
`DELTA_OUT_OF_BOUNDS`, `DELTA_STEP_TOO_LARGE`, `LEARNING_PAUSED`,
`RATE_LIMIT_EXCEEDED`, `INVALID_TRANSITION`, `SHADOW_NOT_PASSED`, `NOT_APPROVED`

This is the hardest part to design well and it's already done correctly. Port this
first, treat the rest as scaffolding.

### Config hashing

Every policy config is serialized to canonical JSON and SHA-256 hashed. Every
evaluation logs which hash was used. This means you can always reconstruct exactly
which config produced a given decision — critical for audit trails.

### Shadow + delta as separate repositories

`shadow_repository.py` and `delta_repository.py` are clean separations — shadow
testing lives in its own layer, delta proposals have their own lifecycle. Don't
collapse these into the main repository.

---

## What Needs to Change for AGSignal Core

### 1. Decouple from trading-specific policy types

**Problem:** `PolicyName` enum is hardcoded to MIP domains:
```python
class PolicyName(str, Enum):
    PREDICTION_POLICY = "PREDICTION_POLICY"
    SCORING_PARAMS = "SCORING_PARAMS"
    RISK_POLICY = "RISK_POLICY"
    EXECUTION_POLICY = "EXECUTION_POLICY"
```

**Fix:** Replace with a registry/plugin pattern. Policy types should be registered
at startup, not baked into the enum. The historical UNS PRD's notification-centric policy
types (routing overrides, delivery guarantees, rate limits per intent) are different
from trading policy types.

### 2. Replace database layer

**Problem:** `repository.py` uses raw psycopg2 with a MIP-specific
`DatabaseConnectionManager` singleton. There's even a comment acknowledging the
async migration debt:

```python
# NOTE: Uses raw psycopg2 connections via DatabaseConnectionManager - pending async migration
# Migration requires converting %s params to :named params and RealDictCursor to mappings()
```

**Fix:** AGSignal Core already uses async SQLAlchemy. Port repository.py to use the existing
`src/db/` stack. `async_repository.py` in MIP is already partway there — use it
as the starting point, not `repository.py`.

### 3. Strip trading-specific payload schemas

**Problem:** The concrete policy config schemas are MIP-specific:
- `PredictionSleeveAllocParamsV1` (insider_wt, flow_wt, whale_wt)
- `WAIComponentWeightsV1` (Whale Activity Index component weights)
- `RiskPolicyParamsV1` (position sizing, volatility limits)
- `ExecutionPolicyParamsV1` (gating thresholds)

**Fix:** Replace with AGSignal Core notification policy schemas. The `PolicyConfigEnvelope`
wrapper pattern (generic envelope + typed payload) is correct — just swap the
payload types. New policy types needed:

- `NotificationRoutingPolicyV1` — per-intent channel overrides
- `DeliveryGuaranteePolicyV1` — GUARANTEED vs BEST_EFFORT rules
- `RateLimitPolicyV1` — per-channel/per-intent rate limits
- `AckTimeoutPolicyV1` — acknowledgment timeout overrides

### 4. YAML loader generalization

**Problem:** `loader.py` has hardcoded fallback defaults for MIP-specific params.
The `LoadedPolicyConfig` dataclass exposes trading-specific properties directly
(`warn_acc`, `disable_acc`, `throttle_acc`, etc.).

**Fix:** Make the loader generic — `LoadedPolicyConfig[T]` where T is the typed
params model. Fallback defaults should be registered alongside policy types, not
hardcoded in the loader.

---

## Recommended Migration Order

### Current MIP-254 implementation notes

MIP-254 is being implemented in narrow parity slices rather than one large port.
The first AGSignal-native slice preserves the MIP enforcement boundary:

- ACTIVE policies are the only policies eligible for runtime enforcement.
- PREVIEW policies are loaded through an explicit shadow/simulation path.
- DRAFT UI edits and RETIRED policies do not silently affect enforcement.
- The existing mixed `load_registry()` behavior remains for backward
  compatibility while new callers can choose `load_runtime_registry()` or
  `load_shadow_registry()`.

See [MIP-254A Policy Lifecycle Runtime Boundary Design](superpowers/specs/2026-05-06-mip-254a-policy-lifecycle-runtime-boundary-design.md).

The second slice ports the MIP delta state machine into AGSignal-neutral
learning primitives:

- `PolicyDelta` models proposed field-level policy changes without trading
  policy names or ATP table coupling.
- `DeltaState` preserves `PROPOSED -> SHADOW -> APPROVED -> APPLIED`, with
  `REJECTED` and `APPLIED` as terminal states.
- `transition_to()` validates moves, returns immutable copies, and appends
  auditable transition history.

See [MIP-254B Policy Delta Core Design](superpowers/specs/2026-05-06-mip-254b-policy-delta-core-design.md).

The third slice ports the reusable shadow and guard primitives:

- `ShadowEvaluationResult` records original and candidate outcomes for a host
  decision.
- `ShadowEvaluationAggregate` captures sample size, win rate, threshold flags,
  and whether approval preconditions are met.
- `GuardResult` and `FieldBound` make guard checks explicit and auditable
  without importing trading snapshots or ticker-specific metrics.

See [MIP-254C Shadow And Guard Core Design](superpowers/specs/2026-05-06-mip-254c-shadow-guard-core-design.md).

The fourth slice ports the donor repository behavior into AGSignal's sync
SQLAlchemy style:

- `SQLAlchemyPolicyLearningStore` creates, fetches, lists, and transitions
  policy deltas.
- Transition history is persisted with each delta and invalid transitions fail
  without mutating the row.
- Shadow results and per-delta aggregates are persisted in standalone tables.
- Approval is blocked until the shadow aggregate passes its sample and threshold
  gates.

See [MIP-254D Policy Learning Store Design](superpowers/specs/2026-05-06-mip-254d-policy-learning-store-design.md).

### Phase 1 — Port the learning layer first (highest value, most unique)

1. Copy `learning_schemas.py` verbatim — it has no MIP-specific types
2. Adapt `shadow_repository.py` to async SQLAlchemy
3. Adapt `delta_repository.py` to async SQLAlchemy
4. Write tests against the delta state machine transitions

### Phase 2 — Port the core policy engine with generalized types

1. Create generic `PolicyConfigEnvelope` and `PolicyName` registry
2. Define AGSignal Core-specific policy payload schemas (routing, delivery, rate limits, ack)
3. Adapt `async_repository.py` to AGSignal Core db stack (preferred over `repository.py`)
4. Adapt `async_loader.py` with generic typed loader

### Phase 3 — Wire into AGSignal Core service layer

1. Hook policy loading into `NotificationService` / `DeliveryEngine`
2. Add hot-reload support (already planned in historical UNS PRD Phase 2)
3. Expose policy CRUD via MCP server routes
4. Add admin UI for policy lifecycle management

---

## Files to Copy vs Rewrite

| File | Action | Notes |
|---|---|---|
| `learning_schemas.py` | **Copy verbatim** | No MIP-specific types, pure data models |
| `async_repository.py` | **Adapt** | Good starting point, needs db layer swap |
| `shadow_repository.py` | **Adapt** | Swap db layer, otherwise solid |
| `delta_repository.py` | **Adapt** | Swap db layer, otherwise solid |
| `schemas.py` | **Rewrite** | Keep envelope/hash/lifecycle patterns, replace payload types |
| `loader.py` | **Rewrite** | Generalize the typed loader pattern |
| `repository.py` | **Skip** | Use async_repository.py instead |
| `async_loader.py` | **Adapt** | Minor changes after loader rewrite |

---

## Notes

- The MIP snapshot is at `~/trading-assistant/backups/mip-snapshot-20260208.tar.gz`
  if the live repo gets cleaned up
- `learning_schemas.py` is labeled Phase 17.3 in MIP — it was built late in the
  project lifecycle and is the most mature piece
- The `web/components/policy-learning/` directory in MIP has the UI for the
  learning approval workflow — worth reviewing when building the AGSignal Core admin UI
